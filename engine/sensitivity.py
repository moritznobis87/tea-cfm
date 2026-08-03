"""
Automatische Sensitivitaetsanalyse des EAG-Zuschlagswertes.

Ruft run_valuation() wiederholt mit variiertem Zuschlagswert auf - kennt
dadurch nichts von den internen Berechnungsmodulen und bleibt auch bei
spaeteren Aenderungen an der Cashflow-Engine automatisch konsistent.
"""

from __future__ import annotations

import pandas as pd

from .models import GlobalAssumptions, PVProject

#: Abweichungen vom gebotenen Zuschlagswert. Bewusst eng gefasst
#: (2,5 % und 5 %): In einer Ausschreibungsrunde bewegt sich der
#: Zuschlagswert um wenige Zehntel Cent - eine Variation um 10 % traf
#: keine Entscheidung mehr, die tatsaechlich zur Wahl stand.
DEFAULT_VARIANTEN_PCT = [0.05, 0.025, 0.0, -0.025, -0.05]


def variantenname(delta_pct: float) -> str:
    """Beschriftung einer Variante, z.B. "+2,5 %" oder "Basis".

    Eine Nachkommastelle, aber nur wenn sie etwas beitraegt - "+5,0 %"
    neben "+2,5 %" liest sich wie eine Genauigkeit, die die Zahl nicht
    hat.
    """
    if delta_pct == 0:
        return "Basis"
    text = f"{delta_pct * 100:+.1f}".replace(".0", "").replace(".", ",")
    return f"{text} %"


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
                "variante": variantenname(delta_pct),
                "delta_pct": delta_pct,
                "eag_zuschlagswert_ct_kwh": variante.eag_zuschlagswert_ct_kwh,
                "equity_irr": result.kpis.equity_irr,
                "npv_eur": result.kpis.npv_eur,
            }
        )

    return pd.DataFrame(rows)
