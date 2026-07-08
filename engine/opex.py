"""
Berechnet die Betriebskosten-Zeitreihe aus einer beliebig langen Liste von
Kostenpositionen (statt Excels starrer 9-Zeilen-Tabelle).

Bekannte MVP-Vereinfachung: Die im Excel-Original enthaltene Position
"Rueckbaukosten & Avalgebuehren" folgt einer abweichenden Formel (Kosten
pro kWh statt pro kWp, plus ein einmaliger Betrag im letzten Betriebsjahr)
und ist in Phase 1 bewusst NICHT als OpexItem abbildbar - das erfordert
einen eigenen Kostentyp und wird in Phase 2 ergaenzt.
"""

from __future__ import annotations

import pandas as pd

from .models import OpexItem

OPEX_COLUMNS = ["jahr", "opex_gesamt_eur"]


def calculate_opex(
    timeline: pd.DataFrame, opex_items: list[OpexItem], nennleistung_kwp: float
) -> pd.DataFrame:
    df = timeline[["jahr"]].copy()
    df["opex_gesamt_eur"] = 0.0

    for item in opex_items:
        basis_eur = item.basiswert_eur_kwp * nennleistung_kwp
        aktiv = df["jahr"] >= item.start_betriebsjahr
        if item.end_betriebsjahr is not None:
            aktiv &= df["jahr"] <= item.end_betriebsjahr

        jahre_seit_start = (df["jahr"] - item.start_betriebsjahr).clip(lower=0)
        indexierter_betrag = basis_eur * (1 + item.index_pct_pa) ** jahre_seit_start

        df["opex_gesamt_eur"] += aktiv.astype(float) * indexierter_betrag

    return df[OPEX_COLUMNS]
