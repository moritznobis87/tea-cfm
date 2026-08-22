"""
Wie gross soll der Speicher sein? Ein Raster ueber Leistung und Dauer -
neben dem exakten Optimierer in optimum.py.

Zwei Verfahren auf dieselbe Frage, und beide werden gebraucht.

Der OPTIMIERER (optimum.py) macht Leistung und Kapazitaet zu Variablen
desselben linearen Programms wie die Fahrweise. Seine Antwort ist exakt
und stetig. Sie hat nur einen Haken: Er maximiert den Barwert des
Speichers nach pauschalem Steuersatz und ohne Fremdkapital, weil die
EK-Rendite keine lineare Funktion der Auslegung ist. Kein LP und kein DP
kann sie direkt maximieren - dazu muesste man Verlustvortrag,
Freibetrag, Tilgungsprofil und eine interne Verzinsung linearisieren.

Das RASTER hier rechnet umgekehrt: wenige, gebaute Auslegungen, jede
durch den VOLLEN Cashflow. Es sagt nicht, wo das Optimum liegt, sondern
was eine Auslegung wirklich einbringt - mit Steuer, Abschreibung,
Fremdkapital und DSCR.

Und es hat einen Vorzug, den kein Optimierer hat: Am Ende steht nicht
eine Zahl, sondern die ganze Flaeche. Ob das Optimum ein scharfer Gipfel
ist oder ein Plateau, auf dem die halbe Investition fast dasselbe
bringt, ist die eigentlich interessante Auskunft - und sie geht
verloren, sobald man nur das Maximum ausgibt.

Der Rasterlauf ruft den Optimierer mit auf und rechnet dessen Auslegung
als zusaetzlichen Punkt durch den Cashflow. Landen beide an derselben
Stelle, ist das die staerkste Bestaetigung, die hier zu haben ist: zwei
voellig verschiedene Wege, ein Ergebnis.

Die Rasterpunkte selbst sind bewusst grob. Niemand baut einen
1,146-Stunden-Speicher; gefragt ist, ob die Speicherleistung der
Einspeiseleistung entsprechen soll oder ein Stueck darunter, und ob er
zwei, sechs oder zwoelf Stunden durchhaelt.

Warum Stuetzjahre
-----------------
Ein Rasterpunkt ueber alle dreissig Betriebsjahre kostet rund zwanzig
Sekunden. Vierzig Punkte waeren vierzehn Minuten, und niemand wartet
vierzehn Minuten auf eine Vorauswahl.

Gerechnet werden deshalb wenige STUETZJAHRE, und ihr Ergebnis wird auf
die Jahre hochgerechnet, fuer die sie stehen. Zwei Dinge machen das
tragfaehig:

    1. Die Bloecke enden an der Grenze der Foerderdauer. Innerhalb der
       Foerderung bemisst sich die Praemie am Referenzmarktwert, danach
       am erzielten Preis - der Speicherwert springt dort, und ueber
       einen Sprung hinweg zu mitteln waere schlicht falsch.
    2. Hochgerechnet wird nicht flach, sondern mit den beiden Groessen,
       die sich analytisch angeben lassen: dem nominalen Preisniveau und
       der Jahresmenge. Der Verschleiss folgt nur der Menge - sein Satz
       je MWh ist nominal fest.

Was dabei NICHT erfasst wird, ist die Veraenderung der PREISSPREIZUNG von
Kalenderjahr zu Kalenderjahr. Genau dagegen helfen mehr Stuetzjahre, und
genau deshalb ist ihre Zahl einstellbar.

Der Fehler ist ausserdem in der Richtung harmlos, auf die es hier
ankommt: Er trifft alle Rasterpunkte gleichermassen, denn sie rechnen
dieselben Stuetzjahre mit denselben Preisen. Die REIHENFOLGE der Punkte
haelt er damit weit besser als ihre Absolutwerte - und die Reihenfolge
ist die Antwort. Wer den genauen Wert der gewaehlten Auslegung braucht,
laesst sie anschliessend als gewoehnlichen Dispatchlauf ueber alle Jahre
rechnen; dafuer gibt es den Knopf, den es vorher schon gab.

Was hier NICHT entschieden wird
-------------------------------
Ob nach Rendite oder nach Barwert gesucht wird. Beide Spalten stehen im
Ergebnis, und sie zeigen nicht auf denselben Punkt: Die Rendite bevorzugt
den kleinen Speicher, der wenig Kapital bindet, der Barwert den grossen,
der viel verdient. Welche der beiden Fragen die richtige ist, haengt
daran, ob Eigenkapital knapp ist - und das weiss dieses Modul nicht.

Warum kein DP
-------------
Fuer die Fahrweise war die dynamische Programmierung der naheliegende
Ansatz und wurde gemessen: Sie war rund dreimal langsamer als das LP und
dabei 0,3 bis 0,7 Prozent UNGENAUER, weil sie den Fuellstand
diskretisieren muss. Fuer die Auslegung passt sie ohnehin nicht - eine
Groesse ist keine Folge von Entscheidungen ueber der Zeit, und genau das
ist die Struktur, die ein DP braucht.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..models import BatteryConfig, EffectiveAssumptions
from .dispatch import dispatch_jahr, vergleichsfall
from .economics import jahreswert
from .kosten import capex_eur, opex_jahr_eur
from .models import SolverFehler, StorageJahreswert
from .optimum import StetigesOptimum, optimum_stetig
from .valuation import Jahreseingabe, SpeicherBeitrag, jahreseingabe

#: Speicherdauern zur Wahl, in Stunden. Ganzzahlige Vielfache der
#: Leistung - eine 4-MW-Anlage mit 3 h hat 12 MWh. Krumme Dauern sind
#: bewusst nicht dabei: Sie versprechen eine Genauigkeit, die weder die
#: Preisreihe noch die Kostenkalibrierung hergibt.
DAUERN_STUNDEN: tuple[int, ...] = (1, 2, 3, 4, 6, 8, 10, 12)

#: Was ohne weitere Angabe gerechnet wird.
DAUERN_STANDARD: tuple[int, ...] = (2, 4, 6, 8, 10, 12)

#: Feinste Stufe der Speicherleistung, in MW. Ein Speicher wird nicht
#: auf drei Nachkommastellen bestellt; hundert Kilowatt sind die
#: kleinste Groesse, ueber die sich zu reden lohnt.
LEISTUNGSSCHRITT_MW = 0.1

#: Wie weit ueber die Einspeiseleistung hinaus Auslegungen zur Wahl
#: stehen. Mehr Leistung als der Anschluss hergibt klingt widersinnig,
#: ist es aber nicht: Entladen kann der Speicher nur bis zur
#: Anschlussgrenze, LADEN aus der PV-Anlage dagegen so schnell, wie sie
#: liefert - und genau in den Stunden, in denen sie ueber der Grenze
#: liegt, entsteht die Abregelung, die er zurueckholen soll.
LEISTUNG_UEBER_ANSCHLUSS = 1.5

#: Ungefaehr so viele Stufen soll die Auswahl haben. Zwoelf bis
#: achtzehn passen in eine Liste, ohne dass man scrollt.
_STUFEN_ANGESTREBT = 14

#: Runde Schrittweiten in MW. Aus dieser Reihe wird die genommen, die
#: der angestrebten Stufenzahl am naechsten kommt - so stehen im
#: Auswahlfeld runde Zahlen (0,5 / 1,0 / 1,5 MW) und nicht die krummen
#: Vielfachen eines Prozentsatzes (1,75 / 3,50 / 5,25 MW).
_SCHRITTREIHE: tuple[float, ...] = (
    0.1, 0.2, 0.25, 0.5, 1.0, 2.0, 2.5, 5.0, 10.0, 20.0, 25.0, 50.0,
)


def _schrittweite(spanne_mw: float) -> float:
    """Die runde Schrittweite, die `spanne_mw` am besten aufteilt."""
    ziel = spanne_mw / _STUFEN_ANGESTREBT
    tauglich = [s for s in _SCHRITTREIHE if s >= LEISTUNGSSCHRITT_MW]
    return min(tauglich, key=lambda s: abs(s - ziel))


def leistungsstufen(einspeiseleistung_mw: float) -> tuple[float, ...]:
    """Waehlbare Speicherleistungen in MW - runde Zahlen, keine Prozente.

    Prozentwerte waren die erste Fassung und die schlechtere: "75 %"
    beantwortet die Frage nicht, solange nicht danebensteht, wovon.
    Genau diese Rueckfrage kam aus der Anwendung, und zwar mit drei
    plausiblen Kandidaten - Modulleistung, Einspeiseleistung oder der
    bereits eingestellte Speicher.

    In MW stellt sie sich nicht. Die Liste richtet sich trotzdem nach
    der Einspeiseleistung, denn sie ist die Groesse, an der die Antwort
    haengt; sichtbar ist davon aber nur noch das Ergebnis.
    """
    obergrenze = max(
        einspeiseleistung_mw * LEISTUNG_UEBER_ANSCHLUSS, LEISTUNGSSCHRITT_MW
    )
    schritt = _schrittweite(obergrenze)
    anzahl = max(1, int(round(obergrenze / schritt)))
    return tuple(
        round(schritt * (i + 1), 3) for i in range(anzahl)
    )


def leistungen_standard(einspeiseleistung_mw: float) -> tuple[float, ...]:
    """Was ohne weitere Angabe angehakt ist.

    Vier Stufen rund um die Einspeiseleistung - ein Viertel, die
    Haelfte, drei Viertel, voll -, auf die verfuegbaren Stufen gerundet.
    Das ist dieselbe Spreizung wie in der ersten Fassung, nur ohne dass
    der Nutzer sie in Prozent lesen muss.
    """
    stufen = leistungsstufen(einspeiseleistung_mw)
    if not stufen:
        return ()
    gewuenscht = [einspeiseleistung_mw * a for a in (0.25, 0.5, 0.75, 1.0)]
    gewaehlt = {
        min(stufen, key=lambda s, z=ziel: abs(s - z)) for ziel in gewuenscht
    }
    return tuple(sorted(gewaehlt))

#: Stuetzjahre ohne weitere Angabe.
STUETZJAHRE_STANDARD = 4

#: Nach welcher Spalte das Optimum bestimmt wird.
NACH_RENDITE = "rendite"
NACH_BARWERT = "barwert"


# ---------------------------------------------------------------------------
# Das Raster
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Kandidat:
    """Eine Auslegung, die zur Wahl steht."""

    #: Anteil an der EINSPEISELEISTUNG - die Groesse, in der die Frage
    #: gestellt wird ("so viel wie die Anlage einspeisen darf, oder die
    #: Haelfte davon?").
    leistungsanteil: float
    leistung_mw: float
    dauer_h: float

    @property
    def kapazitaet_mwh(self) -> float:
        return self.leistung_mw * self.dauer_h

    def batterie(self, vorlage: BatteryConfig) -> BatteryConfig:
        """Die Vorlage mit DIESER Groesse.

        Alles Uebrige - Betriebsart, Wirkungsgrad, Fuellstandsgrenzen,
        Verschleiss, Netzbezugsgrenze - bleibt, wie der Nutzer es
        eingestellt hat. Das Raster beantwortet die Groessenfrage und
        keine andere.
        """
        return vorlage.model_copy(update={
            "aktiv": True,
            "leistung_mw": self.leistung_mw,
            "kapazitaet_mwh": self.kapazitaet_mwh,
        })


def raster(
    leistungen_mw: Sequence[float],
    dauern: Sequence[int] = DAUERN_STANDARD,
    einspeiseleistung_mw: float = 0.0,
) -> tuple[Kandidat, ...]:
    """Alle Punkte des Rasters, nach Leistung und dann Dauer sortiert.

    Die Leistungen kommen ABSOLUT in MW herein. Der Anteil an der
    Einspeiseleistung wird nur noch mitgefuehrt, weil der Optimierer
    seinen Kandidaten damit einordnet - gefragt und angezeigt wird er
    nicht mehr (siehe `leistungsstufen`).
    """
    return tuple(
        Kandidat(
            leistungsanteil=(
                float(mw) / einspeiseleistung_mw
                if einspeiseleistung_mw else 0.0
            ),
            leistung_mw=round(float(mw), 3),
            dauer_h=int(dauer),
        )
        for mw in sorted(set(leistungen_mw))
        for dauer in sorted(set(dauern))
    )


# ---------------------------------------------------------------------------
# Stuetzjahre
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Stuetzjahr:
    """Ein gerechnetes Jahr und die Betriebsjahre, fuer die es steht."""

    jahr: int
    kalenderjahr: int
    #: Betriebsjahre (1-basiert), die dieses Jahr vertritt.
    vertritt: tuple[int, ...]

    @property
    def anzahl(self) -> int:
        return len(self.vertritt)


def _abschnitte(foerderanteil: Sequence[float] | None, jahre: int) -> list[list[int]]:
    """Betriebsjahre als Indexlisten, getrennt an der Foerdergrenze.

    Der Uebergang aus der Foerderung heraus ist ein Sprung und keine
    Steigung: Innerhalb der Foerderdauer misst sich die Marktpraemie am
    REFERENZmarktwert, danach zaehlt der erzielte Preis. Ein Stuetzjahr
    aus der Foerderzeit sagt ueber die Zeit danach nichts aus.
    """
    if foerderanteil is None:
        return [list(range(jahre))]
    drin = [float(w) > 0.5 for w in foerderanteil[:jahre]]
    drin += [drin[-1] if drin else False] * (jahre - len(drin))

    abschnitte: list[list[int]] = []
    laufend: list[int] = []
    for i, ist_drin in enumerate(drin):
        if laufend and ist_drin != drin[i - 1]:
            abschnitte.append(laufend)
            laufend = []
        laufend.append(i)
    if laufend:
        abschnitte.append(laufend)
    return abschnitte


#: In welcher Groessenordnung der Kapitalkostenfaktor gemessen wird -
#: als Vielfaches der mittleren Rasterinvestition. Der Faktor ist nicht
#: streng linear: Bei sehr grossen Investitionen greifen Steuerfreibetrag
#: und Verlustvortrag, gemessen 0,62 bei 1 Mio und 0,76 bei 40 Mio Euro.
#: Gemessen wird deshalb DORT, wo das Raster tatsaechlich rechnet.
_FAKTOR_MESSPUNKT = 1.0


def kapitalkostenfaktor(
    assumptions: EffectiveAssumptions,
    project_id: str,
    hoehe_eur: float,
) -> float:
    """Was ein Euro Speicherinvestition den Projektbarwert wirklich kostet.

    Gemessen statt hergeleitet, mit zwei gewoehnlichen Bewertungslaeufen
    (je rund 50 ms): einmal ohne, einmal mit einer Investition dieser
    Hoehe und OHNE jeden Erloes. Die Differenz je Euro ist der Faktor.

    Warum das noetig ist
    --------------------
    Der Optimierer rechnete zuvor mit `1 - Abschreibungsschild` und
    unterstellte damit eine unverschuldete Investition. Gemessen an einem
    Projekt mit 20 % Eigenkapital und 4,2 % Fremdkapitalzins:

        1 Mio EUR/Jahr Beitrag   Modell 8.665.448 | Formel 8.668.493
        10 Mio EUR Investition   Modell 6.692.680 | Formel 8.870.913

    Die Erloesseite stimmte auf 0,04 Prozent. Die Kostenseite lag um ein
    Viertel daneben - und zwar systematisch zugunsten zu kleiner
    Speicher. Wer zu 4,2 Prozent leiht und mit 8 Prozent diskontiert,
    verdient an der Differenz; bei 11,8 Mio Euro Investition sind das
    2,9 Mio Euro, die im Optimum fehlten.

    Der Faktor faellt mit sinkender Eigenkapitalquote (0,89 bei 100 %,
    0,67 bei 20 %) und steigt mit dem Zins (0,56 bei 2 %, 1,03 bei
    10 %). Bei einem Zins in Hoehe des Diskontsatzes verschwindet der
    Vorteil, und die alte Formel stimmt wieder.

    Und er erfasst etwas, das eine geschlossene Formel gar nicht
    wissen kann: ob sich die Abschreibung ueberhaupt VERRECHNEN laesst.
    Das Schild setzt steuerpflichtigen Gewinn voraus. Ein Projekt mit
    schmalem Ergebnis bekommt fuer eine grosse Investition kaum etwas
    davon - gemessen am Testprojekt (775.000 EUR steuerliches Ergebnis
    ueber 25 Jahre) liegt der Faktor bei rund 1,0 statt bei den 0,89 der
    Formel, weil zehn Millionen Abschreibung auf keinen Gewinn treffen.

    Was er NICHT erfasst: die Rueckwirkung auf die Kovenanten. Ein
    Speicher, der den DSCR unter die Schwelle drueckt, ist teurer als
    dieser Faktor sagt - das steht in der DSCR-Spalte des Rasters.
    """
    from ..pipeline import run_valuation_from_assumptions

    if hoehe_eur <= 0:
        return 1.0
    jahre = assumptions.betriebsdauer_jahre
    leer = tuple(0.0 for _ in range(jahre))
    ohne = run_valuation_from_assumptions(
        assumptions, project_id, compute_npv_curve=False
    )
    mit = run_valuation_from_assumptions(
        assumptions, project_id, compute_npv_curve=False,
        speicher=SpeicherBeitrag(
            wertbeitrag_eur_je_jahr=leer,
            capex_eur=float(hoehe_eur),
            opex_eur_je_jahr=leer,
            jahreswerte=(), hinweise=(),
        ),
    )
    return (ohne.kpis.npv_eur - mit.kpis.npv_eur) / float(hoehe_eur)


#: Mit welchem Satz die Bloecke gewichtet werden. KEINE
#: Finanzierungsannahme und keine Rechengroesse - er entscheidet allein
#: darueber, WO die Stuetzjahre liegen. Ein frueher Euro schlaegt im
#: Barwert und noch staerker in der Rendite schwerer durch als ein
#: spaeter; die Stuetzjahre gehoeren deshalb dorthin, wo ein Fehler weh
#: tut. Der Wert entspricht dem Diskontsatz der NPV-Kennzahl.
_GEWICHT_SATZ = 0.08


def _gewichte(indizes: Sequence[int]) -> np.ndarray:
    """Diskontgewicht je Betriebsjahr, auf Summe 1 gebracht."""
    roh = np.array(
        [(1.0 + _GEWICHT_SATZ) ** -(i + 1) for i in indizes], dtype=float
    )
    summe = roh.sum()
    return roh / summe if summe > 0 else np.full(len(indizes), 1.0 / len(indizes))


def bloecke(
    foerderanteil: Sequence[float] | None, jahre: int, anzahl: int
) -> list[list[int]]:
    """Die Betriebsjahre in `anzahl` Bloecke teilen.

    Jeder Abschnitt bekommt mindestens einen Block - sonst faellt die
    Zeit nach der Foerderung unter den Tisch, und das ist bei einer
    zwanzigjaehrigen Foerderung und dreissig Betriebsjahren ein Drittel
    der Laufzeit.

    Geteilt wird nach GEWICHT und nicht nach Jahren. Gleich lange Bloecke
    waeren die naheliegende Wahl und die schlechtere: Sie legen ueber die
    ersten Jahre denselben groben Raster wie ueber die letzten, obwohl
    ein Fehler in Jahr 3 die Rendite weit staerker verzieht als einer in
    Jahr 28. Gemessen an einem vollen Lauf sank der Renditefehler bei
    vier Stuetzjahren dadurch deutlich, ohne dass eine einzige zusaetzliche
    Optimierung noetig wurde.
    """
    abschnitte = _abschnitte(foerderanteil, jahre)
    anzahl = max(len(abschnitte), min(int(anzahl), jahre))

    # Bloecke auf die Abschnitte verteilen: Wer je Block das meiste
    # Gewicht traegt, bekommt den naechsten.
    gewicht = _gewichte(list(range(jahre)))
    je_abschnitt = [float(gewicht[a].sum()) for a in abschnitte]
    zahl = [1] * len(abschnitte)
    for _ in range(anzahl - len(abschnitte)):
        groesster = max(
            range(len(abschnitte)),
            key=lambda k: (
                je_abschnitt[k] / zahl[k]
                if zahl[k] < len(abschnitte[k]) else -1.0
            ),
        )
        if zahl[groesster] >= len(abschnitte[groesster]):
            break
        zahl[groesster] += 1

    geteilt: list[list[int]] = []
    for abschnitt, k in zip(abschnitte, zahl, strict=True):
        geteilt.extend(_teilen(abschnitt, k))
    return geteilt


def _teilen(abschnitt: Sequence[int], k: int) -> list[list[int]]:
    """Einen Abschnitt in `k` Bloecke gleichen Gewichts schneiden."""
    if k <= 1 or len(abschnitt) <= 1:
        return [list(abschnitt)]
    lauf = np.cumsum(_gewichte(abschnitt))
    bloecke_: list[list[int]] = []
    von = 0
    for n in range(1, k):
        ziel = n / k
        bis = int(np.searchsorted(lauf, ziel, side="right")) + 1
        # Jeder Block braucht mindestens ein Jahr, und fuer die
        # verbleibenden Bloecke muss auch noch je eines uebrig sein.
        bis = max(von + 1, min(bis, len(abschnitt) - (k - n)))
        bloecke_.append(list(abschnitt[von:bis]))
        von = bis
    bloecke_.append(list(abschnitt[von:]))
    return [b for b in bloecke_ if b]


def _vertreter(block: Sequence[int]) -> int:
    """Das Jahr in der MITTE des Blocks.

    Nicht das erste: Es liegt am Rand, und der Rand ist genau die Stelle,
    an der die Hochrechnung am weitesten traegt.
    """
    return block[len(block) // 2]


@dataclass(frozen=True)
class Stuetze:
    """Ein gerechnetes Jahr mit allem, was daran haengt.

    Eigenes Objekt, weil es ZWEI Verfahren benutzen: den Rasterlauf und
    die Mitoptimierung (optimum.py). Beide muessen dieselben Jahre mit
    denselben Gewichten sehen - sonst waeren ihre Ergebnisse nicht
    vergleichbar, und genau der Vergleich ist der Zweck der Uebung.
    """

    #: Indizes der vertretenen Betriebsjahre (0-basiert).
    block: tuple[int, ...]
    #: Index des Vertreters selbst.
    i: int
    eingabe: Jahreseingabe
    #: (Zielwert, Abregelung) des Laufs ohne Speicher.
    vergleich: tuple[float, float]
    #: Abgezinste Zahl vertretener Jahre - fuer die Erloesseite mit
    #: Preisniveau, fuer den Verschleiss ohne (siehe `hochrechnen`).
    gewicht_erloes: float
    gewicht_verschleiss: float
    beschreibung: Stuetzjahr


def stuetzen_vorbereiten(
    assumptions: EffectiveAssumptions,
    *,
    energy: pd.DataFrame,
    revenue: pd.DataFrame,
    preise_je_jahr: dict[int, tuple[float, ...]],
    form: Sequence[float],
    foerderdauer_anteil: Sequence[float] | None,
    anzahl: int,
    diskontsatz: float = _GEWICHT_SATZ,
) -> tuple[list[Stuetze], list[str]]:
    """Die Stuetzjahre samt Eingaben, Vergleichsfall und Gewichten.

    Der Vergleichsfall wird hier EINMAL je Stuetzjahr geloest. Er haengt
    an keiner Eigenschaft des Speichers (siehe dispatch.vergleichsfall),
    und ein Rasterlauf ueber fuenfzig Auslegungen rechnete ihn sonst
    fuenfzigmal.
    """
    jahre = [int(j) for j in energy["jahr"].to_numpy()]
    mengen = _mengen(energy)
    hinweise: list[str] = []
    stuetzen: list[Stuetze] = []

    for block in bloecke(foerderdauer_anteil, len(jahre), anzahl):
        i = _vertreter(block)
        eingabe = jahreseingabe(
            assumptions, energy=energy, revenue=revenue,
            preise_je_jahr=preise_je_jahr, form=form, i=i,
            foerderdauer_anteil=foerderdauer_anteil,
        )
        if eingabe is None:
            hinweise.append(
                f"Fuer Betriebsjahr {jahre[i]} liegt keine Stundenpreisreihe "
                "vor - der Block bleibt ohne Speicherbeitrag."
            )
            continue

        niveau_stuetze = _preisniveau(assumptions, eingabe.kalenderjahr)
        gewicht_erloes = 0.0
        gewicht_verschleiss = 0.0
        for k in block:
            kalenderjahr = assumptions.inbetriebnahme_jahr + jahre[k] - 1
            abzinsung = 1.0 / (1.0 + diskontsatz) ** (k + 1)
            mengenanteil = (
                float(mengen[k]) / float(mengen[i]) if mengen[i] else 1.0
            )
            gewicht_verschleiss += mengenanteil * abzinsung
            gewicht_erloes += (
                _preisniveau(assumptions, kalenderjahr) / niveau_stuetze
            ) * mengenanteil * abzinsung

        stuetzen.append(Stuetze(
            block=tuple(block),
            i=i,
            eingabe=eingabe,
            vergleich=vergleichsfall(
                eingabe.pv_mw, eingabe.preise_eur_mwh,
                eingabe.grenzerloes_eur_mwh, eingabe.export_limit_mw,
            ),
            gewicht_erloes=gewicht_erloes,
            gewicht_verschleiss=gewicht_verschleiss,
            beschreibung=Stuetzjahr(
                jahr=jahre[i],
                kalenderjahr=eingabe.kalenderjahr,
                vertritt=tuple(jahre[k] for k in block),
            ),
        ))

    if not stuetzen:
        raise SolverFehler(
            "Fuer kein einziges Betriebsjahr liegt eine Stundenpreisreihe "
            "vor - eine Auslegungssuche hat damit keine Grundlage."
        )
    return stuetzen, hinweise


# ---------------------------------------------------------------------------
# Hochrechnung
# ---------------------------------------------------------------------------


def _preisniveau(assumptions: EffectiveAssumptions, kalenderjahr: int) -> float:
    """Der nominale Faktor auf die realen Szenariopreise.

    Dieselbe Formel wie in valuation.jahreseingabe - die Stundenpreise
    sind real auf der Preisbasis des Szenarios.
    """
    return (1 + assumptions.marktpreis_inflation_pct_pa) ** (
        kalenderjahr - assumptions.marktpreis_inflation_basisjahr
    )


def _mengen(energy: pd.DataFrame) -> np.ndarray:
    """Die Jahreserzeugung VOR der Abregelung, je Betriebsjahr, in MWh."""
    produktion = energy["produktion_kwh"].to_numpy(dtype=float)
    kappung = (
        energy["kappung_kwh"].to_numpy(dtype=float)
        if "kappung_kwh" in energy.columns
        else np.zeros(len(energy))
    )
    return (produktion + kappung) / 1000.0


def hochrechnen(
    wert: StorageJahreswert,
    *,
    niveau_stuetze: float,
    niveau_ziel: float,
    menge_stuetze: float,
    menge_ziel: float,
) -> float:
    """Der Deckungsbeitrag des Stuetzjahres, uebertragen auf ein anderes.

    Zerlegt statt pauschal skaliert, weil die drei Bestandteile
    unterschiedlich mitwandern:

        Mehrerloes und Netzbezug   Preisniveau MAL Menge. Beide sind
                                   Betraege in Euro und damit linear in
                                   den Preisen; die Menge skaliert, wie
                                   viel ueberhaupt zu verschieben ist.
        Verschleiss                nur Menge. Sein Satz steht in
                                   EUR/MWh und wird im Modell nicht
                                   inflationiert (siehe BatteryConfig).

    Ein pauschaler Faktor auf den Deckungsbeitrag haette den Verschleiss
    mit hochinflationiert und den Speicherwert der spaeten Jahre damit zu
    klein gerechnet - im dreissigsten Jahr um rund die Haelfte des
    Verschleisses.
    """
    preis_faktor = (niveau_ziel / niveau_stuetze) if niveau_stuetze else 1.0
    mengen_faktor = (menge_ziel / menge_stuetze) if menge_stuetze else 1.0
    erloesseite = (wert.mehrerloes_eur - wert.netzbezugskosten_eur) * (
        preis_faktor * mengen_faktor
    )
    return erloesseite - wert.degradationskosten_eur * mengen_faktor


# ---------------------------------------------------------------------------
# Der Rasterlauf
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rasterpunkt:
    """Ein durchgerechneter Punkt des Rasters."""

    kandidat: Kandidat
    beitrag: SpeicherBeitrag
    #: Kennzahlen des GANZEN Projekts mit diesem Speicher.
    equity_irr: float | None
    npv_eur: float
    dscr_min: float | None

    @property
    def capex_eur(self) -> float:
        return self.beitrag.capex_eur

    @property
    def wertbeitrag_gesamt_eur(self) -> float:
        return self.beitrag.wertbeitrag_gesamt_eur

    @property
    def vollzyklen(self) -> float:
        return self.beitrag.vollzyklen_mittel


@dataclass(frozen=True)
class Rasterergebnis:
    """Die ganze Flaeche samt Bezugspunkt."""

    punkte: tuple[Rasterpunkt, ...]
    #: Dasselbe Projekt OHNE Speicher - der Massstab jeder Aussage hier.
    equity_irr_ohne: float | None
    npv_eur_ohne: float
    stuetzjahre: tuple[Stuetzjahr, ...]
    betriebsjahre: int
    hinweise: tuple[str, ...] = ()
    #: Das exakte stetige Optimum der Dispatch-Oekonomie (optimum.py) -
    #: None, wenn nicht mitoptimiert wurde.
    optimum: StetigesOptimum | None = None
    #: Derselbe Punkt, aber durch den vollen Cashflow gerechnet. Erst er
    #: sagt, was das stetige Optimum im Modell dieser Anwendung wert
    #: ist - mit Steuer, Abschreibung und Fremdkapital.
    optimum_punkt: Rasterpunkt | None = None

    def bestes(self, nach: str = NACH_RENDITE) -> Rasterpunkt | None:
        """Der beste Punkt nach Rendite oder nach Barwert.

        Punkte ohne Rendite (kein Vorzeichenwechsel im Zahlungsstrom)
        scheiden bei der Renditesuche aus - `None` ist keine kleine
        Rendite, sondern eine nicht bestimmbare.
        """
        if not self.punkte:
            return None
        if nach == NACH_BARWERT:
            return max(self.punkte, key=lambda p: p.npv_eur)
        mit_rendite = [p for p in self.punkte if p.equity_irr is not None]
        return max(mit_rendite, key=lambda p: p.equity_irr) if mit_rendite else None

    @property
    def einig(self) -> bool:
        """Zeigen Rendite und Barwert auf dieselbe Auslegung?

        Wenn nicht, ist das die wichtigste Auskunft des ganzen Laufs -
        dann haengt die Antwort daran, ob Eigenkapital knapp ist.
        """
        nach_rendite = self.bestes(NACH_RENDITE)
        nach_barwert = self.bestes(NACH_BARWERT)
        if nach_rendite is None or nach_barwert is None:
            return True
        return nach_rendite.kandidat == nach_barwert.kandidat

    def tabelle(self) -> pd.DataFrame:
        """Das Raster als Tabelle - eine Zeile je Punkt."""
        return pd.DataFrame([
            {
                "leistungsanteil": p.kandidat.leistungsanteil,
                "leistung_mw": p.kandidat.leistung_mw,
                "dauer_h": p.kandidat.dauer_h,
                "kapazitaet_mwh": p.kandidat.kapazitaet_mwh,
                "capex_eur": p.capex_eur,
                "wertbeitrag_eur": p.wertbeitrag_gesamt_eur,
                "vollzyklen": p.vollzyklen,
                "equity_irr": p.equity_irr,
                "npv_eur": p.npv_eur,
                "dscr_min": p.dscr_min,
                "delta_irr": (
                    None if p.equity_irr is None or self.equity_irr_ohne is None
                    else p.equity_irr - self.equity_irr_ohne
                ),
                "delta_npv_eur": p.npv_eur - self.npv_eur_ohne,
            }
            for p in self.punkte
        ])


def rasterlauf(
    assumptions: EffectiveAssumptions,
    project_id: str,
    vorlage: BatteryConfig,
    kandidaten: Sequence[Kandidat],
    *,
    energy: pd.DataFrame,
    revenue: pd.DataFrame,
    preise_je_jahr: dict[int, tuple[float, ...]],
    form: Sequence[float],
    foerderdauer_anteil: Sequence[float] | None = None,
    stuetzjahre_anzahl: int = STUETZJAHRE_STANDARD,
    mitoptimieren: bool = True,
    leistung_hoechstens_mw: float | None = None,
    leistung_fest_mw: float | None = None,
    fortschritt: Callable[[int, int], None] | None = None,
) -> Rasterergebnis:
    """Rechnet jeden Kandidaten auf den Stuetzjahren und bewertet ihn.

    Der teure Teil sind die linearen Programme: je Kandidat und
    Stuetzjahr eines. Der VERGLEICHSFALL - dasselbe Jahr ohne Speicher -
    haengt an keiner Eigenschaft des Speichers und wird deshalb einmal je
    Stuetzjahr gerechnet und durchgereicht. Das halbiert die Laufzeit,
    ohne an einer einzigen Zahl etwas zu aendern.

    Der billige Teil ist die Bewertung: Sie laeuft je Kandidat einmal
    ueber den gewoehnlichen Weg (rund 50 ms) und liefert damit dieselben
    Kennzahlen, die auf der Projektseite stehen - einschliesslich
    Finanzierung, Steuer und Abschreibung der Speicherinvestition.
    """
    # Lokaler Import: pipeline.py kennt engine.storage, der umgekehrte
    # Weg waere ein Zirkelbezug. Dieselbe Loesung wie in
    # engine/sensitivity.py.
    from ..pipeline import run_valuation_from_assumptions

    jahre = [int(j) for j in energy["jahr"].to_numpy()]
    mengen = _mengen(energy)
    stuetzen, hinweise = stuetzen_vorbereiten(
        assumptions, energy=energy, revenue=revenue,
        preise_je_jahr=preise_je_jahr, form=form,
        foerderdauer_anteil=foerderdauer_anteil, anzahl=stuetzjahre_anzahl,
    )
    stuetzjahre = tuple(s.beschreibung for s in stuetzen)

    ohne = run_valuation_from_assumptions(
        assumptions, project_id, compute_npv_curve=False
    )

    # --- Das Raster ---------------------------------------------------
    punkte: list[Rasterpunkt] = []
    for nummer, kandidat in enumerate(kandidaten, start=1):
        batterie = kandidat.batterie(vorlage)
        beitrag = _beitrag(
            assumptions, batterie, stuetzen,
            jahre=jahre, mengen=mengen, hinweise=hinweise,
        )
        bewertet = run_valuation_from_assumptions(
            assumptions, project_id, compute_npv_curve=False, speicher=beitrag
        )
        punkte.append(Rasterpunkt(
            kandidat=kandidat,
            beitrag=beitrag,
            equity_irr=bewertet.kpis.equity_irr,
            npv_eur=bewertet.kpis.npv_eur,
            dscr_min=bewertet.kpis.dscr_min,
        ))
        if fortschritt is not None:
            fortschritt(nummer, len(kandidaten))

    # --- Das stetige Optimum ------------------------------------------
    # Es steht NEBEN dem Raster und nicht darin: Seine Auslegung ist
    # krumm und gehoert in keine Zeile und keine Spalte. Gerechnet wird
    # sie trotzdem durch den vollen Cashflow - sonst stuende eine Zahl
    # aus einem anderen Modell neben Zahlen aus diesem, und niemand
    # koennte sie vergleichen.
    stetig = None
    stetig_punkt = None
    if mitoptimieren:
        # Der Kostenfaktor wird DORT gemessen, wo das Raster rechnet -
        # er ist nicht streng linear (siehe kapitalkostenfaktor).
        mittlere_investition = (
            sum(p.capex_eur for p in punkte) / len(punkte) if punkte else 0.0
        )
        faktor = kapitalkostenfaktor(
            assumptions, project_id,
            mittlere_investition * _FAKTOR_MESSPUNKT,
        )
        stetig = optimum_stetig(
            assumptions, vorlage,
            [s.eingabe for s in stuetzen],
            [(s.gewicht_erloes, s.gewicht_verschleiss) for s in stuetzen],
            betriebsjahre=len(jahre),
            diskontsatz=_GEWICHT_SATZ,
            leistung_hoechstens_mw=leistung_hoechstens_mw,
            leistung_fest_mw=leistung_fest_mw,
            kapitalkostenfaktor=faktor,
            vergleiche=[s.vergleich[0] for s in stuetzen],
        )
        if stetig.wirksam:
            bezug = (
                leistung_fest_mw or leistung_hoechstens_mw
                or stetig.leistung_mw
            )
            kandidat = Kandidat(
                leistungsanteil=(
                    stetig.leistung_mw / bezug if bezug else 0.0
                ),
                leistung_mw=stetig.leistung_mw,
                dauer_h=stetig.dauer_h,
            )
            beitrag = _beitrag(
                assumptions, kandidat.batterie(vorlage), stuetzen,
                jahre=jahre, mengen=mengen, hinweise=hinweise,
            )
            bewertet = run_valuation_from_assumptions(
                assumptions, project_id, compute_npv_curve=False,
                speicher=beitrag,
            )
            stetig_punkt = Rasterpunkt(
                kandidat=kandidat, beitrag=beitrag,
                equity_irr=bewertet.kpis.equity_irr,
                npv_eur=bewertet.kpis.npv_eur,
                dscr_min=bewertet.kpis.dscr_min,
            )

    return Rasterergebnis(
        punkte=tuple(punkte),
        equity_irr_ohne=ohne.kpis.equity_irr,
        npv_eur_ohne=ohne.kpis.npv_eur,
        stuetzjahre=stuetzjahre,
        betriebsjahre=len(jahre),
        hinweise=tuple(hinweise),
        optimum=stetig,
        optimum_punkt=stetig_punkt,
    )


def _beitrag(
    assumptions: EffectiveAssumptions,
    batterie: BatteryConfig,
    stuetzen: Sequence[Stuetze],
    *,
    jahre: list[int],
    mengen: np.ndarray,
    hinweise: list[str],
) -> SpeicherBeitrag:
    """Ein Kandidat ueber alle Stuetzjahre, hochgerechnet auf die Laufzeit."""
    wertbeitrag = np.zeros(len(jahre))
    jahreswerte: list[StorageJahreswert] = []

    for stuetze in stuetzen:
        eingabe = stuetze.eingabe
        ergebnis = dispatch_jahr(
            eingabe.pv_mw, eingabe.preise_eur_mwh, eingabe.grenzerloes_eur_mwh,
            batterie, eingabe.export_limit_mw,
            jahr=jahre[stuetze.i], kalenderjahr=eingabe.kalenderjahr,
            vergleich=stuetze.vergleich,
        )
        wert = jahreswert(ergebnis, batterie, ergebnis.abregelung_pv_only_mwh)
        jahreswerte.append(wert)

        niveau_stuetze = _preisniveau(assumptions, eingabe.kalenderjahr)
        for k in stuetze.block:
            kalenderjahr = assumptions.inbetriebnahme_jahr + jahre[k] - 1
            wertbeitrag[k] = hochrechnen(
                wert,
                niveau_stuetze=niveau_stuetze,
                niveau_ziel=_preisniveau(assumptions, kalenderjahr),
                menge_stuetze=float(mengen[stuetze.i]),
                menge_ziel=float(mengen[k]),
            )
        for hinweis in ergebnis.hinweise:
            text = f"Jahr {jahre[stuetze.i]}: {hinweis}"
            if text not in hinweise:
                hinweise.append(text)

    return SpeicherBeitrag(
        wertbeitrag_eur_je_jahr=tuple(float(w) for w in wertbeitrag),
        capex_eur=capex_eur(batterie, assumptions),
        opex_eur_je_jahr=tuple(opex_jahr_eur(batterie, assumptions) for _ in jahre),
        # Nur die tatsaechlich gerechneten Jahre. Die hochgerechneten
        # hier mitzufuehren hiesse, geschaetzte Vollzyklen und
        # geschaetzte Mengen wie gerechnete aussehen zu lassen.
        jahreswerte=tuple(jahreswerte),
        hinweise=(),
    )
