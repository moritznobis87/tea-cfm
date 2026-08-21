"""
Der Speicherdispatch als Dienst der Oberflaeche.

Die Rechnung selbst steht in engine/storage/. Hier steht, WANN sie laeuft -
und das ist die eigentliche Entscheidung dieses Moduls.

Warum kein automatischer Lauf
-----------------------------
Ein Mehrjahresdispatch braucht rund zwanzig Sekunden: 31 Jahre mal 8.760
Stunden, je Jahr zwei lineare Programme (mit und ohne Speicher). Die
uebrige Bewertung liegt bei Millisekunden und laeuft bei JEDEM
Streamlit-Durchlauf - also bei jedem Tastendruck in der Parameterspalte.
Beides im selben Takt zu rechnen, machte die Maske unbenutzbar.

Der Dispatch laeuft deshalb nur auf ausdruecklichen Knopfdruck. Das
schafft aber ein neues Problem, und dieses Modul existiert vor allem, um
es zu loesen: Sobald der Nutzer danach IRGENDETWAS am Projekt aendert,
gehoert das gerechnete Ergebnis zu einem anderen Projekt als dem, das
auf dem Bildschirm steht.

Der Fingerabdruck
-----------------
Jeder Lauf traegt den Fingerabdruck seiner Eingaben. Vor jeder Anzeige
wird er gegen den Fingerabdruck des aktuellen Entwurfs gehalten. Stimmen
sie nicht ueberein, gilt der Lauf als VERALTET: Seine Zahlen fliessen
dann weder in die Kennzahlen noch in den Cashflow, und die Oberflaeche
sagt, dass neu zu rechnen ist.

Der Fingerabdruck ist bewusst GROB - er umfasst das ganze Projekt, nicht
nur die Felder, an denen der Dispatch haengt. Eine gepflegte Feldliste
waere praeziser und in der falschen Richtung gefaehrlich: Wer ein Feld
vergisst, bekommt keinen Fehler, sondern eine Zahl, die zu einem anderen
Projekt gehoert und trotzdem als aktuell ausgewiesen wird. Der grobe
Fingerabdruck kann nur den umgekehrten Fehler machen - er erklaert einen
Lauf fuer veraltet, der noch gueltig waere. Das kostet einen Knopfdruck.

Warum ein eigener Speicher statt st.cache_data
----------------------------------------------
Die Laeufe liegen als gewoehnliches dict im Session-State, je Projekt
einige wenige, mit dem Fingerabdruck als Schluessel. Wer einen Wert
aendert und wieder zuruecknimmt, bekommt sein Ergebnis damit ohne neuen
Lauf zurueck.

`st.cache_data` waere der naheliegende Weg und hat hier zwei Haken.
Erstens raeumt Streamlit Caches auf, wann es will; ein Fehltreffer ist
von einem Treffer nicht zu unterscheiden und wuerde stillschweigend eine
halbe Minute rechnen - genau das, was hier nie passieren darf. Zweitens
zeichnet Streamlit die Elemente auf, die eine gecachte Funktion erzeugt,
und spielt sie beim Treffer erneut ab. Der Fortschrittsbalken dieses
Laufs entsteht ausserhalb, und die Wiedergabe scheitert daran mit einem
Fehler (CacheReplayClosureError). Ein einfaches dict hat keine dieser
Eigenschaften.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

import numpy as np
import pandas as pd
import streamlit as st

from app import services
from engine import GlobalAssumptions, PVProject
from engine.energy import calculate_energy_production
from engine.io_lastgang import LastgangFehler, projektreihe, stundenprofil
from engine.io_preise import PREIS_VERZEICHNIS, preisreihe, reihe_fuer_szenario
from engine.pipeline import resolve_assumptions
from engine.revenue import calculate_revenue
from engine.storage import (
    BAHN_SPALTEN,
    STUETZJAHRE_STANDARD,
    BatteryConfig,
    Rasterergebnis,
    SolverFehler,
    SpeicherBeitrag,
    dispatch_jahr,
    dispatch_mehrjahr,
    jahreseingabe,
    raster,
    rasterlauf,
)
from engine.storage.valuation import _exportlimit_mw
from engine.timeline import build_timeline

#: Session-State: Projekt-ID -> {Fingerabdruck: Lauf}.
_LAEUFE = "speicher_laeufe"
#: Session-State: Projekt-ID -> zuletzt gerechneter Fingerabdruck.
_ZULETZT = "speicher_zuletzt"
#: Wie viele Laeufe je Projekt aufgehoben werden. Vier reichen fuer das
#: uebliche Hin und Her zwischen zwei, drei Auslegungen; ein Beitrag ueber
#: dreissig Jahre sind ein paar hundert Zahlen.
_HOECHSTENS = 4


@dataclass(frozen=True)
class Lauf:
    """Ein gerechneter Dispatch samt seiner Herkunft."""

    fingerabdruck: str
    beitrag: SpeicherBeitrag
    #: Dateiname der verwendeten Stundenpreisreihe - gehoert in die
    #: Anzeige: Welche Preise gerechnet wurden, ist die erste Rueckfrage
    #: zu jedem Speicherergebnis.
    preisreihe_datei: str
    gerechnet_am: datetime

    @property
    def jahreswerte(self) -> pd.DataFrame:
        """Die Jahresergebnisse als Tabelle - fuer Anzeige und Export."""
        return pd.DataFrame(
            [
                {
                    "jahr": w.jahr,
                    "kalenderjahr": w.kalenderjahr,
                    "mehrerloes_eur": w.mehrerloes_eur,
                    "netzbezugskosten_eur": w.netzbezugskosten_eur,
                    "degradationskosten_eur": w.degradationskosten_eur,
                    "deckungsbeitrag_eur": w.deckungsbeitrag_eur,
                    "mehrmenge_kwh": w.mehrmenge_kwh,
                    "rueckgewonnene_kappung_kwh": w.rueckgewonnene_kappung_kwh,
                    "ladung_mwh": w.speicher_ladung_mwh,
                    "entladung_mwh": w.speicher_entladung_mwh,
                    "vollzyklen": w.vollzyklen,
                }
                for w in self.beitrag.jahreswerte
            ]
        )


# ---------------------------------------------------------------------------
# Voraussetzungen
# ---------------------------------------------------------------------------


def hat_speicher(projekt: PVProject) -> bool:
    """Ist an diesem Projekt ein wirksamer Speicher eingerichtet?

    `wirksam` und nicht nur `is not None`: Ein abgeschalteter Speicher
    oder einer mit null Leistung rechnet nichts und soll auch nichts
    anzeigen (siehe BatteryConfig.wirksam).
    """
    return projekt.battery is not None and projekt.battery.wirksam


def preisreihe_datei(projekt: PVProject, ga: GlobalAssumptions) -> str | None:
    """Die Stundenpreisreihe des Projektszenarios - None, wenn keine da ist.

    Aufgeloest wird ueber den TATSAECHLICH gerechneten Szenarionamen und
    nicht ueber das Feld im Projekt: Das Projekt fuehrt den Namen ohne
    Bauform, die Bauform waehlt daraus die Kurve (siehe
    engine/io_aurora.szenario_fuer). Fuer die Preisreihe fallen beide
    wieder zusammen - der Day-Ahead-Preis haengt nicht an der
    Aufstaenderung -, aber der Weg ueber die aufgeloesten Annahmen
    stellt sicher, dass hier dasselbe Szenario steht wie im Cashflow.
    """
    assumptions = resolve_assumptions(projekt, ga)
    return reihe_fuer_szenario(assumptions.marktpreisszenario_name)


def stundenform(projekt: PVProject) -> tuple[float, ...] | None:
    """Die Erzeugungsform des Projekts ueber ein Jahr, Summe 1.

    Vorrang hat die hinterlegte Projektreihe (RatedPower-Export); ohne
    sie gilt die Reihe der Bauform. Das ist dieselbe Rangfolge wie bei
    der Kappungsanalyse - ein Speicher, der auf einer anderen
    Erzeugungsform optimiert als die Abregelung gerechnet wird, gaebe
    zwei Antworten auf dieselbe Frage.
    """
    eigene = projektreihe(projekt.lastgang_datei)
    if eigene:
        return eigene
    try:
        return stundenprofil(projekt.bauform)
    except LastgangFehler:
        return None


def fehlgrund(projekt: PVProject, ga: GlobalAssumptions) -> str | None:
    """Warum sich fuer dieses Projekt kein Dispatch rechnen laesst.

    Gibt einen Textschluessel zurueck oder None, wenn alles vorliegt.
    Die Pruefung steht VOR dem Knopf: Ein Knopf, der nur eine
    Fehlermeldung erzeugen kann, sollte gar nicht erst anklickbar sein.
    """
    if not hat_speicher(projekt):
        return "oberflaeche.speicher_fehlt_auslegung"
    if preisreihe_datei(projekt, ga) is None:
        return "oberflaeche.speicher_fehlt_preisreihe"
    if stundenform(projekt) is None:
        return "oberflaeche.speicher_fehlt_erzeugungsform"
    return None


# ---------------------------------------------------------------------------
# Fingerabdruck
# ---------------------------------------------------------------------------


def fingerabdruck(
    projekt: PVProject, ga: GlobalAssumptions, *zusatz: str
) -> str:
    """Kennung der Eingaben eines Dispatchlaufs.

    Enthaelt das ganze Projekt, den Zeitstempel der globalen Annahmen und
    Name UND Zeitstempel der Preisreihe. Die Preisdatei gehoert dazu, weil
    sie ausserhalb beider Dateien liegt: Ein neuer Aurora-Import
    veraendert das Ergebnis, ohne dass Projekt oder Annahmen sich
    ruehren.

    `zusatz` sind weitere Bestandteile der Eingabe, die nicht im Projekt
    stehen - beim Rasterlauf etwa die Definition des Rasters selbst.

    Warum grob: siehe Modulkopf. Lieber ein Lauf zu viel als eine Zahl,
    die zu einem anderen Projekt gehoert.
    """
    datei = preisreihe_datei(projekt, ga)
    pfad = PREIS_VERZEICHNIS / datei if datei else None
    teile = [
        projekt.model_dump_json(),
        str(services.GLOBAL_ASSUMPTIONS_PATH.stat().st_mtime),
        datei or "",
        str(pfad.stat().st_mtime) if pfad and pfad.exists() else "",
        *zusatz,
    ]
    return hashlib.sha256("␟".join(teile).encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Rechnen
# ---------------------------------------------------------------------------


def _eingaben(projekt: PVProject, ga: GlobalAssumptions):
    """Alles, was Dispatch und Diagramm brauchen - aus EINER Quelle.

    Timeline, Erzeugung und Erloese entstehen hier genauso wie in
    engine/pipeline.py. Sie ein zweites Mal zu rechnen kostet
    Millisekunden und erspart, den halben Bewertungsweg als Rueckgabewert
    durch die Oberflaeche zu reichen.
    """
    assumptions = resolve_assumptions(projekt, ga)
    timeline = build_timeline(
        inbetriebnahme_datum=date(
            assumptions.inbetriebnahme_jahr, assumptions.inbetriebnahme_monat, 1
        ),
        laufzeit_jahre=assumptions.betriebsdauer_jahre,
    )
    energy = calculate_energy_production(timeline, assumptions)
    revenue = calculate_revenue(timeline, energy, assumptions)
    return assumptions, energy, revenue


def _rechnen(
    kennung: str,
    projekt: PVProject,
    ga: GlobalAssumptions,
    fortschritt=None,
) -> Lauf:
    """Der eigentliche Lauf. Rechnet immer - das Aufheben macht `berechnen`."""
    assumptions, energy, revenue = _eingaben(projekt, ga)
    datei = preisreihe_datei(projekt, ga)
    reihen = preisreihe(datei) or {}
    form = stundenform(projekt)

    beitrag = dispatch_mehrjahr(
        assumptions, projekt.battery,
        energy=energy, revenue=revenue,
        preise_je_jahr=reihen, form=form,
        foerderdauer_anteil=revenue["foerderanteil"].to_numpy(),
        fortschritt=fortschritt,
    )
    return Lauf(
        fingerabdruck=kennung,
        beitrag=beitrag,
        preisreihe_datei=datei or "",
        gerechnet_am=datetime.now(),
    )


def _abgelegte(projekt_id: str) -> dict[str, Lauf]:
    return st.session_state.setdefault(_LAEUFE, {}).setdefault(projekt_id, {})


def berechnen(
    projekt: PVProject, ga: GlobalAssumptions, fortschritt=None
) -> Lauf:
    """Rechnet den Dispatch und legt ihn ab.

    Der einzige Weg, auf dem ein Lauf entsteht - gerufen vom Knopf.
    Liegt fuer diese Eingaben schon einer vor, kommt er ohne neuen Lauf
    zurueck; das ist der Fall, wenn jemand einen Wert aendert und wieder
    zuruecknimmt.
    """
    kennung = fingerabdruck(projekt, ga)
    abgelegt = _abgelegte(projekt.id)
    ergebnis = abgelegt.get(kennung) or _rechnen(kennung, projekt, ga, fortschritt)

    # Neu einsortieren, damit die Reihenfolge die Benutzung widerspiegelt:
    # Beim Ausduennen faellt der aelteste Eintrag heraus, nicht der
    # gerade wieder gebrauchte.
    abgelegt.pop(kennung, None)
    abgelegt[kennung] = ergebnis
    while len(abgelegt) > _HOECHSTENS:
        abgelegt.pop(next(iter(abgelegt)))
    st.session_state.setdefault(_ZULETZT, {})[projekt.id] = kennung
    return ergebnis


def letzter_lauf(projekt: PVProject) -> Lauf | None:
    """Der zuletzt gerechnete Lauf - AUCH wenn er veraltet ist.

    Getrennt von `lauf()`, und die Trennung ist der Punkt: `lauf()`
    beantwortet "darf das in die Rechnung?", diese Funktion "was war
    zuletzt zu sehen?". Wer sie benutzt, muss mit `veraltet()`
    dazusagen, woran der Nutzer gerade schaut - ein veralteter Lauf
    ohne diesen Hinweis waere eine falsche Auskunft.
    """
    kennung = st.session_state.get(_ZULETZT, {}).get(projekt.id)
    return _abgelegte(projekt.id).get(kennung) if kennung else None


def lauf(projekt: PVProject, ga: GlobalAssumptions) -> Lauf | None:
    """Der GUELTIGE Lauf dieses Projekts - None, wenn keiner gueltig ist.

    Gueltig heisst: Fuer GENAU diese Eingaben liegt ein Ergebnis vor.
    Das schliesst einen frueheren Lauf ein, zu dem der Nutzer
    zurueckgekehrt ist - er ist so gueltig wie der letzte.
    """
    return _abgelegte(projekt.id).get(fingerabdruck(projekt, ga))


def veraltet(projekt: PVProject, ga: GlobalAssumptions) -> bool:
    """Wurde gerechnet, passt aber nichts davon zum aktuellen Entwurf?"""
    return letzter_lauf(projekt) is not None and lauf(projekt, ga) is None


def vergessen(projekt_id: str) -> None:
    """Loescht die gemerkten Laeufe - etwa beim Verwerfen des Entwurfs."""
    st.session_state.get(_LAEUFE, {}).pop(projekt_id, None)
    st.session_state.get(_ZULETZT, {}).pop(projekt_id, None)


def beitrag(projekt: PVProject, ga: GlobalAssumptions) -> SpeicherBeitrag | None:
    """Der Beitrag fuer den Cashflow - nur aus einem gueltigen Lauf.

    Diese Funktion ist die Naht zur Bewertung. Sie gibt bewusst None
    zurueck, solange nichts Gueltiges vorliegt: Die Kennzahlen oben auf
    der Seite zeigen dann die reine PV-Bewertung, und die Seite sagt
    dazu, dass der Speicher nicht enthalten ist. Eine stillschweigend
    beigemischte alte Zahl waere die schlechtere Antwort - man saehe ihr
    nicht an, dass sie nicht mehr passt.
    """
    gueltig = lauf(projekt, ga)
    return gueltig.beitrag if gueltig else None


# ---------------------------------------------------------------------------
# Stundenbahn fuer die Anzeige
# ---------------------------------------------------------------------------


def bahn(
    projekt: PVProject, ga: GlobalAssumptions, betriebsjahr: int = 1
) -> pd.DataFrame | None:
    """Die Stundenbahn EINES Betriebsjahres - fuer das Dispatch-Diagramm.

    Nachgerechnet statt mitgespeichert: Alle Jahre mit ihren Bahnen
    aufzuheben waeren bei 31 Jahren rund 2,5 Millionen Zahlen im
    Sitzungsspeicher, von denen im Regelfall eine Woche eines Jahres
    angesehen wird. Ein einzelnes Jahr rechnet sich in unter einer
    Sekunde.

    Die Eingaben kommen aus derselben Funktion wie im Mehrjahreslauf
    (engine/storage/valuation.jahreseingabe) - das Diagramm zeigt damit
    garantiert den Lauf, der auch im Cashflow steht.
    """
    if not hat_speicher(projekt):
        return None
    assumptions, energy, revenue = _eingaben(projekt, ga)
    reihen = preisreihe(preisreihe_datei(projekt, ga)) or {}
    form = stundenform(projekt)
    if not reihen or form is None:
        return None

    jahre = [int(j) for j in energy["jahr"].to_numpy()]
    if betriebsjahr not in jahre:
        return None
    i = jahre.index(betriebsjahr)

    eingabe = jahreseingabe(
        assumptions, energy=energy, revenue=revenue,
        preise_je_jahr=reihen, form=form, i=i,
        foerderdauer_anteil=revenue["foerderanteil"].to_numpy(),
    )
    if eingabe is None:
        return None
    try:
        ergebnis = dispatch_jahr(
            eingabe.pv_mw, eingabe.preise_eur_mwh, eingabe.grenzerloes_eur_mwh,
            projekt.battery, eingabe.export_limit_mw,
            jahr=betriebsjahr, kalenderjahr=eingabe.kalenderjahr,
        )
    except SolverFehler:
        return None

    tabelle = pd.DataFrame(ergebnis.bahn, columns=list(BAHN_SPALTEN))
    tabelle.insert(0, "stunde", np.arange(len(tabelle)))
    tabelle.attrs["kalenderjahr"] = eingabe.kalenderjahr
    return tabelle


def beispielwoche(bahn_df: pd.DataFrame) -> tuple[int, int]:
    """Erste und letzte Stunde der aussagekraeftigsten Woche.

    Gewaehlt wird die Woche mit dem groessten Speicherumsatz - dort ist
    zu sehen, was der Speicher tut. Die erste Januarwoche zeigte bei
    einer PV-Anlage vor allem eine flache Linie.
    """
    stunden_je_woche = 24 * 7
    entladung = bahn_df["speicher_ins_netz_mw"].to_numpy()
    ladung = (
        bahn_df["pv_in_speicher_mw"].to_numpy()
        + bahn_df["netz_in_speicher_mw"].to_numpy()
    )
    umsatz = entladung + ladung
    wochen = len(bahn_df) // stunden_je_woche
    if wochen < 1:
        return 0, len(bahn_df)
    summen = [
        float(umsatz[w * stunden_je_woche:(w + 1) * stunden_je_woche].sum())
        for w in range(wochen)
    ]
    beste = int(np.argmax(summen))
    return beste * stunden_je_woche, (beste + 1) * stunden_je_woche


# ---------------------------------------------------------------------------
# Auslegungssuche
# ---------------------------------------------------------------------------
#
# Derselbe Aufbau wie beim Dispatch: ein Lauf auf Knopfdruck, abgelegt
# unter dem Fingerabdruck seiner Eingaben, und ein Ergebnis, das sich als
# veraltet zu erkennen gibt. Ein Unterschied ist wesentlich - siehe
# `raster_abdruck`.

#: Session-State: Projekt-ID -> {Fingerabdruck: Rasterergebnis}.
_RASTER = "speicher_raster"
#: Session-State: Projekt-ID -> zuletzt gerechneter Rasterabdruck.
_RASTER_ZULETZT = "speicher_raster_zuletzt"
#: Ein Rasterergebnis traegt je Punkt eine volle Beitragsreihe; zwei
#: davon reichen, um zwei Raster nebeneinander zu halten.
_RASTER_HOECHSTENS = 2


def einspeiseleistung_mw(projekt: PVProject, ga: GlobalAssumptions) -> float:
    """Was am Netzverknuepfungspunkt hinausgehen darf, in MW.

    Die Bezugsgroesse der Auslegungsfrage - und nicht die
    Modulleistung. Bei einer 70-%-Anlage sind das 70 % davon: Ein
    Speicher mit "100 % der Modulleistung" haette eine Entladeleistung,
    die zu keinem Zeitpunkt abfliessen koennte.

    Gerechnet wird sie dort, wo auch die Kappung sie herholt (siehe
    engine/storage/valuation._exportlimit_mw) - PV und Speicher teilen
    sich EINEN Anschluss, und zwei Wahrheiten ueber seine Grenze waeren
    eine zu viel.
    """
    return _exportlimit_mw(resolve_assumptions(projekt, ga))


#: Suchmodus: Leistung UND Dauer werden gesucht.
MODUS_BEIDES = "beides"
#: Suchmodus: Die Leistung steht fest, gesucht ist nur die Dauer.
MODUS_NUR_DAUER = "nur_dauer"


def raster_abdruck(
    projekt: PVProject,
    ga: GlobalAssumptions,
    leistungen_mw: Sequence[float],
    dauern: Sequence[int],
    stuetzjahre: int,
    modus: str = MODUS_BEIDES,
) -> str:
    """Kennung eines Rasterlaufs.

    Wie der Fingerabdruck des Dispatchs, mit einer Ausnahme: Was die
    Suche ERSETZT, wird herausgerechnet. Ein Lauf, der fuer 3 MW /
    12 MWh gerechnet wurde, gilt unveraendert, wenn der Nutzer danach
    4 MW / 16 MWh einstellt - sonst waere die Suche in der Praxis
    unbrauchbar: Ihr erster Nutzen ist, die gefundene Auslegung zu
    uebernehmen, und genau das erklaerte ihr eigenes Ergebnis fuer
    veraltet.

    Was herausfaellt, haengt am Suchmodus, und diese Unterscheidung ist
    keine Feinheit:

        MODUS_BEIDES      Leistung UND Kapazitaet fallen heraus.
        MODUS_NUR_DAUER   Nur die Kapazitaet. Die Leistung ist hier
                          EINGABE und keine gesuchte Groesse - aendert
                          der Nutzer sie, gehoert der Lauf zu einer
                          anderen Frage und muss veralten.

    Alles Uebrige am Speicher (Betriebsart, Wirkungsgrad, Verschleiss,
    Fuellstandsgrenzen) bewegt den Abdruck in beiden Modi, denn es geht
    in jeden einzelnen Rasterpunkt ein.
    """
    entwurf = projekt.model_copy(deep=True)
    if entwurf.battery is not None:
        heraus = {"kapazitaet_mwh": 0.0}
        if modus == MODUS_BEIDES:
            heraus["leistung_mw"] = 0.0
        entwurf.battery = entwurf.battery.model_copy(update=heraus)
    raster_text = (
        ",".join(f"{float(a):.3f}" for a in sorted(set(leistungen_mw)))
        + "|" + ",".join(str(int(d)) for d in sorted(set(dauern)))
        + "|" + str(int(stuetzjahre))
        + "|" + modus
    )
    return fingerabdruck(entwurf, ga, raster_text)


def _raster_abgelegte(projekt_id: str) -> dict[str, Rasterergebnis]:
    return st.session_state.setdefault(_RASTER, {}).setdefault(projekt_id, {})


def feste_leistung_mw(projekt: PVProject) -> float:
    """Die eingestellte Speicherleistung - Eingabe der Dauersuche.

    Beim Graustromspeicher ist sie keine Entwurfsgroesse, sondern das
    Ergebnis einer Vereinbarung: Was aus dem Netz bezogen werden darf,
    steht im Netzanschlussvertrag. Gesucht ist dann nur noch, wie viele
    Stunden der Speicher damit durchhalten soll.
    """
    return projekt.battery.leistung_mw if projekt.battery else 0.0


def raster_rechnen(
    projekt: PVProject,
    ga: GlobalAssumptions,
    *,
    leistungen_mw: Sequence[float],
    dauern: Sequence[int],
    stuetzjahre: int = STUETZJAHRE_STANDARD,
    modus: str = MODUS_BEIDES,
    fortschritt=None,
) -> Rasterergebnis:
    """Rechnet die Auslegungssuche und legt sie ab.

    Der Speicher des Projekts dient als VORLAGE: Betriebsart,
    Wirkungsgrad, Fuellstandsgrenzen und Verschleiss gelten fuer jeden
    Rasterpunkt. Ist noch kein Speicher eingerichtet, gilt die
    Vorbelegung von BatteryConfig - sonst liesse sich die Frage "lohnt
    sich hier ueberhaupt einer?" gar nicht erst stellen.

    Zwei Suchmodi, und sie stellen verschiedene Fragen:

        MODUS_BEIDES      Leistung und Dauer werden gesucht. Bezug der
                          Leistung ist die Einspeiseleistung.
        MODUS_NUR_DAUER   Die Leistung steht fest (die eingestellte),
                          gesucht ist nur die Dauer. Aus dem
                          zweidimensionalen Problem wird ein
                          eindimensionales - und der Optimierer loest es
                          exakt, statt es zu rastern.
    """
    kennung = raster_abdruck(
        projekt, ga, leistungen_mw, dauern, stuetzjahre, modus
    )
    abgelegt = _raster_abgelegte(projekt.id)
    ergebnis = abgelegt.get(kennung)
    if ergebnis is None:
        assumptions, energy, revenue = _eingaben(projekt, ga)
        reihen = preisreihe(preisreihe_datei(projekt, ga)) or {}
        nur_dauer = modus == MODUS_NUR_DAUER
        fest = feste_leistung_mw(projekt) if nur_dauer else None
        ergebnis = rasterlauf(
            assumptions, projekt.id,
            projekt.battery or BatteryConfig(),
            raster(
                [fest] if nur_dauer else leistungen_mw, dauern,
                einspeiseleistung_mw=einspeiseleistung_mw(projekt, ga),
            ),
            energy=energy, revenue=revenue, preise_je_jahr=reihen,
            form=stundenform(projekt),
            foerderdauer_anteil=revenue["foerderanteil"].to_numpy(),
            stuetzjahre_anzahl=stuetzjahre,
            # Der Deckel des Optimierers ist die Einspeiseleistung
            # selbst. Ohne ihn faende er Auslegungen weit darueber:
            # Entladen darf der Speicher bis zur Anschlussgrenze, und
            # solange die Preisspreizung traegt, schoepft er sie aus.
            # Eine Leistung, die das Netz nicht abnimmt, waere aber
            # keine Auslegung, sondern ein Rechenartefakt.
            leistung_hoechstens_mw=(
                None if nur_dauer else einspeiseleistung_mw(projekt, ga)
            ),
            leistung_fest_mw=fest,
            fortschritt=fortschritt,
        )

    abgelegt.pop(kennung, None)
    abgelegt[kennung] = ergebnis
    while len(abgelegt) > _RASTER_HOECHSTENS:
        abgelegt.pop(next(iter(abgelegt)))
    st.session_state.setdefault(_RASTER_ZULETZT, {})[projekt.id] = kennung
    return ergebnis


def letztes_raster(projekt: PVProject) -> tuple[Rasterergebnis | None, str]:
    """Das zuletzt gerechnete Raster und sein Abdruck - auch veraltet.

    Beides zusammen, weil beides zusammengehoert: Wer das Ergebnis
    zeigt, muss den Abdruck gegen den aktuellen halten koennen.
    """
    kennung = st.session_state.get(_RASTER_ZULETZT, {}).get(projekt.id)
    if not kennung:
        return None, ""
    return _raster_abgelegte(projekt.id).get(kennung), kennung


def raster_vergessen(projekt_id: str) -> None:
    st.session_state.get(_RASTER, {}).pop(projekt_id, None)
    st.session_state.get(_RASTER_ZULETZT, {}).pop(projekt_id, None)
