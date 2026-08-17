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
from app.theme import Colors
from app.views.vergleich import render_vergleich
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
    ("vergleich", "oberflaeche.projekt_tab_vergleich"),
)


def _ziel_equity_irr() -> float:
    """Zielrendite, an der die Kennzahlenleiste und der Variantenvergleich
    dieselbe Marke setzen."""
    ga = services.get_global_assumptions()
    return getattr(ga, "ziel_equity_irr_pct", None) or 0.08


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


#: Modellfeld -> Beschriftung in der Aenderungsanzeige. Die Namen
#: folgen den Feldern der Parameterspalte; was hier fehlt, erscheint
#: mit seinem technischen Feldnamen - das ist selten und immer noch
#: brauchbarer als gar kein Hinweis.
_FELD_LABEL: dict[str, str] = {
    "name": "Name",
    "standort": "Standort",
    "variante": "Variante",
    "inbetriebnahme_jahr": "IBN-Jahr",
    "inbetriebnahme_monat": "IBN-Monat",
    "anlagentyp": "Anlagentyp",
    "nennleistung_kwp": "Leistung",
    "vollbenutzungsstunden_kwh_kwp": "Vollbenutzungsstunden",
    "bauform": "Bauform",
    "capex": "Investkosten",
    "zusatz_opex": "Zusatz-OPEX",
    "pacht_eur_kwp_jahr": "Pacht",
    "pacht_modus": "Pachtmodus",
    "pacht_umsatzbeteiligung_pct": "Umsatzbeteiligung",
    "pacht_mindestpacht_eur_ha_jahr": "Mindestpacht",
    "projektflaeche_ha": "Projektfläche",
    "fremdkapitalzins_pct": "FK-Zins",
    "eigenkapitalquote_pct": "EK-Anteil",
    "eag_zuschlagswert_ct_kwh": "EAG-Zuschlagswert",
    "gemeindeabgabe_eur_mwh": "Gemeindeabgabe",
    "direktvermarktungskosten_eur_mwh": "Direktvermarktung",
    "marktpreisszenario": "Marktpreisszenario",
    "ppa_anteil_pct": "PPA-Anteil",
    "ppa_preis_eur_mwh": "PPA-Preis",
    "ppa_start_jahr": "PPA-Start",
    "ppa_laufzeit_jahre": "PPA-Laufzeit",
    "ppa_indexierung_pct_pa": "PPA-Indexierung",
    "leitvariante": "Leitfall",
    "aktiv": "Aktiv",
}


def _geaenderte_felder(entwurf: PVProject, gespeichert: PVProject) -> list[str]:
    """Beschriftungen der Modellfelder, die im Entwurf abweichen.

    Verschachtelte Strukturen (capex, Zusatzpositionen) zaehlen als ein
    Feld - die Liste soll zeigen, WORAN gearbeitet wurde, keine exakte
    Feldbilanz sein. Ohne sie sagt die Spalte nur "3 Aenderungen", und
    bei ueber vierzig Feldern ist das keine Auskunft.
    """
    a = entwurf.model_dump()
    b = gespeichert.model_dump()
    # 0,01 €/kWp Spielraum - das Doppelte des groesstmoeglichen
    # Rundungsfehlers der spezifischen Anzeige, und weit unter einem
    # Eingabeschritt. Die Schranke gilt AUSSCHLIESSLICH fuer die
    # Investkosten: Auf Anteile (Eigenkapitalquote, Zinssatz) angewandt
    # wuerde eine Euro-Schranke jede denkbare Aenderung verschlucken.
    absolut = 0.01 * max(entwurf.nennleistung_kwp, gespeichert.nennleistung_kwp)
    return [
        _FELD_LABEL.get(schluessel, schluessel)
        for schluessel in a
        if _weicht_ab(
            a[schluessel], b.get(schluessel),
            absolut if schluessel == "capex" else 0.0,
        )
    ]


