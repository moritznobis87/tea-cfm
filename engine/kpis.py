"""
Berechnet Kennzahlen aus der vollstaendigen Cashflow-Zeitreihe.

Equity-IRR wird als echtes XIRR auf Kalenderdaten berechnet (nicht nur
auf Jahresindizes) - das entspricht der Excel-Formel `=XIRR(...)` und ist
wichtig, sobald Projekte nicht exakt am 1. Januar in Betrieb gehen.

Robustheit der IRR-Suche: brentq benoetigt einen Vorzeichenwechsel der
XNPV-Funktion innerhalb des Suchintervalls. Da extrem gute Projekte eine
IRR > 1000% theoretisch nicht ausschliessen (und extrem schlechte nahe
-100% liegen), wird das Intervall bei Bedarf schrittweise erweitert,
statt sofort `None` zu liefern.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
from scipy.optimize import brentq

from .cashflow import CashflowTimeseries
from .models import KPIs

#: Obergrenzen des IRR-Suchintervalls, die nacheinander probiert werden.
_IRR_SUCHGRENZEN_OBEN = (10.0, 100.0, 1000.0)
_IRR_SUCHGRENZE_UNTEN = -0.9999


def _xnpv(rate: float, cashflows: list[float], dates: list[date]) -> float:
    """Excel-kompatibles XNPV: Diskontierung auf Tagesbasis (Act/365)."""
    d0 = dates[0]
    return sum(
        cf / (1 + rate) ** ((d - d0).days / 365.0) for cf, d in zip(cashflows, dates, strict=True)
    )


def _xirr(cashflows: list[float], dates: list[date]) -> float | None:
    if not any(cf < 0 for cf in cashflows) or not any(cf > 0 for cf in cashflows):
        # Kein Vorzeichenwechsel im Cashflow -> IRR nicht definiert.
        return None
    for obergrenze in _IRR_SUCHGRENZEN_OBEN:
        try:
            return brentq(
                lambda r: _xnpv(r, cashflows, dates),
                _IRR_SUCHGRENZE_UNTEN,
                obergrenze,
            )
        except ValueError:
            # Kein Vorzeichenwechsel der XNPV-Funktion in diesem Intervall -
            # naechstgroesseres Intervall probieren.
            continue
    return None


def calculate_kpis(
    cashflow: CashflowTimeseries, diskontsatz_pct: float = 0.08
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
    # Eigenkapitaleinsatz = tatsaechlicher Mittelabfluss im Jahr 0
    # (CAPEX abzueglich Kreditaufnahme).
    eigenkapital_eur = float(-df.loc[df["jahr"] == 0, "cf_gesamt_eur"].iloc[0])

    dscr_werte = df["dscr"].dropna()
    dscr_min = float(dscr_werte.min()) if len(dscr_werte) > 0 else None

    return KPIs(
        equity_irr=equity_irr,
        npv_eur=float(npv_eur),
        payback_jahre=payback_jahre,
        capex_total_eur=capex_total_eur,
        eigenkapital_eur=eigenkapital_eur,
        dscr_min=dscr_min,
    )


def npv_at(cashflow: CashflowTimeseries, diskontsatz_pct: float) -> float:
    """Exakter NPV (XNPV, Act/365) fuer einen beliebigen Diskontsatz.

    Fuer die UI-Einstellung "NPV bei x %": kein Interpolieren zwischen
    Kurvenpunkten noetig - der Wert wird direkt aus der Cashflow-Zeitreihe
    berechnet (identische Formel wie fuer die NPV-Kurve).
    """
    df = cashflow.data
    return float(
        _xnpv(diskontsatz_pct, df["cf_gesamt_eur"].tolist(), df["datum"].tolist())
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
