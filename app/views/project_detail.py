"""
Die einzelnen Auswertungen eines Projekts.

Dieses Modul liefert die Bausteine, die app/views/project_page.py zu vier
Sichten zusammensetzt: Ergebnis (Cashflow + Erlöse), Finanzierung,
Risiko (Sensitivität + Monte Carlo + Szenarien) und Annahmen. Der Rahmen
- Kopfzeile, Kennzahlen, Parameterspalte, Aktionen - liegt in
project_page.py.
"""

from __future__ import annotations

import numpy as np
import streamlit as st

from app import services
from app.components import charts
from app.components.kpi import render_kpi_row
from app.formatting import fmt_ct_kwh, fmt_dscr, fmt_eur, fmt_kwp, fmt_number, fmt_pct
from app.theme import section_title
from engine import (
    NegativeStundenModus,
    NegativeStundenRegel,
)
from engine.analytics import HEATMAP_ACHSEN
from texte import txt

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------------------------------------------------------------------------
# DSCR-Kovenanten (Cash Trap / Event of Default)
# ---------------------------------------------------------------------------


def _jahresliste(jahre: list[int], hoechstens: int = 8) -> str:
    """Jahre als Aufzaehlung; lange Listen werden gekuerzt, damit die
    Statuszeile nicht ueber mehrere Zeilen laeuft."""
    if len(jahre) <= hoechstens:
        return ", ".join(str(j) for j in jahre)
    sichtbar = ", ".join(str(j) for j in jahre[:hoechstens])
    return f"{sichtbar} … (+{len(jahre) - hoechstens})"


def render_kovenanten_status(result) -> None:
    """Ampel zu den beiden DSCR-Schwellen des Kreditvertrags.

    Die Kacheln zeigen bewusst keinen DSCR mehr - der einzelne Minimalwert
    sagt wenig darueber aus, ob er eine Ausschuettungssperre oder eine
    Nachschusspflicht ausloest. Genau das steht hier.
    """
    kovenanten = getattr(result, "kovenanten", None)
    if kovenanten is None:
        return

    kopf = txt(
        "oberflaeche.projekt_kovenanten_kopf",
        dscr=fmt_dscr(kovenanten.dscr_min),
        trap=fmt_dscr(kovenanten.schwelle_cash_trap),
        eod=fmt_dscr(kovenanten.schwelle_event_of_default),
    )

    if not kovenanten.hat_cash_trap and not kovenanten.hat_event_of_default:
        st.success(f"{kopf} {txt('oberflaeche.projekt_kovenanten_ok')}")
        return

    st.markdown(f"**{kopf}**")

    if kovenanten.hat_cash_trap:
        st.warning(
            txt(
                "oberflaeche.projekt_kovenanten_cash_trap",
                anzahl=len(kovenanten.jahre_cash_trap),
                jahre=_jahresliste(kovenanten.jahre_cash_trap),
                trap=fmt_dscr(kovenanten.schwelle_cash_trap),
            )
        )

    if kovenanten.hat_event_of_default:
        st.error(
            txt(
                "oberflaeche.projekt_kovenanten_eod",
                anzahl=len(kovenanten.jahre_event_of_default),
                jahre=_jahresliste(kovenanten.jahre_event_of_default),
                eod=fmt_dscr(kovenanten.schwelle_event_of_default),
                betrag=fmt_eur(kovenanten.nachschuss_gesamt_eur),
            )
        )

    # Kernaussage: Traegt sich der Nachschuss aus dem, was das Projekt
    # zuvor selbst erwirtschaftet hat, oder braucht es Geld von aussen?
    if kovenanten.nachschuss_gesamt_eur > 0:
        if kovenanten.braucht_externes_kapital:
            st.error(
                txt(
                    "oberflaeche.projekt_kovenanten_extern",
                    extern=fmt_eur(kovenanten.nachschuss_extern_eur),
                    intern=fmt_eur(kovenanten.nachschuss_intern_eur),
                )
            )
        else:
            st.info(
                txt(
                    "oberflaeche.projekt_kovenanten_intern",
                    intern=fmt_eur(kovenanten.nachschuss_intern_eur),
                )
            )


