"""
Berechnet die Erloes-Zeitreihe aus Produktion und Verguetungssatz.

Phase 1 deckt EEG_FIXED und PPA ab (konstanter Satz ueber die gesamte
Vertragslaufzeit, keine Indexierung - das entspricht dem im Excel-Original
beobachteten Verhalten fuer die EEG-Verguetung, die ueber die gesamte
Laufzeit flach bei 4,99 ct/kWh blieb).

MARKET_BEST_GUESS (zentrale Marktpreiskurve) sowie die "Goldenes Ende"-
Anschlussvermarktung nach Ablauf der Vertragslaufzeit sind bewusst NICHT
Teil von Phase 1 - die genaue Formel dafuer war in der Excel-Analyse als
Unklarheit markiert und wird erst nach Klaerung ergaenzt.
"""

from __future__ import annotations

import pandas as pd

from .models import RevenueAssumptions, TariffType

REVENUE_COLUMNS = ["jahr", "verguetungssatz_ct_kwh", "erloes_eur"]


def calculate_revenue(
    timeline: pd.DataFrame, energy: pd.DataFrame, revenue: RevenueAssumptions
) -> pd.DataFrame:
    if revenue.tariff_type == TariffType.EEG_FIXED:
        satz_ct_kwh = revenue.eeg_satz_ct_kwh
    elif revenue.tariff_type == TariffType.PPA:
        satz_ct_kwh = revenue.ppa_satz_ct_kwh
    else:
        raise NotImplementedError(
            f"tariff_type={revenue.tariff_type} ist erst ab Phase 2 implementiert."
        )

    satz_effektiv = satz_ct_kwh + revenue.direktvermarktung_abschlag_ct_kwh

    df = timeline[["jahr"]].copy()
    df["verguetungssatz_ct_kwh"] = satz_effektiv
    df["erloes_eur"] = energy["produktion_kwh"].to_numpy() * satz_effektiv / 100.0

    return df[REVENUE_COLUMNS]
