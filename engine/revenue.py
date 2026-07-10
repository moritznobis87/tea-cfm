"""
Berechnet die Erloes-Zeitreihe nach dem oesterreichischen EAG-
Marktpraemien-Mechanismus (gleitende Marktpraemie):

- Solange die EAG-Foerderdauer laeuft: Verguetung = MAX(Marktwert Solar,
  EAG-Zuschlagswert). Liegt der Marktwert unter dem Zuschlagswert, wird die
  Differenz als Praemie zugeschossen; liegt er darueber, erhaelt der
  Betreiber den (hoeheren) Marktwert.
- Nach Ablauf der Foerderdauer: reiner Marktpreisverkauf zum Marktwert
  Solar (keine Praemie mehr).
- In Stunden mit negativen Strompreisen entfaellt die Foerderung
  vollstaendig (anteil_negativer_stunden_pct_je_jahr reduziert die
  verguetete Produktionsmenge) - das ist eine gesetzliche Regelung, keine
  Vereinfachung.
"""

from __future__ import annotations

import pandas as pd

from .models import EffectiveAssumptions

REVENUE_COLUMNS = ["jahr", "verguetungssatz_ct_kwh", "erloes_eur"]


def calculate_revenue(
    timeline: pd.DataFrame, energy: pd.DataFrame, assumptions: EffectiveAssumptions
) -> pd.DataFrame:
    df = timeline[["jahr"]].copy()

    marktwert = df["jahr"].map(assumptions.marktwert_solar_ct_kwh_je_jahr)
    if marktwert.isna().any():
        letzter_bekannter_wert = (
            pd.Series(assumptions.marktwert_solar_ct_kwh_je_jahr)
            .sort_index()
            .iloc[-1]
            if assumptions.marktwert_solar_ct_kwh_je_jahr
            else 0.0
        )
        marktwert = marktwert.fillna(letzter_bekannter_wert)

    innerhalb_foerderdauer = df["jahr"] <= assumptions.eag_foerderdauer_jahre
    praemie = (assumptions.eag_zuschlagswert_effektiv_ct_kwh - marktwert).clip(
        lower=0
    )
    satz_ct_kwh = marktwert + innerhalb_foerderdauer.astype(float) * praemie

    df["verguetungssatz_ct_kwh"] = satz_ct_kwh

    anteil_negativ = (
        df["jahr"].map(assumptions.anteil_negativer_stunden_pct_je_jahr).fillna(0.0)
    )
    verguetete_produktion_kwh = energy["produktion_kwh"].to_numpy() * (
        1 - anteil_negativ.to_numpy()
    )

    df["erloes_eur"] = verguetete_produktion_kwh * satz_ct_kwh.to_numpy() / 100.0

    return df[REVENUE_COLUMNS]