def _zaehle_aenderungen(entwurf: PVProject, gespeichert: PVProject) -> int:
    """Anzahl der abweichenden Modellfelder - siehe _geaenderte_felder."""
    return len(_geaenderte_felder(entwurf, gespeichert))


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

    varianten = services.varianten_von(gespeichert)
    weg = [txt("oberflaeche.nav_portfolio"), gespeichert.name]
    if gespeichert.variante:
        weg.append(gespeichert.variante)
    st.markdown(
        f'<div class="brotkrume"><b>{html.escape(weg[0])}</b> › '
        + " › ".join(html.escape(t) for t in weg[1:])
        + "</div>",
        unsafe_allow_html=True,
    )

    # --- Kopfzeile mit Aktionen ---------------------------------------------
    col_titel, col_pdf, col_excel, col_mehr = st.columns([6, 1.5, 1.0, 0.5],
                                                         vertical_alignment="bottom")
    with col_titel:
        st.markdown(f"### {gespeichert.name}")

    _variantenleiste(varianten, projekt_id)

    # Die Loeschabfrage entsteht hier, gleich unter der Kopfzeile - dort
    # steht auch der Knopf, der sie ausloest. Frueher wurde sie erst nach
    # dem Aufbau der Arbeitsflaeche erzeugt und landete deshalb UNTER
    # Kennzahlen, Diagrammen und Parameterspalte: Wer im Ueberlaufmenue
    # "Loeschen" waehlte, sah oben nichts geschehen und hielt das
    # Loeschen fuer kaputt.
    _loeschbestaetigung(gespeichert, pfad)

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
    # Die Parameterspalte kommt mit rund einem Viertel der Breite aus -
    # die Felder stehen ohnehin untereinander. Das Ergebnis gewinnt damit
    # spuerbar Platz fuer die Diagramme.
    #
    # Ausnahme Vergleichssicht: Sie stellt ALLE Varianten gegenueber, die
    # Parameterspalte bearbeitet aber nur die eine geoeffnete. Nebeneinander
    # gestellt naehme sie ein Viertel der Breite fuer eine Eingabe, die zur
    # gezeigten Frage nichts beitraegt - und legte nahe, man bearbeite den
    # Vergleich.
    ist_vergleich = router.aktueller_tab() == "vergleich"
    if ist_vergleich:
        col_ergebnis = st.container()
        entwurf = None
    else:
        col_ergebnis, col_parameter = st.columns([0.745, 0.255], gap="medium")

        with col_parameter, st.container(key="parameterbox"):
            st.markdown(
                f'<div class="parameter-kopf">'
                f'{html.escape(txt("oberflaeche.parameter_titel"))}</div>',
                unsafe_allow_html=True,
            )
            # Die Speicherleiste steht OBEN, gleich unter der
            # Kopfzeile: Sie braucht die Zahl der Aenderungen, die erst
            # nach dem Aufbau der Felder feststeht - deshalb hier nur
            # ein Platzhalter, der spaeter gefuellt wird. Unten war sie
            # bei langer Spalte nur nach einer Bildschirmhoehe Scrollen
            # erreichbar, obwohl "Verwerfen" gerade dann gebraucht wird,
            # wenn man sich verrannt hat.
            speicherbereich = st.container()
            entwurf = render_parameter_spalte(gespeichert, form_key)

    # Faellt die Maske aus (z.B. leerer Name), bleibt der gespeicherte
    # Stand die Rechengrundlage - die Seite soll nicht leer werden.
    aktiv = entwurf or gespeichert
    result = services.get_valuation_fuer(aktiv)
    geaendert = _geaenderte_felder(aktiv, gespeichert) if entwurf else []
    aenderungen = len(geaendert)

    if not ist_vergleich:
        with speicherbereich:
            _speicherleiste(aktiv, gespeichert, pfad, form_key, geaendert)

    with col_kontext:
        _kontextzeile(aktiv, result, global_assumptions, npv_satz_pct)

    with col_pdf:
        _pdf_knopf(projekt_id, gespeichert, npv_satz_pct, aenderungen)
    with col_excel:
        st.download_button(
            txt("oberflaeche.btn_excel_export"),
            data=services.cashflow_to_excel(result),
            file_name=f"{services.slugify(aktiv.anzeigename)}_cashflow.xlsx",
            mime=_XLSX_MIME, width="stretch",
        )
    with col_mehr:
        _weitere_aktionen(gespeichert, pfad)

    with col_ergebnis:
        _kennzahlen(result, npv_satz_pct, aenderungen, global_assumptions)
        render_kovenanten_status(result)
        _analyse_tabs(result, aktiv, projekt_id, npv_satz_pct, aenderungen)


