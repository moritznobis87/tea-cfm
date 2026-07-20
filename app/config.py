"""
Zentrale Konfiguration der Anwendung: Pfade und app-weite Konstanten.

Alle anderen App-Module beziehen Pfade ausschliesslich von hier - dadurch
gibt es genau eine Stelle, an der z.B. ein Wechsel des Datenverzeichnisses
(etwa fuer Tests oder ein Deployment mit persistentem Volume) erfolgt.
"""

from __future__ import annotations

from pathlib import Path

#: Wurzelverzeichnis des Repositories (Ordner, der streamlit_app.py enthaelt).
ROOT_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT_DIR / "data"
PROJECTS_DIR = DATA_DIR / "projects"
GLOBAL_ASSUMPTIONS_PATH = DATA_DIR / "global_assumptions.yaml"

ASSETS_DIR = ROOT_DIR / "assets"
#: Nobis-Analytics-Markenwerte (Standardmarke). Fuer die tatsaechlich
#: AKTIVE Marke (inkl. verdecktem Schalter auf die vorherige
#: Trianel-Gestaltung) siehe app.branding.aktive_marke() - dort werden
#: diese Konstanten NICHT gelesen, sie dienen nur als Referenz/
#: Ausgangswert der Registry in app/branding.py.
LOGO_PATH = ASSETS_DIR / "nobis_logo.png"
#: Beschnittene, quadratische Logovariante fuer den Browser-Tab.
FAVICON_PATH = ASSETS_DIR / "favicon.png"
#: Ordner mit den Flaggen-Icons fuer den Sprachumschalter (siehe
#: texte.SPRACHEN fuer die Zuordnung Sprachcode -> Dateiname).
FLAGS_DIR = ASSETS_DIR / "flags"

APP_TITLE = "Nobis Analytics"

def monate() -> list[str]:
    """Sprachabhaengige Monatsnamen (Index 0 = Januar) - als Funktion statt
    Modulkonstante, damit sie zur Laufzeit die aktuell gewaehlte Sprache
    (Dropdown) widerspiegeln, nicht die Importzeit-Sprache."""
    from texte import txt

    return [txt(f"oberflaeche.monat_{i:02d}") for i in range(1, 13)]


def monate_kurz() -> list[str]:
    """Sprachabhaengige kurze Monatsnamen (Index 0 = Jan)."""
    from texte import txt

    return [txt(f"oberflaeche.monat_kurz_{i:02d}") for i in range(1, 13)]

#: Session-State-Schluessel (zentral, um Tippfehler-Bugs auszuschliessen).
STATE_SELECTED_PROJECT = "selected_project"
STATE_DELETE_CANDIDATE = "delete_candidate"
