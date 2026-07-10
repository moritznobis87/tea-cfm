"""
Berechnet Zinsen, Tilgung und Darlehensstand ueber ein Kredit mit
Annuitaeten- oder linearer Tilgung.
"""

from __future__ import annotations

import numpy_financial as npf
import pandas as pd

from .models import TilgungsArt

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
    eigenkapitalquote_pct: float,
    fremdkapitalzins_pct: float,
    kreditlaufzeit_jahre: int,
    tilgungsart: TilgungsArt,
) -> pd.DataFrame:
    fremdkapital_eur = investitionsvolumen_eur * (1 - eigenkapitalquote_pct)

    if tilgungsart == TilgungsArt.ANNUITAET:
        annuitaet_eur = npf.pmt(
            fremdkapitalzins_pct, kreditlaufzeit_jahre, -fremdkapital_eur
        )
    else:
        tilgung_linear_eur = fremdkapital_eur / kreditlaufzeit_jahre

    rows = []
    balance = fremdkapital_eur
    for _, period in timeline.iterrows():
        jahr = int(period["jahr"])
        if jahr <= kreditlaufzeit_jahre:
            zinsen = balance * fremdkapitalzins_pct
            if tilgungsart == TilgungsArt.ANNUITAET:
                schuldendienst = annuitaet_eur
                tilgung = schuldendienst - zinsen
            else:
                tilgung = tilgung_linear_eur
                schuldendienst = tilgung + zinsen
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
