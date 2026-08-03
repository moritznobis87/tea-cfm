"""
Projektseite: Kennzahlen und Auswertungen links, Parameter rechts.

Zwei Entscheidungen praegen den Aufbau:

1. Die Seite hat eine eigene Adresse (?seite=projekt&id=...&tab=...) -
   Neuladen, Lesezeichen, verschickte Links und der Zurueck-Knopf des
   Browsers funktionieren dadurch. Siehe app/router.py.

2. Eingabe und Ergebnis stehen nebeneinander. Die Parameterspalte
   arbeitet auf einem ENTWURF: Jede Aenderung rechnet sofort durch,
   gespeichert wird erst auf Knopfdruck. Dadurch laesst sich gefahrlos
   ausprobieren - frueher war Absenden und Speichern derselbe Schritt.

Was bewusst NICHT live rechnet: Tornado, Heatmap, Monte Carlo,
Szenarien und Break-even im Tab "Risiko". Diese Auswertungen fuehren je
Aufruf Dutzende bis Tausende Bewertungslaeufe aus; sie beziehen sich
weiterhin auf den gespeicherten Stand, und die Seite weist darauf hin,
solange ein abweichender Entwurf offen ist.
"""

from __future__ import annotations

import html

import streamlit as st

from app import router, services
from app.components.kpi import Kennzahl, render_kennzahlen
from app.components.project_form import render_parameter_spalte, verwirf_entwurf
from app.config import STATE_DELETE_CANDIDATE, monate_kurz
from app.formatting import (
    fmt_ct_kwh,
    fmt_eur,
    fmt_eur_kompakt,
    fmt_number,
    fmt_pct,
)
from app.views.project_detail import (
    render_assumptions_tab,
    render_cashflow_tab,
    render_financing_tab,
    render_kovenanten_status,
    render_monte_carlo_tab,
    render_revenue_tab,
    render_scenario_tab,
    render_sensitivity_tab,
)
from engine import AnlagenTyp, MarktSystem, PVProject
from engine.kpis import npv_at
from texte import txt

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Reihenfolge der Analyse-Tabs; die Codes stehen auch in der Adresse.
_TABS = (
    ("ergebnis", "oberflaeche.projekt_tab_ergebnis"),
    ("finanzierung", "oberflaeche.projekt_tab_finanzierung"),
    ("risiko", "oberflaeche.projekt_tab_risiko"),
    ("annahmen", "oberflaeche.projekt_tab_annahmen"),
)


def _typ_label(project: PVProject) -> str:
    return (txt("oberflaeche.badge_agri")
            if project.anlagentyp == AnlagenTyp.AGRI_PV
            else txt("oberflaeche.badge_konventionell"))


#: Relative Schranke, ab der ein Zahlenunterschied als Aenderung zaehlt.
#: Zwei Rundungen liegen zwischen Anzeige und Modell: die spezifische
#: Eingabe (€/kWp, eine Nachkommastelle) und das Speicherformat der
#: YAML-Datei. Ohne Schranke meldete eine frisch geoeffnete Projektseite
#: deshalb Aenderungen, die niemand vorgenommen hat. 1e-4 liegt sicher
#: ueber diesen Artefakten (rund 1e-5) und deutlich unter der kleinsten
#: sinnvollen Eingabeaenderung (ein Schritt = rund 2e-3).
_TOLERANZ = 1e-4


def _weicht_ab(a, b, absolut: float = 0.0) -> bool:
    """Vergleich zweier Modellwerte, tolerant gegen Rundungsartefakte.

    absolut: zusaetzliche absolute Schranke in Euro. Sie ergibt sich aus
    der spezifischen Eingabe: Ein auf zwei Nachkommastellen angezeigter
    €/kWp-Wert traegt beim Rueckweg einen Fehler von bis zu
    0,005 €/kWp * Nennleistung. Ohne diese Schranke meldeten kleine
    Investkostenpositionen (wenige zehntausend Euro) eine Abweichung,
    obwohl nur die Anzeige gerundet wurde.
    """
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        schranke = max(_TOLERANZ * max(abs(a), abs(b), 1.0), absolut)
        return abs(a - b) > schranke
    if isinstance(a, dict) and isinstance(b, dict):
        return any(_weicht_ab(a[k], b.get(k), absolut) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) != len(b) or any(
            _weicht_ab(x, y, absolut) for x, y in zip(a, b, strict=False)
        )
    return a != b