# ---------------------------------------------------------------------------
# Bausteine
# ---------------------------------------------------------------------------


def _variantenleiste(varianten: list[PVProject], projekt_id: str) -> None:
    """Die Sensitivitaeten eines Standorts als Reiterreihe.

    Warum hier und nicht in der Seitenleiste: Varianten sind kein
    Ortswechsel, sondern derselbe Standort unter anderen Annahmen. Stehen
    sie in der Projektliste, waechst diese mit jeder Sensitivitaet, und
    man sieht der Liste nicht an, welche Eintraege dasselbe Feld meinen.
    Hier bleibt der Standort stehen, waehrend die Rechnung wechselt - und
    der Vergleich zweier Sensitivitaeten ist ein Klick.

    Jede Variante ist weiterhin ein eigenes Projekt mit eigener Adresse;
    der Reiter navigiert also schlicht zur Schwester-id.

    Hier steht auch der Leitfall: Der Stern markiert die Rechnung, die
    fuer diesen Standort in die Portfoliozahlen eingeht, und der Knopf
    daneben macht die geoeffnete Variante dazu. Diese Wahl gehoerte
    hierher und nicht nur in die Vergleichssicht - sie betrifft die
    Reiterreihe selbst, und wer sie nur im Vergleich findet, findet sie
    gar nicht.
    """
    leitfall = services.leitvariante_von(varianten)
    mehrere = len(varianten) > 1
    with st.container(key="variantenleiste", horizontal=True):
        st.markdown(
            f'<div class="varianten-label">'
            f'{html.escape(txt("oberflaeche.varianten_label"))}</div>',
            unsafe_allow_html=True,
        )
        for variante in varianten:
            key = f"variante_{variante.id}"
            ist_leitfall = mehrere and variante.id == leitfall.id
            hilfe = variante.anzeigename
            if ist_leitfall:
                hilfe += " · " + txt("oberflaeche.variante_leitfall_hilfe")
            beschriftung = (f"★ {variante.variantenlabel}" if ist_leitfall
                            else variante.variantenlabel)
            if st.button(beschriftung, key=key, type="tertiary", help=hilfe):
                router.gehe_zu("projekt", projekt_id=variante.id)
        _variante_umbenennen(projekt_id, varianten)
        if st.button(txt("oberflaeche.btn_neue_variante"), key="variante_neu",
                     type="tertiary",
                     help=txt("oberflaeche.btn_neue_variante_hilfe")):
            neue = services.duplicate_project(projekt_id)
            if neue is not None:
                router.gehe_zu("projekt", projekt_id=neue.id)
        # Nur bei mehreren Varianten: Wo es nichts zu waehlen gibt, ist
        # die geoeffnete Rechnung ohnehin der Leitfall.
        if mehrere and projekt_id != leitfall.id and st.button(
            txt("oberflaeche.btn_leitfall_setzen"), key="variante_leitfall",
            type="tertiary", help=txt("oberflaeche.btn_leitfall_setzen_hilfe"),
        ):
            services.setze_leitvariante(projekt_id)
            st.rerun()
        # Der Vergleich ist keine weitere Variante, sondern die Sicht auf
        # alle - deshalb am Ende der Reihe und in die Sicht verlinkt,
        # nicht als eigener Reiter daneben.
        if len(varianten) > 1 and st.button(
            txt("oberflaeche.btn_vergleich"), key="variante_vergleich",
            type="tertiary", help=txt("oberflaeche.btn_vergleich_hilfe"),
        ):
            router.gehe_zu("projekt", projekt_id=projekt_id, tab="vergleich")
    st.markdown(
        f"<style>.st-key-variante_{projekt_id} button {{"
        f"background: {Colors.SELECT} !important;"
        f"color: {Colors.INK} !important;"
        f"font-weight: 600 !important;"
        f"box-shadow: inset 0 -2px 0 {Colors.BRAND} !important;"
        "}</style>",
        unsafe_allow_html=True,
    )


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
    """Leitkennzahl Equity IRR, daneben die vier begleitenden Groessen.

    Reihenfolge der Begleiter: NPV, Equity Value, CAPEX, Enterprise
    Value. Sie stehen zweispaltig und werden zeilenweise gefuellt -
    damit liegen die beiden Wertbegriffe (Equity Value oben rechts,
    Enterprise Value unten rechts) uebereinander statt ueber Eck.
    """
    kpis = result.kpis
    npv_wert = npv_at(result.cashflow, npv_satz_pct / 100)
    equity_value = npv_wert + kpis.eigenkapital_eur
    fremdkapital = kpis.capex_total_eur - kpis.eigenkapital_eur
    enterprise_value = equity_value + fremdkapital

    ziel_pct = _ziel_equity_irr()
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
                txt("oberflaeche.projekt_kpi_capex"),
                fmt_eur_kompakt(kpis.capex_total_eur),
                f"{fmt_number(kpis.capex_total_eur / result.effective_assumptions.nennleistung_kwp, 0)} €/kWp"
                if result.effective_assumptions.nennleistung_kwp else None,
                fmt_eur(kpis.capex_total_eur),
            ),
            Kennzahl(
                txt("oberflaeche.projekt_kpi_enterprise_value"),
                fmt_eur_kompakt(enterprise_value),
                txt("oberflaeche.kpi_enterprise_value_formel"),
                fmt_eur(enterprise_value),
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
                    form_key: str, geaendert: list[str]) -> None:
    """Kopfzeile der Parameterspalte: Aenderungen benennen, sichern oder
    verwerfen. Ohne offene Aenderungen bleibt sie unauffaellig."""
    aenderungen = len(geaendert)
    # Statuszeile ueber statt neben den Knoepfen: In der schmalen Spalte
    # blieb sonst so wenig Platz, dass "Speichern" und "Verwerfen" in den
    # Knoepfen umbrachen.
    if aenderungen:
        st.markdown(
            f":orange[{txt('oberflaeche.parameter_aenderungen', anzahl=aenderungen)}]"
        )
        # WELCHE Felder offen sind, beantwortet die Zahl allein nicht -
        # bei ueber vierzig Feldern ist das die eigentliche Frage.
        st.caption(", ".join(geaendert))
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
    st.divider()


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
            file_name=f"{services.slugify(project.anzeigename)}_bericht.pdf",
            mime="application/pdf", width="stretch", type="primary",
            key=f"pdf_dl_{projekt_id}",
        )


