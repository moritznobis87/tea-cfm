"""
Kennzahlenleiste: eine hervorgehobene Leitkennzahl, daneben begleitende
Kacheln.

Warum die Hierarchie: Fuenf gleich grosse Kacheln beantworten die Frage
"worauf schaue ich zuerst?" nicht. Auf der Projektseite haengt die
Investitionsentscheidung am Equity IRR; NPV, Equity Value und Enterprise
Value sind drei Ausprägungen derselben Wertbetrachtung, CAPEX ist eine
Groessenangabe. Die Leitkachel setzt das um, ohne dass etwas verschwindet.

Warum keine Schriftanpassung per JavaScript mehr: Die frueheren
abgeschnittenen Werte waren kein Layout-, sondern ein Formatproblem -
"9.338.144 €" ist breiter als jede vertretbare Kachel. Mit der
gerundeten Darstellung ("9,34 Mio €", siehe app/formatting.py) passt
jeder Wert bei fester Schriftgroesse. Das frueher noetige Mess-Skript
mit Resize- und MutationObserver entfaellt damit ersatzlos; der genaue
Betrag steht im title-Attribut (Tooltip).
"""

from __future__ import annotations

import html
from dataclasses import dataclass

import streamlit as st


@dataclass
class Kennzahl:
    """Eine Kachel der Kennzahlenleiste.

    label:   Beschriftung (klein, gesperrt, Grossbuchstaben)
    wert:    bereits formatierter Anzeigewert
    zusatz:  kurze Einordnung rechts (Begleitkachel) bzw. Methodenhinweis
             in der Fusszeile (Leitkachel)
    genau:   vollstaendiger Wert fuer den Tooltip, falls die Anzeige
             gerundet ist
    """

    label: str
    wert: str
    zusatz: str | None = None
    genau: str | None = None


def _tooltip(kennzahl: Kennzahl) -> str:
    if not kennzahl.genau:
        return ""
    return f' title="{html.escape(kennzahl.genau)}"'


def _leitkachel(
    kennzahl: Kennzahl,
    abweichung: str | None,
    ziel: tuple[float, float, str] | None,
) -> str:
    """ziel: (Anteil des Werts, Anteil der Zielmarke, Beschriftung) - beide
    Anteile auf 0..1 bezogen auf die Balkenbreite."""
    teile = [
        f'<div class="kpi-label">{html.escape(kennzahl.label)}</div>',
        f'<div class="kpi-hero-value"{_tooltip(kennzahl)}>'
        f"{html.escape(kennzahl.wert)}</div>",
    ]
    if abweichung:
        teile.append(
            f'<div class="kpi-delta">{html.escape(abweichung)}</div>'
        )
    if ziel is not None:
        anteil, marke, beschriftung = ziel
        teile.append(
            '<div class="kpi-ziel">'
            f'<div class="kpi-ziel-bahn">'
            f'<div class="kpi-ziel-fuell" style="width:{anteil * 100:.1f}%"></div>'
            f'<div class="kpi-ziel-marke" style="left:{marke * 100:.1f}%"></div>'
            "</div>"
            f'<div class="kpi-ziel-label">{html.escape(beschriftung)}</div>'
            "</div>"
        )
    if kennzahl.zusatz:
        teile.append(f'<div class="kpi-fuss">{html.escape(kennzahl.zusatz)}</div>')
    return f'<div class="kpi-hero">{"".join(teile)}</div>'


def _begleitkachel(kennzahl: Kennzahl) -> str:
    zusatz = (
        f'<span class="kpi-sub">{html.escape(kennzahl.zusatz)}</span>'
        if kennzahl.zusatz
        else ""
    )
    return (
        '<div class="kpi-card">'
        f'<div class="kpi-label">{html.escape(kennzahl.label)}</div>'
        f'<div class="kpi-zeile"><span class="kpi-value"{_tooltip(kennzahl)}>'
        f"{html.escape(kennzahl.wert)}</span>{zusatz}</div>"
        "</div>"
    )


def render_kennzahlen(
    leit: Kennzahl,
    begleiter: list[Kennzahl],
    group: str,
    abweichung: str | None = None,
    ziel: tuple[float, float, str] | None = None,
) -> None:
    """Rendert die Kennzahlenleiste: Leitkachel links, Begleiter im Raster.

    group: Kennung fuer Tests und CSS-Zugriff ("projekt", "portfolio").
    abweichung: Kurztext ueber die Abweichung zum gespeicherten Stand -
                erscheint nur, wenn ungespeicherte Aenderungen anliegen.
    """
    kacheln = "".join(_begleitkachel(k) for k in begleiter)
    st.markdown(
        f'<div class="kpi-leiste" data-kpi-group="{html.escape(group)}">'
        f"{_leitkachel(leit, abweichung, ziel)}"
        f'<div class="kpi-begleiter">{kacheln}</div>'
        "</div>",
        unsafe_allow_html=True,
    )


def render_kpi_row(items: list[tuple[str, str]], group: str) -> None:
    """Schlichte Kachelzeile ohne Hierarchie - fuer Stellen, an denen es
    keine Leitkennzahl gibt (z.B. Zwischenergebnisse im Auktionsmodul)."""
    kacheln = "".join(
        f'<div class="kpi-card">'
        f'<div class="kpi-label">{html.escape(label)}</div>'
        f'<div class="kpi-zeile"><span class="kpi-value">'
        f"{html.escape(value)}</span></div>"
        f"</div>"
        for label, value in items
    )
    st.markdown(
        f'<div class="kpi-row" data-kpi-group="{html.escape(group)}">'
        f"{kacheln}</div>",
        unsafe_allow_html=True,
    )