def _zaehle_aenderungen(entwurf: PVProject, gespeichert: PVProject) -> int:
    """Anzahl der Modellfelder, die im Entwurf abweichen.

    Verschachtelte Strukturen (capex, Zusatzpositionen) zaehlen als ein
    Feld - die Zahl soll die Groessenordnung der offenen Aenderungen
    zeigen, keine exakte Feldbilanz sein.
    """
    a = entwurf.model_dump()
    b = gespeichert.model_dump()
    # 0,01 €/kWp Spielraum - das Doppelte des groesstmoeglichen
    # Rundungsfehlers der spezifischen Anzeige, und weit unter einem
    # Eingabeschritt. Die Schranke gilt AUSSCHLIESSLICH fuer die
    # Investkosten: Auf Anteile (Eigenkapitalquote, Zinssatz) angewandt
    # wuerde eine Euro-Schranke jede denkbare Aenderung verschlucken.
    absolut = 0.01 * max(entwurf.nennleistung_kwp, gespeichert.nennleistung_kwp)
    return sum(
        1 for schluessel in a
        if _weicht_ab(
            a[schluessel], b.get(schluessel),
            absolut if schluessel == "capex" else 0.0,
        )
    )


def render_project_page() -> None:
    projekte = services.list_project_files()
    projekt_id = router.aktuelles_projekt()
    if not projekte:
        st.info(txt("oberflaeche.overview_keine_projekte"))
        return
    if projekt_id not in projekte:
        # Direkt aufgerufene Adresse mit unbekannter id, oder das Projekt
        # wurde inzwischen geloescht.
        st.warning(txt("oberflaeche.projekt_unbekannt"))
        if st.button(txt("oberflaeche.btn_zum_portfolio")):
            router.gehe_zu("portfolio")
        return

    pfad = projekte[projekt_id]
    gespeichert = services.get_project(projekt_id)
    global_assumptions = services.get_global_assumptions()

    st.markdown(
        f'<div class="brotkrume"><b>{html.escape(txt("oberflaeche.nav_portfolio"))}'
        f"</b> › {html.escape(gespeichert.name)}</div>",
        unsafe_allow_html=True,
    )

    # --- Kopfzeile mit Aktionen ---------------------------------------------
    col_titel, col_pdf, col_excel, col_mehr = st.columns([6, 1.5, 1.0, 0.5],
                                                         vertical_alignment="bottom")
    with col_titel:
        st.markdown(f"### {gespeichert.name}")

    form_key = f"param_{projekt_id}"

    # --- Kontextzeile und Diskontsatz ---------------------------------------
    st.session_state.setdefault("npv_diskontsatz_pct", 8.0)
    col_kontext, col_satz = st.columns([5, 1.2], vertical_alignment="center")
    with col_satz, st.popover(
        txt("oberflaeche.kontext_diskontsatz_knopf",
            satz=fmt_number(st.session_state["npv_diskontsatz_pct"], 2)),
        width="stretch",
    ):
        st.number_input(
            txt("oberflaeche.projekt_npv_diskontsatz_label"),
            min_value=0.0, max_value=10.0, step=0.25,
            key="npv_diskontsatz_pct",
            help=txt("oberflaeche.projekt_npv_diskontsatz_hilfe"),
        )
    npv_satz_pct = st.session_state["npv_diskontsatz_pct"]

    # --- Arbeitsflaeche: Ergebnis links, Parameter rechts --------------------
    col_ergebnis, col_parameter = st.columns([0.655, 0.345], gap="medium")

    with col_parameter, st.container(key="parameterbox"):
        st.markdown(
            f'<div class="parameter-kopf">'
            f'{html.escape(txt("oberflaeche.parameter_titel"))}</div>',
            unsafe_allow_html=True,
        )
        entwurf = render_parameter_spalte(gespeichert, form_key)
        # Platzhalter fuer die Speicherleiste: Sie braucht die Zahl der
        # Aenderungen, die erst nach dem Aufbau der Felder feststeht, soll
        # aber innerhalb des Rahmens stehen.
        fussbereich = st.container()

    # Faellt die Maske aus (z.B. leerer Name), bleibt der gespeicherte
    # Stand die Rechengrundlage - die Seite soll nicht leer werden.
    aktiv = entwurf or gespeichert
    result = services.get_valuation_fuer(aktiv)
    aenderungen = _zaehle_aenderungen(aktiv, gespeichert) if entwurf else 0

    with fussbereich:
        _speicherleiste(aktiv, gespeichert, pfad, form_key, aenderungen)

    with col_kontext:
        _kontextzeile(aktiv, result, global_assumptions, npv_satz_pct)

    with col_pdf:
        _pdf_knopf(projekt_id, gespeichert, npv_satz_pct, aenderungen)
    with col_excel:
        st.download_button(
            txt("oberflaeche.btn_excel_export"),
            data=services.cashflow_to_excel(result),
            file_name=f"{services.slugify(aktiv.name)}_cashflow.xlsx",
            mime=_XLSX_MIME, width="stretch",
        )
    with col_mehr:
        _weitere_aktionen(gespeichert, pfad)

    _loeschbestaetigung(gespeichert, pfad)

    with col_ergebnis:
        _kennzahlen(result, npv_satz_pct, aenderungen, global_assumptions)
        render_kovenanten_status(result)
        _analyse_tabs(result, aktiv, projekt_id, npv_satz_pct, aenderungen)


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------


