"""
PV-Projektbewertungs-Tool - Oberflaeche fuer Projektentwickler.

Bewusst NICHT am Excel-Original orientiert: Die Projektmaske zeigt nur,
was sich von Projekt zu Projekt unterscheidet. Alles Uebrige (Preiskurven,
Standardbetriebskosten, Finanzierungskonditionen, Steuerlogik) kommt aus
den Globalen Annahmen und wird automatisch angewendet.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from engine.io_yaml import (
    load_global_assumptions_yaml,
    load_project_yaml,
    save_global_assumptions_yaml,
    save_project_yaml,
)
from engine.models import (
    AnlagenTyp,
    CapexBreakdown,
    GlobalAssumptions,
    OpexItem,
    PVProject,
    TilgungsArt,
)
from engine.pipeline import run_valuation
from engine.sensitivity import run_eag_sensitivity

DATA_DIR = Path(__file__).parent / "data"
PROJECTS_DIR = DATA_DIR / "projects"
GLOBAL_ASSUMPTIONS_PATH = DATA_DIR / "global_assumptions.yaml"

st.set_page_config(page_title="PV-Projektbewertung", layout="wide", page_icon="☀️")

CUSTOM_CSS = """
<style>
    .block-container { padding-top: 2rem; max-width: 1200px; }
    div[data-testid="stMetric"] {
        background: #F7F9F8;
        border: 1px solid #E3E8E6;
        border-radius: 10px;
        padding: 16px 18px 12px 18px;
    }
    div[data-testid="stMetric"] label { color: #5B6B66; }
    .project-card {
        border: 1px solid #E3E8E6;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
        background: white;
    }
    h1, h2, h3 { color: #163832; }
    .stTabs [data-baseweb="tab"] { font-weight: 500; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Daten laden/speichern
# ---------------------------------------------------------------------------


def list_projects() -> dict[str, Path]:
    return {f.stem: f for f in sorted(PROJECTS_DIR.glob("*.yaml"))}


@st.cache_data
def _load_global_assumptions_cached(mtime: float) -> GlobalAssumptions:
    return load_global_assumptions_yaml(GLOBAL_ASSUMPTIONS_PATH)


def load_global_assumptions() -> GlobalAssumptions:
    # mtime im Cache-Key sorgt dafuer, dass Aenderungen nach dem Speichern
    # sofort sichtbar werden, ohne bei jedem Rerun neu von Platte zu lesen.
    mtime = GLOBAL_ASSUMPTIONS_PATH.stat().st_mtime
    return _load_global_assumptions_cached(mtime)


def format_pct(value: float | None, digits: int = 2) -> str:
    return f"{value:.{digits}%}" if value is not None else "n/a"


def format_eur(value: float) -> str:
    return f"{value:,.0f} €".replace(",", ".")


# ---------------------------------------------------------------------------
# Seite: Neues Projekt
# ---------------------------------------------------------------------------


def render_new_project_form() -> None:
    st.subheader("Neues Projekt anlegen")
    st.caption(
        "Nur projektspezifische Angaben. Preiskurven, Standardbetriebskosten, "
        "Kreditlaufzeit und Steuerlogik werden automatisch aus den "
        "Globalen Annahmen übernommen."
    )

    with st.form("neues_projekt", clear_on_submit=False):
        name = st.text_input("Projektname", placeholder="z.B. Sonnenfeld Agri-PV")

        st.markdown("**Technische Anlagenparameter**")
        col1, col2, col3 = st.columns(3)
        nennleistung_kwp = col1.number_input(
            "Leistung (kWp)", min_value=0.0, value=5000.0, step=100.0
        )
        vollbenutzungsstunden = col2.number_input(
            "Vollbenutzungsstunden (kWh/kWp)", min_value=0.0, value=1050.0, step=10.0
        )
        anlagentyp_label = col3.radio(
            "Anlagentyp", ["Agri-PV", "Konventionell"], horizontal=True
        )

        st.markdown("**Wirtschaftliche Parameter**")
        col4, col5, col6, col7 = st.columns(4)
        pacht = col4.number_input(
            "Pacht (€/kWp/Jahr)", min_value=0.0, value=4.0, step=0.1
        )
        fk_zins = col5.number_input(
            "Fremdkapitalzins (%)", min_value=0.0, value=3.5, step=0.1
        )
        ek_anteil = col6.number_input(
            "Eigenkapitalanteil (%)", min_value=0.0, max_value=100.0, value=20.0, step=1.0
        )
        eag_zuschlag = col7.number_input(
            "EAG-Zuschlagswert (ct/kWh)", min_value=0.0, value=7.2, step=0.1
        )
        if anlagentyp_label == "Konventionell":
            st.caption(
                f"ℹ️ Konventionell: automatischer Abschlag von 25 % wird angewendet "
                f"→ effektiv {eag_zuschlag * 0.75:.2f} ct/kWh"
            )

        st.markdown("**Investkosten (EUR)**")
        c1, c2, c3, c4 = st.columns(4)
        epc = c1.number_input("EPC", min_value=0.0, value=nennleistung_kwp * 600, step=1000.0)
        netzanschluss = c2.number_input("Netzanschluss", min_value=0.0, value=150000.0, step=1000.0)
        trasse = c3.number_input("Trasse", min_value=0.0, value=60000.0, step=1000.0)
        sonstige_extern = c4.number_input("Sonstige Extern", min_value=0.0, value=40000.0, step=1000.0)
        c5, c6, c7 = st.columns(3)
        agm = c5.number_input("AGM", min_value=0.0, value=30000.0, step=1000.0)
        m_and_a = c6.number_input("M&A", min_value=0.0, value=20000.0, step=1000.0)
        poenale = c7.number_input("Pönale + Puffer", min_value=0.0, value=35000.0, step=1000.0)

        submitted = st.form_submit_button("Projekt anlegen und berechnen", type="primary")

    if not submitted:
        return

    if not name.strip():
        st.error("Bitte einen Projektnamen angeben.")
        return

    project_id = name.strip().lower().replace(" ", "-")
    project = PVProject(
        id=project_id,
        name=name.strip(),
        anlagentyp=AnlagenTyp.AGRI_PV
        if anlagentyp_label == "Agri-PV"
        else AnlagenTyp.KONVENTIONELL,
        nennleistung_kwp=nennleistung_kwp,
        vollbenutzungsstunden_kwh_kwp=vollbenutzungsstunden,
        pacht_eur_kwp_jahr=pacht,
        fremdkapitalzins_pct=fk_zins / 100,
        eigenkapitalquote_pct=ek_anteil / 100,
        eag_zuschlagswert_ct_kwh=eag_zuschlag,
        capex=CapexBreakdown(
            epc_eur=epc,
            netzanschluss_eur=netzanschluss,
            trasse_eur=trasse,
            sonstige_extern_eur=sonstige_extern,
            agm_eur=agm,
            m_and_a_eur=m_and_a,
            poenale_puffer_eur=poenale,
        ),
    )

    save_path = PROJECTS_DIR / f"{project_id}.yaml"
    save_project_yaml(project, save_path)
    st.session_state["selected_project"] = project_id
    st.cache_data.clear()

    st.success(f"Projekt „{project.name}“ angelegt und berechnet.")
    st.divider()
    global_assumptions = load_global_assumptions()
    render_project_dashboard(project, global_assumptions)


# ---------------------------------------------------------------------------
# Seite: Projektuebersicht + Dashboard
# ---------------------------------------------------------------------------


def render_project_overview() -> None:
    projects = list_projects()
    if not projects:
        st.info("Noch keine Projekte angelegt. Starten Sie mit „Neues Projekt“.")
        return

    global_assumptions = load_global_assumptions()

    st.subheader("Projekte")
    selected = st.session_state.get("selected_project")
    cols = st.columns(min(len(projects), 4))
    for i, (pid, path) in enumerate(projects.items()):
        project = load_project_yaml(path)
        result = run_valuation(project, global_assumptions)
        with cols[i % len(cols)]:
            typ_label = "Agri-PV" if project.anlagentyp == AnlagenTyp.AGRI_PV else "Konventionell"
            st.markdown(
                f"""<div class="project-card">
                <b>{project.name}</b><br/>
                <span style="color:#5B6B66;">{typ_label} · {project.nennleistung_kwp:,.0f} kWp</span><br/>
                <span style="font-size:1.4em; font-weight:600;">{format_pct(result.kpis.equity_irr)}</span>
                <span style="color:#5B6B66;"> EK-Rendite</span>
                </div>""".replace(",", "."),
                unsafe_allow_html=True,
            )
            if st.button("Öffnen", key=f"open_{pid}", width="stretch"):
                st.session_state["selected_project"] = pid
                st.rerun()

    if not selected or selected not in projects:
        return

    st.divider()
    project = load_project_yaml(projects[selected])
    render_project_dashboard(project, global_assumptions)


def render_project_dashboard(
    project: PVProject, global_assumptions: GlobalAssumptions
) -> None:
    result = run_valuation(project, global_assumptions)
    df = result.cashflow.data
    kpis = result.kpis

    typ_label = "Agri-PV" if project.anlagentyp == AnlagenTyp.AGRI_PV else "Konventionell"
    st.markdown(f"### {project.name}")
    st.caption(
        f"{typ_label} · {project.nennleistung_kwp:,.0f} kWp · "
        f"Inbetriebnahme {project.inbetriebnahme_jahr} · "
        f"effektiver EAG-Zuschlag {project.eag_zuschlagswert_effektiv_ct_kwh:.2f} ct/kWh"
        .replace(",", ".")
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("EK-Rendite (IRR)", format_pct(kpis.equity_irr))
    col2.metric("NPV bei 5 %", format_eur(kpis.npv_eur))
    col3.metric("Payback", f"{kpis.payback_jahre:.0f} Jahre" if kpis.payback_jahre else "n/a")
    col4.metric("Investitionsvolumen", format_eur(kpis.capex_total_eur))

    tab_cf, tab_npv, tab_sens = st.tabs(
        ["Cashflow", "NPV-Sensitivität (Diskontsatz)", "Sensitivität EAG-Zuschlag"]
    )

    with tab_cf:
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
            height=420,
        )
        st.plotly_chart(fig, width="stretch")

        display_df = df.copy()
        for col in [
            "cf_operativ_eur", "cf_invest_eur", "cf_finanzierung_eur",
            "cf_gesamt_eur", "cf_kumuliert_eur",
        ]:
            display_df[col] = display_df[col].round(0)
        st.dataframe(display_df, width="stretch", hide_index=True)

    with tab_npv:
        npv_df = result.npv_curve.copy()
        fig = go.Figure()
        fig.add_scatter(
            x=npv_df["diskontsatz_pct"] * 100,
            y=npv_df["npv_eur"],
            mode="lines+markers",
            name="NPV",
        )
        fig.add_hline(y=0, line_dash="dot", line_color="gray")
        if kpis.equity_irr is not None:
            fig.add_vline(
                x=kpis.equity_irr * 100,
                line_dash="dot",
                line_color="#2E7D32",
                annotation_text="IRR",
            )
        fig.update_layout(
            xaxis_title="Diskontsatz (%)",
            yaxis_title="NPV (€)",
            margin=dict(t=20, b=20),
            height=420,
        )
        st.plotly_chart(fig, width="stretch")

        npv_display = npv_df.copy()
        npv_display["diskontsatz_pct"] = (npv_display["diskontsatz_pct"] * 100).round(1)
        npv_display["npv_eur"] = npv_display["npv_eur"].round(0)
        npv_display.columns = ["Diskontsatz (%)", "NPV (€)"]
        st.dataframe(npv_display, width="stretch", hide_index=True)

    with tab_sens:
        sens_df = run_eag_sensitivity(project, global_assumptions)
        fig = go.Figure()
        fig.add_bar(
            x=sens_df["variante"],
            y=sens_df["equity_irr"] * 100,
            marker_color=[
                "#2E7D32" if v == "Basis" else "#8AA6A0" for v in sens_df["variante"]
            ],
        )
        fig.update_layout(
            xaxis_title="EAG-Zuschlagswert-Variante",
            yaxis_title="EK-Rendite (%)",
            margin=dict(t=20, b=20),
            height=380,
        )
        st.plotly_chart(fig, width="stretch")

        sens_display = sens_df.copy()
        sens_display["eag_zuschlagswert_ct_kwh"] = sens_display[
            "eag_zuschlagswert_ct_kwh"
        ].round(3)
        sens_display["equity_irr"] = sens_display["equity_irr"].apply(format_pct)
        sens_display["npv_eur"] = sens_display["npv_eur"].round(0)
        sens_display.columns = ["Variante", "EAG-Zuschlag (ct/kWh)", "EK-Rendite", "NPV (€)"]
        st.dataframe(sens_display, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Seite: Globale Annahmen
# ---------------------------------------------------------------------------


def render_global_assumptions_page() -> None:
    st.subheader("Globale Annahmen")
    st.caption(
        "Gelten für alle Projekte, sofern nicht projektspezifisch überschrieben. "
        "Änderungen wirken sich erst nach „Speichern“ auf alle Projekte aus."
    )

    ga = load_global_assumptions()

    with st.expander("Preiskurven (Marktwert Solar & negative Stunden)", expanded=True):
        jahre = sorted(
            set(ga.marktwert_solar_ct_kwh_je_jahr)
            | set(ga.anteil_negativer_stunden_pct_je_jahr)
        )
        kurven_df = pd.DataFrame(
            {
                "Jahr": jahre,
                "Marktwert Solar (ct/kWh)": [
                    ga.marktwert_solar_ct_kwh_je_jahr.get(j) for j in jahre
                ],
                "Anteil neg. Stunden (%)": [
                    (ga.anteil_negativer_stunden_pct_je_jahr.get(j) or 0) * 100
                    for j in jahre
                ],
            }
        )
        edited_kurven = st.data_editor(
            kurven_df, width="stretch", hide_index=True, num_rows="dynamic",
            key="kurven_editor",
        )

    with st.expander("Standardbetriebskosten"):
        opex_df = pd.DataFrame(
            [
                {
                    "Position": item.name,
                    "EUR/kWp/Jahr": item.basiswert_eur_kwp,
                    "Index %/Jahr": item.index_pct_pa * 100,
                    "Indexierung ab Jahr": item.indexierung_ab_jahr,
                }
                for item in ga.opex_standard
            ]
        )
        edited_opex = st.data_editor(
            opex_df, width="stretch", hide_index=True, num_rows="dynamic",
            key="opex_editor",
        )

    with st.expander("Förderung, Finanzierung, Steuer"):
        col1, col2, col3 = st.columns(3)
        eag_foerderdauer = col1.number_input(
            "EAG-Förderdauer (Jahre)", min_value=1, value=ga.eag_foerderdauer_jahre
        )
        betriebsdauer = col2.number_input(
            "Betrachtungsdauer (Jahre)", min_value=1, value=ga.betriebsdauer_jahre
        )
        kreditlaufzeit = col3.number_input(
            "Kreditlaufzeit (Jahre)", min_value=1, value=ga.kreditlaufzeit_jahre
        )
        col4, col5, col6 = st.columns(3)
        degradation = col4.number_input(
            "Degradation (%/Jahr)", min_value=0.0, value=ga.degradation_pct_pa * 100, step=0.05
        )
        steuersatz = col5.number_input(
            "Steuersatz (%)", min_value=0.0, value=ga.steuersatz_pct * 100, step=0.5
        )
        tilgungsart = col6.selectbox(
            "Tilgungsart", ["annuitaet", "linear"],
            index=0 if ga.tilgungsart.value == "annuitaet" else 1,
        )

    if st.button("Speichern", type="primary"):
        ga.marktwert_solar_ct_kwh_je_jahr = {
            int(r["Jahr"]): float(r["Marktwert Solar (ct/kWh)"])
            for _, r in edited_kurven.iterrows()
            if pd.notna(r["Jahr"]) and pd.notna(r["Marktwert Solar (ct/kWh)"])
        }
        ga.anteil_negativer_stunden_pct_je_jahr = {
            int(r["Jahr"]): float(r["Anteil neg. Stunden (%)"]) / 100
            for _, r in edited_kurven.iterrows()
            if pd.notna(r["Jahr"]) and pd.notna(r["Anteil neg. Stunden (%)"])
        }
        ga.opex_standard = [
            OpexItem(
                name=r["Position"],
                basiswert_eur_kwp=float(r["EUR/kWp/Jahr"]),
                index_pct_pa=float(r["Index %/Jahr"]) / 100,
                indexierung_ab_jahr=int(r["Indexierung ab Jahr"]),
            )
            for _, r in edited_opex.iterrows()
            if pd.notna(r["Position"])
        ]
        ga.eag_foerderdauer_jahre = int(eag_foerderdauer)
        ga.betriebsdauer_jahre = int(betriebsdauer)
        ga.kreditlaufzeit_jahre = int(kreditlaufzeit)
        ga.degradation_pct_pa = degradation / 100
        ga.steuersatz_pct = steuersatz / 100
        ga.tilgungsart = TilgungsArt(tilgungsart)

        save_global_assumptions_yaml(ga, GLOBAL_ASSUMPTIONS_PATH)
        st.cache_data.clear()
        st.success("Globale Annahmen gespeichert.")
        st.rerun()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


st.title("☀️ PV-Projektbewertung")

nav = st.sidebar.radio(
    "Navigation",
    ["Projektübersicht", "Neues Projekt", "Globale Annahmen"],
    key="nav",
)

if nav == "Projektübersicht":
    render_project_overview()
elif nav == "Neues Projekt":
    render_new_project_form()
else:
    render_global_assumptions_page()
