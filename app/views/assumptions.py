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
from app.components import charts
from app.config import FLAGS_DIR, monate_kurz
from app.formatting import fmt_number
from engine import io_aurora
from engine.io_aurora import AuroraImportFehler
from engine import (
    DirektvermarktungsModus,
    GlobalAssumptions,
    MarktpreisSzenario,
    MarktSystem,
    NegativeStundenModus,
    NegativeStundenRegel,
    OpexItem,
    PraemienModell,
    TaxModus,
    TilgungsArt,
    Zeitaufloesung,
    ZinsMethode,
)
from texte import txt

#: Marktsystematik-Umschalter: Code -> (Flaggen-Datei, Textschluessel).
#: Gleiche Bild-Icon-Technik wie der Sprachumschalter in
#: streamlit_app.py (echte PNG-Flaggen statt Emoji, siehe Begruendung
#: dort und in texte.SPRACHEN).
_MARKT_SYSTEME: dict[MarktSystem, tuple[str, str]] = {
    MarktSystem.OESTERREICH: ("at", "oberflaeche.annahmen_markt_oesterreich"),
    MarktSystem.DEUTSCHLAND: ("de", "oberflaeche.annahmen_markt_deutschland"),
}


def _wechsle_markt_system(ga: GlobalAssumptions, ziel: MarktSystem) -> None:
    """Stellt die Marktsystematik als Paket um und speichert sofort.

    Oesterreich (EAG): 6h-Regel, Koerperschaftsteuer mit AfA, act/365.
    Deutschland (EEG): 1h-Regel, deutsche Gewerbesteuer, 30/360.
    Titelzeile und Marktpraemienseite folgen dem Schalter zur Laufzeit
    (streamlit_app.py bzw. app/views/auktion.py); die einzelnen Felder
    bleiben danach weiterhin manuell aenderbar.
    """
    ga.markt_system = ziel
    if ziel == MarktSystem.OESTERREICH:
        ga.negative_stunden_regel = NegativeStundenRegel.SECHS_STUNDEN
        ga.tax_modus = TaxModus.AFA_KOERPERSCHAFTSTEUER
        # Pflichtfeld des AfA-Modus (siehe GlobalAssumptions.check_afa_fields).
        ga.afa_nutzungsdauer_jahre = ga.afa_nutzungsdauer_jahre or 20
        ga.zinsmethode = ZinsMethode.OESTERREICH
    else:
        ga.negative_stunden_regel = NegativeStundenRegel.EINE_STUNDE
        ga.tax_modus = TaxModus.GEWERBESTEUER_DE
        ga.zinsmethode = ZinsMethode.DEUTSCH
    services.save_global_assumptions(ga)


def _render_markt_system_schalter(ga: GlobalAssumptions) -> None:
    """Flaggen-Buttons direkt unter der Ueberschrift der Seite."""
    st.markdown(txt("oberflaeche.annahmen_marktsystem_titel"))
    spalten = st.columns([1, 1, 3])
    for spalte, (system, (flagge, schluessel)) in zip(
        spalten, _MARKT_SYSTEME.items(), strict=False
    ):
        with spalte:
            col_flagge, col_knopf = st.columns([1, 3], vertical_alignment="center")
            flaggen_pfad = FLAGS_DIR / f"{flagge}.png"
            if flaggen_pfad.exists():
                col_flagge.image(str(flaggen_pfad), width=28)
            if col_knopf.button(
                txt(schluessel),
                key=f"marktsystem_{flagge}",
                type="primary" if ga.markt_system == system else "secondary",
                width="stretch",
            ) and ga.markt_system != system:
                _wechsle_markt_system(ga, system)
                st.rerun()
    st.caption(txt("oberflaeche.annahmen_marktsystem_hinweis"))


def _datei(hochgeladen) -> tuple[bytes, str] | None:
    """Streamlit-Upload zu (Inhalt, Dateiname) - oder None."""
    return (hochgeladen.getvalue(), hochgeladen.name) if hochgeladen else None