def _kontextzeile(project, result, global_assumptions, npv_satz_pct: float) -> None:
    """Die app-weit geltenden Randbedingungen, sichtbar statt versteckt."""
    markt = (
        "EEG Deutschland"
        if global_assumptions.markt_system == MarktSystem.DEUTSCHLAND
        else "EAG Österreich"
    )
    teile = [
        markt,
        result.effective_assumptions.marktpreisszenario_name,
        txt("oberflaeche.kontext_diskontsatz",
            satz=fmt_number(npv_satz_pct, 2)),
        f"{fmt_number(project.nennleistung_kwp / 1000, 1)} MWp",
        txt("oberflaeche.kontext_ibn",
            monat=monate_kurz()[project.inbetriebnahme_monat - 1],
            jahr=project.inbetriebnahme_jahr),
        _typ_label(project),
        txt("oberflaeche.kontext_zuschlag",
            wert=fmt_ct_kwh(project.eag_zuschlagswert_effektiv_ct_kwh)),
    ]
    inhalt = "   ·   ".join(html.escape(t) for t in teile)
    st.markdown(
        f'<div class="kontextzeile">{inhalt}</div>', unsafe_allow_html=True
    )


def _kennzahlen(result, npv_satz_pct: float, aenderungen: int,
                global_assumptions) -> None:
    """Leitkennzahl Equity IRR, daneben die vier begleitenden Groessen."""
    kpis = result.kpis
    npv_wert = npv_at(result.cashflow, npv_satz_pct / 100)
    equity_value = npv_wert + kpis.eigenkapital_eur
    fremdkapital = kpis.capex_total_eur - kpis.eigenkapital_eur
    enterprise_value = equity_value + fremdkapital

    ziel_pct = getattr(global_assumptions, "ziel_equity_irr_pct", None) or 0.08
    ziel = None
    if kpis.equity_irr is not None:
        # Bezugsgroesse der Balkenbreite: das 1,5-fache der Zielrendite -
        # so liegt die Marke bei zwei Dritteln und bleibt auch bei
        # deutlicher Zielverfehlung oder -uebererfuellung im Bild.
        bezug = ziel_pct * 1.5
        ziel = (
            min(max(kpis.equity_irr / bezug, 0.0), 1.0),
            min(ziel_pct / bezug, 1.0),
            txt("oberflaeche.kpi_ziel", wert=fmt_pct(ziel_pct, 1)),
        )

    render_kennzahlen(
        leit=Kennzahl(
            label=txt("oberflaeche.projekt_kpi_irr"),
            wert=fmt_pct(kpis.equity_irr, 1),
            zusatz=txt("oberflaeche.kpi_irr_methode"),
        ),
        begleiter=[
            Kennzahl(
                txt("oberflaeche.projekt_kpi_npv_bei",
                    satz=fmt_number(npv_satz_pct, 2)),
                fmt_eur_kompakt(npv_wert), "XNPV act/365", fmt_eur(npv_wert),
            ),
            Kennzahl(
                txt("oberflaeche.projekt_kpi_equity_value"),
                fmt_eur_kompakt(equity_value),
                txt("oberflaeche.kpi_equity_value_formel"),
                fmt_eur(equity_value),
            ),
            Kennzahl(
                txt("oberflaeche.projekt_kpi_enterprise_value"),
                fmt_eur_kompakt(enterprise_value),
                txt("oberflaeche.kpi_enterprise_value_formel"),
                fmt_eur(enterprise_value),
            ),
            Kennzahl(
                txt("oberflaeche.projekt_kpi_capex"),
                fmt_eur_kompakt(kpis.capex_total_eur),
                f"{fmt_number(kpis.capex_total_eur / result.effective_assumptions.nennleistung_kwp, 0)} €/kWp"
                if result.effective_assumptions.nennleistung_kwp else None,
                fmt_eur(kpis.capex_total_eur),
            ),
        ],
        group="projekt",
        abweichung=(
            txt("oberflaeche.kpi_ungespeichert", anzahl=aenderungen)
            if aenderungen else None
        ),
        ziel=ziel,
    )


