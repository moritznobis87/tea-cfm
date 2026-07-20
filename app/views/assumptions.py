"""
Seite "Globale Annahmen": zentrale Verwaltung von Marktpreisszenarien,
Standardbetriebskosten, technischen Annahmen, Finanzierung und Steuern.

Aenderungen wirken erst nach explizitem "Speichern" - und dann automatisch
auf ALLE Projekte (die Bewertungs-Caches werden dabei invalidiert, siehe
services.save_global_assumptions).
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import services
from engine import (
    DirektvermarktungsModus,
    MarktpreisSzenario,
    NegativeStundenModus,
    NegativeStundenRegel,
    OpexItem,
    TaxModus,
    TilgungsArt,
)
from texte import txt


def render_assumptions() -> None:
    st.subheader(txt("oberflaeche.nav_globale_annahmen"))
    st.caption(txt("oberflaeche.annahmen_hinweis"))

    ga = services.get_global_assumptions()

    # --- Marktpreisszenarien -------------------------------------------------
    with st.expander(txt("oberflaeche.annahmen_marktpreisszenarien_titel"), expanded=True):
        st.caption(txt("oberflaeche.annahmen_szenarien_hinweis"))

        st.markdown(txt("oberflaeche.annahmen_inflation_marktwerte_titel"))
        st.caption(txt("oberflaeche.annahmen_inflation_marktwerte_hinweis"))
        col_infl1, col_infl2, col_infl3 = st.columns(3)
        marktpreis_inflation = col_infl1.number_input(
            txt("oberflaeche.annahmen_inflation_marktwerte_label"), min_value=0.0,
            value=ga.marktpreis_inflation_pct_pa * 100, step=0.1,
        )
        marktpreis_basisjahr = col_infl2.number_input(
            txt("oberflaeche.annahmen_basisjahr_label"), min_value=2000,
            max_value=2100, value=ga.marktpreis_inflation_basisjahr, step=1,
            help=txt("oberflaeche.annahmen_basisjahr_hilfe"),
        )
        kosten_inflation = col_infl3.number_input(
            txt("oberflaeche.annahmen_kosteninflation_label"), min_value=0.0,
            value=ga.kosten_inflation_pct_pa * 100, step=0.1,
            help=txt("oberflaeche.annahmen_kosteninflation_hilfe"),
        )

        st.markdown(txt("oberflaeche.annahmen_negative_stunden_gewichtung_titel"))
        st.caption(txt("oberflaeche.annahmen_negative_stunden_gewichtung_hinweis"))
        negative_stunden_gewichtung = st.slider(
            txt("oberflaeche.annahmen_gewichtung_label"), min_value=0, max_value=100,
            value=int(round(ga.negative_stunden_gewichtung_pct * 100)), step=5,
        )

        st.markdown(txt("oberflaeche.annahmen_praemienentfall_titel"))
        st.caption(txt("oberflaeche.annahmen_praemienentfall_hinweis"))
        regel_labels = {
            NegativeStundenRegel.SECHS_STUNDEN.value: (
                txt("oberflaeche.annahmen_regel_6h")
            ),
            NegativeStundenRegel.EINE_STUNDE.value: txt("oberflaeche.annahmen_regel_1h"),
        }
        regel_optionen = [r.value for r in NegativeStundenRegel]
        negative_stunden_regel = st.radio(
            txt("oberflaeche.annahmen_regel_label"),
            regel_optionen,
            format_func=lambda v: regel_labels[v],
            index=regel_optionen.index(ga.negative_stunden_regel.value),
            horizontal=True,
            label_visibility="collapsed",
        )

        st.markdown(txt("oberflaeche.annahmen_verhalten_negativ_titel"))
        neg_modus_labels = {
            NegativeStundenModus.ABREGELUNG.value: (
                txt("oberflaeche.annahmen_modus_abregelung")
            ),
            NegativeStundenModus.MARKTWERT.value: (
                txt("oberflaeche.annahmen_modus_marktwert")
            ),
        }
        neg_modus_optionen = [m.value for m in NegativeStundenModus]
        negative_stunden_modus = st.radio(
            txt("oberflaeche.annahmen_negativstunden_modus_label"),
            neg_modus_optionen,
            format_func=lambda v: neg_modus_labels[v],
            index=neg_modus_optionen.index(ga.negative_stunden_modus.value),
            label_visibility="collapsed",
            help=txt("oberflaeche.annahmen_negativstunden_modus_hilfe"),
        )

        edited_szenarien: dict[str, pd.DataFrame] = {}
        if not ga.marktpreisszenarien:
            st.info(txt("oberflaeche.annahmen_kein_szenario"))
        else:
            tabs = st.tabs([s.name for s in ga.marktpreisszenarien])
            for tab, szenario in zip(tabs, ga.marktpreisszenarien, strict=True):
                with tab:
                    jahre = sorted(
                        set(szenario.marktwert_solar_ct_kwh_je_kalenderjahr)
                        | set(szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr)
                        | set(szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr)
                    )
                    kurven_df = pd.DataFrame(
                        {
                            "Kalenderjahr": jahre,
                            "Marktwert Solar (ct/kWh)": [
                                szenario.marktwert_solar_ct_kwh_je_kalenderjahr.get(j)
                                for j in jahre
                            ],
                            "Erzeugungsmenge neg. Stunden 6h (%)": [
                                (
                                    szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr.get(
                                        j
                                    )
                                    or 0
                                )
                                * 100
                                for j in jahre
                            ],
                            "Erzeugungsmenge neg. Stunden 1h (%)": [
                                (
                                    szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr.get(
                                        j
                                    )
                                    or 0
                                )
                                * 100
                                for j in jahre
                            ],
                        }
                    )
                    st.caption(txt("oberflaeche.annahmen_erzeugung_negativ_hinweis"))
                    edited_szenarien[szenario.name] = st.data_editor(
                        kurven_df, width="stretch", hide_index=True,
                        num_rows="dynamic", key=f"kurven_editor_{szenario.name}",
                        column_config={
                            "Kalenderjahr": st.column_config.NumberColumn(
                                txt("oberflaeche.annahmen_col_kalenderjahr"),
                                format="%d",
                            ),
                            "Marktwert Solar (ct/kWh)": st.column_config.NumberColumn(
                                txt("oberflaeche.annahmen_col_marktwert_solar"),
                            ),
                            "Erzeugungsmenge neg. Stunden 6h (%)":
                                st.column_config.NumberColumn(
                                    txt("oberflaeche.annahmen_col_neg6h"),
                                ),
                            "Erzeugungsmenge neg. Stunden 1h (%)":
                                st.column_config.NumberColumn(
                                    txt("oberflaeche.annahmen_col_neg1h"),
                                ),
                        },
                    )

        st.divider()
        st.markdown(txt("oberflaeche.annahmen_neues_szenario_titel"))
        neuer_szenario_name = st.text_input(
            txt("oberflaeche.annahmen_neues_szenario_label"),
            key="neues_szenario_name",
            placeholder=txt("oberflaeche.annahmen_neues_szenario_platzhalter"),
        )
        if st.button(txt("oberflaeche.annahmen_szenario_hinzufuegen")) and neuer_szenario_name.strip():
            if neuer_szenario_name in ga.szenario_namen:
                st.error(txt("oberflaeche.annahmen_szenario_existiert_bereits"))
            else:
                ga.marktpreisszenarien.append(
                    MarktpreisSzenario(name=neuer_szenario_name.strip())
                )
                services.save_global_assumptions(ga)
                st.rerun()

    # --- Standardbetriebskosten ----------------------------------------------
    with st.expander(txt("oberflaeche.annahmen_standardbetriebskosten_titel")):
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
            column_config={
                "Position": st.column_config.TextColumn(
                    txt("oberflaeche.annahmen_col_position"),
                ),
                "EUR/kWp/Jahr": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_col_eur_kwp_jahr"),
                ),
                "Index %/Jahr": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_col_index_pct"),
                ),
                "Indexierung ab Jahr": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_col_index_ab_jahr"), format="%d",
                ),
            },
        )
        gemeindeabgabe = st.number_input(
            txt("oberflaeche.annahmen_gemeindeabgabe_label"),
            min_value=0.0, value=ga.gemeindeabgabe_eur_kwh * 1000, step=0.5,
            help=txt("oberflaeche.annahmen_gemeindeabgabe_hilfe"),
        )
        st.markdown(txt("oberflaeche.annahmen_direktvermarktung_titel"))
        dv_modus_absolut = txt("oberflaeche.annahmen_dv_modus_absolut")
        dv_modus_relativ = txt("oberflaeche.annahmen_dv_modus_relativ")
        dv_modus_label = st.radio(
            txt("oberflaeche.annahmen_dv_modus_label"),
            [dv_modus_absolut, dv_modus_relativ],
            index=0
            if ga.direktvermarktung_modus == DirektvermarktungsModus.ABSOLUT
            else 1,
            horizontal=True,
            help=txt("oberflaeche.annahmen_dv_modus_hilfe"),
        )
        dv_relativ = dv_modus_label == dv_modus_relativ
        col_dv1, col_dv2 = st.columns(2)
        direktvermarktungskosten = col_dv1.number_input(
            txt("oberflaeche.annahmen_dv_vorschlagswert_label"),
            min_value=0.0, value=ga.direktvermarktungskosten_eur_kwh * 1000,
            step=0.1,
            disabled=dv_relativ,
            help=txt("oberflaeche.annahmen_dv_vorschlagswert_hilfe"),
        )
        dv_pct_marktwert = col_dv2.number_input(
            txt("oberflaeche.annahmen_dv_anteil_marktwert_label"),
            min_value=0.0, max_value=100.0,
            value=ga.direktvermarktung_pct_marktwert * 100, step=0.5,
            disabled=not dv_relativ,
            help=txt("oberflaeche.annahmen_dv_anteil_marktwert_hilfe"),
        )

    # --- Technische Standardannahmen -------------------------------------------
    with st.expander(txt("oberflaeche.annahmen_technische_standardannahmen_titel"), expanded=True):
        st.caption(txt("oberflaeche.annahmen_technisch_hinweis"))
        col_deg, col_sich = st.columns(2)
        degradation = col_deg.number_input(
            txt("oberflaeche.annahmen_degradation_label"), min_value=0.0,
            value=ga.degradation_pct_pa * 100, step=0.05,
            help=txt("oberflaeche.annahmen_degradation_hilfe"),
        )
        sicherheitsabschlag = col_sich.number_input(
            txt("oberflaeche.annahmen_sicherheitsabschlag_label"),
            min_value=0.0, max_value=100.0,
            value=ga.sicherheitsabschlag_pct * 100, step=0.5,
            help=txt("oberflaeche.annahmen_sicherheitsabschlag_hilfe"),
        )

    # --- Foerderung, Finanzierung ----------------------------------------------
    with st.expander(txt("oberflaeche.annahmen_foerderung_finanzierung_titel"), expanded=True):
        col1, col2, col3 = st.columns(3)
        eag_foerderdauer = col1.number_input(
            txt("oberflaeche.annahmen_eag_foerderdauer_label"), min_value=1, value=ga.eag_foerderdauer_jahre
        )
        betriebsdauer = col2.number_input(
            txt("oberflaeche.annahmen_betrachtungsdauer_label"), min_value=1, value=ga.betriebsdauer_jahre
        )
        kreditlaufzeit = col3.number_input(
            txt("oberflaeche.annahmen_kreditlaufzeit_label"), min_value=1, value=ga.kreditlaufzeit_jahre
        )
        tilgungsart = st.selectbox(
            txt("oberflaeche.annahmen_tilgungsart_label"), [art.value for art in TilgungsArt],
            index=0 if ga.tilgungsart == TilgungsArt.ANNUITAET else 1,
        )
        tilgungsfreies_anlaufjahr = st.toggle(
            txt("oberflaeche.annahmen_tilgungsfreies_anlaufjahr_label"),
            value=ga.tilgungsfreies_anlaufjahr,
            help=txt("oberflaeche.annahmen_tilgungsfreies_anlaufjahr_hilfe"),
        )

    # --- Steuern ---------------------------------------------------------------
    with st.expander(txt("oberflaeche.annahmen_steuern_titel"), expanded=False):
        tax_modus_optionen = [modus.value for modus in TaxModus]
        tax_modus_labels = {
            "pauschal_auf_ebt": txt("oberflaeche.annahmen_steuermodus_pauschal"),
            "afa_koerperschaftsteuer": txt("oberflaeche.annahmen_steuermodus_afa"),
        }
        tax_modus = st.radio(
            txt("oberflaeche.annahmen_steuermodus_label"),
            tax_modus_optionen,
            format_func=lambda v: tax_modus_labels[v],
            index=tax_modus_optionen.index(ga.tax_modus.value),
            horizontal=True,
        )

        col4, col5 = st.columns(2)
        steuersatz = col4.number_input(
            txt("oberflaeche.annahmen_steuersatz_label"), min_value=0.0,
            value=ga.steuersatz_pct * 100, step=0.5,
            help=txt("oberflaeche.annahmen_steuersatz_hilfe"),
        )
        verlustvortrag_grenze = col5.number_input(
            txt("oberflaeche.annahmen_verlustvortrag_label"),
            min_value=0.0, max_value=100.0,
            value=ga.verlustvortrag_verrechnungsgrenze_pct * 100, step=5.0,
            help=txt("oberflaeche.annahmen_verlustvortrag_hilfe"),
        )

        if tax_modus == TaxModus.AFA_KOERPERSCHAFTSTEUER.value:
            col6, col7 = st.columns(2)
            afa_nutzungsdauer = col6.number_input(
                txt("oberflaeche.annahmen_afa_nutzungsdauer_label"), min_value=1,
                value=ga.afa_nutzungsdauer_jahre or 20,
                help=txt("oberflaeche.annahmen_afa_nutzungsdauer_hilfe"),
            )
            freibetrag = col7.number_input(
                txt("oberflaeche.annahmen_freibetrag_label"), min_value=0.0,
                value=ga.freibetrag_eur, step=100.0,
            )
        else:
            afa_nutzungsdauer = ga.afa_nutzungsdauer_jahre
            freibetrag = ga.freibetrag_eur
            st.caption(txt("oberflaeche.annahmen_afa_pauschal_hinweis"))

    # --- Speichern ---------------------------------------------------------------
    if st.button(txt("oberflaeche.btn_speichern"), type="primary"):
        neue_szenarien = []
        for szenario in ga.marktpreisszenarien:
            edited = edited_szenarien.get(szenario.name)
            if edited is None:
                neue_szenarien.append(szenario)
                continue
            neue_szenarien.append(
                MarktpreisSzenario(
                    name=szenario.name,
                    marktwert_solar_ct_kwh_je_kalenderjahr={
                        int(r["Kalenderjahr"]): float(r["Marktwert Solar (ct/kWh)"])
                        for _, r in edited.iterrows()
                        if pd.notna(r["Kalenderjahr"])
                        and pd.notna(r["Marktwert Solar (ct/kWh)"])
                    },
                    erzeugungsmenge_negativ_6h_pct_je_kalenderjahr={
                        int(r["Kalenderjahr"]): float(
                            r["Erzeugungsmenge neg. Stunden 6h (%)"]
                        )
                        / 100
                        for _, r in edited.iterrows()
                        if pd.notna(r["Kalenderjahr"])
                        and pd.notna(r["Erzeugungsmenge neg. Stunden 6h (%)"])
                    },
                    erzeugungsmenge_negativ_1h_pct_je_kalenderjahr={
                        int(r["Kalenderjahr"]): float(
                            r["Erzeugungsmenge neg. Stunden 1h (%)"]
                        )
                        / 100
                        for _, r in edited.iterrows()
                        if pd.notna(r["Kalenderjahr"])
                        and pd.notna(r["Erzeugungsmenge neg. Stunden 1h (%)"])
                    },
                )
            )
        ga.marktpreisszenarien = neue_szenarien
        ga.marktpreis_inflation_pct_pa = marktpreis_inflation / 100
        ga.kosten_inflation_pct_pa = kosten_inflation / 100
        ga.marktpreis_inflation_basisjahr = int(marktpreis_basisjahr)
        ga.negative_stunden_gewichtung_pct = negative_stunden_gewichtung / 100
        ga.negative_stunden_modus = NegativeStundenModus(negative_stunden_modus)
        ga.negative_stunden_regel = NegativeStundenRegel(negative_stunden_regel)

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
        ga.sicherheitsabschlag_pct = sicherheitsabschlag / 100
        ga.steuersatz_pct = steuersatz / 100
        ga.tilgungsart = TilgungsArt(tilgungsart)
        ga.tilgungsfreies_anlaufjahr = tilgungsfreies_anlaufjahr
        ga.gemeindeabgabe_eur_kwh = gemeindeabgabe / 1000
        ga.direktvermarktungskosten_eur_kwh = direktvermarktungskosten / 1000
        ga.direktvermarktung_modus = (
            DirektvermarktungsModus.RELATIV_MARKTWERT
            if dv_relativ
            else DirektvermarktungsModus.ABSOLUT
        )
        ga.direktvermarktung_pct_marktwert = dv_pct_marktwert / 100
        ga.tax_modus = TaxModus(tax_modus)
        ga.afa_nutzungsdauer_jahre = (
            int(afa_nutzungsdauer) if afa_nutzungsdauer else None
        )
        ga.freibetrag_eur = float(freibetrag)
        ga.verlustvortrag_verrechnungsgrenze_pct = verlustvortrag_grenze / 100

        services.save_global_assumptions(ga)
        st.success(txt("oberflaeche.annahmen_gespeichert"))
        st.rerun()
