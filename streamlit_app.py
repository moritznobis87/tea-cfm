"""
Nobis Analytics PV-Projektbewertung - Einstiegspunkt.

Bewusst duenn gehalten: Seitenkonfiguration, Theme, Kopfzeile und
Navigation. Die eigentlichen Seiten leben in app/views/, wieder-
verwendbare Bausteine in app/components/, Datenzugriff und Caching in
app/services.py, die Fachlogik in engine/.
"""

from __future__ import annotations

import streamlit as st

from app.branding import aktive_marke

# Verdeckter Marken-Schalter: URL-Parameter ?marke=trianel zeigt die
# vorherige Trianel-Gestaltung, sonst (Standard) Nobis Analytics -
# siehe app/branding.py fuer Details. Muss vor set_page_config/
# apply_theme ermittelt und angewendet werden.
_MARKE = aktive_marke()

# Markenfarbe und Schrift zur Laufzeit fixieren: .streamlit/config.toml
# greift nur, wenn die App aus dem Projektordner gestartet wird. Damit die
# Akzentfarbe unabhaengig vom Startverzeichnis (und vom aktiven Marken-
# Schalter) gilt, werden die Theme-Optionen hier zusaetzlich gesetzt (vor
# set_page_config, damit sie in der ersten an den Browser gesendeten
# Session ankommen).
from streamlit import config as _st_config  # noqa: E402

from app.theme import apply_theme, wende_farben_an  # noqa: E402

wende_farben_an(_MARKE["farben"])

_INTER = (
    "Inter:https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700"
    "&display=swap, sans-serif"
)
for _option, _wert in [
    ("theme.primaryColor", _MARKE["farben"]["BRAND"]),
    ("theme.font", _INTER),
    ("theme.headingFont", _INTER),
]:
    if _st_config.get_option(_option) != _wert:
        _st_config.set_option(_option, _wert)

st.set_page_config(
    page_title=_MARKE["app_titel"],
    layout="wide",
    page_icon=str(_MARKE["favicon"]) if _MARKE["favicon"].exists() else "☀️",
)
apply_theme()

# Imports der Views erst NACH set_page_config - Streamlit verlangt, dass
# set_page_config der allererste Streamlit-Befehl des Skripts ist, und die
# Views fuehren beim Import bereits Streamlit-Code aus (Caching-Dekoratoren).
from app import services  # noqa: E402
from app.components.sidebar import render_import_export  # noqa: E402
from app.config import FLAGS_DIR  # noqa: E402
from app.views.assumptions import render_assumptions  # noqa: E402
from engine import MarktSystem  # noqa: E402
from app.views.auktion import render_auktion  # noqa: E402
from app.views.new_project import render_new_project  # noqa: E402
from app.views.overview import render_overview  # noqa: E402
from texte import SESSION_KEY, SPRACHEN, sprachauswahl_label, txt  # noqa: E402

# --- Kopfzeile (Hero) --------------------------------------------------------
# In einem eigenen, per key adressierbaren Container (siehe CSS-Regel
# .st-key-app_header in app/theme.py): Ohne Mindesthoehe faellt die
# Zeilenhoehe bei kurzem, unumbrochenem Titeltext knapp auf die Hoehe
# des Titeltexts selbst - Logo und Sprach-Popover (beide etwas hoeher)
# werden dann oben abgeschnitten. Bricht der Titel dagegen um (schmales
# Fenster), waechst die Zeile automatisch mit und das Problem
# verschwindet von selbst - ein sicheres Erkennungsmerkmal dafuer, dass
# schlicht die garantierte Mindesthoehe fehlte.
with st.container(key="app_header"):
    col_logo, col_title, col_sprache = st.columns(
        [2.2, 7, 1.4], vertical_alignment="center"
    )
    if _MARKE["logo"].exists():
        col_logo.image(str(_MARKE["logo"]), width=_MARKE["logo_breite"])
    # Untertitel folgt der in den globalen Annahmen gewaehlten
    # Marktsystematik (EAG Oesterreich / EEG Deutschland).
    _untertitel_key = (
        "oberflaeche.app_untertitel_de"
        if services.get_global_assumptions().markt_system == MarktSystem.DEUTSCHLAND
        else "oberflaeche.app_untertitel_at"
    )
    col_title.markdown(
        f"""<div>
        <p class="app-hero-title">{_MARKE["kopfzeile_titel"]}</p>
        <p class="app-hero-sub">{txt(_untertitel_key)}</p>
        </div>""",
        unsafe_allow_html=True,
    )

    # Sprachauswahl als Popover mit echten Flaggen-Bildicons (assets/flags/):
    # Emoji-Flaggen werden je nach Betriebssystem/Browser/Schriftart oft
    # nicht dargestellt (u.a. verbreitet unter Windows), und st.selectbox
    # kann grundsaetzlich keine Bilder in seinen Optionen anzeigen (nur
    # Text via format_func) - st.popover erlaubt dagegen beliebigen Inhalt,
    # hier eine Zeile Bild+Button je Sprache. Trigger nutzt ein Material-
    # Icon (":material/..."), das Streamlit selbst mitliefert und damit
    # ebenfalls unabhaengig von der System-Emoji-Schrift zuverlaessig
    # rendert.
    _sprachcodes = list(SPRACHEN)
    _aktuell = st.session_state.get(SESSION_KEY, _sprachcodes[0])
    if _aktuell not in _sprachcodes:
        _aktuell = _sprachcodes[0]
    with col_sprache.popover(
        sprachauswahl_label(_aktuell), icon=":material/language:",
        use_container_width=True,
    ):
        for code in _sprachcodes:
            col_flagge, col_knopf = st.columns([1, 3], vertical_alignment="center")
            flaggen_pfad = FLAGS_DIR / f"{SPRACHEN[code]['flagge']}.png"
            if flaggen_pfad.exists():
                col_flagge.image(str(flaggen_pfad), width=28)
            if col_knopf.button(
                SPRACHEN[code]["label"],
                key=f"sprachauswahl_{code}",
                type="primary" if code == _aktuell else "secondary",
                width="stretch",
            ) and code != _aktuell:
                st.session_state[SESSION_KEY] = code
                st.rerun()

st.markdown('<div class="app-header-rule"></div>', unsafe_allow_html=True)

# --- Navigation ----------------------------------------------------------------
# Stabile interne Codes als Radio-Werte (nicht die uebersetzten Labels):
# so bleibt die Auswahl beim Sprachwechsel gueltig und Streamlit muss den
# gespeicherten Widget-Zustand nicht verwerfen. Explizite Zuordnung zu den
# Sprachdatei-Schluesseln (keine Namenskonvention noetig/riskant).
_NAV_SCHLUESSEL = {
    "portfolio": "oberflaeche.nav_portfolio",
    "neu": "oberflaeche.nav_neues_projekt",
    "auktion": "oberflaeche.nav_ausschreibung",
    "annahmen": "oberflaeche.nav_globale_annahmen",
}
nav = st.sidebar.radio(
    txt("oberflaeche.nav_titel"),
    list(_NAV_SCHLUESSEL),
    format_func=lambda code: txt(_NAV_SCHLUESSEL[code]),
    key="nav",
)
render_import_export()

if nav == "portfolio":
    render_overview()
elif nav == "neu":
    render_new_project()
elif nav == "auktion":
    render_auktion()
else:
    render_assumptions()
