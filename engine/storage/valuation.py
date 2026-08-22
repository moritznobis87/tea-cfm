"""
Vom Stundendispatch zum Cashflow.

`dispatch.py` optimiert EIN Jahr. Dieses Modul rechnet alle Betriebsjahre
und uebersetzt das Ergebnis in die wenigen Zahlen, die der Cashflow
braucht.

Warum jedes Jahr einzeln
------------------------
Ein Modell ueber 30 Jahre x 8.760 Stunden haette 1,6 Millionen Variablen
und keinen Erkenntnisgewinn: Ein Speicher kann Energie nicht ueber
Jahresgrenzen tragen - seine Kapazitaet reicht fuer Stunden, nicht fuer
Monate. Die Jahre sind damit unabhaengig, und 30 Modelle mit je 52.000
Variablen loesen sich schneller als eines mit 1,6 Millionen.

Was in den Cashflow geht - und was nicht
----------------------------------------
Uebergeben wird ein DELTA, kein absoluter Erloes:

    Wertbeitrag = (PV+Speicher, stundenscharf) - (PV allein, stundenscharf)

Der Grund ist wichtig. Der bestehende Cashflow rechnet den PV-Erloes aus
CAPTURE PRICES - dem Marktwert Solar des Szenarios. Der stundenscharfe
PV-only-Lauf kommt auf einen anderen Wert, weil er mit Stundenpreisen
rechnet und die Abregelung stundenscharf bestimmt. Beide Zahlen sind fuer
sich richtig; sie beantworten verschiedene Fragen.

Wuerde der absolute Wert uebergeben, aenderte das Einschalten eines
Speichers stillschweigend auch die PV-Bewertung - und niemand koennte
mehr sagen, welcher Teil der IRR-Aenderung vom Speicher kommt. Das Delta
haelt beides auseinander: Der bestehende Bewertungsweg bleibt
unangetastet, der Speicher steuert genau seinen Beitrag bei.

Die Abregelungsrueckgewinnung steckt in diesem Delta mit drin: Sie ist
Teil der Differenz beider Laeufe.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..models import BatteryConfig, EffectiveAssumptions
from .dispatch import dispatch_jahr
from .economics import grenzerloes_je_stunde, jahreswert
from .kosten import capex_eur, mit_verschleiss, opex_jahr_eur
from .models import StorageJahreswert


@dataclass(frozen=True)
class SpeicherBeitrag:
    """Was der Speicher dem Cashflow beisteuert.

    Die Reihen sind nach BETRIEBSJAHR indiziert: Index 0 ist Jahr 1.
    """

    #: Zusaetzlicher Erloes je Betriebsjahr in Euro (nominal).
    wertbeitrag_eur_je_jahr: tuple[float, ...]
    #: Investition in Jahr 0.
    capex_eur: float
    #: Feste Betriebskosten je Betriebsjahr.
    opex_eur_je_jahr: tuple[float, ...]
    #: Das ausfuehrliche Jahresergebnis - fuer Anzeige und Auswertung.
    jahreswerte: tuple[StorageJahreswert, ...]
    hinweise: tuple[str, ...]

    @property
    def wertbeitrag_gesamt_eur(self) -> float:
        return float(sum(self.wertbeitrag_eur_je_jahr))

    @property
    def vollzyklen_mittel(self) -> float:
        if not self.jahreswerte:
            return 0.0
        return sum(j.vollzyklen for j in self.jahreswerte) / len(self.jahreswerte)


#: Erste Stunde des 29. Februar: 31 Tage Januar + 28 Tage Februar.
_SCHALTTAG_AB = (31 + 28) * 24
_TAG = 24


def _stundenform(form: Sequence[float], stunden: int) -> np.ndarray:
    """Die Erzeugungsform auf die Stundenzahl DIESES Jahres bringen.

    Ein Schaltjahr hat 8.784 Stunden, die hinterlegte Reihe meist 8.760.
    Eingefuegt wird deshalb EIN TAG an der Stelle des 29. Februar - eine
    Kopie des 28. Februar.

    Warum nicht strecken
    --------------------
    Der naheliegende Weg waere, die Reihe linear auf 8.784 Punkte zu
    interpolieren. Das haelt die Jahressumme und die Jahreszeiten und
    zerstoert trotzdem genau das, worauf es hier ankommt: den TAGESGANG.

    Streckt man 8.760 auf 8.784, verschiebt sich jede Stunde gegenueber
    ihrer Tageszeit um 8.784/8.760, und die Verschiebung summiert sich
    ueber das Jahr auf volle 24 Stunden. Ab der Jahresmitte "scheint die
    Sonne" in der gestreckten Reihe also mitten in der Nacht der
    Preisreihe. Fuer den Cashflow einer PV-Anlage faellt das kaum auf -
    die Jahresmenge stimmt. Fuer einen Speicher ist es fatal: Sein
    ganzer Wert entsteht aus dem Zusammenspiel von Erzeugung und Preis
    INNERHALB eines Tages.

    Gemessen an einem echten Lauf: Mit Streckung brach der Wertbeitrag
    der Schaltjahre auf gut die Haelfte der Nachbarjahre ein (130 statt
    248 Tsd. EUR, 196 statt 265 Vollzyklen), obwohl der Preisspread
    dieser Jahre unveraendert war. Mit eingefuegtem Tag liegen sie in
    der Reihe ihrer Nachbarn.

    Die Kopie des Vortages ist eine Annahme, aber eine kleine und
    offensichtliche: Sie betrifft einen von 366 Tagen und haelt jede
    andere Stunde des Jahres exakt an ihrem Platz.
    """
    werte = np.asarray(form, dtype=float)
    if len(werte) == stunden:
        return werte
    if stunden == len(werte) + _TAG:
        return np.concatenate([
            werte[:_SCHALTTAG_AB],
            werte[_SCHALTTAG_AB - _TAG:_SCHALTTAG_AB],
            werte[_SCHALTTAG_AB:],
        ])
    if stunden == len(werte) - _TAG:
        return np.concatenate([
            werte[:_SCHALTTAG_AB], werte[_SCHALTTAG_AB + _TAG:]
        ])
    # Weder Normal- noch Schaltjahr: eine Reihe, die nicht zu einem
    # Kalenderjahr passt. Dann bleibt nur das Strecken - mit allen oben
    # beschriebenen Nachteilen, aber besser als ein Abbruch.
    ziel = np.linspace(0, len(werte) - 1, stunden)
    return np.interp(ziel, np.arange(len(werte)), werte)


@dataclass(frozen=True)
class Jahreseingabe:
    """Was der Optimierer fuer EIN Betriebsjahr braucht.

    Eigenes Objekt, weil es zwei Aufrufer gibt: den Mehrjahreslauf und
    die Oberflaeche, die ein einzelnes Jahr nachrechnet, um seine
    Stundenbahn zu zeichnen. Beide muessen dieselben Zahlen sehen - eine
    zweite Herleitung derselben Eingaben waere eine zweite Wahrheit, und
    ein Diagramm, das etwas anderes zeigt als der Cashflow rechnet, ist
    schlimmer als kein Diagramm.
    """

    jahr: int
    kalenderjahr: int
    #: PV-Erzeugung je Stunde in MW, VOR der Abregelung.
    pv_mw: np.ndarray
    #: Day-Ahead-Preise je Stunde, nominal.
    preise_eur_mwh: np.ndarray
    #: Erloes einer zusaetzlich verschobenen MWh in dieser Stunde.
    grenzerloes_eur_mwh: np.ndarray
    export_limit_mw: float


def jahreseingabe(
    assumptions: EffectiveAssumptions,
    *,
    energy: pd.DataFrame,
    revenue: pd.DataFrame,
    preise_je_jahr: dict[int, tuple[float, ...]],
    form: Sequence[float],
    i: int,
    foerderdauer_anteil: Sequence[float] | None = None,
) -> Jahreseingabe | None:
    """Die Eingaben des i-ten Betriebsjahres - None ohne Preisreihe."""
    jahr = int(energy["jahr"].to_numpy()[i])
    kalenderjahr = assumptions.inbetriebnahme_jahr + jahr - 1
    preise_real = preise_je_jahr.get(kalenderjahr)
    if preise_real is None:
        preise_real = _naechstes_jahr(preise_je_jahr, kalenderjahr)
    if preise_real is None:
        return None

    stunden = len(preise_real)
    # Nominal wie im uebrigen Modell: Die Aurora-Reihen sind reale
    # Preise auf der Preisbasis des Szenarios (siehe revenue.py).
    faktor = (1 + assumptions.marktpreis_inflation_pct_pa) ** (
        kalenderjahr - assumptions.marktpreis_inflation_basisjahr
    )
    preise = np.asarray(preise_real, dtype=float) * faktor

    zeile = energy.iloc[i]
    menge_mwh = (
        float(zeile["produktion_kwh"]) + float(zeile.get("kappung_kwh", 0.0))
    ) / 1000.0
    form_jahr = _stundenform(form, stunden)
    summe = form_jahr.sum()
    pv = form_jahr / summe * menge_mwh if summe > 0 else np.zeros(stunden)

    referenz = float(revenue.iloc[i]["marktwert_nominal_ct_kwh"])
    anteil = 1.0 if foerderdauer_anteil is None else float(foerderdauer_anteil[i])
    return Jahreseingabe(
        jahr=jahr,
        kalenderjahr=kalenderjahr,
        pv_mw=pv,
        preise_eur_mwh=preise,
        grenzerloes_eur_mwh=grenzerloes_je_stunde(
            preise, referenz, assumptions, in_foerderdauer=anteil > 0.5
        ),
        export_limit_mw=_exportlimit_mw(assumptions),
    )


def dispatch_mehrjahr(
    assumptions: EffectiveAssumptions,
    batterie: BatteryConfig,
    *,
    energy: pd.DataFrame,
    revenue: pd.DataFrame,
    preise_je_jahr: dict[int, tuple[float, ...]],
    form: Sequence[float],
    foerderdauer_anteil: Sequence[float] | None = None,
    fortschritt: Callable[[int, int], None] | None = None,
) -> SpeicherBeitrag:
    """Optimiert jedes Betriebsjahr und fasst die Ergebnisse zusammen.

    `energy` und `revenue` kommen aus der laufenden Bewertung - dieselbe
    Quelle wie der uebrige Cashflow. Damit wird die Jahresmenge, die
    Degradation, das Anlaufjahr und der Referenzmarktwert nicht ein
    zweites Mal hergeleitet.

    Die PV-Reihe des Dispatch ist die Erzeugung VOR der Abregelung
    (`produktion_kwh + kappung_kwh`): Ueber die Abregelung entscheidet
    der Optimierer selbst anhand des Exportlimits. Waere sie schon
    abgezogen, zaehlte sie doppelt.
    """
    # Der Verschleisssatz wird HIER aufgeloest, einmal fuer den ganzen
    # Lauf: Er ist eine Marktannahme (Zellpreis je Zyklus) und keine
    # Eigenschaft der Auslegung. Siehe kosten.mit_verschleiss.
    batterie = mit_verschleiss(batterie, assumptions)

    jahre = [int(j) for j in energy["jahr"].to_numpy()]
    wertbeitrag: list[float] = []
    jahreswerte: list[StorageJahreswert] = []
    hinweise: list[str] = []

    for i, jahr in enumerate(jahre):
        eingabe = jahreseingabe(
            assumptions, energy=energy, revenue=revenue,
            preise_je_jahr=preise_je_jahr, form=form, i=i,
            foerderdauer_anteil=foerderdauer_anteil,
        )
        if eingabe is None:
            hinweise.append(
                f"Fuer {assumptions.inbetriebnahme_jahr + jahr - 1} liegt "
                "keine Stundenpreisreihe vor - das Jahr bleibt ohne "
                "Speicherbeitrag."
            )
            wertbeitrag.append(0.0)
            continue

        ergebnis = dispatch_jahr(
            eingabe.pv_mw, eingabe.preise_eur_mwh, eingabe.grenzerloes_eur_mwh,
            batterie, eingabe.export_limit_mw,
            jahr=jahr, kalenderjahr=eingabe.kalenderjahr,
        )
        wertbeitrag.append(ergebnis.wertbeitrag_eur)
        jahreswerte.append(
            jahreswert(ergebnis, batterie, ergebnis.abregelung_pv_only_mwh)
        )
        for hinweis in ergebnis.hinweise:
            text = f"Jahr {jahr}: {hinweis}"
            if text not in hinweise:
                hinweise.append(text)
        if fortschritt is not None:
            fortschritt(i + 1, len(jahre))

    return SpeicherBeitrag(
        wertbeitrag_eur_je_jahr=tuple(wertbeitrag),
        capex_eur=capex_eur(batterie, assumptions),
        opex_eur_je_jahr=tuple(
            opex_jahr_eur(batterie, assumptions) for _ in jahre
        ),
        jahreswerte=tuple(jahreswerte),
        hinweise=tuple(hinweise),
    )


def _exportlimit_mw(assumptions: EffectiveAssumptions) -> float:
    """Die Einspeisegrenze am Netzverknuepfungspunkt.

    Bewusst dieselbe Groesse, mit der die Kappung gerechnet wird (siehe
    engine/clipping.py): PV und Speicher teilen sich EINEN Anschluss, und
    zwei Wahrheiten ueber seine Grenze waeren eine zu viel. Ohne
    hinterlegtes Limit gilt die Nennleistung selbst - dann bindet die
    Restriktion nie.
    """
    limit = assumptions.einspeiselimit_pct
    leistung_mw = assumptions.nennleistung_kwp / 1000.0
    return leistung_mw * (limit if limit else 1.0)


def _naechstes_jahr(
    reihen: dict[int, tuple[float, ...]], kalenderjahr: int
) -> tuple[float, ...] | None:
    """Klammerregel wie bei den Jahreskurven: das naechstliegende Jahr.

    Ein Projekt, das ueber das letzte Szenariojahr hinauslaeuft, bekommt
    dessen Reihe. Die Aussage wird dadurch schwaecher, je weiter man sich
    entfernt - aber sie bricht nicht ab.
    """
    if not reihen:
        return None
    naechstes = min(reihen, key=lambda j: abs(j - kalenderjahr))
    return reihen[naechstes]
