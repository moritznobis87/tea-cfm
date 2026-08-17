"""
Berechnet die Stromproduktions-Zeitreihe aus Nennleistung,
Vollbenutzungsstunden, Degradation und Sicherheitsabschlag.

Zwei Aufloesungen, eine Quelle: `calculate_energy_production_monatlich`
verteilt die Jahresmenge ueber die Einspeisekurve auf zwoelf Monate,
`calculate_energy_production` liefert die Jahresmenge - in der
Monatsaufloesung als Summe eben dieser Monatswerte. Dadurch koennen
Erloesrechnung (monatlich) und Kostenrechnung (jaehrlich) nicht
auseinanderlaufen.

Das Anlaufjahr folgt deshalb in BEIDEN Aufloesungen der
Einspeisekurve: Eine im Dezember angeschlossene Anlage hat 8,5 % des
Jahres hinter sich, erzeugt aber nur rund 5 % der Jahresmenge - der
Dezember ist der schwaechste Monat. Fuer eine Inbetriebnahme im April
liegt es umgekehrt (76 % statt 75 %). Welche Richtung der Fehler hat,
haengt an der Kurve; dass der Tagesanteil die falsche Frage beantwortet,
haengt nicht davon ab.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .models import EffectiveAssumptions, Zeitaufloesung

ENERGY_COLUMNS = ["jahr", "degradationsfaktor", "produktion_kwh"]
ENERGY_MONTH_COLUMNS = [
    "jahr", "monat", "kalenderjahr", "degradationsfaktor", "produktion_kwh",
]


def einspeisekurve(assumptions: EffectiveAssumptions) -> np.ndarray:
    """Die auf 1 normierte Einspeisekurve.

    Normiert wird bewusst hier und nicht bei der Eingabe: Eine Kurve aus
    gerundeten Prozentwerten summiert sich auf 99,8 %, und niemand
    moechte, dass die Jahresmenge deshalb um 0,2 % sinkt.
    """
    kurve = np.array(assumptions.einspeisekurve_pct_je_monat, dtype=float)
    summe = kurve.sum()
    return kurve / summe if summe else kurve


def anlaufjahr_anteil(assumptions: EffectiveAssumptions) -> float:
    """Anteil der Jahreserzeugung, der im Anlaufjahr noch anfaellt.

    Summe der Einspeisekurve ab dem Inbetriebnahmemonat - fuer eine
    Inbetriebnahme im Januar also 1,0. Diese Zahl ist der Unterschied
    zwischen "wie viel Zeit ist vergangen" und "wie viel Strom ist
    entstanden": Im Dezember sind 8,5 % des Jahres vergangen, aber nur
    rund 5 % der Erzeugung angefallen.
    """
    kurve = einspeisekurve(assumptions)
    return float(kurve[assumptions.inbetriebnahme_monat - 1:].sum())


def _jahresmenge_kwh(assumptions: EffectiveAssumptions, jahr: pd.Series) -> pd.Series:
    """Volle Jahresmenge je Betriebsjahr - ohne Anlaufjahr-Kuerzung."""
    basis = assumptions.nennleistung_kwp * assumptions.vollbenutzungsstunden_kwh_kwp
    degradation = (1 - assumptions.degradation_pct_pa) ** (jahr - 1)
    return basis * degradation * (1 - assumptions.sicherheitsabschlag_pct)


def calculate_energy_production_monatlich(
    timeline: pd.DataFrame, assumptions: EffectiveAssumptions
) -> pd.DataFrame:
    """Erzeugung je Betriebsjahr und Monat.

    Die Betriebsjahre folgen dem KALENDERJAHR (siehe timeline.py): Jahr 1
    endet am 31.12. des Inbetriebnahmejahres. Im Anlaufjahr entfallen
    deshalb die Monate vor der Inbetriebnahme - und mit ihnen ihr Anteil
    an der Jahreserzeugung.
    """
    kurve = einspeisekurve(assumptions)
    ibn_monat = assumptions.inbetriebnahme_monat

    zeilen = []
    for jahr in timeline["jahr"]:
        kalenderjahr = assumptions.inbetriebnahme_jahr + int(jahr) - 1
        jahresmenge = float(_jahresmenge_kwh(assumptions, pd.Series([jahr])).iloc[0])
        degradation = float(
            (1 - assumptions.degradation_pct_pa) ** (int(jahr) - 1)
        )
        for monat in range(1, 13):
            aktiv = not (jahr == 1 and monat < ibn_monat)
            zeilen.append(
                {
                    "jahr": int(jahr),
                    "monat": monat,
                    "kalenderjahr": kalenderjahr,
                    "degradationsfaktor": degradation,
                    "produktion_kwh": (
                        jahresmenge * kurve[monat - 1] if aktiv else 0.0
                    ),
                }
            )
    return pd.DataFrame(zeilen, columns=ENERGY_MONTH_COLUMNS)


def calculate_energy_production(
    timeline: pd.DataFrame, assumptions: EffectiveAssumptions
) -> pd.DataFrame:
    """Erzeugung je Betriebsjahr.

    In der Monatsaufloesung ist das die Summe der Monatswerte, sonst die
    bisherige Rechnung mit taggenauem Anlaufjahr-Faktor.
    """
    if assumptions.zeitaufloesung == Zeitaufloesung.MONAT:
        monatlich = calculate_energy_production_monatlich(timeline, assumptions)
        df = (
            monatlich.groupby("jahr", as_index=False)
            .agg(degradationsfaktor=("degradationsfaktor", "first"),
                 produktion_kwh=("produktion_kwh", "sum"))
        )
        return df[ENERGY_COLUMNS]

    df = timeline[["jahr", "pro_rata_faktor"]].copy()
    df["degradationsfaktor"] = (1 - assumptions.degradation_pct_pa) ** (
        df["jahr"] - 1
    )
    # Das Anlaufjahr folgt der Einspeisekurve, nicht dem Tagesanteil:
    # Eine im Dezember in Betrieb gegangene Anlage hat 8,5 % des Jahres
    # hinter sich, aber nur rund 5 % der Jahreserzeugung - der Dezember
    # ist der schwaechste Monat. Umgekehrt liefert eine Julianlage mehr
    # als die Haelfte. Der Tagesanteil kann das nicht wissen; er stand
    # hier, solange es die Kurve noch nicht gab.
    anteil = df["pro_rata_faktor"].to_numpy().astype(float).copy()
    anteil[df["jahr"].to_numpy() == 1] = anlaufjahr_anteil(assumptions)
    df["produktion_kwh"] = _jahresmenge_kwh(assumptions, df["jahr"]) * anteil

    return df[ENERGY_COLUMNS]
