"""
Portfolioseite: aggregierte Kennzahlen, Portfolio-Analytik
(Rendite-Risiko-Landkarte, Ranking, Vergleichstabelle) und die
Projektkarten als Einstieg.

Das Dashboard eines Projekts haengt NICHT mehr unten an dieser Seite -
es hat eine eigene Adresse (siehe app/views/project_page.py). Dadurch
beginnt die Projektansicht oben statt nach drei Bildschirmhoehen, und ein
Link auf ein bestimmtes Projekt laesst sich verschicken.
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app import router, services
from app.components import charts
from app.components.kpi import Kennzahl, render_kennzahlen
from app.config import STATE_SELECTED_PROJECT
from app.formatting import fmt_eur, fmt_eur_kompakt, fmt_kwp, fmt_number, fmt_pct
from app.theme import badge
from engine import AnlagenTyp
from engine.io_yaml import load_project_yaml
from texte import txt

#: Karten je Reihe. Die letzte Reihe wird nicht gestreckt - die Karten
#: behalten ihre Breite, damit die Uebersicht ein Raster bleibt.
_KARTEN_JE_REIHE = 4


def _projektkarte(z: dict, selected: str | None) -> None:
    """Eine Projektkarte samt Oeffnen-Knopf."""
    project = z["projekt"]
    kpis = z["kpis"]
    ist_agri = project.anlagentyp == AnlagenTyp.AGRI_PV
    typ_badge = (badge(txt("oberflaeche.badge_agri"), "agri") if ist_agri
                 else badge(txt("oberflaeche.badge_konventionell"), "konv"))
    if not project.aktiv:
        typ_badge += " " + badge(txt("oberflaeche.badge_inaktiv"), "inaktiv")
    klassen = "project-card"
    if z["id"] == selected:
        klassen += " selected"
    if not project.aktiv:
        klassen += " inaktiv"
    # Die Variante steht in der Unterzeile, nicht im Titel: Sonst waeren
    # drei Karten desselben Standorts nur an ihrem abgeschnittenen
    # Namensende auseinanderzuhalten.
    # Eigene Zeile statt Anhaengsel der technischen Zeile: Diese ist auf
    # eine Zeile gekuerzt, ein angehaengtes Kennzeichen fiele bei langen
    # Namen der Kuerzung zum Opfer - und genau dann wird es gebraucht.
    # Die Zeile haengt ohne Umbruch am vorigen Element: Eine leere Zeile
    # gefolgt von eingerueckten Zeilen liest Markdown als Codeblock, und
    # die Karte zeigte dann ihren eigenen HTML-Quelltext.
    variante_zeile = (
        f'<div class="card-variante">{html.escape(project.variantenlabel)}</div>'
        if project.variante else ""
    )
    st.markdown(
        f'''<div class="{klassen}" title="{html.escape(project.anzeigename)}">
        <div class="card-kopf">
          <span class="card-title">{html.escape(project.name)}</span>
          <span class="card-badges">{typ_badge}</span>
        </div>{variante_zeile}
        <span class="card-sub">{fmt_kwp(project.nennleistung_kwp)} · IBN {project.inbetriebnahme_jahr}</span>
        <div class="card-kpi-zeile">
          <span class="card-kpi">{fmt_pct(kpis.equity_irr)}</span>
          <span class="card-kpi-label">Equity IRR</span>
        </div>
        <span class="card-sub">Equity {fmt_eur(kpis.eigenkapital_eur)}</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button(txt("oberflaeche.btn_oeffnen"), key=f"open_{z['id']}",
                 width="stretch"):
        st.session_state[STATE_SELECTED_PROJECT] = z["id"]
        router.gehe_zu("projekt", projekt_id=z["id"])


def _standortkarte(gruppe: dict, selected: str | None) -> None:
    """Eine Karte je Standort - mit der Spanne der Varianten statt einer
    einzelnen Zahl.

    Die Spanne ist die eigentliche Aussage: "9,84 %" verschweigt, dass
    dieselbe Flaeche unter anderen Annahmen 6,46 % oder 13,50 % bringt.
    """
    leit, varianten = gruppe["leit"], gruppe["varianten"]
    kpis = gruppe["leit_kpis"]
    ist_agri = leit.anlagentyp == AnlagenTyp.AGRI_PV
    typ_badge = (badge(txt("oberflaeche.badge_agri"), "agri") if ist_agri
                 else badge(txt("oberflaeche.badge_konventionell"), "konv"))
    klassen = "project-card"
    if leit.id == selected:
        klassen += " selected"

    irr_werte = [z["kpis"].equity_irr for z in varianten
                 if z["kpis"].equity_irr is not None]
    if len(varianten) > 1 and irr_werte:
        spanne = (
            f'<div class="card-variante">{len(varianten)} Varianten · '
            f"{fmt_pct(min(irr_werte))} – {fmt_pct(max(irr_werte))}</div>"
        )
    else:
        spanne = ""

    st.markdown(
        f'''<div class="{klassen}" title="{html.escape(leit.name)}">
        <div class="card-kopf">
          <span class="card-title">{html.escape(leit.name)}</span>
          <span class="card-badges">{typ_badge}</span>
        </div>{spanne}
        <span class="card-sub">{fmt_kwp(leit.nennleistung_kwp)} · IBN {leit.inbetriebnahme_jahr}</span>
        <div class="card-kpi-zeile">
          <span class="card-kpi">{fmt_pct(kpis.equity_irr)}</span>
          <span class="card-kpi-label">Equity IRR</span>
        </div>
        <span class="card-sub">{html.escape(txt("oberflaeche.portfolio_leitfall", name=leit.variantenlabel))}</span>
        </div>''',
        unsafe_allow_html=True,
    )
    if st.button(txt("oberflaeche.btn_oeffnen"), key=f"open_{leit.id}",
                 width="stretch"):
        st.session_state[STATE_SELECTED_PROJECT] = leit.id
        router.gehe_zu("projekt", projekt_id=leit.id)


def _variantentabelle(gruppen: list[dict], ziel_pct: float,
                      dscr_grenze: float) -> None:
    """Alle Rechnungen der Pipeline, nach Standort gruppiert.

    Die Ampel beantwortet die Frage, die eine Sortierung nach Rendite
    nicht beantwortet: Welche Varianten halten Ziel UND Kovenanten ein?
    """
    zeilen = []
    for gruppe in gruppen:
        for z in gruppe["varianten"]:
            projekt, kpis = z["projekt"], z["kpis"]
            erfuellt = (
                kpis.equity_irr is not None and kpis.equity_irr >= ziel_pct
                and kpis.dscr_min is not None and kpis.dscr_min >= dscr_grenze
            )
            zeilen.append(
                {
                    txt("oberflaeche.vergleich_spalte_standort"): projekt.name,
                    txt("oberflaeche.vergleich_spalte_variante"):
                        projekt.variantenlabel,
                    txt("oberflaeche.portfolio_spalte_leitfall"):
                        projekt.id == gruppe["leit"].id,
                    txt("oberflaeche.vergleich_spalte_irr") + " (%)": (
                        round(kpis.equity_irr * 100, 2)
                        if kpis.equity_irr is not None else None
                    ),
                    txt("oberflaeche.vergleich_spalte_dscr") + " (x)": (
                        round(kpis.dscr_min, 2)
                        if kpis.dscr_min is not None else None
                    ),
                    "€/kWp": (
                        round(kpis.capex_total_eur / projekt.nennleistung_kwp)
                        if projekt.nennleistung_kwp else None
                    ),
                    txt("oberflaeche.portfolio_spalte_ziel"): erfuellt,
                }
            )
    st.dataframe(
        pd.DataFrame(zeilen), width="stretch", hide_index=True,
        column_config={
            # Ohne Formatangabe zeigt die Tabelle "18.07" und "1.1" - im
            # Rest der App steht "18,07 %" und "1,10x".
            txt("oberflaeche.vergleich_spalte_irr") + " (%)":
                st.column_config.NumberColumn(format="%.2f"),
            txt("oberflaeche.vergleich_spalte_dscr") + " (x)":
                st.column_config.NumberColumn(format="%.2f"),
            "€/kWp": st.column_config.NumberColumn(format="%d"),
            txt("oberflaeche.portfolio_spalte_leitfall"):
                st.column_config.CheckboxColumn(disabled=True),
            txt("oberflaeche.portfolio_spalte_ziel"):
                st.column_config.CheckboxColumn(
                    disabled=True,
                    help=txt("oberflaeche.portfolio_spalte_ziel_hilfe"),
                ),
        },
    )


def render_overview() -> None:
    projects = services.list_project_files()
    if not projects:
        st.info(txt("oberflaeche.overview_keine_projekte"))
        return

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

    # Nach Standort buendeln und je Standort die Leitvariante bestimmen -
    # die Rechnung, die fuer dieses Feld gilt.
    gruppen = []
    for standort, varianten in services.gruppiere_nach_standort(
        [z["projekt"] for z in zeilen]
    ).items():
        leit = services.leitvariante_von(varianten)
        teil = [z for z in zeilen if z["projekt"].name == standort]
        gruppen.append(
            {
                "standort": standort,
                "leit": leit,
                "leit_kpis": next(z["kpis"] for z in teil if z["id"] == leit.id),
                "varianten": teil,
            }
        )

    # --- Sichtwahl -----------------------------------------------------------
    # Standorte: je Feld die Leitvariante. Alle Varianten: jede Rechnung
    # einzeln. Der Unterschied ist keine Darstellungsfrage - er entscheidet,
    # ob ein Standort mit drei Sensitivitaeten in Leistung, Investitions-
    # volumen und Eigenkapital dreifach zaehlt.
    hat_varianten = any(len(g["varianten"]) > 1 for g in gruppen)
    sicht = "standorte"
    if hat_varianten:
        wahl = st.segmented_control(
            txt("oberflaeche.portfolio_sicht_label"),
            [txt("oberflaeche.portfolio_sicht_standorte"),
             txt("oberflaeche.portfolio_sicht_varianten")],
            default=txt("oberflaeche.portfolio_sicht_standorte"),
            key="portfolio_sicht", label_visibility="collapsed",
            help=txt("oberflaeche.portfolio_sicht_hilfe"),
        )
        if wahl == txt("oberflaeche.portfolio_sicht_varianten"):
            sicht = "varianten"

    if sicht == "standorte":
        leit_ids = {g["leit"].id for g in gruppen}
        basis = [z for z in zeilen if z["id"] in leit_ids]
    else:
        basis = zeilen

    # --- Portfolio-KPIs ------------------------------------------------------
    aktive = [z for z in basis if z["projekt"].aktiv]
    inaktive_anzahl = len(basis) - len(aktive)
    if inaktive_anzahl:
        mit_inaktiven = st.toggle(
            txt("oberflaeche.portfolio_toggle_inaktive", anzahl=inaktive_anzahl),
            value=False, key="portfolio_mit_inaktiven",
            help=txt("oberflaeche.portfolio_toggle_inaktive_hilfe"),
        )
    else:
        mit_inaktiven = False
    kpi_basis = basis if mit_inaktiven else aktive

    gesamt_kwp = sum(z["projekt"].nennleistung_kwp for z in kpi_basis)
    gesamt_capex = sum(z["kpis"].capex_total_eur for z in kpi_basis)
    gesamt_ek = sum(z["kpis"].eigenkapital_eur for z in kpi_basis)
    irr_werte = [z["kpis"].equity_irr for z in kpi_basis
                 if z["kpis"].equity_irr is not None]
    mittlere_irr = sum(irr_werte) / len(irr_werte) if irr_werte else None

    # Leitkennzahl statt fuenf gleichrangiger Kacheln: Der mittlere Equity
    # IRR ist die Zahl, an der das Portfolio gemessen wird; Anzahl, MWp und
    # die beiden Summen ordnen ihn nur ein.
    ga = services.get_global_assumptions()
    ziel_pct = 0.08
    ziel = None
    if mittlere_irr is not None:
        bezug = ziel_pct * 1.5
        ziel = (
            min(max(mittlere_irr / bezug, 0.0), 1.0),
            min(ziel_pct / bezug, 1.0),
            txt("oberflaeche.kpi_ziel", wert=fmt_pct(ziel_pct, 1)),
        )
    render_kennzahlen(
        leit=Kennzahl(
            label=txt("oberflaeche.portfolio_kpi_ek_rendite"),
            wert=fmt_pct(mittlere_irr, 1),
            zusatz=txt("oberflaeche.portfolio_kpi_irr_methode"),
        ),
        begleiter=[
            Kennzahl(txt("oberflaeche.portfolio_kpi_anzahl_projekte"),
                     f"{len(kpi_basis)}"),
            Kennzahl(txt("oberflaeche.portfolio_kpi_gesamt_kwp"),
                     f"{fmt_number(gesamt_kwp / 1000, 1)} MWp"),
            Kennzahl(txt("oberflaeche.portfolio_kpi_gesamt_capex"),
                     fmt_eur_kompakt(gesamt_capex), None, fmt_eur(gesamt_capex)),
            Kennzahl(txt("oberflaeche.portfolio_kpi_gesamt_ek"),
                     fmt_eur_kompakt(gesamt_ek), None, fmt_eur(gesamt_ek)),
        ],
        group="portfolio",
        ziel=ziel,
    )

    # --- Portfolio-Analytik ---------------------------------------------------
    selected = st.session_state.get(STATE_SELECTED_PROJECT)
    analytik = pd.DataFrame(
        [
            {
                "id": z["id"],
                "name": z["projekt"].anzeigename,
                # Traegt die Variantenpfade der Landkarte: Rechnungen
                # desselben Standorts werden verbunden.
                "standort": z["projekt"].name,
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

    # Kein Klappfeld mehr um die Tabs: Tabs sind gleichrangige Sichten auf
    # denselben Gegenstand, Klappfelder optionales Detail INNERHALB einer
    # Sicht - und nie ineinander (dieselbe Regel gilt auf der Projektseite).
    st.subheader(txt("oberflaeche.portfolio_analytik_titel"))
    tab_karte, tab_ranking, tab_tabelle, tab_varianten = st.tabs([
        txt("oberflaeche.portfolio_tab_karte"),
        txt("oberflaeche.portfolio_tab_ranking"),
        txt("oberflaeche.portfolio_tab_tabelle"),
        txt("oberflaeche.portfolio_tab_varianten"),
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
                    "Projekt": z["projekt"].anzeigename,
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
    with tab_varianten:
        st.caption(txt("oberflaeche.portfolio_varianten_hilfe"))
        _variantentabelle(gruppen, ziel_pct, ga.dscr_cash_trap)

    # --- Projektkarten ------------------------------------------------------
    # Je Reihe ein eigener Spaltensatz: Ein einziger Satz mit
    # Modulo-Verteilung stapelt die Karten SPALTENWEISE - eine hohe Karte
    # verschiebt dann alles darunter in ihrer Spalte, und nichts fluchtet
    # mehr. Mit einem Satz je Reihe richten sich die Karten zeilenweise
    # aus; die feste Kartenhoehe (app/theme.py) sorgt fuer eine gerade
    # Unterkante, auch wenn ein Projektname laenger ist als der andere.
    st.subheader(txt("oberflaeche.overview_projekte_titel"))
    if sicht == "standorte":
        karten = [(g, _standortkarte) for g in gruppen]
    else:
        karten = [(z, _projektkarte) for z in zeilen]
    for reihe in range(0, len(karten), _KARTEN_JE_REIHE):
        cols = st.columns(_KARTEN_JE_REIHE)
        for spalte, (eintrag, zeichne) in enumerate(
            karten[reihe:reihe + _KARTEN_JE_REIHE]
        ):
            with cols[spalte]:
                zeichne(eintrag, selected)
