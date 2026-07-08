"""
Phase-1-MVP: Ein Testprojekt aus YAML laden, Cashflow berechnen, Tabelle
und Kennzahlen anzeigen. Bewusst noch keine Mehrprojektverwaltung, kein
Szenariovergleich, keine Datenbank - das kommt in den naechsten Phasen.
"""

from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from engine.io_yaml import load_project_yaml
from engine.pipeline import run_valuation

st.set_page_config(page_title="PV-Cashflow-Rechner", layout="wide")

PROJECT_PATH = Path(__file__).parent / "data" / "projects" / "halsdorf.yaml"

st.title("PV-Cashflow-Rechner (Phase 1)")
st.caption(
    "Testprojekt aus YAML geladen. Noch kein Szenariovergleich, "
    "keine Mehrprojektverwaltung - das folgt in den naechsten Ausbaustufen."
)

try:
    project = load_project_yaml(PROJECT_PATH)
except Exception as exc:  # bewusst breit: Validierungsfehler sollen sichtbar sein
    st.error(f"Projekt konnte nicht geladen werden: {exc}")
    st.stop()

result = run_valuation(project)
df = result.cashflow.data
kpis = result.kpis

st.subheader(project.name)
st.caption(
    f"Nennleistung {project.technical.nennleistung_kwp:,.0f} kWp · "
    f"Inbetriebnahme {project.technical.inbetriebnahme_datum} · "
    f"Vertragslaufzeit {project.revenue.vertragslaufzeit_jahre} Jahre"
)

col1, col2, col3, col4 = st.columns(4)
col1.metric(
    "Eigenkapitalrendite (IRR)",
    f"{kpis.equity_irr:.2%}" if kpis.equity_irr is not None else "n/a",
)
col2.metric("NPV (5% Diskontsatz)", f"{kpis.npv_eur:,.0f} €")
col3.metric(
    "Payback",
    f"{kpis.payback_jahre:.0f} Jahre" if kpis.payback_jahre is not None else "n/a",
)
col4.metric("Investitionsvolumen", f"{kpis.capex_total_eur:,.0f} €")

st.markdown("### Cashflow-Zeitreihe")

fig = go.Figure()
fig.add_bar(x=df["jahr"], y=df["cf_gesamt_eur"], name="Cashflow (Jahr)")
fig.add_scatter(
    x=df["jahr"],
    y=df["cf_kumuliert_eur"],
    name="Kumulierter Cashflow",
    mode="lines+markers",
    yaxis="y2",
)
fig.update_layout(
    yaxis=dict(title="Cashflow (Jahr) in €"),
    yaxis2=dict(title="Kumuliert in €", overlaying="y", side="right"),
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
    margin=dict(t=40, b=20),
)
st.plotly_chart(fig, width='stretch')

st.markdown("### Tabelle")
display_df = df.copy()
for col in [
    "cf_operativ_eur",
    "cf_invest_eur",
    "cf_finanzierung_eur",
    "cf_gesamt_eur",
    "cf_kumuliert_eur",
]:
    display_df[col] = display_df[col].round(0)
st.dataframe(display_df, width='stretch', hide_index=True)

with st.expander("Bekannte Abweichungen zum Excel-Original"):
    st.markdown(
        """
        - **"Goldenes Ende"** (Anschlussvermarktung am Markt nach Ablauf der
          EEG-Vertragslaufzeit) ist noch **nicht** implementiert. Excels
          Referenz-IRR von ca. 9,78 % bezieht sich vermutlich auf einen
          30-Jahres-Lauf inkl. dieser Tail-Periode; dieser MVP rechnet
          bewusst nur die 20-jährige EEG-Kernlaufzeit (IRR ≈ 6,9 %).
        - Die Position **"Rückbaukosten & Avalgebühren"** (~2,50 €/Jahr bei
          diesem Projekt) ist nicht enthalten, da sie im Original auf einer
          ct/kWh-Basis statt EUR/kWp gerechnet wird.
        - Alle übrigen Zwischenwerte (Erlöse, OPEX, Zinsen, Tilgung, Steuer,
          operativer Cashflow) wurden gegen das Excel-Original für die
          ersten Betriebsjahre auf den Cent genau abgeglichen.
        """
    )