def _speicherleiste(entwurf: PVProject, gespeichert: PVProject, pfad,
                    form_key: str, aenderungen: int) -> None:
    """Fusszeile der Parameterspalte: Aenderungen zaehlen, sichern oder
    verwerfen. Ohne offene Aenderungen bleibt sie unauffaellig."""
    st.divider()
    # Statuszeile ueber statt neben den Knoepfen: In der schmalen Spalte
    # blieb sonst so wenig Platz, dass "Speichern" und "Verwerfen" in den
    # Knoepfen umbrachen.
    if aenderungen:
        st.markdown(
            f":orange[{txt('oberflaeche.parameter_aenderungen', anzahl=aenderungen)}]"
        )
    else:
        st.caption(txt("oberflaeche.parameter_keine_aenderungen"))

    col_verwerfen, col_speichern = st.columns(2, vertical_alignment="center")
    if col_verwerfen.button(
        txt("oberflaeche.btn_verwerfen"), key=f"{form_key}__verwerfen",
        width="stretch", disabled=not aenderungen,
    ):
        verwirf_entwurf(form_key)
        st.rerun()

    if col_speichern.button(
        txt("oberflaeche.btn_speichern_kurz"), key=f"{form_key}__speichern",
        type="primary", width="stretch", disabled=not aenderungen,
    ):
        services.save_project(entwurf, pfad)
        st.session_state.pop(f"pdf_bericht_{gespeichert.id}", None)
        st.success(txt("oberflaeche.projekt_aktualisiert"))
        st.rerun()


def _pdf_knopf(projekt_id: str, project: PVProject, npv_satz_pct: float,
               aenderungen: int) -> None:
    """Bericht erzeugen und herunterladen - zwei Schritte, weil der Aufbau
    einige Sekunden dauert."""
    pdf_key = f"pdf_bericht_{projekt_id}"
    if pdf_key not in st.session_state:
        if st.button(txt("oberflaeche.btn_pdf_bericht"),
                     key=f"pdf_btn_{projekt_id}", type="primary",
                     width="stretch",
                     help=txt("oberflaeche.btn_pdf_bericht_hilfe")
                     if aenderungen else None):
            with st.spinner(txt("oberflaeche.projekt_pdf_spinner")):
                st.session_state[pdf_key] = services.build_project_report(
                    projekt_id, npv_satz_pct / 100
                )
            st.rerun()
    else:
        st.download_button(
            txt("oberflaeche.btn_pdf_bericht_laden"),
            data=st.session_state[pdf_key],
            file_name=f"{services.slugify(project.name)}_bericht.pdf",
            mime="application/pdf", width="stretch", type="primary",
            key=f"pdf_dl_{projekt_id}",
        )