def _aurora_import(ga: GlobalAssumptions) -> None:
    """Aurora-Marktdaten zu einem Marktpreisszenario.

    Vier Dateien liefert Aurora je Szenario: Systemdatei und
    Technologiedatei, beide in Jahres- und Monatsaufloesung. Pflicht ist
    hier allein die TECHNOLOGIEDATEI IN MONATSAUFLOESUNG - aus ihr
    stammen Capture Price, Abregelungsquoten und der Ertragsverlauf. Ohne
    Monatswerte waeren die Vertragsformen der Foerderung (zweiseitiger
    CfD, Toleranzband) nicht rechenbar, weil sich in einem Jahresmittel
    nicht mehr erkennen laesst, welche Monate ueber der
    Abschoepfungsschwelle lagen.
    """
    with st.expander(txt("oberflaeche.aurora_titel"), expanded=False):
        st.caption(txt("oberflaeche.aurora_hinweis"))

        col_t1, col_t2 = st.columns(2)
        tech_monat = col_t1.file_uploader(
            txt("oberflaeche.aurora_tech_monat"), type=["csv", "xlsx", "xlsm"],
            key="aurora_tech_monat",
            help=txt("oberflaeche.aurora_tech_monat_hilfe"),
        )
        tech_jahr = col_t2.file_uploader(
            txt("oberflaeche.aurora_tech_jahr"), type=["csv", "xlsx", "xlsm"],
            key="aurora_tech_jahr",
            help=txt("oberflaeche.aurora_tech_jahr_hilfe"),
        )
        col_s1, col_s2 = st.columns(2)
        system_jahr = col_s1.file_uploader(
            txt("oberflaeche.aurora_system_jahr"), type=["csv", "xlsx", "xlsm"],
            key="aurora_system_jahr",
            help=txt("oberflaeche.aurora_system_jahr_hilfe"),
        )
        system_monat = col_s2.file_uploader(
            txt("oberflaeche.aurora_system_monat"), type=["csv", "xlsx", "xlsm"],
            key="aurora_system_monat",
            help=txt("oberflaeche.aurora_system_monat_hilfe"),
        )

        if tech_monat is None:
            st.info(txt("oberflaeche.aurora_warte_auf_datei"))
            return

        # Die Technologieauswahl kommt aus der Datei selbst: "Solar"
        # steht je nach Marktgebiet als eigene Gruppe oder als
        # Untergruppe, das kann nur die Datei beantworten.
        try:
            auswahl = io_aurora.technologien(*_datei(tech_monat))
        except AuroraImportFehler as fehler:
            st.error(str(fehler))
            return
        if not auswahl:
            st.error(txt("oberflaeche.aurora_keine_technologien"))
            return
        vorschlag = io_aurora.vorschlag_solar(auswahl)
        technologie = st.selectbox(
            txt("oberflaeche.aurora_technologie_label"), auswahl,
            index=auswahl.index(vorschlag) if vorschlag in auswahl else 0,
            help=txt("oberflaeche.aurora_technologie_hilfe"),
        )

        col_name, col_preis = st.columns([1.2, 2])
        name = col_name.text_input(
            txt("oberflaeche.aurora_name_label"),
            value=tech_monat.name.rsplit(".", 1)[0][:40],
            help=txt("oberflaeche.aurora_name_hilfe"),
        )
        uncurtailed = col_preis.radio(
            txt("oberflaeche.aurora_preisbasis_label"),
            [True, False],
            format_func=lambda w: (
                txt("oberflaeche.aurora_preis_uncurtailed") if w
                else txt("oberflaeche.aurora_preis_curtailed")
            ),
            horizontal=True,
            help=txt("oberflaeche.aurora_preisbasis_hilfe"),
        )

        col_o1, col_o2, col_o3 = st.columns(3)
        mit_kurve = col_o1.checkbox(
            txt("oberflaeche.aurora_uebernimm_kurve"), value=True,
            help=txt("oberflaeche.aurora_uebernimm_kurve_hilfe"),
        )
        mit_inflation = col_o2.checkbox(
            txt("oberflaeche.aurora_uebernimm_inflation"), value=True,
            help=txt("oberflaeche.aurora_uebernimm_inflation_hilfe"),
        )
        auf_monat = col_o3.checkbox(
            txt("oberflaeche.aurora_setze_monatsmodus"), value=True,
            help=txt("oberflaeche.aurora_setze_monatsmodus_hilfe"),
        )

        if not st.button(txt("oberflaeche.aurora_importieren"), type="primary"):
            return

        try:
            ergebnis = io_aurora.importiere_aurora(
                name=name,
                technologie_monat=_datei(tech_monat),
                technologie_jahr=_datei(tech_jahr),
                system_jahr=_datei(system_jahr),
                system_monat=_datei(system_monat),
                technologie=technologie,
                uncurtailed=uncurtailed,
            )
        except AuroraImportFehler as fehler:
            st.error(str(fehler))
            return

        # Ein bestehendes Szenario gleichen Namens wird ersetzt, nicht
        # verdoppelt: Ein Reimport derselben Studie ist eine Korrektur.
        ga.marktpreisszenarien = [
            s for s in ga.marktpreisszenarien if s.name != ergebnis.szenario.name
        ] + [ergebnis.szenario]
        if mit_kurve and ergebnis.einspeisekurve_pct_je_monat:
            ga.einspeisekurve_pct_je_monat = ergebnis.einspeisekurve_pct_je_monat
        if mit_inflation and ergebnis.inflation_basisjahr is not None:
            ga.marktpreis_inflation_basisjahr = ergebnis.inflation_basisjahr
            if ergebnis.inflation_pct_pa is not None:
                ga.marktpreis_inflation_pct_pa = ergebnis.inflation_pct_pa
        if auf_monat:
            ga.zeitaufloesung = Zeitaufloesung.MONAT
        services.save_global_assumptions(ga)

        st.success(
            txt("oberflaeche.aurora_erfolg",
                name=ergebnis.szenario.name,
                technologie=ergebnis.technologie,
                von=ergebnis.jahre[0], bis=ergebnis.jahre[1],
                monatsjahre=ergebnis.monatsjahre)
        )
        if mit_inflation and ergebnis.inflation_basisjahr is not None:
            st.caption(
                txt("oberflaeche.aurora_inflation_uebernommen",
                    basisjahr=ergebnis.inflation_basisjahr,
                    rate=fmt_number((ergebnis.inflation_pct_pa or 0) * 100, 2))
            )
        for hinweis in ergebnis.hinweise:
            st.warning(hinweis)
        st.plotly_chart(
            charts.szenarien_linien_chart(
                [(ergebnis.szenario.name,
                  ergebnis.szenario.marktwert_solar_ct_kwh_je_kalenderjahr)],
                txt("diagramme.achse_marktwert_solar"), "ct/kWh",
            ),
            width="stretch", key="aurora_vorschau",
        )


