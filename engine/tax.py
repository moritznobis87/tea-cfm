"""
Berechnet die Steuerlast - Pauschalsatz auf EBT oder AfA-basierte
Koerperschaftsteuer mit Freibetrag (siehe TaxModus in models.py).
"""

from __future__ import annotations

import pandas as pd

from .models import TaxModus

TAX_COLUMNS = ["jahr", "steuer_eur"]


def calculate_tax(
    revenue: pd.DataFrame,
    opex: pd.DataFrame,
    financing: pd.DataFrame,
    capex_total_eur: float,
    tax_modus: TaxModus,
    steuersatz_pct: float,
    afa_nutzungsdauer_jahre: int | None,
    freibetrag_eur: float,
) -> pd.DataFrame:
    df = pd.DataFrame({"jahr": revenue["jahr"]})

    ebt_vor_afa = (
        revenue["erloes_eur"].to_numpy()
        - opex["opex_gesamt_eur"].to_numpy()
        - financing["zinsen_eur"].to_numpy()
    )

    if tax_modus == TaxModus.PAUSCHAL_AUF_EBT:
        df["steuer_eur"] = ebt_vor_afa * steuersatz_pct
    else:
        afa_eur = capex_total_eur / afa_nutzungsdauer_jahre
        ebt = ebt_vor_afa - afa_eur - freibetrag_eur
        df["steuer_eur"] = ebt.clip(min=0) * steuersatz_pct

    return df[TAX_COLUMNS]
