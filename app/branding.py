"""
Verdeckter Marken-Schalter: zwei vollstaendige Gestaltungen (Farben,
Logo, Favicon, Kopfzeilentexte) hinterlegt - die aktuelle Nobis-
Analytics-Gestaltung (Standard) und die vorherige Trianel-Gestaltung.

Aktivierung ueber den URL-Parameter ?marke=trianel, z.B.
https://<app-url>/?marke=trianel - nirgends in der Oberflaeche
verlinkt oder dokumentiert, daher "verdeckt". Zurueck zu Nobis
Analytics: ?marke=nobis oder den Parameter aus der URL entfernen und
neu laden (ein einmal gesetzter Wert bleibt sonst fuer die laufende
Session bestehen, siehe aktive_marke_code()).

Nutzung (frueh im Entry-Point, vor set_page_config/apply_theme):

    from app.branding import aktive_marke
    marke = aktive_marke()
    ... marke["app_titel"], marke["logo"], marke["favicon"],
        marke["farben"] (dict mit denselben Schluesseln wie
        app.theme.Colors: BRAND, INK, INK_SOFT, MUTED, NEUTRAL,
        LINE, WASH) ...

Bekannte Einschraenkung: app.theme.Colors (und die gespiegelten
Konstanten in app.report) sind PROZESSWEIT globaler Zustand, nicht
sitzungsspezifisch. Bei mehreren GLEICHZEITIGEN Nutzern auf demselben
Streamlit-Worker-Prozess koennte sich in seltenen, timing-abhaengigen
Faellen die Farbwahl einer Session kurzzeitig mit der einer anderen
ueberschneiden (kein Datenrisiko, rein optisch). Fuer eine verdeckte,
selten genutzte Vergleichsansicht ist das ein akzeptabler Kompromiss;
fuer produktiven Mehrnutzerbetrieb mit haeufigem Markenwechsel muesste
die Farbgebung stattdessen sitzungsspezifisch (z.B. per Parameter statt
globalem Zustand) durchgereicht werden.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

#: Beide Paletten wie in app.theme.Colors bzw. app.report dokumentiert;
#: siehe dort fuer Herleitung/Kontrastwerte. Trianel-Werte sind die vor
#: dem Rebrand (v4.15) verwendeten Originalwerte.
MARKEN: dict[str, dict] = {
    "nobis": {
        "app_titel": "Nobis Analytics",
        "kopfzeile_titel": "PV-Projektbewertung",
        "logo": _ASSETS_DIR / "nobis_logo.png",
        "logo_breite": 190,
        "favicon": _ASSETS_DIR / "favicon.png",
        "farben": {
            "BRAND": "#167B88", "INK": "#14304F", "INK_SOFT": "#2B4F77",
            "MUTED": "#5C636A", "NEUTRAL": "#8A97A6",
            "LINE": "#E1E4E8", "WASH": "#F6F7F9",
        },
    },
    "trianel": {
        "app_titel": "TEA PV-Projektbewertung",
        "kopfzeile_titel": "TEA PV-Projektbewertung",
        "logo": _ASSETS_DIR / "trianel" / "logo.png",
        "logo_breite": 84,
        "favicon": _ASSETS_DIR / "trianel" / "favicon.png",
        "farben": {
            "BRAND": "#BE172B", "INK": "#143530", "INK_SOFT": "#2E5A52",
            "MUTED": "#5B6B66", "NEUTRAL": "#8AA6A0",
            "LINE": "#E1E8E5", "WASH": "#F6F9F8",
        },
    },
}

STANDARD_MARKE = "nobis"
_SESSION_KEY = "aktive_marke"
_QUERY_PARAM = "marke"


def aktive_marke_code() -> str:
    """Ermittelt die aktive Marke: URL-Parameter > laufende Session >
    Standard (Nobis Analytics). Ein per URL gesetzter Wert wird in die
    Session uebernommen, damit er auch nach dem Wegfallen des
    Parameters (z.B. Klick auf einen internen Link) fuer den Rest der
    Sitzung bestehen bleibt."""
    try:
        param = st.query_params.get(_QUERY_PARAM)
    except Exception:
        param = None
    if param in MARKEN:
        st.session_state[_SESSION_KEY] = param
    return st.session_state.get(_SESSION_KEY, STANDARD_MARKE)


def aktive_marke() -> dict:
    return MARKEN[aktive_marke_code()]
