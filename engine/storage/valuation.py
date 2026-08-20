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


def _stundenform(form: Sequence[float], stunden: int) -> np.ndarray:
    """Die Erzeugungsform auf die Stundenzahl DIESES Jahres bringen.

    Ein Schaltjahr hat 8.784 Stunden, die hinterlegte Reihe meist 8.760.
    Gestreckt statt abgeschnitten: Ein abgeschnittener Dezember verschoebe
    die Jahresmenge in den Sommer.
    """
    werte = np.asarray(form, dtype=float)
    if len(werte) == stunden:
        return werte
    ziel = np.linspace(0, len(werte) - 1, stunden)
    return np.interp(ziel, np.arange(len(werte)), werte)


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
    export_limit_mw = _exportlimit_mw(assumptions)
    jahre = [int(j) for j in energy["jahr"].to_numpy()]
    wertbeitrag: list[float] = []
    jahreswerte: list[StorageJahreswert] = []
    hinweise: list[str] = []

    for i, jahr in enumerate(jahre):
        kalenderjahr = assumptions.inbetriebnahme_jahr + jahr - 1
        preise_real = preise_je_jahr.get(kalenderjahr)
        if preise_real is None:
            preise_real = _naechstes_jahr(preise_je_jahr, kalenderjahr)
        if preise_real is None:
            hinweise.append(
                f"Fuer {kalenderjahr} liegt keine Stundenpreisreihe vor - "
                "das Jahr bleibt ohne Speicherbeitrag."
            )
            wertbeitrag.append(0.0)
            continue

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
        grenzerloes = grenzerloes_je_stunde(
            preise, referenz, assumptions, in_foerderdauer=anteil > 0.5
        )

        ergebnis = dispatch_jahr(
            pv, preise, grenzerloes, batterie, export_limit_mw,
            jahr=jahr, kalenderjahr=kalenderjahr,
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
        capex_eur=batterie.capex_gesamt_eur,
        opex_eur_je_jahr=tuple(batterie.opex_jahr_eur for _ in jahre),
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
