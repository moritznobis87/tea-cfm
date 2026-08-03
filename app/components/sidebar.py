"""
Seitenleiste: Navigation, Projektwechsel und Sichern/Wiederherstellen.

Warum Knoepfe statt eines Radio-Feldes: Ein Radio-Feld ist ein
Formularelement - es sagt "triff eine Auswahl innerhalb dieses Formulars".
Navigation ist aber keine Auswahl, sondern ein Ortswechsel. Der aktive
Eintrag wird deshalb hervorgehoben ("hier bist du gerade"), und aus
demselben Grund sieht das geoeffnete Projekt genauso aus wie die aktive
Seite: Es ist dieselbe Sache.

Sichern und Wiederherstellen bleiben bewusst in der Navigation und nicht
auf einer Einstellungsseite - beides wird haeufig gebraucht und soll ein
Klick sein. Hintergrund: Streamlit Cloud hat kein dauerhaftes Dateisystem,
neu angelegte Projekte gehen bei einem Reboot verloren, wenn sie nicht
gesichert wurden. Der Excel-Down-/Upload ist der bewusst einfache
Sicherungsweg (und fuer tabellarische Daten wie Preiskurven ohnehin das
bequemere Bearbeitungsformat als YAML).
"""

from __future__ import annotations

import streamlit as st

from app import router, services
from app.config import PROJECTS_DIR
from app.theme import Colors
from engine.io_excel import (
    excel_to_global_assumptions,
    excel_to_projects,
    global_assumptions_to_excel,
    projects_to_excel,
)
from engine.io_yaml import load_project_yaml
from texte import txt

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

#: Navigationseintraege ausserhalb der Projektliste.
_NAV = (
    ("portfolio", "oberflaeche.nav_portfolio"),
    ("annahmen", "oberflaeche.nav_globale_annahmen"),
)

#: Werkzeuge stehen bewusst in einer eigenen Gruppe: Die Ausschreibungs-
#: analyse wertet vergangene Runden aus und liefert einen Vorschlagswert,
#: sie fuehrt aber keine eigenen Projektdaten. Gleichrangig neben
#: Portfolio und Annahmen gestellt, legte sie das Gegenteil nahe.
_WERKZEUGE = (
    ("ausschreibung", "oberflaeche.nav_ausschreibung"),
)


def _hervorhebung(keys: list[str]) -> None:
    """Hebt die genannten Knopf-Container als 'aktiv' hervor.

    Streamlit vergibt fuer jeden Container mit `key` die CSS-Klasse
    `st-key-<key>`; darueber laesst sich genau der aktive Eintrag
    einfaerben, ohne alle Knoepfe der Seitenleiste anzufassen.
    """
    if not keys:
        return
    wahl = ", ".join(f".st-key-{k} button" for k in keys)
    st.markdown(
        f"""<style>
        {wahl} {{
            background: {Colors.SELECT} !important;
            color: {Colors.INK} !important;
            font-weight: 600 !important;
            box-shadow: inset 3px 0 0 {Colors.BRAND} !important;
        }}
        </style>""",
        unsafe_allow_html=True,
    )


def _ausgrauen(keys: list[str]) -> None:
    """Inaktive Projekte blasser darstellen - dieselbe Aussage wie die
    ausgegraute Projektkarte im Portfolio, ohne Zusatzzeichen im Namen."""
    if not keys:
        return
    wahl = ", ".join(f".st-key-{k} button" for k in keys)
    st.markdown(
        f"<style>{wahl} {{ opacity: 0.55; font-style: italic; }}</style>",
        unsafe_allow_html=True,
    )


def _gruppentitel(text: str) -> None:
    st.sidebar.markdown(
        f'<div class="nav-gruppe">{text}</div>', unsafe_allow_html=True
    )


