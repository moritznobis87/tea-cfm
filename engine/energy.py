"""
Berechnet die Stromproduktions-Zeitreihe aus Nennleistung,
Vollbenutzungsstunden, Degradation und Sicherheitsabschlag.
"""

from __future__ import annotations

import pandas as pd

from .models import EffectiveAssumptions

ENERGY_COLUMNS = ["jahr", "degradationsfaktor", "produktion_kwh"]


def calculate_energy_production(
    timeline: pd.DataFrame, assumptions: EffectiveAssumptions
) -> pd.DataFrame:
    basis_produktion_kwh = (
        assumptions.nennleistung_kwp * assumptions.vollbenutzungsstunden_kwh_kwp
    )

    df = timeline[["jahr", "pro_rata_faktor"]].copy()
    df["degradationsfaktor"] = (1 - assumptions.degradation_pct_pa) ** (
        df["jahr"] - 1
    )

    produktion_kwh = (
        basis_produktion_kwh * df["degradationsfaktor"] * df["pro_rata_faktor"]
    )
    produktion_kwh = produktion_kwh * (1 - assumptions.sicherheitsabschlag_pct)
    df["produktion_kwh"] = produktion_kwh

    return df[ENERGY_COLUMNS]
