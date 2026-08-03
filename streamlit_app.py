"""
Valyze PV-Projektbewertung - Einstiegspunkt.

Bewusst duenn gehalten: Seitenkonfiguration, Theme, Kopfzeile und
Navigation. Die eigentlichen Seiten leben in app/views/, wieder-
verwendbare Bausteine in app/components/, Datenzugriff und Caching in
app/services.py, die Fachlogik in engine/.
"""

from __future__ import annotations

import streamlit as st

from app.branding import aktive_marke, logo_bild

# Verdeckter Marken-Schalter: URL-Parameter ?marke=trianel zeigt die
# vorherige Trianel-Gestaltung, sonst (Standard) Valyze -
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
from app import router, services  # noqa: E402
from app.components.sidebar import render_sidebar  # noqa: E402
from app.config import FLAGS_DIR  # noqa: E402
from app.views.assumptions import render_assumptions  # noqa: E402
from engine import MarktSystem  # noqa: E402
from app.views.auktion import render_auktion  # noqa: E402
from app.views.new_project import render_new_project  # noqa: E402
from app.views.overview import render_overview  # noqa: E402
from app.views.project_page import render_project_page  # noqa: E402
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
    col_logo, col_title, col_sprache, col_hilfe = st.columns(
        [2.2, 6.4, 1.4, 0.6], vertical_alignment="center"
    )
    if _MARKE["logo"].exists():
        # logo_bild() entfernt den weissen Rand der Markendatei, damit die
        # Kopfzeile nicht vom Weissraum bestimmt wird (siehe app.branding).
        col_logo.image(logo_bild(_MARKE), width=_MARKE["logo_breite"])
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

    # Hilfe-Knopf ganz rechts: laedt die Rechenweg-Dokumentation als PDF
    # herunter. Bewusst ein Download-Knopf statt eines Links - die Datei
    # liegt im Repository und soll ohne Netzzugriff verfuegbar sein.
    # Fehlt sie (z.B. Deployment ohne gebautes PDF), entfaellt der Knopf
    # stillschweigend, statt einen toten Knopf zu zeigen.
    _doku_pdf = services.get_dokumentation_pdf()
    if _doku_pdf is not None:
        col_hilfe.download_button(
            "",
            data=_doku_pdf,
            file_name=txt("oberflaeche.hilfe_dokumentation_dateiname"),
            mime="application/pdf",
            icon=":material/help:",
            help=txt("oberflaeche.hilfe_dokumentation"),
            key="dokumentation_download",
            width="stretch",
        )

st.markdown('<div class="app-header-rule"></div>', unsafe_allow_html=True)

# --- Navigation ----------------------------------------------------------------
# Die geoeffnete Seite steht in der Adresse (?seite=...), nicht nur im
# Session-State - siehe app/router.py. Dadurch funktionieren Neuladen,
# Lesezeichen, verschickte Links und der Zurueck-Knopf des Browsers.
render_sidebar()

_seite = router.aktuelle_seite()
if _seite == "portfolio":
    render_overview()
elif _seite == "projekt":
    render_project_page()
elif _seite == "neu":
    render_new_project()
elif _seite == "ausschreibung":
    render_auktion()
else:
    render_assumptions()
