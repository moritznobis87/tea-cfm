"""
Berechnet Kennzahlen aus der vollstaendigen Cashflow-Zeitreihe.

Equity-IRR wird als echtes XIRR auf Kalenderdaten berechnet (nicht nur
auf Jahresindizes) - das entspricht der Excel-Formel `=XIRR(...)` und ist
wichtig, sobald Projekte nicht exakt am 1. Januar in Betrieb gehen.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from .cashflow import CashflowTimeseries
from .models import KPIs


def _xnpv(rate: float, cashflows: list[float], dates: list[date]) -> float:
    d0 = dates[0]
    return sum(
        cf / (1 + rate) ** ((d - d0).days / 365.0) for cf, d in zip(cashflows, dates)
    )


def _xirr(cashflows: list[float], dates: list[date]) -> float | None:
    if not any(cf < 0 for cf in cashflows) or not any(cf > 0 for cf in cashflows):
        # Kein Vorzeichenwechsel -> IRR nicht definiert.
        return None
    try:
        return brentq(lambda r: _xnpv(r, cashflows, dates), -0.99, 10.0)
    except ValueError:
        # Kein Vorzeichenwechsel innerhalb des Suchintervalls gefunden.
        return None


def calculate_kpis(
    cashflow: CashflowTimeseries, diskontsatz_pct: float = 0.05
) -> KPIs:
    df = cashflow.data
    cashflows = df["cf_gesamt_eur"].tolist()
    dates = df["datum"].tolist()

    equity_irr = _xirr(cashflows, dates)
    npv_eur = _xnpv(diskontsatz_pct, cashflows, dates)

    kumuliert = df["cf_kumuliert_eur"].to_numpy()
    positive_jahre = df["jahr"].to_numpy()[kumuliert >= 0]
    payback_jahre = float(positive_jahre[0]) if len(positive_jahre) > 0 else None

    capex_total_eur = float(-df.loc[df["jahr"] == 0, "cf_invest_eur"].iloc[0])

    dscr_werte = df["dscr"].dropna()
    dscr_min = float(dscr_werte.min()) if len(dscr_werte) > 0 else None

    return KPIs(
        equity_irr=equity_irr,
        npv_eur=float(npv_eur),
        payback_jahre=payback_jahre,
        capex_total_eur=capex_total_eur,
        dscr_min=dscr_min,
    )


def calculate_npv_curve(
    cashflow: CashflowTimeseries, diskontsaetze_pct: list[float] | None = None
) -> pd.DataFrame:
    """NPV fuer eine Reihe von Diskontsaetzen (Default: 0%-10% in 0,5%-
    Schritten, 21 Punkte) - fuer die NPV-Kurve/-Tabelle in der UI."""
    if diskontsaetze_pct is None:
        diskontsaetze_pct = [round(i * 0.005, 4) for i in range(0, 21)]

    df = cashflow.data
    cashflows = df["cf_gesamt_eur"].tolist()
    dates = df["datum"].tolist()

    rows = [
        {"diskontsatz_pct": rate, "npv_eur": _xnpv(rate, cashflows, dates)}
        for rate in diskontsaetze_pct
    ]
    return pd.DataFrame(rows)
