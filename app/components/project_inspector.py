"""
Der Project Inspector - die rechte Spalte der Projektseite.

Links wird das Projekt analysiert, rechts wird es gesteuert. Diese Datei
liefert die Bausteine der Steuerseite; die Felder selbst bleiben in
project_form.py, wo auch der Entwurf entsteht.

Drei Bausteine
--------------
1. `quick_adjust` - die vier Groessen, an denen man beim Durchspielen
   tatsaechlich dreht, als 2x2-Gitter ganz oben.
2. `summary_card` - je Themenbereich eine Karte mit Titel, Kurzfassung
   und Aenderungsstand. Sie ist LESBAR, ohne dass man sie bedient; der
   Oeffnen-Knopf sitzt als kleines Zeichen rechts oben.
3. Das OVERLAY - der Zwischenspeicher fuer Bereiche, die in einen Dialog
   ausgelagert sind.

Warum es das Overlay gibt
-------------------------
Der Entwurf ist in dieser Anwendung nicht ein eigenes Objekt, sondern der
WIDGET-ZUSTAND selbst: `project_form._felder()` liest bei jedem Durchlauf
alle Widgets und baut daraus ein frisches PVProject. Das ist der Grund,
warum Widget-Zustand und Entwurf nie auseinanderlaufen koennen - es gibt
nur eine Wahrheit.

Ein Dialog bricht das: Streamlit verwirft den Zustand eines Widgets, das
in einem Durchlauf nicht entsteht. Ein Feld, das nur im geoeffneten
Dialog existiert, waere beim naechsten Durchlauf ohne Dialog verschwunden
- und mit ihm sein Wert.

Das Overlay ist deshalb ein gewoehnliches dict unter einem Schluessel
OHNE Widget: Streamlit fasst es nie an. Fuer ausgelagerte Bereiche liest
`_felder()` daraus statt aus Widgets, der Dialog schreibt beim Uebernehmen
hinein, und `verwirf_entwurf()` loescht es mit. Dasselbe Muster benutzt
der Laenderschalter bereits (`project_form._land_wunsch_einloesen`).

Damit bleiben drei Zustaende sauber getrennt:

    Dialog-Widgets (dlg_*)  ->  Overlay + Widget-Zustand  ->  YAML
         verwerfen mit             der ENTWURF                gespeichert
         "Abbrechen"           "Uebernehmen" schreibt      "Speichern"
                                   hierhin                 schreibt hierhin
"""

from __future__ import annotations

import html
from typing import Any

import streamlit as st

from texte import txt

# --- Overlay ----------------------------------------------------------------
#
# Ein dict je Projektmaske. Der Schluessel traegt bewusst denselben
# Praefix wie die Widgets (`form_key`), damit `verwirf_entwurf` ihn mit
# derselben Regel erwischt wie alles andere.


def overlay_schluessel(form_key: str) -> str:
    return f"{form_key}__overlay"


def overlay(form_key: str) -> dict[str, Any]:
    """Der Zwischenspeicher dieser Maske - immer dasselbe dict."""
    return st.session_state.setdefault(overlay_schluessel(form_key), {})


def overlay_wert(form_key: str, feld: str, vorgabe):
    """Wert aus dem Overlay, sonst die Vorgabe (der gespeicherte Stand).

    Ein Feld, das nie im Dialog angefasst wurde, steht nicht im Overlay -
    dann gilt der gespeicherte Wert. Das ist dieselbe Regel wie bei den
    Widgets, nur ohne Widget.
    """
    return overlay(form_key).get(feld, vorgabe)


def overlay_setzen(form_key: str, werte: dict[str, Any]) -> None:
    """Uebernimmt Dialogwerte in den Entwurf."""
    overlay(form_key).update(werte)


def overlay_leeren(form_key: str) -> None:
    st.session_state.pop(overlay_schluessel(form_key), None)


# --- Darstellung ------------------------------------------------------------


def abschnittstitel(text: str) -> None:
    """Kleine Gliederungsmarke im Inspector (QUICK ADJUST, DETAILS)."""
    st.markdown(
        f'<div class="inspector-gruppe">{html.escape(text)}</div>',
        unsafe_allow_html=True,
    )


def summary_card(
    titel: str,
    zusammenfassung: str,
    *,
    geaendert: int = 0,
    key: str,
):
    """Eine Themenkarte des Inspectors.

    Gibt den Container zurueck, in den der Aufrufer seinen Oeffnen-Knopf
    setzt (Popover oder Dialog-Knopf).

    Warum die Karte HTML ist und nur der Knopf ein Widget: Ein Streamlit-
    Knopf traegt genau eine Beschriftung. Titel, Kurzfassung und
    Aenderungsstand als eine Zeile hineinzuzwingen ergaebe wieder eine
    Knopfleiste - der Inspector soll aber LESBAR sein, ohne dass man ihn
    bedient. Die Karte ist deshalb Text, der Knopf sitzt als kleines
    Zeichen rechts oben darin (siehe .inspector-karte in app/theme.py).
    """
    kasten = st.container(key=f"card_{key}")
    with kasten:
        marke = (
            f'<span class="inspector-marke" title="'
            f'{html.escape(txt("oberflaeche.inspector_karte_geaendert_titel"))}">'
            f"{geaendert}</span>"
            if geaendert
            else ""
        )
        st.markdown(
            f'<div class="inspector-karte-text">'
            f'<div class="inspector-karte-kopf">'
            f'<span class="inspector-karte-titel">{html.escape(titel)}</span>'
            f"{marke}</div>"
            f'<div class="inspector-karte-zeile">{html.escape(zusammenfassung)}</div>'
            f"</div>",
            unsafe_allow_html=True,
        )
    return kasten


def kurzfassung(teile: list[str]) -> str:
    """Verbindet die Angaben einer Karte - leere fallen weg.

    Mittelpunkt statt Komma: Die Teile sind gleichrangige Angaben, keine
    Aufzaehlung eines Satzes, und der Punkt trennt in einer schmalen
    Spalte sichtbarer.
    """
    return " · ".join(t for t in teile if t)