def render_assumptions() -> None:
    st.subheader(txt("oberflaeche.nav_globale_annahmen"))

    ga = services.get_global_assumptions()
    _render_markt_system_schalter(ga)
    st.caption(txt("oberflaeche.annahmen_hinweis"))

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
            # Zuerst das Bild, dann die Zahlen: Der Vergleich der
            # Szenarien ist die Frage, die man an diese Sammlung hat -
            # vier Tabellen mit je 36 Zeilen beantworten sie nicht. Die
            # Kurven bleiben editierbar, aber einen Schalter entfernt.
            st.markdown(txt("oberflaeche.annahmen_szenarien_plot_titel"))
            st.caption(txt("oberflaeche.annahmen_szenarien_plot_hinweis"))
            col_preis, col_negativ = st.columns(2)
            with col_preis:
                st.plotly_chart(
                    charts.szenarien_linien_chart(
                        [
                            (s.name, s.marktwert_solar_ct_kwh_je_kalenderjahr)
                            for s in ga.marktpreisszenarien
                        ],
                        txt("diagramme.achse_marktwert_solar"), "ct/kWh",
                    ),
                    width="stretch", key="szenarien_marktwert",
                )
            with col_negativ:
                st.plotly_chart(
                    charts.szenarien_linien_chart(
                        [
                            (
                                s.name,
                                s.erzeugungsmenge_negativ(
                                    NegativeStundenRegel(negative_stunden_regel)
                                ),
                            )
                            for s in ga.marktpreisszenarien
                        ],
                        txt("diagramme.achse_negativ_anteil"), "%",
                        faktor=100.0, nachkommastellen=1,
                    ),
                    width="stretch", key="szenarien_negativ",
                )

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
                    monatsjahre = len(szenario.marktwert_solar_ct_kwh_je_monat)
                    st.caption(
                        txt("oberflaeche.annahmen_szenario_umfang",
                            jahre=len(jahre), monatsjahre=monatsjahre)
                    )
                    # Bewusst ein Schalter und kein Klappfeld: Klappfelder
                    # lassen sich in Streamlit nicht ineinander setzen,
                    # und dieser Block steckt bereits in einem.
                    if not st.toggle(
                        txt("oberflaeche.annahmen_zahlen_zeigen"),
                        key=f"kurven_zahlen_{szenario.name}",
                        help=txt("oberflaeche.annahmen_zahlen_zeigen_hilfe"),
                    ):
                        continue
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

    # --- Aurora-Import ---------------------------------------------------------
    _aurora_import(ga)

    # --- Zeitaufloesung, Foerdermodell, PPA ------------------------------------
    with st.expander(txt("oberflaeche.annahmen_modell_titel"), expanded=False):
        st.markdown(txt("oberflaeche.annahmen_zeitaufloesung_titel"))
        st.caption(txt("oberflaeche.annahmen_zeitaufloesung_hinweis"))
        aufloesung_labels = {
            Zeitaufloesung.JAHR.value: txt("oberflaeche.annahmen_aufloesung_jahr"),
            Zeitaufloesung.MONAT.value: txt("oberflaeche.annahmen_aufloesung_monat"),
        }
        aufloesung_optionen = [a.value for a in Zeitaufloesung]
        zeitaufloesung = st.radio(
            txt("oberflaeche.annahmen_zeitaufloesung_label"),
            aufloesung_optionen,
            format_func=lambda v: aufloesung_labels[v],
            index=aufloesung_optionen.index(ga.zeitaufloesung.value),
            horizontal=True, label_visibility="collapsed",
            help=txt("oberflaeche.annahmen_zeitaufloesung_hilfe"),
        )

        st.markdown(txt("oberflaeche.annahmen_einspeisekurve_titel"))
        st.caption(txt("oberflaeche.annahmen_einspeisekurve_hinweis"))
        kurve_df = pd.DataFrame(
            {
                "Monat": monate_kurz(),
                "Anteil (%)": [w * 100 for w in ga.einspeisekurve_pct_je_monat],
            }
        )
        edited_kurve = st.data_editor(
            kurve_df, width="stretch", hide_index=True, key="einspeisekurve_editor",
            column_config={
                "Monat": st.column_config.TextColumn(
                    txt("oberflaeche.annahmen_col_monat"), disabled=True,
                ),
                "Anteil (%)": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_col_anteil_jahreserzeugung"),
                    min_value=0.0, format="%.2f",
                ),
            },
        )
        summe_kurve = float(pd.to_numeric(edited_kurve["Anteil (%)"],
                                          errors="coerce").fillna(0).sum())
        st.caption(txt("oberflaeche.annahmen_einspeisekurve_summe",
                       summe=fmt_number(summe_kurve, 1)))

        st.divider()
        st.markdown(txt("oberflaeche.annahmen_praemienmodell_titel"))
        st.caption(txt("oberflaeche.annahmen_praemienmodell_hinweis"))
        modell_labels = {
            PraemienModell.EINSEITIG_CFD.value: txt("oberflaeche.annahmen_modell_einseitig"),
            PraemienModell.ZWEISEITIG_CFD.value: txt("oberflaeche.annahmen_modell_zweiseitig"),
            PraemienModell.EAG_TOLERANZBAND.value: txt("oberflaeche.annahmen_modell_eag"),
        }
        modell_optionen = [m.value for m in PraemienModell]
        praemien_modell = st.radio(
            txt("oberflaeche.annahmen_praemienmodell_label"),
            modell_optionen,
            format_func=lambda v: modell_labels[v],
            index=modell_optionen.index(ga.praemien_modell.value),
            label_visibility="collapsed",
        )
        # Die drei Parameter stehen immer sichtbar, aber nur im
        # Toleranzband-Modell wirksam: Ausgeblendete Felder wuerden beim
        # Wechsel des Modells stumm auf ihren alten Wert zurueckfallen.
        st.caption(txt("oberflaeche.annahmen_eag_rueckzahlung_hinweis"))
        col_mw, col_band, col_anteil = st.columns(3)
        eag_ab_mw = col_mw.number_input(
            txt("oberflaeche.annahmen_eag_ab_mw_label"), min_value=0.0,
            value=float(ga.eag_rueckzahlung_ab_mw), step=0.5,
            disabled=praemien_modell != PraemienModell.EAG_TOLERANZBAND.value,
            help=txt("oberflaeche.annahmen_eag_ab_mw_hilfe"),
        )
        eag_band = col_band.number_input(
            txt("oberflaeche.annahmen_eag_band_label"), min_value=0.0,
            value=ga.eag_rueckzahlung_toleranzband_pct * 100, step=5.0,
            disabled=praemien_modell != PraemienModell.EAG_TOLERANZBAND.value,
            help=txt("oberflaeche.annahmen_eag_band_hilfe"),
        )
        eag_anteil = col_anteil.number_input(
            txt("oberflaeche.annahmen_eag_anteil_label"),
            min_value=0.0, max_value=100.0,
            value=ga.eag_rueckzahlung_anteil_pct * 100, step=1.0,
            disabled=praemien_modell != PraemienModell.EAG_TOLERANZBAND.value,
            help=txt("oberflaeche.annahmen_eag_anteil_hilfe"),
        )

        st.divider()
        st.markdown(txt("oberflaeche.annahmen_ppa_titel"))
        st.caption(txt("oberflaeche.annahmen_ppa_hinweis"))
        col_ppa1, col_ppa2, col_ppa3, col_ppa4 = st.columns(4)
        ppa_anteil_vorschlag = col_ppa1.number_input(
            txt("oberflaeche.annahmen_ppa_anteil_label"),
            min_value=0.0, max_value=100.0,
            value=ga.ppa_anteil_pct_vorschlag * 100, step=5.0,
        )
        ppa_preis_vorschlag = col_ppa2.number_input(
            txt("oberflaeche.annahmen_ppa_preis_label"), min_value=0.0,
            value=ga.ppa_preis_eur_mwh_vorschlag, step=1.0,
        )
        ppa_laufzeit_vorschlag = col_ppa3.number_input(
            txt("oberflaeche.annahmen_ppa_laufzeit_label"), min_value=0,
            value=ga.ppa_laufzeit_jahre_vorschlag, step=1,
        )
        ppa_index_vorschlag = col_ppa4.number_input(
            txt("oberflaeche.annahmen_ppa_index_label"), min_value=0.0,
            value=ga.ppa_indexierung_pct_pa_vorschlag * 100, step=0.25,
        )

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
        pacht_umsatzbeteiligung_vorschlag = st.number_input(
            txt("oberflaeche.annahmen_pacht_umsatzbeteiligung_vorschlag_label"),
            min_value=0.0, max_value=100.0,
            value=ga.pacht_umsatzbeteiligung_pct_vorschlag * 100, step=0.5,
            help=txt("oberflaeche.annahmen_pacht_umsatzbeteiligung_vorschlag_hilfe"),
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
        # DSCR-Kovenanten des Kreditvertrags: Sie veraendern die
        # Cashflow-Rechnung nicht, sondern werden darauf ausgewertet
        # (siehe engine/covenants.py).
        col_trap, col_eod = st.columns(2)
        dscr_cash_trap = col_trap.number_input(
            txt("oberflaeche.annahmen_dscr_cash_trap_label"),
            min_value=0.0, max_value=5.0, step=0.05,
            value=float(ga.dscr_cash_trap),
            help=txt("oberflaeche.annahmen_dscr_cash_trap_hilfe"),
        )
        dscr_event_of_default = col_eod.number_input(
            txt("oberflaeche.annahmen_dscr_event_of_default_label"),
            min_value=0.0, max_value=5.0, step=0.05,
            value=float(ga.dscr_event_of_default),
            help=txt("oberflaeche.annahmen_dscr_event_of_default_hilfe"),
        )

        zm_oesterreich = txt("oberflaeche.annahmen_zinsmethode_oesterreich")
        zm_deutsch = txt("oberflaeche.annahmen_zinsmethode_deutsch")
        zinsmethode_label = st.radio(
            txt("oberflaeche.annahmen_zinsmethode_label"),
            [zm_oesterreich, zm_deutsch],
            index=0 if ga.zinsmethode == ZinsMethode.OESTERREICH else 1,
            horizontal=True,
            help=txt("oberflaeche.annahmen_zinsmethode_hilfe"),
        )

    # --- Steuern ---------------------------------------------------------------
    with st.expander(txt("oberflaeche.annahmen_steuern_titel"), expanded=False):
        tax_modus_optionen = [modus.value for modus in TaxModus]
        tax_modus_labels = {
            "pauschal_auf_ebt": txt("oberflaeche.annahmen_steuermodus_pauschal"),
            "afa_koerperschaftsteuer": txt("oberflaeche.annahmen_steuermodus_afa"),
            "gewerbesteuer_de": txt("oberflaeche.annahmen_steuermodus_gewerbesteuer_de"),
        }
        tax_modus = st.radio(
            txt("oberflaeche.annahmen_steuermodus_label"),
            tax_modus_optionen,
            format_func=lambda v: tax_modus_labels[v],
            index=tax_modus_optionen.index(ga.tax_modus.value),
            horizontal=True,
        )

        if tax_modus == TaxModus.GEWERBESTEUER_DE.value:
            st.caption(txt("oberflaeche.annahmen_gewerbesteuer_hinweis"))
            col4, col5, col6 = st.columns(3)
            afa_nutzungsdauer = col4.number_input(
                txt("oberflaeche.annahmen_afa_nutzungsdauer_label"), min_value=1,
                value=ga.afa_nutzungsdauer_jahre or 20,
                help=txt("oberflaeche.annahmen_afa_nutzungsdauer_hilfe"),
            )
            gewerbesteuer_hebesatz = col5.number_input(
                txt("oberflaeche.annahmen_gewerbesteuer_hebesatz_label"),
                min_value=0.0, value=ga.gewerbesteuer_hebesatz_pct, step=10.0,
                help=txt("oberflaeche.annahmen_gewerbesteuer_hebesatz_hilfe"),
            )
            gewerbesteuer_freibetrag = col6.number_input(
                txt("oberflaeche.annahmen_gewerbesteuer_freibetrag_label"),
                min_value=0.0, value=ga.gewerbesteuer_freibetrag_eur, step=500.0,
                help=txt("oberflaeche.annahmen_gewerbesteuer_freibetrag_hilfe"),
            )
            effektiver_gewerbesteuersatz = 0.035 * (gewerbesteuer_hebesatz / 100)
            st.caption(txt(
                "oberflaeche.annahmen_gewerbesteuer_effektiv_hinweis",
                satz=f"{effektiver_gewerbesteuersatz * 100:.2f}",
            ))
            steuersatz = ga.steuersatz_pct * 100
            verlustvortrag_grenze = ga.verlustvortrag_verrechnungsgrenze_pct * 100
            freibetrag = ga.freibetrag_eur
        else:
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
            gewerbesteuer_hebesatz = ga.gewerbesteuer_hebesatz_pct
            gewerbesteuer_freibetrag = ga.gewerbesteuer_freibetrag_eur

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
                    # Die Monatsreihen bleiben unangetastet: Der Editor
                    # oben zeigt nur die Jahreskurven, ein Neuaufbau ohne
                    # sie wuerde sie beim Speichern loeschen.
                    marktwert_solar_ct_kwh_je_monat=(
                        szenario.marktwert_solar_ct_kwh_je_monat
                    ),
                    erzeugungsmenge_negativ_6h_pct_je_monat=(
                        szenario.erzeugungsmenge_negativ_6h_pct_je_monat
                    ),
                    erzeugungsmenge_negativ_1h_pct_je_monat=(
                        szenario.erzeugungsmenge_negativ_1h_pct_je_monat
                    ),
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
        ga.dscr_cash_trap = float(dscr_cash_trap)
        ga.dscr_event_of_default = float(dscr_event_of_default)
        ga.zinsmethode = (
            ZinsMethode.OESTERREICH if zinsmethode_label == zm_oesterreich
            else ZinsMethode.DEUTSCH
        )
        ga.gemeindeabgabe_eur_kwh = gemeindeabgabe / 1000
        ga.pacht_umsatzbeteiligung_pct_vorschlag = pacht_umsatzbeteiligung_vorschlag / 100
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
        ga.gewerbesteuer_hebesatz_pct = float(gewerbesteuer_hebesatz)
        ga.gewerbesteuer_freibetrag_eur = float(gewerbesteuer_freibetrag)
        ga.verlustvortrag_verrechnungsgrenze_pct = verlustvortrag_grenze / 100

        ga.zeitaufloesung = Zeitaufloesung(zeitaufloesung)
        anteile = [
            float(w) / 100
            for w in pd.to_numeric(edited_kurve["Anteil (%)"],
                                   errors="coerce").fillna(0)
        ]
        # Eine leere oder nur aus Nullen bestehende Kurve waere eine
        # Anlage ohne Erzeugung - dann bleibt die bisherige stehen.
        if len(anteile) == 12 and sum(anteile) > 0:
            ga.einspeisekurve_pct_je_monat = anteile
        ga.praemien_modell = PraemienModell(praemien_modell)
        ga.eag_rueckzahlung_ab_mw = float(eag_ab_mw)
        ga.eag_rueckzahlung_toleranzband_pct = eag_band / 100
        ga.eag_rueckzahlung_anteil_pct = eag_anteil / 100
        ga.ppa_anteil_pct_vorschlag = ppa_anteil_vorschlag / 100
        ga.ppa_preis_eur_mwh_vorschlag = float(ppa_preis_vorschlag)
        ga.ppa_laufzeit_jahre_vorschlag = int(ppa_laufzeit_vorschlag)
        ga.ppa_indexierung_pct_pa_vorschlag = ppa_index_vorschlag / 100

        services.save_global_assumptions(ga)
        st.success(txt("oberflaeche.annahmen_gespeichert"))
        st.rerun()
