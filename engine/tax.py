"""
Berechnet die Steuerlast ueber einen Pauschalsatz auf (Erloese - OPEX -
Zinsen) - bewusst identisch zur vereinfachten Excel-Logik.

Keine AfA, kein Verlustvortrag, keine getrennte Gewerbe-/Koerperschafts-
steuer in Phase 1 - das war eine der in der Excel-Analyse benannten
Unklarheiten und wird erst nach fachlicher Klaerung erweitert.
"""

from __future__ import annotations

import pandas as pd

from .models import TaxAssumptions

TAX_COLUMNS = ["jahr", "steuer_eur"]


def calculate_tax(
    revenue: pd.DataFrame,
    opex: pd.DataFrame,
    financing: pd.DataFrame,
    tax: TaxAssumptions,
) -> pd.DataFrame:
    bemessungsgrundlage = (
        revenue["erloes_eur"].to_numpy()
        - opex["opex_gesamt_eur"].to_numpy()
        - financing["zinsen_eur"].to_numpy()
    )

    df = pd.DataFrame({"jahr": revenue["jahr"]})
    df["steuer_eur"] = bemessungsgrundlage * tax.steuersatz_pauschal_pct

    return df[TAX_COLUMNS]
