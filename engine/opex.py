"""
Berechnet die Betriebskosten-Zeitreihe aus den globalen Standard-OPEX-
Positionen plus der projektspezifischen Pacht (wird in pipeline.py bereits
zu einer gemeinsamen Liste zusammengefuehrt und hier uebergeben).
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

        jahre_seit_indexstart = (df["jahr"] - item.indexierung_ab_jahr).clip(lower=0)
        indexierter_betrag = basis_eur * (1 + item.index_pct_pa) ** jahre_seit_indexstart

        df["opex_gesamt_eur"] += aktiv.astype(float) * indexierter_betrag

    return df[OPEX_COLUMNS]