def render_sidebar() -> None:
    """Baut die vollstaendige Seitenleiste."""
    aktiv_keys: list[str] = []
    seite = router.aktuelle_seite()
    offenes_projekt = router.aktuelles_projekt()

    _gruppentitel(txt("oberflaeche.nav_titel"))
    for code, schluessel in _NAV:
        key = f"nav_{code}"
        if seite == code:
            aktiv_keys.append(key)
        if st.sidebar.button(
            txt(schluessel), key=key, width="stretch", type="tertiary"
        ):
            router.gehe_zu(code)

    _gruppentitel(txt("oberflaeche.nav_gruppe_werkzeuge"))
    for code, schluessel in _WERKZEUGE:
        key = f"nav_{code}"
        if seite == code:
            aktiv_keys.append(key)
        if st.sidebar.button(
            txt(schluessel), key=key, width="stretch", type="tertiary",
            help=txt("oberflaeche.nav_ausschreibung_hilfe"),
        ):
            router.gehe_zu(code)

    # --- Projekte -----------------------------------------------------------
    # Ein Eintrag je STANDORT, nicht je Variante: Sonst waechst die Liste
    # mit jeder Sensitivitaet, und man sieht ihr nicht an, welche
    # Eintraege dasselbe Feld meinen. Die Varianten waehlt man im
    # Projektfenster (siehe app/views/project_page.py).
    projekte = services.list_project_files()
    standorte = services.gruppiere_nach_standort()
    _gruppentitel(txt("oberflaeche.nav_gruppe_projekte"))
    if not projekte:
        st.sidebar.caption(txt("oberflaeche.sidebar_keine_projekte"))
    inaktiv_keys: list[str] = []
    for standort, varianten in standorte.items():
        # Ist eine Variante dieses Standorts offen, zeigt der Eintrag auf
        # genau sie; sonst auf die erste. Andernfalls wuerde ein Klick auf
        # den ohnehin aktiven Eintrag die offene Variante wechseln.
        ziel = next(
            (v for v in varianten if v.id == offenes_projekt), varianten[0]
        )
        key = f"projektwahl_{ziel.id}"
        if seite == "projekt" and offenes_projekt in {v.id for v in varianten}:
            aktiv_keys.append(key)
        if all(not v.aktiv for v in varianten):
            inaktiv_keys.append(key)
        # Der vollstaendige Name steht im Tooltip - in der Leiste wird er
        # auf eine Zeile gekuerzt (siehe app/theme.py).
        beschriftung = standort
        hilfe = standort
        if len(varianten) > 1:
            beschriftung = f"{standort}  ·{len(varianten)}"
            hilfe = txt("oberflaeche.sidebar_standort_hilfe",
                        name=standort,
                        varianten=", ".join(v.variantenlabel for v in varianten))
        if all(not v.aktiv for v in varianten):
            hilfe = f"{hilfe} — {txt('oberflaeche.badge_inaktiv')}"
        if st.sidebar.button(
            beschriftung, key=key, width="stretch", type="tertiary",
            help=hilfe,
        ):
            router.gehe_zu("projekt", projekt_id=ziel.id)
    _ausgrauen(inaktiv_keys)

    if st.sidebar.button(
        txt("oberflaeche.nav_neues_projekt_knopf"), key="nav_neu",
        width="stretch", type="primary",
    ):
        router.gehe_zu("neu")

    # --- Sichern ------------------------------------------------------------
    _gruppentitel(txt("oberflaeche.nav_gruppe_sichern"))
    if projekte:
        alle_projekte = [load_project_yaml(p) for p in projekte.values()]
        st.sidebar.download_button(
            txt("oberflaeche.sidebar_projekte_sichern"),
            data=projects_to_excel(alle_projekte),
            file_name="projekte.xlsx",
            mime=_XLSX_MIME,
            width="stretch",
            help=txt("oberflaeche.sidebar_projekte_beschreibung"),
        )
    st.sidebar.download_button(
        txt("oberflaeche.sidebar_annahmen_sichern"),
        data=global_assumptions_to_excel(services.get_global_assumptions()),
        file_name="globale_annahmen.xlsx",
        mime=_XLSX_MIME,
        width="stretch",
        help=txt("oberflaeche.sidebar_annahmen_beschreibung"),
    )
    _wiederherstellen()

    _hervorhebung(aktiv_keys)


def _wiederherstellen() -> None:
    """Beide Uploads in einem Popover - Wiederherstellen ist der seltenere
    Fall und soll die Leiste nicht dauerhaft in die Laenge ziehen."""
    with st.sidebar.popover(
        txt("oberflaeche.sidebar_wiederherstellen"), width="stretch"
    ):
        st.markdown(f"**{txt('oberflaeche.sidebar_projekte_titel')}**")
        hochgeladene_projekte = st.file_uploader(
            txt("oberflaeche.sidebar_projekte_upload_label"),
            type=["xlsx"], key="project_upload",
        )
        if hochgeladene_projekte and st.button(
            txt("oberflaeche.sidebar_hochgeladene_projekte_speichern"),
            type="primary", width="stretch",
        ):
            try:
                importierte = excel_to_projects(hochgeladene_projekte.getvalue())
                for projekt in importierte:
                    services.save_project(
                        projekt, PROJECTS_DIR / f"{projekt.id}.yaml"
                    )
                st.success(
                    txt("oberflaeche.sidebar_projekte_gespeichert",
                        namen=", ".join(p.name for p in importierte))
                )
                st.rerun()
            except Exception as fehler:
                st.error(txt("oberflaeche.sidebar_excel_fehler", fehler=fehler))

        st.divider()
        st.markdown(f"**{txt('oberflaeche.sidebar_annahmen_titel')}**")
        hochgeladene_ga = st.file_uploader(
            txt("oberflaeche.sidebar_annahmen_upload_label"), type=["xlsx"],
            key="global_assumptions_upload",
        )
        if hochgeladene_ga and st.button(
            txt("oberflaeche.sidebar_annahmen_uebernehmen"),
            type="primary", width="stretch",
        ):
            try:
                neue_ga = excel_to_global_assumptions(hochgeladene_ga.getvalue())
                services.save_global_assumptions(neue_ga)
                st.success(txt("oberflaeche.sidebar_annahmen_uebernommen"))
                st.rerun()
            except Exception as fehler:
                st.error(txt("oberflaeche.sidebar_excel_fehler", fehler=fehler))
