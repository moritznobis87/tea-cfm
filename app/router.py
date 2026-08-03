"""
Seitensteuerung ueber Adressparameter.

Warum ueberhaupt: Bis Version 4.29 lag die geoeffnete Ansicht allein im
Session-State. Die Adresse blieb dadurch immer dieselbe - Neuladen verwarf
die Auswahl, ein Link auf ein bestimmtes Projekt liess sich nicht
verschicken, und der Zurueck-Knopf des Browsers hatte nichts, wohin er
haette fuehren koennen.

Aufbau:
    ?seite=portfolio
    ?seite=projekt&id=<projekt-id>&tab=<tab>
    ?seite=neu
    ?seite=ausschreibung
    ?seite=annahmen

Die massgebliche Fassung steht weiterhin im Session-State; die
Adressparameter werden bei jedem Wechsel mitgeschrieben und beim ersten
Durchlauf einer Sitzung eingelesen. Diese Doppelung ist Absicht: Der
Session-State funktioniert auch dort, wo keine echten Adressparameter
vorliegen (Streamlits AppTest-Rahmen), die Adresse traegt dafuer den
Zustand ueber Neuladen und Lesezeichen hinweg.
"""

from __future__ import annotations

import streamlit as st

#: Alle gueltigen Seiten. Reihenfolge = Reihenfolge in der Navigation.
SEITEN = ("portfolio", "projekt", "neu", "ausschreibung", "annahmen")
STANDARD_SEITE = "portfolio"

#: Analyse-Tabs der Projektseite (siehe app/views/project_detail.py).
PROJEKT_TABS = ("ergebnis", "finanzierung", "risiko", "annahmen",
                "vergleich")
STANDARD_TAB = "ergebnis"

_STATE_SEITE = "route_seite"
_STATE_ID = "route_projekt_id"
_STATE_TAB = "route_tab"


def _aus_adresse(schluessel: str, erlaubt: tuple[str, ...] | None = None) -> str | None:
    """Liest einen Adressparameter, sofern er gueltig ist.

    st.query_params ist ausserhalb eines echten Browserlaufs leer bzw.
    nicht verfuegbar - der Zugriff wird deshalb abgesichert, damit
    dieselben Codepfade auch im Testrahmen laufen.
    """
    try:
        wert = st.query_params.get(schluessel)
    except Exception:  # pragma: no cover - nur ausserhalb des Browsers
        return None
    if not wert:
        return None
    wert = str(wert)
    if erlaubt is not None and wert not in erlaubt:
        return None
    return wert


def _initialisiere() -> None:
    """Uebernimmt die Adressparameter genau einmal je Sitzung."""
    if _STATE_SEITE in st.session_state:
        return
    st.session_state[_STATE_SEITE] = (
        _aus_adresse("seite", SEITEN) or STANDARD_SEITE
    )
    st.session_state[_STATE_ID] = _aus_adresse("id")
    st.session_state[_STATE_TAB] = (
        _aus_adresse("tab", PROJEKT_TABS) or STANDARD_TAB
    )


def aktuelle_seite() -> str:
    _initialisiere()
    return st.session_state[_STATE_SEITE]


def aktuelles_projekt() -> str | None:
    _initialisiere()
    return st.session_state.get(_STATE_ID)


def aktueller_tab() -> str:
    _initialisiere()
    return st.session_state.get(_STATE_TAB) or STANDARD_TAB


def _schreibe_adresse() -> None:
    """Spiegelt den Zustand in die Adresszeile."""
    try:
        st.query_params.clear()
        st.query_params["seite"] = st.session_state[_STATE_SEITE]
        if st.session_state[_STATE_SEITE] == "projekt":
            if st.session_state.get(_STATE_ID):
                st.query_params["id"] = st.session_state[_STATE_ID]
            st.query_params["tab"] = st.session_state.get(_STATE_TAB, STANDARD_TAB)
    except Exception:  # pragma: no cover - nur ausserhalb des Browsers
        return


def gehe_zu(seite: str, projekt_id: str | None = None,
            tab: str | None = None) -> None:
    """Wechselt die Seite und loest einen Rerun aus.

    Bewusst mit explizitem st.rerun(): Der Aufruf steht ueblicherweise im
    Klick-Zweig eines Knopfes, und der restliche Seitenaufbau dieses
    Durchlaufs gehoert noch zur alten Seite.
    """
    _initialisiere()
    if seite not in SEITEN:
        seite = STANDARD_SEITE
    st.session_state[_STATE_SEITE] = seite
    if projekt_id is not None:
        st.session_state[_STATE_ID] = projekt_id
    if tab is not None:
        st.session_state[_STATE_TAB] = tab if tab in PROJEKT_TABS else STANDARD_TAB
    elif seite == "projekt" and projekt_id is not None:
        # Beim Wechsel auf ein anderes Projekt mit der Standardsicht
        # beginnen, statt den Tab des vorigen Projekts beizubehalten.
        st.session_state[_STATE_TAB] = STANDARD_TAB
    _schreibe_adresse()
    st.rerun()


def setze_tab(tab: str) -> None:
    """Merkt den gewaehlten Analyse-Tab, ohne einen Rerun auszuloesen.

    st.tabs meldet keine Auswahl zurueck; der Tab wird deshalb ueber die
    Segmentauswahl der Projektseite gesetzt (siehe project_detail).
    """
    _initialisiere()
    st.session_state[_STATE_TAB] = tab if tab in PROJEKT_TABS else STANDARD_TAB
    _schreibe_adresse()