def _weitere_aktionen(project: PVProject, pfad) -> None:
    """Duplizieren, Aktiv-Schalter und Loeschen im Ueberlaufmenue.

    Loeschen ist unumkehrbar und darf nicht die visuelle Prominenz eines
    Exports haben - deshalb hier statt in der Knopfreihe.
    """
    with st.popover("⋯", width="stretch", help=txt("oberflaeche.aktionen_weitere")):
        _stammdaten_bearbeiten(project, pfad)
        st.divider()
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


def _variante_umbenennen(projekt_id: str, varianten: list[PVProject]) -> None:
    """Umbenennen der geoeffneten Variante - in der Reiterreihe.

    Hierher gehoert es und nicht in ein Projektmenue: Nach dem
    Duplizieren heisst die Kopie "Variante 2", und der naechste Handgriff
    ist, ihr einen sprechenden Namen zu geben. Der Ort dafuer ist die
    Reihe, in der sie steht.

    Ein leerer Name ist erlaubt - das ist der Grundfall des Standorts,
    den die Oberflaeche "Basis" nennt.
    """
    offen = next((v for v in varianten if v.id == projekt_id), None)
    if offen is None:
        return
    with st.popover("✎", help=txt("oberflaeche.variante_umbenennen_hilfe")):
        name = st.text_input(
            txt("oberflaeche.formular_variante_label"), value=offen.variante,
            key=f"variante_name_{projekt_id}",
            placeholder=txt("oberflaeche.formular_variante_platzhalter"),
        )
        if st.button(txt("oberflaeche.btn_uebernehmen"),
                     key=f"variante_name_speichern_{projekt_id}",
                     width="stretch", disabled=name.strip() == offen.variante):
            offen.variante = name.strip()
            services.save_project(offen)
            st.rerun()