def _weitere_aktionen(project: PVProject, pfad) -> None:
    """Duplizieren, Aktiv-Schalter und Loeschen im Ueberlaufmenue.

    Loeschen ist unumkehrbar und darf nicht die visuelle Prominenz eines
    Exports haben - deshalb hier statt in der Knopfreihe.
    """
    with st.popover("⋯", width="stretch", help=txt("oberflaeche.aktionen_weitere")):
        if st.button(txt("oberflaeche.btn_duplizieren"),
                     key=f"dup_{project.id}", width="stretch"):
            kopie = services.duplicate_project(project.id)
            if kopie is not None:
                router.gehe_zu("projekt", projekt_id=kopie.id)
        aktiv_label = (txt("oberflaeche.btn_inaktiv_schalten") if project.aktiv
                       else txt("oberflaeche.btn_aktivieren"))
        if st.button(aktiv_label, key=f"aktiv_{project.id}", width="stretch"):
            project.aktiv = not project.aktiv
            services.save_project(project, pfad)
            st.rerun()
        if st.button(txt("oberflaeche.btn_loeschen"), key=f"del_{project.id}",
                     width="stretch"):
            st.session_state[STATE_DELETE_CANDIDATE] = project.id
            st.rerun()


def _loeschbestaetigung(project: PVProject, pfad) -> None:
    if st.session_state.get(STATE_DELETE_CANDIDATE) != project.id:
        return
    st.warning(txt("oberflaeche.projekt_loeschen_warnung", name=project.name))
    col_ja, col_nein, _ = st.columns([1, 1, 4])
    if col_ja.button(txt("oberflaeche.btn_ja_loeschen"), type="primary",
                     key=f"del_ok_{project.id}"):
        services.delete_project(project.id)
        st.session_state.pop(STATE_DELETE_CANDIDATE, None)
        router.gehe_zu("portfolio")
    if col_nein.button(txt("oberflaeche.btn_abbrechen"),
                       key=f"del_no_{project.id}"):
        st.session_state.pop(STATE_DELETE_CANDIDATE, None)
        st.rerun()


def _analyse_tabs(result, project: PVProject, projekt_id: str,
                  npv_satz_pct: float, aenderungen: int) -> None:
    """Vier Sichten auf dasselbe Projekt.

    Regel der Gliederung: Tabs sind gleichrangige Sichten, Klappfelder
    optionales Detail INNERHALB einer Sicht - und nie ineinander. Aus den
    frueheren sieben Tabs werden dadurch vier; die drei Risikosichten
    stehen als Abschnitte untereinander, weil sie dieselbe Frage mit
    unterschiedlicher Methode beantworten.
    """
    aktueller = router.aktueller_tab()
    codes = [code for code, _ in _TABS]
    beschriftungen = [txt(schluessel) for _, schluessel in _TABS]
    wahl = st.segmented_control(
        txt("oberflaeche.projekt_ansicht_label"),
        beschriftungen,
        default=beschriftungen[codes.index(aktueller)],
        key=f"tabwahl_{projekt_id}",
        label_visibility="collapsed",
        width="stretch",
    )
    gewaehlt = codes[beschriftungen.index(wahl)] if wahl in beschriftungen else aktueller
    if gewaehlt != aktueller:
        router.setze_tab(gewaehlt)

    df = result.cashflow.data
    if gewaehlt == "ergebnis":
        render_cashflow_tab(result, df)
        st.divider()
        render_revenue_tab(result, df)
    elif gewaehlt == "finanzierung":
        render_financing_tab(result, df, project)
    elif gewaehlt == "risiko":
        if aenderungen:
            st.info(txt("oberflaeche.risiko_gespeicherter_stand"))
        render_sensitivity_tab(result, project, projekt_id)
        st.divider()
        render_monte_carlo_tab(projekt_id, npv_satz_pct / 100)
        st.divider()
        render_scenario_tab(result, projekt_id, npv_satz_pct / 100)
    else:
        render_assumptions_tab(result)
