"""
Fuehrt Erloes-, OPEX-, Finanzierungs- und Steuerzeitreihen zu einer
vollstaendigen Cashflow-Zeitreihe zusammen (operativ, Investition,
Finanzierung, gesamt, kumuliert, DSCR).

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

import numpy as np
import pandas as pd

CASHFLOW_COLUMNS = [
    "jahr",
    "datum",
    "produktion_kwh",
    "marktwert_real_ct_kwh",
    "marktwert_nominal_ct_kwh",
    "verguetungssatz_ct_kwh",
    "erloes_eur",
    "erloes_markt_eur",
    "erloes_praemie_eur",
    "opex_gesamt_eur",
    "gemeindeabgabe_eur",
    "direktvermarktungskosten_eur",
    "zinsen_eur",
    "tilgung_eur",
    "afa_eur",
    "steuerliches_ergebnis_vor_verlustvortrag_eur",
    "verlustvortrag_genutzt_eur",
    "verlustvortrag_bestand_eur",
    "steuerliches_ergebnis_eur",
    "steuer_eur",
    "cf_operativ_eur",
    "cf_invest_eur",
    "cf_finanzierung_eur",
    "cf_gesamt_eur",
    "cf_kumuliert_eur",
    "dscr",
]


@dataclass
class CashflowTimeseries:
    data: pd.DataFrame
    project_id: str
    scenario_name: str | None = field(default=None)
    # Namen der dynamischen OPEX-Einzelpositionen (fuer die Aufschluesselung
    # in der UI, z.B. im gestapelten Betriebskosten-Chart).
    opex_posten: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        missing = set(CASHFLOW_COLUMNS) - set(self.data.columns)
        if missing:
            raise ValueError(f"CashflowTimeseries fehlt Spalten: {missing}")


def calculate_cashflow(
    timeline: pd.DataFrame,
    energy: pd.DataFrame,
    revenue: pd.DataFrame,
    opex: pd.DataFrame,
    financing: pd.DataFrame,
    tax: pd.DataFrame,
    capex_total_eur: float,
    eigenkapitalquote_pct: float,
    inbetriebnahme_datum: date,
    project_id: str,
) -> CashflowTimeseries:
    # Einzelne OPEX-Kostenpositionen (dynamisch, projektabhaengig - z.B.
    # "Pacht", "Technische Betriebsführung", ...) werden 1:1 durchgereicht,
    # damit die UI eine vollstaendige Aufschluesselung anzeigen kann.
    opex_posten_spalten = [
        c for c in opex.columns if c not in ("jahr", "opex_gesamt_eur", "gemeindeabgabe_eur", "direktvermarktungskosten_eur")
    ]

    cf_operativ = (
        revenue["erloes_eur"].to_numpy()
        - opex["opex_gesamt_eur"].to_numpy()
        - financing["zinsen_eur"].to_numpy()
        - tax["steuer_eur"].to_numpy()
    )
    # Tilgung ist ein Abfluss, daher negatives Vorzeichen in der CF-Sicht.
    cf_finanzierung_betrieb = -financing["tilgung_eur"].to_numpy()

    # DSCR = CFADS (Cash Flow Available for Debt Service) / Schuldendienst.
    # CFADS ist der Cashflow VOR Zinsen (Zinsen sind Teil des Schuldendienstes
    # im Nenner, duerfen also nicht auch schon im Zaehler abgezogen sein).
    cfads = (
        revenue["erloes_eur"].to_numpy()
        - opex["opex_gesamt_eur"].to_numpy()
        - tax["steuer_eur"].to_numpy()
    )
    schuldendienst = financing["schuldendienst_eur"].to_numpy()
    dscr = np.divide(
        cfads,
        schuldendienst,
        out=np.full_like(cfads, np.nan, dtype=float),
        where=schuldendienst > 0,
    )

    betriebsjahre = pd.DataFrame(
        {
            "jahr": timeline["jahr"],
            "datum": timeline["datum_ende"],
            "produktion_kwh": energy["produktion_kwh"].to_numpy(),
            "marktwert_real_ct_kwh": revenue["marktwert_real_ct_kwh"].to_numpy(),
            "marktwert_nominal_ct_kwh": revenue["marktwert_nominal_ct_kwh"].to_numpy(),
            "verguetungssatz_ct_kwh": revenue["verguetungssatz_ct_kwh"].to_numpy(),
            "erloes_eur": revenue["erloes_eur"].to_numpy(),
            "erloes_markt_eur": revenue["erloes_markt_eur"].to_numpy(),
            "erloes_praemie_eur": revenue["erloes_praemie_eur"].to_numpy(),
            "opex_gesamt_eur": opex["opex_gesamt_eur"].to_numpy(),
            "gemeindeabgabe_eur": opex["gemeindeabgabe_eur"].to_numpy(),
            "direktvermarktungskosten_eur": opex["direktvermarktungskosten_eur"].to_numpy(),
            **{spalte: opex[spalte].to_numpy() for spalte in opex_posten_spalten},
            "zinsen_eur": financing["zinsen_eur"].to_numpy(),
            "tilgung_eur": financing["tilgung_eur"].to_numpy(),
            "afa_eur": tax["afa_eur"].to_numpy(),
            "steuerliches_ergebnis_vor_verlustvortrag_eur": tax[
                "steuerliches_ergebnis_vor_verlustvortrag_eur"
            ].to_numpy(),
            "verlustvortrag_genutzt_eur": tax["verlustvortrag_genutzt_eur"].to_numpy(),
            "verlustvortrag_bestand_eur": tax["verlustvortrag_bestand_eur"].to_numpy(),
            "steuerliches_ergebnis_eur": tax["steuerliches_ergebnis_eur"].to_numpy(),
            "steuer_eur": tax["steuer_eur"].to_numpy(),
            "cf_operativ_eur": cf_operativ,
            "cf_invest_eur": 0.0,
            "cf_finanzierung_eur": cf_finanzierung_betrieb,
            "dscr": dscr,
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
                "produktion_kwh": 0.0,
                "marktwert_real_ct_kwh": 0.0,
                "marktwert_nominal_ct_kwh": 0.0,
                "verguetungssatz_ct_kwh": 0.0,
                "erloes_eur": 0.0,
                "erloes_markt_eur": 0.0,
                "erloes_praemie_eur": 0.0,
                "opex_gesamt_eur": 0.0,
                "gemeindeabgabe_eur": 0.0,
                "direktvermarktungskosten_eur": 0.0,
                **{spalte: 0.0 for spalte in opex_posten_spalten},
                "zinsen_eur": 0.0,
                "tilgung_eur": 0.0,
                "afa_eur": 0.0,
                "steuerliches_ergebnis_vor_verlustvortrag_eur": 0.0,
                "verlustvortrag_genutzt_eur": 0.0,
                "verlustvortrag_bestand_eur": 0.0,
                "steuerliches_ergebnis_eur": 0.0,
                "steuer_eur": 0.0,
                "cf_operativ_eur": 0.0,
                "cf_invest_eur": -capex_total_eur,
                "cf_finanzierung_eur": fremdkapital_eur,
                "dscr": np.nan,
            }
        ]
    )

    df = pd.concat([investitionsjahr, betriebsjahre], ignore_index=True)
    df["cf_gesamt_eur"] = (
        df["cf_operativ_eur"] + df["cf_invest_eur"] + df["cf_finanzierung_eur"]
    )
    df["cf_kumuliert_eur"] = df["cf_gesamt_eur"].cumsum()

    finale_spalten = CASHFLOW_COLUMNS + opex_posten_spalten
    return CashflowTimeseries(
        data=df[finale_spalten], project_id=project_id, opex_posten=opex_posten_spalten
    )