# ---------------------------------------------------------------------------
# Tab: Cashflow
# ---------------------------------------------------------------------------


def render_cashflow_tab(result, df) -> None:
    section_title(txt("oberflaeche.dashboard_wertbruecke"))
    st.caption(txt("oberflaeche.projekt_wertbruecke_beschreibung"))
    st.plotly_chart(charts.equity_waterfall_chart(df), width="stretch")

    section_title(txt("oberflaeche.dashboard_gesamt_cashflow"))
    st.caption(txt("oberflaeche.projekt_gesamt_cashflow_beschreibung"))
    st.plotly_chart(charts.total_cashflow_chart(df), width="stretch")

    section_title(txt("oberflaeche.dashboard_betriebskosten_position"))
    st.caption(txt("oberflaeche.projekt_betriebskosten_beschreibung"))
    st.plotly_chart(
        charts.opex_stacked_chart(df, result.cashflow.opex_posten), width="stretch"
    )

    section_title(txt("oberflaeche.dashboard_steuerzahlungen"))
    st.caption(txt("oberflaeche.projekt_steuerzahlungen_beschreibung"))
    st.plotly_chart(charts.tax_chart(df), width="stretch")

    section_title(txt("oberflaeche.dashboard_operativer_cashflow"))
    st.caption(txt("oberflaeche.projekt_operativer_cf_beschreibung"))
    st.plotly_chart(charts.operating_cashflow_chart(df), width="stretch")

    with st.expander(txt("oberflaeche.projekt_detailtabelle_titel")):
        detail_df = df[
            [
                "jahr", "marktwert_real_ct_kwh", "marktwert_nominal_ct_kwh",
                "verguetungssatz_ct_kwh", "erloes_eur", "opex_gesamt_eur",
                "gemeindeabgabe_eur", "direktvermarktungskosten_eur",
                "zinsen_eur", "tilgung_eur", "afa_eur",
                "steuerliches_ergebnis_vor_verlustvortrag_eur",
                "verlustvortrag_genutzt_eur", "verlustvortrag_bestand_eur",
                "steuerliches_ergebnis_eur", "steuer_eur",
            ]
        ].copy()
        for col in detail_df.columns:
            if col == "jahr":
                continue
            nachkommastellen = 3 if "ct_kwh" in col else 0
            detail_df[col] = detail_df[col].round(nachkommastellen)
        detail_df.columns = [
            txt("oberflaeche.projekt_col_jahr"),
            txt("oberflaeche.projekt_col_marktwert_real"),
            txt("oberflaeche.projekt_col_marktwert_nominal"),
            txt("oberflaeche.projekt_col_verguetungssatz"),
            txt("oberflaeche.projekt_col_erloese"),
            txt("oberflaeche.projekt_col_betriebskosten_gesamt"),
            txt("oberflaeche.projekt_col_gemeindeabgabe"),
            txt("oberflaeche.projekt_col_direktvermarktung"),
            txt("oberflaeche.projekt_col_zinsen"),
            txt("oberflaeche.projekt_col_tilgung"),
            txt("oberflaeche.projekt_col_afa"),
            txt("oberflaeche.projekt_col_steuerl_ergebnis_vor"),
            txt("oberflaeche.projekt_col_verlustvortrag_genutzt"),
            txt("oberflaeche.projekt_col_verlustvortrag_bestand"),
            txt("oberflaeche.projekt_col_steuerpflichtig"),
            txt("oberflaeche.projekt_col_steuer"),
        ]
        st.dataframe(detail_df, width="stretch", hide_index=True)

    cf_spalten = [
        "cf_operativ_eur", "cf_invest_eur", "cf_finanzierung_eur",
        "cf_gesamt_eur", "cf_kumuliert_eur",
    ]
    display_df = df[["jahr", *cf_spalten]].copy()
    for col in cf_spalten:
        display_df[col] = display_df[col].round(0)
    display_df.columns = [
        txt("oberflaeche.projekt_col_jahr"), txt("oberflaeche.projekt_col_operativ"),
        txt("oberflaeche.projekt_col_investition"),
        txt("oberflaeche.projekt_col_finanzierung"),
        txt("oberflaeche.projekt_col_gesamt"), txt("oberflaeche.projekt_col_kumuliert"),
    ]
    st.dataframe(display_df, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Erlöse
# ---------------------------------------------------------------------------


def render_revenue_tab(result, df) -> None:
    ea = result.effective_assumptions

    section_title(txt("oberflaeche.dashboard_verguetung_marktwert_zeitverlauf"))
    st.caption(txt("oberflaeche.projekt_verguetung_beschreibung"))
    st.plotly_chart(
        charts.verguetung_chart(
            df, ea.eag_zuschlagswert_effektiv_ct_kwh, ea.eag_foerderdauer_jahre
        ),
        width="stretch",
    )

    section_title(txt("oberflaeche.dashboard_markterloes_vs_praemie"))
    st.caption(txt("oberflaeche.projekt_markterloes_praemie_beschreibung"))
    st.plotly_chart(charts.revenue_split_chart(df), width="stretch")

    betrieb = df[df["jahr"] >= 1]
    erloes_gesamt = float(betrieb["erloes_eur"].sum())
    praemie_gesamt = float(betrieb["erloes_praemie_eur"].sum())
    anteil = praemie_gesamt / erloes_gesamt if erloes_gesamt else 0.0
    st.info(txt("oberflaeche.projekt_praemienanteil_info",
                   anteil=fmt_pct(anteil, 1), betrag=fmt_eur(praemie_gesamt)))

    section_title(txt("oberflaeche.dashboard_umsatzerloese_jahr"))
    st.plotly_chart(charts.revenue_chart(df), width="stretch")


# ---------------------------------------------------------------------------
# Tab: Finanzierung
# ---------------------------------------------------------------------------


def render_financing_tab(result, df, project) -> None:
    ea = result.effective_assumptions
    fremdkapital = ea.capex_total_eur * (1 - ea.eigenkapitalquote_pct)

    dscr_df = df.dropna(subset=["dscr"]).copy()
    if dscr_df.empty:
        st.info(txt("oberflaeche.projekt_kein_dscr"))
    else:
        section_title(txt("oberflaeche.dashboard_dscr"))
        st.plotly_chart(charts.dscr_chart(dscr_df), width="stretch")

        section_title(txt("oberflaeche.dashboard_schuldenprofil"))
        st.caption(txt("oberflaeche.projekt_schuldenprofil_beschreibung"))
        st.plotly_chart(charts.debt_profile_chart(df, fremdkapital), width="stretch")

    col_kap, col_capex = st.columns(2)
    with col_kap:
        section_title(txt("oberflaeche.dashboard_kapitalstruktur"))
        st.plotly_chart(
            charts.kapitalstruktur_donut_chart(
                ea.capex_total_eur * ea.eigenkapitalquote_pct, fremdkapital
            ),
            width="stretch",
        )
    with col_capex:
        section_title(txt("oberflaeche.dashboard_investitionsstruktur"))
        capex = project.capex
        posten = {
            txt("oberflaeche.projekt_capex_epc"): capex.epc_eur,
            txt("oberflaeche.projekt_capex_netzanschluss"): capex.netzanschluss_eur,
            txt("oberflaeche.projekt_capex_trasse"): capex.trasse_eur,
            txt("oberflaeche.projekt_capex_widmung"): capex.widmung_eur,
            txt("oberflaeche.projekt_capex_genehmigung"): capex.genehmigung_eur,
            txt("oberflaeche.projekt_capex_sonstige_extern"): capex.sonstige_extern_eur,
            txt("oberflaeche.projekt_capex_agm"): capex.agm_eur,
            txt("oberflaeche.projekt_capex_ma"): capex.m_and_a_eur,
            txt("oberflaeche.projekt_capex_poenale_puffer"): capex.poenale_puffer_eur,
            # Frei benannte Zusatzpositionen des Projekts - erscheinen mit
            # ihrer eigenen Bezeichnung als eigenes Segment.
            **{z.name: z.betrag_eur for z in capex.zusatzpositionen},
        }
        if any(v > 0 for v in posten.values()):
            st.plotly_chart(charts.capex_donut_chart(posten), width="stretch")
        else:
            st.info(txt("oberflaeche.projekt_keine_investitionspositionen"))

    section_title(txt("oberflaeche.dashboard_npv_sensitivitaet"))
    st.caption(txt("oberflaeche.projekt_npv_sensitivitaet_beschreibung"))
    st.plotly_chart(
        charts.npv_curve_chart(result.npv_curve.copy(), result.kpis.equity_irr),
        width="stretch",
    )

    if not dscr_df.empty:
        dscr_display = dscr_df[["jahr", "dscr"]].copy()
        dscr_display["dscr"] = dscr_display["dscr"].round(2)
        dscr_display.columns = [
            txt("oberflaeche.projekt_col_jahr"), txt("oberflaeche.projekt_col_dscr"),
        ]
        with st.expander(txt("oberflaeche.projekt_dscr_tabelle_titel")):
            st.dataframe(dscr_display, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Sensitivität (Tornado, Heatmap, EAG-Varianten, Gebotsassistent)
# ---------------------------------------------------------------------------

_ACHSEN_NAMEN = {k: name for k, (name, _) in HEATMAP_ACHSEN.items()}


def render_sensitivity_tab(result, project, project_id: str) -> None:
    section_title(txt("oberflaeche.dashboard_tornado"))
    st.caption(txt("oberflaeche.projekt_tornado_beschreibung"))
    tornado_df = services.get_tornado(project_id)
    if tornado_df is not None and not tornado_df.empty:
        st.plotly_chart(charts.tornado_chart(tornado_df), width="stretch")

    st.divider()
    section_title(txt("oberflaeche.dashboard_irr_landkarte"))
    st.caption(txt("oberflaeche.projekt_irr_landkarte_beschreibung"))
    col_x, col_y, col_ziel = st.columns([1.4, 1.4, 1])
    achse_x = col_x.selectbox(
        txt("oberflaeche.projekt_treiber_x_label"), list(_ACHSEN_NAMEN),
        format_func=_ACHSEN_NAMEN.get, index=0, key=f"hm_x_{project_id}",
    )
    optionen_y = [k for k in _ACHSEN_NAMEN if k != achse_x]
    achse_y = col_y.selectbox(
        txt("oberflaeche.projekt_treiber_y_label"), optionen_y,
        format_func=_ACHSEN_NAMEN.get, index=0, key=f"hm_y_{project_id}",
    )
    ziel_irr_pct = col_ziel.number_input(
        txt("oberflaeche.projekt_ziel_irr_label"), 0.0, 20.0, 8.0, 0.25,
        key=f"hm_ziel_{project_id}",
    )
    with st.spinner(txt("oberflaeche.projekt_irr_raster_spinner")):
        grid = services.get_irr_heatmap(project_id, achse_x, achse_y)
    if grid is not None:
        st.plotly_chart(
            charts.irr_heatmap_chart(
                grid, _ACHSEN_NAMEN[achse_x], _ACHSEN_NAMEN[achse_y],
                ziel_irr_pct / 100,
            ),
            width="stretch",
        )

    st.divider()
    section_title(txt("oberflaeche.dashboard_gebotsassistent"))
    st.caption(txt("oberflaeche.projekt_gebotsassistent_beschreibung"))
    col_be, col_res = st.columns([1, 2])
    ziel_gebot_pct = col_be.number_input(
        txt("oberflaeche.projekt_ziel_ek_rendite_label"), 0.0, 20.0, 8.0, 0.25,
        key=f"be_ziel_{project_id}",
    )
    break_even = services.get_break_even_zuschlag(project_id, ziel_gebot_pct / 100)
    with col_res:
        if break_even is None:
            st.error(txt("oberflaeche.projekt_breakeven_nicht_erreichbar"))
        elif break_even <= 0.5:
            st.success(txt("oberflaeche.projekt_breakeven_ohne_praemie"))
        else:
            delta = project.eag_zuschlagswert_ct_kwh - break_even
            st.success(txt(
                "oberflaeche.projekt_breakeven_ergebnis",
                breakeven=fmt_ct_kwh(break_even),
                angesetzt=fmt_ct_kwh(project.eag_zuschlagswert_ct_kwh),
                label=txt("oberflaeche.projekt_puffer") if delta >= 0
                else txt("oberflaeche.projekt_fehlbetrag"),
                differenz=fmt_ct_kwh(abs(delta)),
            ))

    st.divider()
    section_title(txt("oberflaeche.dashboard_eag_varianten"))
    sens_df = services.get_eag_sensitivity(project_id)
    if sens_df is None or sens_df.empty:
        st.info(txt("oberflaeche.projekt_keine_sensitivitaetsdaten"))
        return
    st.plotly_chart(charts.eag_sensitivity_chart(sens_df), width="stretch")

    sens_display = sens_df.copy()
    sens_display["eag_zuschlagswert_ct_kwh"] = sens_display[
        "eag_zuschlagswert_ct_kwh"
    ].round(3)
    sens_display["equity_irr"] = sens_display["equity_irr"].apply(fmt_pct)
    sens_display["npv_eur"] = sens_display["npv_eur"].round(0)
    sens_display = sens_display[
        ["variante", "eag_zuschlagswert_ct_kwh", "equity_irr", "npv_eur"]
    ]
    sens_display.columns = [
        txt("oberflaeche.projekt_col_variante"), txt("oberflaeche.projekt_col_eag_zuschlag"),
        txt("oberflaeche.projekt_col_ek_rendite"), txt("oberflaeche.projekt_col_npv"),
    ]
    with st.expander(txt("oberflaeche.projekt_variantentabelle_titel")):
        st.dataframe(sens_display, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Monte Carlo
# ---------------------------------------------------------------------------


def render_monte_carlo_tab(project_id: str, diskontsatz: float) -> None:
    section_title(txt("oberflaeche.dashboard_monte_carlo"))
    st.caption(txt("oberflaeche.projekt_mc_beschreibung"))

    with st.expander(txt("oberflaeche.projekt_mc_unsicherheiten_titel")):
        col1, col2, col3, col4 = st.columns(4)
        s_prod = col1.slider(txt("oberflaeche.projekt_mc_spez_ertrag"),
                             0.0, 15.0, 5.0, 0.5, key=f"mc_prod_{project_id}")
        s_markt = col2.slider(txt("oberflaeche.projekt_mc_marktwert_niveau"),
                              0.0, 30.0, 10.0, 0.5, key=f"mc_markt_{project_id}")
        s_capex = col3.slider(txt("oberflaeche.projekt_mc_investitionskosten"),
                              0.0, 15.0, 5.0, 0.5, key=f"mc_capex_{project_id}")
        s_opex = col4.slider(txt("oberflaeche.projekt_mc_betriebskosten"),
                             0.0, 15.0, 5.0, 0.5, key=f"mc_opex_{project_id}")
        n_laeufe = st.select_slider(
            txt("oberflaeche.projekt_mc_anzahl_laeufe_label"),
            options=[200, 400, 600, 1000], value=400,
            key=f"mc_n_{project_id}",
            help=txt("oberflaeche.projekt_mc_anzahl_laeufe_hilfe"),
        )

    sigmas = {
        "produktion": s_prod / 100, "marktwert": s_markt / 100,
        "capex": s_capex / 100, "opex": s_opex / 100,
    }

    gebots_key = None
    gebot_aktiv = st.toggle(
        txt("oberflaeche.projekt_mc_gebot_toggle_label"),
        value=False, key=f"mc_gebot_{project_id}",
        help=txt("oberflaeche.projekt_mc_gebot_toggle_hilfe"),
    )
    if gebot_aktiv:
        modell = services.get_auktions_modell()
        letzte = modell.letzte_runde
        mc_grundlage_letzte = txt("oberflaeche.projekt_mc_grundlage_letzte")
        mc_modus_label = st.radio(
            txt("oberflaeche.projekt_mc_grundlage_label"),
            [mc_grundlage_letzte, txt("oberflaeche.projekt_mc_grundlage_prognose")],
            horizontal=True, key=f"mc_gebot_modus_{project_id}",
        )
        if mc_modus_label == mc_grundlage_letzte:
            gebots_key = ("letzte",)
        else:
            cap = float(letzte.ausschreibung.preisobergrenze_ct)
            sigma_pm_mc = st.slider(
                txt("oberflaeche.projekt_mc_unsicherheit_grenzzuschlag_label"),
                0.15, 0.8, 0.55, 0.05, key=f"mc_gebot_sigma_{project_id}",
            )
            gebots_key = ("prognose", cap, sigma_pm_mc)  # Ordnung/λ: Standard (2, alle 1)

    # st.tabs rendert alle Tabs bei jedem Rerun - die Simulation laeuft
    # deshalb erst nach explizitem Start (danach haelt der Cache die
    # Ergebnisse, solange sich Projekt/Annahmen/Parameter nicht aendern).
    start_key = f"mc_gestartet_{project_id}"
    if not st.session_state.get(start_key):
        if st.button(txt("oberflaeche.projekt_mc_start_button"), type="primary",
                    key=f"mc_start_{project_id}"):
            st.session_state[start_key] = True
            st.rerun()
        return

    with st.spinner(txt("oberflaeche.projekt_mc_simulation_spinner", n=n_laeufe)):
        mc = services.get_monte_carlo(
            project_id, n_laeufe, sigmas, diskontsatz, gebots_key
        )
    if mc is None:
        st.error(txt("oberflaeche.projekt_simulation_fehlgeschlagen"))
        return

    irr = mc.irr_gueltig
    if len(irr) == 0:
        st.error(txt("oberflaeche.projekt_keine_berechenbare_irr"))
        return
    p10, p50, p90 = (float(np.percentile(irr, q)) for q in (10, 50, 90))

    ziel_pct = st.slider(
        txt("oberflaeche.projekt_mc_ziel_rendite_label"),
        0.0, 15.0, 8.0, 0.25, key=f"mc_ziel_{project_id}",
    )
    prob = mc.wahrscheinlichkeit_irr_ueber(ziel_pct / 100)

    render_kpi_row(
        [
            (txt("oberflaeche.projekt_mc_kpi_p10"), fmt_pct(p10)),
            (txt("oberflaeche.projekt_mc_kpi_p50"), fmt_pct(p50)),
            (txt("oberflaeche.projekt_mc_kpi_p90"), fmt_pct(p90)),
            (txt("oberflaeche.projekt_mc_kpi_p_irr",
                ziel=fmt_number(ziel_pct, 2)), fmt_pct(prob, 0)),
            (txt("oberflaeche.projekt_mc_kpi_npv_median",
                satz=fmt_number(diskontsatz * 100, 2)),
             fmt_eur(float(np.median(mc.npv)))),
        ],
        group="mc",
    )

    nicht_berechenbar = len(mc.irr) - len(irr)
    if nicht_berechenbar:
        st.caption(txt("oberflaeche.projekt_mc_nicht_berechenbar",
                       anzahl=nicht_berechenbar, gesamt=len(mc.irr)))

    section_title(txt("oberflaeche.dashboard_verteilung_ek_rendite"))
    st.plotly_chart(charts.mc_irr_histogram(irr, p10, p50, p90), width="stretch")

    section_title(txt("oberflaeche.dashboard_bandbreite_cashflow"))
    st.caption(txt("oberflaeche.projekt_mc_bandbreite_beschreibung"))
    st.plotly_chart(charts.mc_fan_chart(mc), width="stretch")


# ---------------------------------------------------------------------------
# Tab: Szenarien
# ---------------------------------------------------------------------------


def render_scenario_tab(result, project_id: str, diskontsatz: float) -> None:
    section_title(txt("oberflaeche.dashboard_marktpreisszenarien_vergleich"))
    st.caption(txt(
        "oberflaeche.projekt_szenarien_beschreibung",
        szenario=result.effective_assumptions.marktpreisszenario_name,
    ))
    vergleich = services.get_scenario_comparison(project_id, diskontsatz)
    if vergleich is None or vergleich.kennzahlen.empty:
        st.info(txt("oberflaeche.projekt_keine_marktpreisszenarien"))
        return

    st.plotly_chart(charts.scenario_bar_chart(vergleich.kennzahlen), width="stretch")

    section_title(txt("oberflaeche.dashboard_kumulierter_cf_szenario"))
    st.plotly_chart(charts.scenario_cum_chart(vergleich.kum_cashflows), width="stretch")

    tabelle = vergleich.kennzahlen.copy()
    tabelle["equity_irr"] = tabelle["equity_irr"].apply(fmt_pct)
    tabelle["npv_eur"] = tabelle["npv_eur"].round(0)
    tabelle["erloes_gesamt_eur"] = tabelle["erloes_gesamt_eur"].round(0)
    tabelle.columns = [
        txt("oberflaeche.projekt_col_szenario"), txt("oberflaeche.projekt_col_ek_rendite"),
        txt("oberflaeche.projekt_col_npv_bei", satz=fmt_number(diskontsatz * 100, 2)),
        txt("oberflaeche.projekt_col_erloese_gesamt"),
    ]
    st.dataframe(tabelle, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Tab: Annahmen
# ---------------------------------------------------------------------------


def render_assumptions_tab(result) -> None:
    """Transparenz-Tab: der vollstaendig aufgeloeste Parametersatz, mit dem
    dieses Projekt tatsaechlich gerechnet wurde (Projektmaske + Globale
    Annahmen nach dem Merge)."""
    ea = result.effective_assumptions
    st.caption(txt(
        "oberflaeche.projekt_annahmen_beschreibung",
        szenario=ea.marktpreisszenario_name,
    ))
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.markdown(txt("oberflaeche.projekt_annahmen_anlage_titel"))
        st.markdown(txt(
            "oberflaeche.projekt_annahmen_anlage_zeilen",
            leistung=fmt_kwp(ea.nennleistung_kwp),
            vbh=f"{ea.vollbenutzungsstunden_kwh_kwp:.0f}",
            degradation=fmt_pct(ea.degradation_pct_pa),
            sicherheitsabschlag=fmt_pct(ea.sicherheitsabschlag_pct),
            betrachtungsdauer=ea.betriebsdauer_jahre,
        ))
    with col_b:
        st.markdown(txt("oberflaeche.projekt_annahmen_erloese_titel"))
        regel_text = (
            txt("oberflaeche.projekt_annahmen_regel_6h")
            if ea.negative_stunden_regel == NegativeStundenRegel.SECHS_STUNDEN
            else txt("oberflaeche.projekt_annahmen_regel_1h")
        )
        modus_text = (
            txt("oberflaeche.projekt_annahmen_modus_abregelung")
            if ea.negative_stunden_modus == NegativeStundenModus.ABREGELUNG
            else txt("oberflaeche.projekt_annahmen_modus_marktwert")
        )
        st.markdown(txt(
            "oberflaeche.projekt_annahmen_erloese_zeilen",
            zuschlag=fmt_ct_kwh(ea.eag_zuschlagswert_effektiv_ct_kwh),
            foerderdauer=ea.eag_foerderdauer_jahre,
            inflation=fmt_pct(ea.marktpreis_inflation_pct_pa),
            basisjahr=ea.marktpreis_inflation_basisjahr,
            regel=regel_text,
            gewichtung=fmt_pct(ea.negative_stunden_gewichtung_pct, 0),
            modus=modus_text,
        ))
    with col_c:
        st.markdown(txt("oberflaeche.projekt_annahmen_finanzierung_titel"))
        st.markdown(txt(
            "oberflaeche.projekt_annahmen_finanzierung_zeilen",
            ek_quote=fmt_pct(ea.eigenkapitalquote_pct, 0),
            fk_zins=fmt_pct(ea.fremdkapitalzins_pct),
            laufzeit=ea.kreditlaufzeit_jahre,
            tilgungsart=ea.tilgungsart.value,
            anlaufjahr=txt("oberflaeche.projekt_ja")
            if ea.tilgungsfreies_anlaufjahr else txt("oberflaeche.projekt_nein"),
            steuermodus=ea.tax_modus.value,
            steuersatz=fmt_pct(ea.steuersatz_pct, 0),
        ))
