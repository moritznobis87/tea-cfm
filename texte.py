"""
Zentrale Textverwaltung (Sprachdateien).

Alle sichtbaren Texte der Anwendung liegen in YAML-Dateien unter
locales/<sprache>/ und sind dort nach Textgattung aufgeteilt:

    oberflaeche.yaml  Kurze UI-Texte: Navigation, Buttons, Labels,
                      Abschnittstitel, Hilfe- und Hinweistexte der Views
    diagramme.yaml    Diagrammtitel, Achsen, Legenden, Hover-Texte
    bericht.yaml      Freitext des PDF-Berichts (Kapitel, Absaetze,
                      Abbildungs-/Tabellenunterschriften)
    excel.yaml        Beschriftungen des Excel-Ergebnisexports

Zugriff ueber txt("<datei>.<schluessel>", platzhalter=wert). Platzhalter
stehen in den Texten als {name} (inkl. Formatangaben wie {wert:,.2f});
Texte ohne uebergebene Platzhalter werden unveraendert zurueckgegeben,
so dass geschweifte Klammern (z. B. Plotly-Hovertemplates) unkritisch
sind.

Sprachwahl: In der laufenden App waehlt der Nutzer die Sprache ueber
das Dropdown oben rechts (Flagge + Name); die Auswahl landet in
st.session_state[SESSION_KEY] und wirkt sofort nach einem Rerun.
Ausserhalb der App (Tests, Skripte, Engine-Aufrufe ohne Streamlit)
greift die Umgebungsvariable NOBIS_SPRACHE (Standard "de"). Aktuell
gepflegt: Deutsch (de), Englisch (en), Franzoesisch (fr), Spanisch
(es) - siehe SPRACHEN. Eine weitere Uebersetzung entsteht durch
Kopieren des Ordners locales/de nach z. B. locales/it, Uebersetzen der
Werte und Ergaenzen in SPRACHEN; fehlende Schluessel fallen automatisch
auf Deutsch zurueck, ganz fehlende Schluessel liefern den
Schluesselnamen (fail-soft, kein Absturz durch Luecken).
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

LOCALES_DIR = Path(__file__).resolve().parent / "locales"
STANDARD_SPRACHE = "de"

#: Unterstuetzte Sprachen: Code -> (Anzeigename, Flaggen-Dateiname).
#: Die Flaggen liegen als PNG unter assets/flags/<flagge>.png (siehe
#: app.config.FLAGS_DIR) - Emoji-Flaggen werden je nach Betriebssystem/
#: Browser/Schriftart oft nicht dargestellt (z. B. Windows verbreitet)
#: und st.selectbox kann ohnehin keine Bilder in seinen Optionen
#: anzeigen; der Sprachumschalter in streamlit_app.py baut deshalb
#: einen eigenen Dropdown ueber st.popover mit echten Bild-Icons.
SPRACHEN: dict[str, dict[str, str]] = {
    "de": {"label": "Deutsch", "flagge": "at"},
    "en": {"label": "English", "flagge": "gb"},
    "fr": {"label": "Français", "flagge": "fr"},
    "es": {"label": "Español", "flagge": "es"},
}

#: Session-State-Schluessel, unter dem die App-Seite (streamlit_app.py)
#: die vom Nutzer gewaehlte Sprache ablegt.
SESSION_KEY = "tea_sprache"


def aktive_sprache() -> str:
    """Ermittelt die aktive Sprache: zuerst die in der laufenden
    Streamlit-Session gewaehlte Sprache (Dropdown oben rechts), sonst
    die Umgebungsvariable NOBIS_SPRACHE, sonst Deutsch. Der
    Streamlit-Import ist bewusst lazy/optional, damit dieses Modul auch
    aus der Engine-Schicht (kein Streamlit) und aus Tests heraus ohne
    laufende App funktioniert."""
    try:
        import streamlit as st

        if SESSION_KEY in st.session_state:
            gewaehlt = st.session_state[SESSION_KEY]
            if gewaehlt in SPRACHEN:
                return gewaehlt
    except Exception:
        pass
    return os.environ.get("NOBIS_SPRACHE", STANDARD_SPRACHE).strip() or STANDARD_SPRACHE


def sprachauswahl_label(code: str) -> str:
    """Länderkürzel für Popover-Trigger/Bild-Alt-Text, z. B. 'EN'.
    Die Flagge selbst wird als Bild-Icon dargestellt (siehe
    streamlit_app.py) - Emoji-Flaggen werden je nach Betriebssystem/
    Browser nicht zuverlässig gerendert."""
    return code.upper()


@lru_cache(maxsize=4)
def lade_texte(sprache: str) -> dict[str, str]:
    """Laedt alle YAML-Dateien einer Sprache in einen flachen Namensraum
    '<dateistamm>.<schluessel>' -> Text."""
    texte: dict[str, str] = {}
    ordner = LOCALES_DIR / sprache
    if not ordner.is_dir():
        return texte
    for datei in sorted(ordner.glob("*.yaml")):
        inhalt = yaml.safe_load(datei.read_text(encoding="utf-8")) or {}
        for schluessel, wert in inhalt.items():
            texte[f"{datei.stem}.{schluessel}"] = str(wert)
    return texte


def txt(schluessel: str, /, **platzhalter) -> str:
    """Liefert den Text zum Schluessel in der aktiven Sprache; faellt je
    Schluessel auf Deutsch und zuletzt auf den Schluessel selbst
    zurueck. Platzhalter werden per str.format eingesetzt."""
    sprache = aktive_sprache()
    text = lade_texte(sprache).get(schluessel)
    if text is None and sprache != STANDARD_SPRACHE:
        text = lade_texte(STANDARD_SPRACHE).get(schluessel)
    if text is None:
        return schluessel
    if platzhalter:
        try:
            return text.format(**platzhalter)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def excel_texte() -> dict[str, str]:
    """Beschriftungen fuer den Excel-Ergebnisexport (Engine-Schicht):
    Schluessel ohne Dateiprefix, wie von engine.io_ergebnis_excel
    erwartet."""
    prefix = "excel."
    sprache = aktive_sprache()
    zusammen = dict(lade_texte(STANDARD_SPRACHE))
    if sprache != STANDARD_SPRACHE:
        zusammen.update(lade_texte(sprache))
    return {
        k[len(prefix):]: v for k, v in zusammen.items() if k.startswith(prefix)
    }
