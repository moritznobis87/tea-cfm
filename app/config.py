"""
Zentrale Konfiguration der Anwendung: Pfade und app-weite Konstanten.

Alle anderen App-Module beziehen Pfade ausschliesslich von hier - dadurch
gibt es genau eine Stelle, an der z.B. ein Wechsel des Datenverzeichnisses
(etwa fuer Tests oder ein Deployment mit persistentem Volume) erfolgt.
"""

from __future__ import annotations

import os
from pathlib import Path

#: Wurzelverzeichnis des Repositories (Ordner, der streamlit_app.py enthaelt).
ROOT_DIR = Path(__file__).resolve().parent.parent

#: Name der Umgebungsvariablen, die das Datenverzeichnis umlenkt.
DATA_DIR_ENV = "VALYZE_DATA_DIR"

#: Datenverzeichnis - umlenkbar ueber VALYZE_DATA_DIR.
#:
#: Die Umlenkung ist kein Komfort, sondern ein Schutz. Alles unter DATA_DIR
#: wird zur Laufzeit GESCHRIEBEN: die globalen Annahmen, die Projektdateien,
#: die Ausschreibungsdaten. Die Testsuite fuehrt genau diese Schreibwege vor
#: (Aurora-Import, Speichern-Knopf, Varianten anlegen) und muss dafuer auf
#: eine Kopie zeigen koennen. Sicherungsfixtures, die die echte Datei
#: hinterher zurueckschreiben, reichen dafuer nicht: Bricht ein Lauf hart ab,
#: laeuft ihr finally nie, und der Testzustand bleibt im Repository stehen.
#: Genau so sind schon einmal synthetische Preise in die ausgelieferten
#: Marktdaten geraten.
#:
#: Zweiter Nutzen: ein Deployment mit persistentem Volume ausserhalb des
#: Repositories.
DATA_DIR = Path(os.environ.get(DATA_DIR_ENV) or ROOT_DIR / "data")
PROJECTS_DIR = DATA_DIR / "projects"
GLOBAL_ASSUMPTIONS_PATH = DATA_DIR / "global_assumptions.yaml"

ASSETS_DIR = ROOT_DIR / "assets"
#: Valyze-Markenwerte (Standardmarke). Fuer die tatsaechlich
#: AKTIVE Marke (inkl. verdecktem Schalter auf die vorherige
#: Trianel-Gestaltung) siehe app.branding.aktive_marke() - dort werden
#: diese Konstanten NICHT gelesen, sie dienen nur als Referenz/
#: Ausgangswert der Registry in app/branding.py.
LOGO_PATH = ASSETS_DIR / "valyze_logo.png"
#: Beschnittene, quadratische Logovariante fuer den Browser-Tab.
FAVICON_PATH = ASSETS_DIR / "valyze_favicon.png"
#: Ordner mit den Flaggen-Icons fuer den Sprachumschalter (siehe
#: texte.SPRACHEN fuer die Zuordnung Sprachcode -> Dateiname).
FLAGS_DIR = ASSETS_DIR / "flags"

#: Rechenweg-Dokumentation als PDF - wird ueber den Hilfe-Knopf der
#: Kopfzeile zum Download angeboten. Erzeugt aus
#: docs/rechenmodell/rechenmodell.md (siehe make dokumentation); fehlt
#: die Datei, blendet die Kopfzeile den Knopf aus.
DOKUMENTATION_PDF_PATH = ROOT_DIR / "docs" / "rechenmodell" / "Rechenmodell.pdf"

APP_TITLE = "Valyze"

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
