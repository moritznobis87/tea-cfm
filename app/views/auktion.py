"""
Seite "Ausschreibung": Analyse der historischen EAG-Marktpraemien-
ausschreibungen (PV, Oesterreich), Prognose der Gebotsverteilung der
naechsten Runde (Price-Taker-Modell, engine/auktion.py) und Ableitung
eines empfohlenen Gebotswerts fuer eine gewuenschte Zuschlags-
wahrscheinlichkeit - mit Uebergabe an das Cashflow-Modell.
"""

from __future__ import annotations

import streamlit as st

from app import services
from app.components import charts
from app.components.kpi import render_kpi_row
from app.config import STATE_SELECTED_PROJECT
from app.formatting import fmt_ct_kwh, fmt_number, fmt_pct
from app.theme import section_title
from texte import txt

#: Session-Schluessel, ueber den das Projektformular den empfohlenen
#: Gebotswert als Vorbelegung uebernimmt (manuell ueberschreibbar).
STATE_EMPFOHLENES_GEBOT = "empfohlenes_gebot_ct"


def render_auktion() -> None:
    runden, df = services.get_ausschreibungen()
    modell = services.get_auktions_modell()
    letzte = modell.letzte_runde

    st.markdown(txt("oberflaeche.auktion_intro_titel"))
    st.caption(txt("oberflaeche.auktion_intro_beschreibung"))

    # --- Historie ------------------------------------------------------------
    section_title(txt("oberflaeche.auktion_historie_sektion"))
    st.plotly_chart(charts.auktion_historie_chart(df), width="stretch")
    st.caption(txt("oberflaeche.auktion_historie_beschreibung"))
    section_title(txt("oberflaeche.auktion_verteilungen_sektion"))
    st.caption(txt("oberflaeche.auktion_verteilungen_beschreibung"))
    tab_dichte, tab_cdf = st.tabs([txt("oberflaeche.auktion_tab_dichte"), txt("oberflaeche.auktion_tab_verteilungsfunktion")])
    with tab_dichte:
        st.plotly_chart(
            charts.auktion_historische_verteilungen_chart(modell, "dichte"),
            width="stretch",
        )
    with tab_cdf:
        st.plotly_chart(
            charts.auktion_historische_verteilungen_chart(
                modell, "verteilungsfunktion"
            ),
            width="stretch",
        )

    with st.expander(txt("oberflaeche.auktion_datentabelle_titel")):
        anzeige = df.copy()
        anzeige["bezuschlagt_pct"] = (
            anzeige["bezuschlagt_mw"] / anzeige["ausgeschrieben_mw"] * 100
        ).round(0)
        st.dataframe(anzeige, width="stretch", hide_index=True)
        st.markdown(txt("oberflaeche.auktion_kalibrierung_titel"))
        import pandas as pd

        st.dataframe(pd.DataFrame([
            {
                "Runde": f.ausschreibung.datum,
                "r (Gebote/Ausschr.)": round(f.wettbewerbsquote, 2),
                "r latent": "ja" if f.wettbewerbsquote_latent else "nein",
                "Lage µ/Obergrenze": round(f.mu_rel, 3),
                "Konzentration κ": round(f.kappa, 1),
            }
            for f in sorted(modell.fits, key=lambda f: f.ausschreibung.datum)
        ]), width="stretch", hide_index=True)

    with st.expander(txt("oberflaeche.auktion_modellwahl_titel")):
        vergleich, backtest = services.get_auktions_validierung()
        st.markdown(txt("oberflaeche.auktion_familienvergleich_text"))
        st.dataframe(vergleich, width="stretch", hide_index=True)
        st.markdown(txt("oberflaeche.auktion_backtest_intro"))
        st.dataframe(backtest, width="stretch", hide_index=True)
        st.caption(txt("oberflaeche.auktion_backtest_hinweis"))

    st.divider()

    # --- Prognose naechste Runde ---------------------------------------------
    section_title(txt("oberflaeche.auktion_zuschlagswert_bestimmen"))
    grundlage_letzte = txt("oberflaeche.auktion_grundlage_letzte")
    grundlage_prognose = txt("oberflaeche.auktion_grundlage_prognose")
    modus_label = st.radio(
        txt("oberflaeche.auktion_grundlage_label"),
        [grundlage_letzte, grundlage_prognose],
        horizontal=True,
        help=txt("oberflaeche.auktion_grundlage_hilfe"),
    )
    modus = "letzte" if modus_label == grundlage_letzte else "prognose"

    if modus == "prognose":
        col1, col2, col3 = st.columns(3)
        cap = col1.number_input(
            txt("oberflaeche.auktion_preisobergrenze_label"), 1.0, 15.0,
            float(letzte.ausschreibung.preisobergrenze_ct), 0.01,
            help=txt("oberflaeche.auktion_preisobergrenze_hilfe"),
        )
        ordnung = col2.selectbox(
            txt("oberflaeche.auktion_differenzordnung_label"), [1, 2, 3], index=1,
            help=txt("oberflaeche.auktion_differenzordnung_hilfe"),
        )
        sigma_pm = col3.slider(
            txt("oberflaeche.auktion_unsicherheit_label"), 0.15, 0.8, 0.55, 0.05,
            help=txt("oberflaeche.auktion_unsicherheit_hilfe"),
        )
        lambdas = tuple(
            st.slider(
                txt("oberflaeche.auktion_daempfung_label", k=k, k1=k + 1),
                0.0, 1.0, 1.0, 0.05, key=f"auktion_lambda_{k}",
                help=txt("oberflaeche.auktion_daempfung_hilfe"),
            )
            for k in range(1, int(ordnung))
        )
        prognose = services.get_gebots_prognose("prognose", cap, sigma_pm,
                                                int(ordnung), lambdas)
        st.caption(txt(
            "oberflaeche.auktion_implizierte_quote",
            wert=f"{prognose.wettbewerbsquote:,.2f}".replace(".", ","),
        ))
        with st.expander(txt("oberflaeche.auktion_methodik_titel")):
            wett = sorted(
                (f.ausschreibung for f in modell.fits
                 if not f.ausschreibung.unterzeichnet),
                key=lambda a: a.datum,
            )
            maxes = [a.zuschlag_max_ct for a in wett]
            mittels = [a.zuschlag_mittel_ct for a in wett]
            formel = (
                r"$\widehat{\Delta}^{(m)}_{t+1} = \Delta^{(m)}_t \quad\big|\quad "
                r"\widehat{\Delta}^{(k)}_{t+1} = \Delta^{(k)}_t + "
                r"\lambda_k \cdot \widehat{\Delta}^{(k+1)}_{t+1} "
                r"\quad\big|\quad \hat{x}_{t+1} = x_t + \widehat{\Delta}^{(1)}_{t+1}$"
            )
            st.markdown(
                txt("oberflaeche.auktion_methodik_intro") + "\n\n" + formel
                + "\n\n" + txt("oberflaeche.auktion_methodik_erklaerung")
                + "\n\n" + txt(
                    "oberflaeche.auktion_methodik_ergebnis",
                    maxes_kette=" → ".join(
                        f"{v:,.2f}".replace(".", ",") for v in maxes
                    ),
                    grenzzuschlag_wert=fmt_ct_kwh(prognose.grenzzuschlag_zentral_ct),
                    mittels_kette=" → ".join(
                        f"{v:,.2f}".replace(".", ",") for v in mittels
                    ),
                    mittel_wert=fmt_ct_kwh(prognose.mittel_prognose_ct),
                )
                + "\n\n" + txt("oberflaeche.auktion_methodik_schluss")
            )
    else:
        prognose = services.get_gebots_prognose("letzte")
        st.caption(txt(
            "oberflaeche.auktion_letzte_gesetzt_beschreibung",
            datum=letzte.ausschreibung.datum.strftime("%d.%m.%Y"),
            grenzzuschlag=fmt_ct_kwh(prognose.grenzzuschlag_zentral_ct),
            mittel=fmt_ct_kwh(letzte.ausschreibung.zuschlag_mittel_ct),
            minimum=fmt_ct_kwh(letzte.ausschreibung.zuschlag_min_ct),
        ))

    ziel_prob = st.select_slider(
        txt("oberflaeche.auktion_risikoneigung_label"),
        options=[0.50, 0.60, 0.70, 0.80, 0.90, 0.95], value=0.80,
        format_func=lambda v: f"{v * 100:.0f} %",
        help=txt("oberflaeche.auktion_risikoneigung_hilfe"),
    )
    empfohlen = prognose.empfohlenes_gebot(ziel_prob)

    # Harte Ueberschreibung: der manuell gesetzte Wert gewinnt immer.
    col_o1, col_o2 = st.columns([1, 2])
    ueberschreiben = col_o1.toggle(
        txt("oberflaeche.auktion_ueberschreiben_label"),
        value=False, key="auktion_override",
    )
    if ueberschreiben:
        effektiver_wert = col_o2.number_input(
            txt("oberflaeche.auktion_zuschlagswert_label"), 0.1, 15.0,
            float(round(empfohlen, 2)), 0.01, key="auktion_override_wert",
        )
    else:
        effektiver_wert = float(round(empfohlen, 2))

    render_kpi_row(
        [
            (txt("oberflaeche.auktion_kpi_zuschlagswert")
             + (txt("oberflaeche.auktion_kpi_manuell_suffix") if ueberschreiben
                else txt("oberflaeche.auktion_kpi_empfohlen_suffix")),
             fmt_ct_kwh(effektiver_wert)),
            (txt("oberflaeche.auktion_kpi_wahrscheinlichkeit"),
             fmt_pct(prognose.zuschlagswahrscheinlichkeit(effektiver_wert), 0)),
            (txt("oberflaeche.auktion_kpi_grenzzuschlag")
             + (txt("oberflaeche.auktion_kpi_prognose_suffix") if modus == "prognose"
                else txt("oberflaeche.auktion_kpi_ist_letzte_suffix")),
             fmt_ct_kwh(prognose.grenzzuschlag_zentral_ct)),
            (txt("oberflaeche.auktion_kpi_oe_zuschlagswert")
             + (txt("oberflaeche.auktion_kpi_prognose_suffix") if modus == "prognose"
                else txt("oberflaeche.auktion_kpi_ist_suffix")),
             fmt_ct_kwh(prognose.gebot_mittel_ct if modus == "prognose"
                        else letzte.ausschreibung.zuschlag_mittel_ct)),
            (txt("oberflaeche.auktion_kpi_letzter_grenzzuschlag"),
             fmt_ct_kwh(letzte.ausschreibung.zuschlag_max_ct)),
        ],
        group="auktion",
    )

    col_links, col_rechts = st.columns(2)
    with col_links:
        section_title(txt("oberflaeche.auktion_verteilung_zuschlagswerte"))
        st.plotly_chart(
            charts.gebotsdichte_chart(prognose, effektiver_wert), width="stretch"
        )
        st.caption(
            txt("oberflaeche.auktion_dichte_beschreibung")
            + (txt("oberflaeche.auktion_dichte_band_suffix")
               if modus == "prognose" else "")
        )
    with col_rechts:
        section_title(txt("oberflaeche.auktion_wert_wahrscheinlichkeit"))
        st.plotly_chart(
            charts.zuschlagskurve_chart(prognose,
                prognose.zuschlagswahrscheinlichkeit(effektiver_wert),
                effektiver_wert),
            width="stretch",
        )
        st.caption(
            txt("oberflaeche.auktion_kurve_beschreibung_prognose")
            if modus == "prognose" else
            txt("oberflaeche.auktion_kurve_beschreibung_letzte")
        )

    uebersicht = " · ".join(
        f"{int(z * 100)} % → {fmt_ct_kwh(prognose.empfohlenes_gebot(z))}"
        for z in (0.50, 0.60, 0.70, 0.80, 0.90, 0.95)
    )
    st.info(txt("oberflaeche.auktion_werte_nach_risikoneigung", uebersicht=uebersicht))

    st.divider()

    # --- Uebergabe an das Cashflow-Modell -------------------------------------
    section_title(txt("oberflaeche.auktion_uebergabe_cashflow"))
    st.session_state[STATE_EMPFOHLENES_GEBOT] = float(round(effektiver_wert, 2))
    st.caption(txt("oberflaeche.auktion_uebergabe_beschreibung"))
    projekte = services.list_project_files()
    if projekte:
        namen = {pid: services.get_project(pid).name for pid in projekte}
        col_a, col_b = st.columns([2, 1])
        ziel_projekt = col_a.selectbox(
            txt("oberflaeche.auktion_projekt_label"), list(projekte),
            format_func=namen.get, key="auktion_ziel_projekt",
        )
        if col_b.button(
            txt("oberflaeche.auktion_uebernehmen_btn",
                wert=fmt_number(effektiver_wert, 2)),
            width="stretch", type="primary",
        ):
            projekt = services.get_project(ziel_projekt)
            projekt.eag_zuschlagswert_ct_kwh = float(round(effektiver_wert, 2))
            services.save_project(projekt, projekte[ziel_projekt])
            st.session_state[STATE_SELECTED_PROJECT] = ziel_projekt
            st.success(txt(
                "oberflaeche.auktion_uebernommen_erfolg",
                name=projekt.name, wert=fmt_ct_kwh(effektiver_wert),
            ))
