"""
Berechnet Zinsen, Tilgung und Darlehensstand ueber ein Annuitaetendarlehen.

Phase 1 deckt nur die Annuitaet ab (eine Tranche, konstante Rate).
Alternative Tilgungsarten (linear, endfaellig) oder mehrere Kredittranchen
sind spaetere Erweiterungen, siehe TilgungsArt-Enum-Platzhalter in der
Architekturnotiz aus der Design-Phase.
"""

from __future__ import annotations

import numpy_financial as npf
import pandas as pd

from .models import FinancingAssumptions

FINANCING_COLUMNS = [
    "jahr",
    "zinsen_eur",
    "tilgung_eur",
    "schuldendienst_eur",
    "darlehensstand_bop_eur",
    "darlehensstand_eop_eur",
]


def calculate_financing(
    timeline: pd.DataFrame,
    investitionsvolumen_eur: float,
    financing: FinancingAssumptions,
) -> pd.DataFrame:
    fremdkapital_eur = investitionsvolumen_eur * (1 - financing.eigenkapitalquote_pct)

    # npf.pmt(rate, nper, pv) liefert bei negativem pv einen positiven
    # Zahlungsbetrag zurueck. Wir arbeiten intern bewusst mit positiven
    # Betraegen (Zinsen, Tilgung, Schuldendienst als "Hoehe", nicht als
    # vorzeichenbehafteter Cashflow) und rechnen das Vorzeichen erst in
    # cashflow.py explizit als Abfluss um.
    annuitaet_eur = npf.pmt(
        financing.fremdkapitalzins_pct,
        financing.kreditlaufzeit_jahre,
        -fremdkapital_eur,
    )

    rows = []
    balance = fremdkapital_eur
    for _, period in timeline.iterrows():
        jahr = int(period["jahr"])
        if jahr <= financing.kreditlaufzeit_jahre:
            zinsen = balance * financing.fremdkapitalzins_pct
            schuldendienst = annuitaet_eur
            tilgung = schuldendienst - zinsen
        else:
            zinsen = 0.0
            schuldendienst = 0.0
            tilgung = 0.0

        balance_eop = max(balance - tilgung, 0.0)
        rows.append(
            {
                "jahr": jahr,
                "zinsen_eur": zinsen,
                "tilgung_eur": tilgung,
                "schuldendienst_eur": schuldendienst,
                "darlehensstand_bop_eur": balance,
                "darlehensstand_eop_eur": balance_eop,
            }
        )
        balance = balance_eop

    return pd.DataFrame(rows, columns=FINANCING_COLUMNS)
