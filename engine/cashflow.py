"""
Fuehrt Erloes-, OPEX-, Finanzierungs- und Steuerzeitreihen zu einer
vollstaendigen Cashflow-Zeitreihe zusammen (operativ, Investition,
Finanzierung, gesamt, kumuliert).

Bewusst die "duennste" Funktion der Kette: keine eigene fachliche
Berechnung mehr, nur noch Aggregation. Fehler in den fachlichen Annahmen
bleiben dadurch auf ein Modul isoliert.

Rueckgabe ist ein dataclass-Wrapper um ein pandas DataFrame (siehe
Designentscheidung: DataFrame fuer Zeitreihen, Pydantic fuer Annahmen-
Objekte). Der Wrapper erzwingt das Spaltenschema und traegt Metadaten
(project_id), die spaeter fuer Portfolioaggregation/Szenariovergleich
gebraucht werden.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pandas as pd

CASHFLOW_COLUMNS = [
    "jahr",
    "datum",
    "cf_operativ_eur",
    "cf_invest_eur",
    "cf_finanzierung_eur",
    "cf_gesamt_eur",
    "cf_kumuliert_eur",
]


@dataclass
class CashflowTimeseries:
    data: pd.DataFrame
    project_id: str
    scenario_name: str | None = field(default=None)

    def __post_init__(self) -> None:
        missing = set(CASHFLOW_COLUMNS) - set(self.data.columns)
        if missing:
            raise ValueError(f"CashflowTimeseries fehlt Spalten: {missing}")


def calculate_cashflow(
    timeline: pd.DataFrame,
    revenue: pd.DataFrame,
    opex: pd.DataFrame,
    financing: pd.DataFrame,
    tax: pd.DataFrame,
    capex_total_eur: float,
    eigenkapitalquote_pct: float,
    inbetriebnahme_datum: date,
    project_id: str,
) -> CashflowTimeseries:
    cf_operativ = (
        revenue["erloes_eur"].to_numpy()
        - opex["opex_gesamt_eur"].to_numpy()
        - financing["zinsen_eur"].to_numpy()
        - tax["steuer_eur"].to_numpy()
    )
    # Tilgung ist ein Abfluss, daher negatives Vorzeichen in der CF-Sicht.
    cf_finanzierung_betrieb = -financing["tilgung_eur"].to_numpy()

    betriebsjahre = pd.DataFrame(
        {
            "jahr": timeline["jahr"],
            "datum": timeline["datum_ende"],
            "cf_operativ_eur": cf_operativ,
            "cf_invest_eur": 0.0,
            "cf_finanzierung_eur": cf_finanzierung_betrieb,
        }
    )

    # Nettoeffekt aus Invest (-capex_total) + Kreditaufnahme (+fremdkapital)
    # ergibt den tatsaechlichen Eigenkapital-Abfluss im Jahr 0.
    fremdkapital_eur = capex_total_eur * (1 - eigenkapitalquote_pct)

    investitionsjahr = pd.DataFrame(
        [
            {
                "jahr": 0,
                "datum": inbetriebnahme_datum,
                "cf_operativ_eur": 0.0,
                "cf_invest_eur": -capex_total_eur,
                "cf_finanzierung_eur": fremdkapital_eur,
            }
        ]
    )

    df = pd.concat([investitionsjahr, betriebsjahre], ignore_index=True)
    df["cf_gesamt_eur"] = (
        df["cf_operativ_eur"] + df["cf_invest_eur"] + df["cf_finanzierung_eur"]
    )
    df["cf_kumuliert_eur"] = df["cf_gesamt_eur"].cumsum()

    return CashflowTimeseries(data=df[CASHFLOW_COLUMNS], project_id=project_id)
