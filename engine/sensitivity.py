"""
Automatische Sensitivitaetsanalyse des EAG-Zuschlagswertes.

Ruft run_valuation() wiederholt mit variiertem Zuschlagswert auf - kennt
dadurch nichts von den internen Berechnungsmodulen und bleibt auch bei
spaeteren Aenderungen an der Cashflow-Engine automatisch konsistent.
"""

from __future__ import annotations

import pandas as pd

from .models import GlobalAssumptions, PVProject

DEFAULT_VARIANTEN_PCT = [0.10, 0.05, 0.0, -0.05, -0.10]


def run_eag_sensitivity(
    project: PVProject,
    global_assumptions: GlobalAssumptions,
    varianten_pct: list[float] | None = None,
) -> pd.DataFrame:
    # Lokaler Import, um einen Zirkelbezug pipeline.py <-> sensitivity.py
    # zu vermeiden (pipeline.py importiert diese Funktion nicht).
    from .pipeline import run_valuation

    if varianten_pct is None:
        varianten_pct = DEFAULT_VARIANTEN_PCT

    rows = []
    for delta_pct in varianten_pct:
        variante = project.model_copy(deep=True)
        variante.eag_zuschlagswert_ct_kwh = project.eag_zuschlagswert_ct_kwh * (
            1 + delta_pct
        )
        result = run_valuation(variante, global_assumptions)
        rows.append(
            {
                "variante": f"{delta_pct:+.0%}" if delta_pct != 0 else "Basis",
                "delta_pct": delta_pct,
                "eag_zuschlagswert_ct_kwh": variante.eag_zuschlagswert_ct_kwh,
                "equity_irr": result.kpis.equity_irr,
                "npv_eur": result.kpis.npv_eur,
            }
        )

    return pd.DataFrame(rows)
