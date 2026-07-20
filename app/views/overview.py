"""
Portfolioseite: aggregierte Kennzahlen, Portfolio-Analytik
(Rendite-Risiko-Landkarte, Ranking, Vergleichstabelle), Projektkarten mit
Cashflow-Sparkline und darunter das Dashboard des ausgewaehlten Projekts.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app import services
from app.components import charts
from app.components.kpi import render_kpi_row
from app.config import STATE_SELECTED_PROJECT
from app.formatting import fmt_eur, fmt_kwp, fmt_number, fmt_pct
from app.theme import badge
from app.views.project_detail import render_project_dashboard
from engine import AnlagenTyp
from engine.io_yaml import load_project_yaml
from texte import txt


def render_overview() -> None:
    projects = services.list_project_files()
    if not projects:
        st.info(txt("oberflaeche.overview_keine_projekte"))
        return

    global_assumptions = services.get_global_assumptions()

    # Alle Projekte einmal bewerten (gecacht auf Datei-mtimes, siehe
    # services) - Grundlage fuer Portfolio-KPIs, Analytik und Karten.
    zeilen = []
    for pid, path in projects.items():
        project = load_project_yaml(path)
        result = services.get_valuation(pid)
        zeilen.append(
            {
                "id": pid,
                "projekt": project,
                "kpis": result.kpis,
            }
        )

    # --- Portfolio-KPIs ------------------------------------------------------
    aktive = [z for z in zeilen if z["projekt"].aktiv]
    inaktive_anzahl = len(zeilen) - len(aktive)
    if inaktive_anzahl:
        mit_inaktiven = st.toggle(
            txt("oberflaeche.portfolio_toggle_inaktive", anzahl=inaktive_anzahl),
            value=False, key="portfolio_mit_inaktiven",
            help=txt("oberflaeche.portfolio_toggle_inaktive_hilfe"),
        )
    else:
        mit_inaktiven = False
    kpi_basis = zeilen if mit_inaktiven else aktive

    gesamt_kwp = sum(z["projekt"].nennleistung_kwp for z in kpi_basis)
    gesamt_capex = sum(z["kpis"].capex_total_eur for z in kpi_basis)
    gesamt_ek = sum(z["kpis"].eigenkapital_eur for z in kpi_basis)
    irr_werte = [z["kpis"].equity_irr for z in kpi_basis
                 if z["kpis"].equity_irr is not None]
    mittlere_irr = sum(irr_werte) / len(irr_werte) if irr_werte else None

    render_kpi_row(
        [
            (txt("oberflaeche.portfolio_kpi_anzahl_projekte"), f"{len(kpi_basis)}"),
            (txt("oberflaeche.portfolio_kpi_gesamt_kwp"),
             f"{fmt_number(gesamt_kwp / 1000, 1)} MWp"),
            (txt("oberflaeche.portfolio_kpi_gesamt_capex"), fmt_eur(gesamt_capex)),
            (txt("oberflaeche.portfolio_kpi_gesamt_ek"), fmt_eur(gesamt_ek)),
            (txt("oberflaeche.portfolio_kpi_ek_rendite"), fmt_pct(mittlere_irr)),
        ],
        group="portfolio",
    )

    # --- Portfolio-Analytik ---------------------------------------------------
    selected = st.session_state.get(STATE_SELECTED_PROJECT)
    analytik = pd.DataFrame(
        [
            {
                "id": z["id"],
                "name": z["projekt"].name,
                "typ": "Agri-PV"
                if z["projekt"].anlagentyp == AnlagenTyp.AGRI_PV
                else "Konventionell",
                "kwp": z["projekt"].nennleistung_kwp,
                "irr_pct": (z["kpis"].equity_irr or 0) * 100,
                "invest_eur_kwp": (
                    z["kpis"].capex_total_eur / z["projekt"].nennleistung_kwp
                    if z["projekt"].nennleistung_kwp
                    else 0
                ),
            }
            for z in aktive
        ]
    )

    col_xl1, col_xl2 = st.columns([1.6, 3])
    if col_xl1.button(txt("oberflaeche.btn_pipeline_excel"), width="stretch",
                      help=txt("oberflaeche.portfolio_excel_hilfe")):
        with st.spinner(txt("oberflaeche.portfolio_excel_spinner")):
            st.session_state["pipeline_excel"] = services.build_pipeline_excel()
    if st.session_state.get("pipeline_excel"):
        from datetime import date as _date

        col_xl2.download_button(
            txt("oberflaeche.btn_pipeline_excel_download"),
            data=st.session_state["pipeline_excel"],
            file_name=f"pipeline_ergebnisse_{_date.today().isoformat()}.xlsx",
            mime="application/vnd.openxmlformats-officedocument"
                 ".spreadsheetml.sheet",
            width="stretch",
        )

    # Zuklappbar (Standard: eingeklappt), damit die Uebersicht kompakt
    # bleibt und die Analytik nur bei Bedarf Platz einnimmt.
    with st.expander(
        f"{txt('oberflaeche.portfolio_analytik_titel')} "
        f"({txt('oberflaeche.portfolio_tab_karte')} · "
        f"{txt('oberflaeche.portfolio_tab_ranking')} · "
        f"{txt('oberflaeche.portfolio_tab_tabelle')})",
        expanded=False,
    ):
        tab_karte, tab_ranking, tab_tabelle = st.tabs([
            txt("oberflaeche.portfolio_tab_karte"),
            txt("oberflaeche.portfolio_tab_ranking"),
            txt("oberflaeche.portfolio_tab_tabelle"),
        ])
        with tab_karte:
            st.caption(txt("oberflaeche.overview_bubble_hilfe"))
            st.plotly_chart(
                charts.portfolio_bubble_chart(analytik, selected), width="stretch"
            )
        with tab_ranking:
            st.plotly_chart(
                charts.portfolio_ranking_chart(analytik, selected), width="stretch"
            )
        with tab_tabelle:
            vergleich = pd.DataFrame(
                [
                    {
                        "Projekt": z["projekt"].name,
                        "Typ": "Agri-PV"
                        if z["projekt"].anlagentyp == AnlagenTyp.AGRI_PV
                        else "Konventionell",
                        "Leistung (kWp)": round(z["projekt"].nennleistung_kwp),
                        "EK-Rendite (%)": round(z["kpis"].equity_irr * 100, 2)
                        if z["kpis"].equity_irr is not None
                        else None,
                        "NPV bei 8 % (€)": round(z["kpis"].npv_eur),
                        "Invest (€)": round(z["kpis"].capex_total_eur),
                        "Invest (€/kWp)": round(
                            z["kpis"].capex_total_eur / z["projekt"].nennleistung_kwp
                        )
                        if z["projekt"].nennleistung_kwp
                        else None,
                        "Min. DSCR (x)": round(z["kpis"].dscr_min, 2)
                        if z["kpis"].dscr_min is not None
                        else None,
                        "Payback (Jahr)": z["kpis"].payback_jahre,
                    }
                    for z in aktive
                ]
            )
            st.dataframe(
                vergleich.sort_values("EK-Rendite (%)", ascending=False),
                width="stretch",
                hide_index=True,
            )

    # --- Projektkarten ------------------------------------------------------
    st.subheader(txt("oberflaeche.overview_projekte_titel"))
    cols = st.columns(min(len(zeilen), 4))
    for i, z in enumerate(zeilen):
        project = z["projekt"]
        kpis = z["kpis"]
        ist_agri = project.anlagentyp == AnlagenTyp.AGRI_PV
        typ_badge = badge(txt("oberflaeche.badge_agri"), "agri") if ist_agri else badge(txt("oberflaeche.badge_konventionell"), "konv")
        if not project.aktiv:
            typ_badge += " " + badge(txt("oberflaeche.badge_inaktiv"), "inaktiv")
        selected_cls = " selected" if z["id"] == selected else ""
        if not project.aktiv:
            selected_cls += " inaktiv"
        with cols[i % len(cols)]:
            st.markdown(
                f"""<div class="project-card{selected_cls}">
                <span class="card-title">{html.escape(project.name)}</span> {typ_badge}<br/>
                <span class="card-sub">{fmt_kwp(project.nennleistung_kwp)} · IBN {project.inbetriebnahme_jahr}</span><br/>
                <span class="card-kpi">{fmt_pct(kpis.equity_irr)}</span>
                <span class="card-kpi-label"> EK-Rendite</span><br/>
                <span class="card-sub">EK {fmt_eur(kpis.eigenkapital_eur)}</span>
                </div>""",
                unsafe_allow_html=True,
            )
            if st.button(txt("oberflaeche.btn_oeffnen"), key=f"open_{z['id']}", width="stretch"):
                st.session_state[STATE_SELECTED_PROJECT] = z["id"]
                st.rerun()

    if not selected or selected not in projects:
        return

    st.divider()
    project = load_project_yaml(projects[selected])
    render_project_dashboard(project, global_assumptions, projects[selected])