def _stammdaten_bearbeiten(project: PVProject, pfad) -> None:
    """Name und Standort - im Ueberlaufmenue statt in der Parameterspalte.

    Beide sind keine What-if-Groessen: Niemand dreht am Projektnamen, um
    eine Rendite zu sehen. In der Live-Spalte kosteten sie dauerhaft
    Platz und standen zwischen Groessen, die man staendig anfasst.

    Gespeichert wird hier SOFORT und nicht ueber den Entwurf: Eine
    Umbenennung ist eine abgeschlossene Handlung, kein Ausprobieren -
    und sie soll nicht in der Aenderungszahl der Rechnung mitlaufen.
    """
    st.markdown(f"**{txt('oberflaeche.stammdaten_titel')}**")
    name = st.text_input(
        txt("oberflaeche.formular_name_label"), value=project.name,
        key=f"stammdaten_name_{project.id}",
        help=txt("oberflaeche.formular_name_hilfe"),
    )
    standort = st.text_input(
        txt("oberflaeche.formular_standort_label"), value=project.standort,
        key=f"stammdaten_standort_{project.id}",
        help=txt("oberflaeche.formular_standort_hilfe"),
    )
    geaendert = name.strip() != project.name or standort.strip() != project.standort
    if st.button(txt("oberflaeche.btn_uebernehmen"),
                 key=f"stammdaten_speichern_{project.id}",
                 width="stretch", disabled=not geaendert or not name.strip()):
        project.name = name.strip()
        project.standort = standort.strip()
        services.save_project(project, pfad)
        st.rerun()


def _loeschbestaetigung(project: PVProject, pfad) -> None:
    if st.session_state.get(STATE_DELETE_CANDIDATE) != project.id:
        return
    st.warning(txt("oberflaeche.projekt_loeschen_warnung",
                   name=project.anzeigename))
    col_ja, col_nein, _ = st.columns([1, 1, 4])
    if col_ja.button(txt("oberflaeche.btn_ja_loeschen"), type="primary",
                     key=f"del_ok_{project.id}"):
        # Nach dem Loeschen einer Variante bleibt man am Standort, solange
        # dort noch eine Rechnung steht - der Sprung ins Portfolio waere
        # ein Ortswechsel, den niemand verlangt hat.
        geschwister = [v for v in services.varianten_von(project)
                       if v.id != project.id]
        services.delete_project(project.id)
        st.session_state.pop(STATE_DELETE_CANDIDATE, None)
        if geschwister:
            router.gehe_zu("projekt", projekt_id=geschwister[0].id)
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
    elif gewaehlt == "vergleich":
        render_vergleich(
            services.varianten_von(project), projekt_id,
            _ziel_equity_irr(), npv_satz_pct,
        )
    else:
        render_assumptions_tab(result)
