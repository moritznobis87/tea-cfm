"""
Berechnet Zinsen, Tilgung und Darlehensstand ueber ein Kredit mit
Annuitaeten- oder linearer Tilgung, optional mit tilgungsfreiem
Anlaufjahr.

Konventionen:
- Zinsen eines Jahres fallen auf den Jahresanfangsstand an, die Tilgung
  fliesst nachschuessig am Jahresende (Bankenkonvention).
- Tilgungsfreies Anlaufjahr: Im ersten Betriebsjahr werden nur Zinsen
  auf die volle Kreditsumme gezahlt; die Tilgung beginnt in Jahr 2.
  Die ANZAHL der Tilgungsraten bleibt `kreditlaufzeit_jahre` - der
  Schuldendienst verlaengert sich also insgesamt um ein Jahr. Weil das
  erste Jahr ungetilgt bleibt, faellt auch im zweiten Jahr der Zins noch
  auf die volle Kreditsumme an (Jahresanfangsstand).
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
    tilgungsfreies_anlaufjahr: bool = False,
) -> pd.DataFrame:
    fremdkapital_eur = investitionsvolumen_eur * (1 - eigenkapitalquote_pct)

    # Erstes und letztes Jahr mit Tilgungsrate. Die Annuitaet/lineare Rate
    # wird unveraendert ueber `kreditlaufzeit_jahre` Raten berechnet - das
    # Anlaufjahr verschiebt den Ratenplan nur um ein Jahr nach hinten.
    erstes_tilgungsjahr = 2 if tilgungsfreies_anlaufjahr else 1
    letztes_schuldendienstjahr = kreditlaufzeit_jahre + (
        1 if tilgungsfreies_anlaufjahr else 0
    )

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
        if jahr <= letztes_schuldendienstjahr:
            zinsen = balance * fremdkapitalzins_pct
            if jahr < erstes_tilgungsjahr:
                # Tilgungsfreies Anlaufjahr: nur Zinsen.
                tilgung = 0.0
            elif tilgungsart == TilgungsArt.ANNUITAET:
                tilgung = annuitaet_eur - zinsen
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
