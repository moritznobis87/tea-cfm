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

#: produktion_kwh ist die Menge NACH der Einspeisegrenze - alles
#: Nachgelagerte (Erloese, Abgaben, Kennzahlen) rechnet damit richtig,
#: ohne die Kappung kennen zu muessen. kappung_kwh haelt daneben fest,
#: was sie gekostet hat; ohne Stundenreihe ist die Spalte null.
ENERGY_COLUMNS = ["jahr", "degradationsfaktor", "produktion_kwh", "kappung_kwh"]
ENERGY_MONTH_COLUMNS = [
    "jahr", "monat", "kalenderjahr", "degradationsfaktor", "produktion_kwh",
    "kappung_kwh",
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


def aktive_monate(periode) -> tuple[int, int]:
    """Erster und letzter Betriebsmonat einer Periode (1-12, einschliesslich).

    Jede Periode liegt vollstaendig in EINEM Kalenderjahr (siehe
    engine/timeline.py), also genuegen Start- und Endmonat ihrer Daten.
    Damit ist sowohl das Anlaufjahr (Monat m0 bis 12) als auch das
    Schlussjahr (Monat 1 bis m0-1) erfasst, ohne dass dieses Modul die
    Laufzeitlogik kennen muss.
    """
    return periode["datum_start"].month, periode["datum_ende"].month


def kurvenanteil(periode, kurve: np.ndarray) -> float:
    """Anteil der Jahreserzeugung, der in dieser Periode anfaellt."""
    von, bis = aktive_monate(periode)
    return float(kurve[von - 1:bis].sum())


def _jahresmenge_kwh(assumptions: EffectiveAssumptions, jahr: pd.Series) -> pd.Series:
    """Volle Jahresmenge je Betriebsjahr - ohne Anlaufjahr-Kuerzung."""
    basis = assumptions.nennleistung_kwp * assumptions.vollbenutzungsstunden_kwh_kwp
    degradation = (1 - assumptions.degradation_pct_pa) ** (jahr - 1)
    return basis * degradation * (1 - assumptions.sicherheitsabschlag_pct)


def kappung_je_jahr(assumptions: EffectiveAssumptions, jahr: int):
    """Wirkung der Einspeisegrenze in einem Betriebsjahr, oder None.

    None, sobald eine der drei Voraussetzungen fehlt: eine Grenze, eine
    Stundenreihe, oder ein Ertrag. Die Kappung ist eine Verfeinerung -
    ohne Stundenreihe rechnet das Projekt wie bisher weiter, statt mit
    einer geratenen Zahl.

    **Warum je Jahr und nicht einmal.** Die Grenze steht fest, die
    Anlage degradiert. Ihre Spitzenleistung sinkt also Jahr fuer Jahr
    auf die Grenze zu und faellt irgendwann darunter - ab da kostet die
    Begrenzung nichts mehr. Fuer ein Projekt mit 73,3 % Spitzenleistung
    und 0,25 % Degradation ist das im Jahr 20 der Fall; wer stattdessen
    den Verlust des ersten Jahres ueber die ganze Laufzeit fortschreibt,
    verdreifacht ihn.
    """
    from .clipping import kappungsverlust

    limit = assumptions.einspeiselimit_pct
    reihe = assumptions.lastgang_reihe
    if limit is None or not reihe:
        return None

    # Die Reihe skaliert mit dem Ertrag des Jahres, die Grenze nicht.
    # Beides steckt in den effektiven Vollbenutzungsstunden - die
    # Nennleistung kuerzt sich heraus (siehe engine/clipping.py).
    wirksam = (
        assumptions.vollbenutzungsstunden_kwh_kwp
        * (1 - assumptions.degradation_pct_pa) ** (jahr - 1)
        * (1 - assumptions.sicherheitsabschlag_pct)
    )
    if wirksam <= 0:
        return None
    return kappungsverlust(list(reihe), limit, wirksam)


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

    zeilen = []
    for _, periode in timeline.iterrows():
        jahr = int(periode["jahr"])
        kalenderjahr = assumptions.inbetriebnahme_jahr + jahr - 1
        jahresmenge = float(_jahresmenge_kwh(assumptions, pd.Series([jahr])).iloc[0])
        degradation = float(
            (1 - assumptions.degradation_pct_pa) ** (jahr - 1)
        )
        von, bis = aktive_monate(periode)
        # Die Einspeisegrenze wirkt je Monat verschieden - sie trifft nur
        # die Mittagsstunden des Sommerhalbjahrs. Ein Jahresmittel
        # verteilte den Verlust auf den Dezember mit, wo er nie entsteht.
        kappung = kappung_je_jahr(assumptions, jahr)
        for monat in range(1, 13):
            aktiv = von <= monat <= bis
            menge = jahresmenge * kurve[monat - 1] if aktiv else 0.0
            gekappt = (
                menge * kappung.verlust_pct_je_monat[monat - 1]
                if kappung is not None else 0.0
            )
            zeilen.append(
                {
                    "jahr": jahr,
                    "monat": monat,
                    "kalenderjahr": kalenderjahr,
                    "degradationsfaktor": degradation,
                    "produktion_kwh": menge - gekappt,
                    "kappung_kwh": gekappt,
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
                 produktion_kwh=("produktion_kwh", "sum"),
                 kappung_kwh=("kappung_kwh", "sum"))
        )
        return df[ENERGY_COLUMNS]

    df = timeline[["jahr", "pro_rata_faktor"]].copy()
    df["degradationsfaktor"] = (1 - assumptions.degradation_pct_pa) ** (
        df["jahr"] - 1
    )
    # Rumpfjahre folgen der Einspeisekurve, nicht dem Tagesanteil: Eine im
    # Dezember in Betrieb gegangene Anlage hat 8,5 % des Jahres hinter
    # sich, aber nur rund 5 % der Jahreserzeugung - der Dezember ist der
    # schwaechste Monat. Umgekehrt liefert eine Julianlage mehr als die
    # Haelfte. Der Tagesanteil kann das nicht wissen; er stand hier,
    # solange es die Kurve noch nicht gab.
    #
    # Das betrifft ANLAUF- und SCHLUSSJAHR: Bei unterjaehriger
    # Inbetriebnahme laeuft die Achse ein Kalenderjahr laenger, und das
    # letzte deckt die Monate ab, die im ersten fehlten.
    kurve = einspeisekurve(assumptions)
    anteil = np.array(
        [kurvenanteil(periode, kurve) for _, periode in timeline.iterrows()]
    )
    ungekappt = _jahresmenge_kwh(assumptions, df["jahr"]) * anteil

    # Auch die Jahresrechnung kappt monatsweise und summiert erst danach:
    # Ein Jahresmittel des Verlusts waere nicht dasselbe, weil die
    # Erzeugung ueber das Jahr so ungleich verteilt ist wie der Verlust.
    # In Anlauf- und Schlussjahr zaehlen zudem nur die aktiven Monate.
    kurve = einspeisekurve(assumptions)
    verluste = []
    for (_, periode), menge in zip(timeline.iterrows(), ungekappt, strict=True):
        kappung = kappung_je_jahr(assumptions, int(periode["jahr"]))
        if kappung is None:
            verluste.append(0.0)
            continue
        von, bis = aktive_monate(periode)
        aktiv = kurve[von - 1:bis]
        anteil_aktiv = float(aktiv.sum())
        if anteil_aktiv <= 0:
            verluste.append(0.0)
            continue
        # Gewicht der Monate innerhalb der aktiven Zeit, damit der
        # Verlust die Verteilung genau dieser Monate trifft.
        gewichtet = sum(
            float(aktiv[i]) / anteil_aktiv
            * kappung.verlust_pct_je_monat[von - 1 + i]
            for i in range(len(aktiv))
        )
        verluste.append(menge * gewichtet)

    df["kappung_kwh"] = verluste
    df["produktion_kwh"] = ungekappt - df["kappung_kwh"]

    return df[ENERGY_COLUMNS]
