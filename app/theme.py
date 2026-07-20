"""
Visuelles Fundament der App: Design-Tokens, CSS und ein zentrales
Plotly-Template.

Designsprache: Nobis-Türkis als einziger Markenakzent (Interaktion,
Auswahl, Kopfzeilen-Band) auf ruhigem Navy-Ink; durchgaengig Inter
(fixiert ueber .streamlit/config.toml), KPI-Werte mit tabellarischen
Ziffern. Türkis und Navy sind direkt aus dem Nobis-Analytics-Logo
abgeleitet (siehe assets/nobis_logo.png).

Prinzip: Jede Farbe, jeder Abstand und jedes Diagramm bezieht seine
Gestaltung aus DIESEM Modul. Views und Komponenten enthalten keine
Hex-Codes.
"""

from __future__ import annotations

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st

# ---------------------------------------------------------------------------
# Design-Tokens
# ---------------------------------------------------------------------------


class Colors:
    """Farbpalette: Nobis-Türkis als Markenakzent auf ruhigem Navy-Ink -
    beide direkt aus dem Logo-Farbverlauf abgeleitet (assets/nobis_logo.png:
    Türkis #1F9CAC im Verlauf, Navy #14253B im Icon-Hintergrund). Die
    übrigen Töne sind rechnerisch (gleicher Farbton, angepasste
    Helligkeit/Sättigung) aus Navy hergeleitet, damit die ganze Palette
    aus einer Familie stammt statt einzelner geschätzter Werte."""

    BRAND = "#167B88"          # Nobis-Türkis - Akzent, Auswahl, Primary-Buttons
    INK = "#14304F"            # Tiefes Navy - Ueberschriften, Linien
    INK_SOFT = "#2B4F77"       # hellere Ink-Stufe (Sekundaerserien)
    MUTED = "#5C636A"          # Sekundaertext
    LINE = "#E1E4E8"           # Rahmen, Trennlinien
    WASH = "#F6F7F9"           # Kartenhintergrund
    PAPER = "#FFFFFF"

    POSITIVE = "#2E7D32"       # Zufluesse, "im gruenen Bereich"
    NEGATIVE = "#C0392B"       # Abfluesse, Unterdeckung
    NEUTRAL = "#8A97A6"        # Sekundaere Serien (z.B. Tilgung, Varianten)

    #: Gestufte Warmtoene fuer gestapelte Kostenpositionen.
    OPEX_SCALE = [
        "#C0392B", "#E67E22", "#D68910", "#B9770E", "#A04000",
        "#873600", "#6E2C00", "#943126",
    ]

    #: Serienfarben fuer Szenario-/Mehrlinienvergleiche.
    SERIES = ["#14304F", "#167B88", "#8A97A6", "#2E7D32", "#2B4F77"]

    #: Divergierende Skala fuer die IRR-Heatmap (rot = unter Ziel,
    #: gruen = ueber Ziel - semantisch, kein Dekor).
    HEAT_SCALE = [
        [0.0, "#C0392B"], [0.5, "#F2F1ED"], [1.0, "#2E7D32"],
    ]


def wende_farben_an(farben: dict) -> None:
    """Ueberschreibt die Colors-Klassenattribute zur Laufzeit (z.B. fuer
    den verdeckten Marken-Schalter in app.branding). `farben` erwartet
    die Schluessel BRAND/INK/INK_SOFT/MUTED/NEUTRAL/LINE/WASH; SERIES
    wird daraus neu zusammengesetzt (POSITIVE/NEGATIVE/OPEX_SCALE/
    HEAT_SCALE bleiben unveraendert - semantische Farben, keine
    Markenfarben). Muss VOR apply_theme() aufgerufen werden, da CSS und
    Plotly-Template erst dort (neu) gebaut werden."""
    Colors.BRAND = farben["BRAND"]
    Colors.INK = farben["INK"]
    Colors.INK_SOFT = farben["INK_SOFT"]
    Colors.MUTED = farben["MUTED"]
    Colors.NEUTRAL = farben["NEUTRAL"]
    Colors.LINE = farben["LINE"]
    Colors.WASH = farben["WASH"]
    Colors.SERIES = [Colors.INK, Colors.BRAND, Colors.NEUTRAL,
                     Colors.POSITIVE, Colors.INK_SOFT]


# ---------------------------------------------------------------------------
# Plotly-Template (einmal registrieren, ueberall nutzen)
# ---------------------------------------------------------------------------

_TEMPLATE_NAME = "tea"


def _register_plotly_template() -> None:
    """Baut das Plotly-Template neu auf - bewusst OHNE 'bereits
    registriert'-Fruehausstieg: Colors.* kann sich zur Laufzeit aendern
    (verdeckter Marken-Schalter, siehe app.branding), daher muss jeder
    apply_theme()-Aufruf die aktuellen Werte einbacken."""
    pio.templates[_TEMPLATE_NAME] = go.layout.Template(
        layout=go.Layout(
            font=dict(family="Inter, sans-serif", color=Colors.INK, size=13),
            title_font=dict(family="Inter, sans-serif", size=15),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            # Deutsche Zahlendarstellung in Achsen und Hovern:
            # 1. Zeichen = Dezimaltrenner, 2. Zeichen = Tausendertrenner.
            separators=",.",
            colorway=Colors.SERIES,
            margin=dict(t=28, b=28, l=8, r=8),
            bargap=0.25,
            hoverlabel=dict(
                bgcolor=Colors.PAPER,
                bordercolor=Colors.LINE,
                font=dict(family="Inter, sans-serif", color=Colors.INK, size=13),
            ),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
            xaxis=dict(
                gridcolor=Colors.LINE, zerolinecolor=Colors.LINE,
                linecolor=Colors.LINE, ticks="outside", tickcolor=Colors.LINE,
            ),
            yaxis=dict(
                gridcolor=Colors.LINE, zerolinecolor=Colors.LINE,
                linecolor=Colors.LINE,
            ),
        )
    )
    pio.templates.default = f"plotly_white+{_TEMPLATE_NAME}"


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

def _baue_css() -> str:
    """Baut das CSS frisch mit den aktuellen Colors-Werten (koennen
    sich durch den verdeckten Marken-Schalter zur Laufzeit aendern)."""
    return f"""
    <style>
        .block-container {{ padding-top: 1.4rem; max-width: 1280px; }}

        /* --- Kopfzeile: garantierte Mindesthoehe -------------------------------
           Ohne das hier faellt die Zeilenhoehe bei kurzem, unumbrochenem
           Titeltext knapp auf die Texthoehe - das (etwas hoehere) Logo und
           der Sprach-Popover-Button werden dann oben abgeschnitten. Der
           Container traegt den key "app_header" (siehe streamlit_app.py). */
        .st-key-app_header {{
            min-height: 80px;
            overflow: visible;
        }}
        .st-key-app_header [data-testid="stHorizontalBlock"] {{
            min-height: 80px;
            overflow: visible;
            align-items: center;
        }}
        .st-key-app_header [data-testid="stColumn"] {{
            overflow: visible;
        }}

        /* --- Typografie ------------------------------------------------------ */
        h1, h2, h3 {{ color: {Colors.INK}; letter-spacing: -0.01em; }}

        /* --- Kopfzeile / Hero ------------------------------------------------ */
        .app-hero-title {{
            font-size: 2.05rem;
            font-weight: 700;
            color: {Colors.INK};
            letter-spacing: -0.02em;
            line-height: 1.1;
            margin: 0;
        }}
        .app-hero-sub {{
            color: {Colors.MUTED};
            font-size: 0.95rem;
            margin-top: 2px;
        }}
        .app-header-rule {{
            height: 3px;
            background: linear-gradient(90deg, {Colors.BRAND} 0, {Colors.BRAND} 96px,
                                        {Colors.LINE} 96px, {Colors.LINE} 100%);
            border: none; border-radius: 2px;
            margin: 0.5rem 0 1.2rem 0;
        }}

        /* --- KPI-Kacheln ------------------------------------------------------ */
        div[data-testid="stMetric"] {{
            background: {Colors.WASH};
            border: 1px solid {Colors.LINE};
            border-radius: 12px;
            padding: 14px 18px 10px 18px;
        }}
        div[data-testid="stMetric"] label {{ color: {Colors.MUTED}; }}

        .kpi-row {{
            display: grid;
            grid-auto-flow: column;
            grid-auto-columns: 1fr;
            gap: 12px;
            margin: 0.35rem 0 0.9rem 0;
        }}
        .kpi-card {{
            position: relative;
            background: linear-gradient(180deg, {Colors.PAPER} 0%, {Colors.WASH} 100%);
            border: 1px solid {Colors.LINE};
            border-radius: 12px;
            padding: 14px 16px 12px 16px;
            min-width: 0;               /* erlaubt Schrumpfen in der Grid-Zelle */
            overflow: hidden;
            transition: transform 140ms ease, box-shadow 140ms ease;
        }}
        .kpi-card::before {{
            content: "";
            position: absolute;
            top: 0; left: 0; bottom: 0;
            width: 3px;
            background: {Colors.BRAND};
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 18px rgba(20, 48, 79, 0.10);
        }}
        .kpi-card .kpi-label {{
            color: {Colors.MUTED};
            font-size: 0.78rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            margin-bottom: 3px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .kpi-card .kpi-value {{
            font-variant-numeric: tabular-nums;
            color: {Colors.INK};
            font-weight: 700;
            font-size: 2rem;            /* Maximum; JS passt gruppenweise an */
            line-height: 1.25;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;    /* Sicherheitsnetz, falls die JS-Anpassung
                                           einen Reflow (Sidebar/Expander/Tab) einmal
                                           nicht rechtzeitig einholt */
        }}
        /* 1px-iframes (Schriftgroessen-Skript, siehe app/components/kpi.py)
           samt Container aus dem Layoutfluss nehmen, damit kein Leerraum
           entsteht. Skripte in display:none-iframes laufen weiterhin. */
        div[data-testid="stElementContainer"]:has(iframe[height="0"]),
        div[data-testid="stElementContainer"]:has(iframe[height="1"]) {{
            display: none;
        }}

        /* --- Projektkarten ---------------------------------------------------- */
        .project-card {{
            position: relative;
            border: 1px solid {Colors.LINE};
            border-radius: 12px;
            padding: 14px 16px 10px 16px;
            margin-bottom: 8px;
            background: {Colors.PAPER};
            overflow: hidden;
            transition: transform 140ms ease, box-shadow 140ms ease,
                        border-color 140ms ease;
        }}
        .project-card.inaktiv {{
            background: #f1f3f2;
            opacity: 0.62;
            filter: grayscale(0.55);
            border-style: dashed;
        }}
        .badge-inaktiv {{
            background: #e4e7e6;
            color: #6b7a76;
        }}
        .project-card:hover {{
            transform: translateY(-2px);
            border-color: {Colors.NEUTRAL};
            box-shadow: 0 6px 18px rgba(20, 48, 79, 0.10);
        }}
        .project-card.selected {{
            border-color: {Colors.BRAND};
            box-shadow: 0 0 0 1px {Colors.BRAND};
        }}
        .project-card .card-title {{
            font-weight: 600; color: {Colors.INK}; font-size: 1.02rem;
        }}
        .project-card .card-sub {{ color: {Colors.MUTED}; font-size: 0.84em; }}
        .project-card .card-kpi {{
            font-variant-numeric: tabular-nums;
            font-size: 1.55em; font-weight: 700; color: {Colors.INK};
        }}
        .project-card .card-kpi-label {{ color: {Colors.MUTED}; font-size: 0.84em; }}
        .project-card .card-spark {{ margin-top: 4px; }}

        /* --- Badges ------------------------------------------------------------ */
        .badge {{
            display: inline-block;
            padding: 1px 9px;
            border-radius: 999px;
            font-size: 0.72rem;
            font-weight: 600;
            letter-spacing: 0.02em;
            vertical-align: middle;
        }}
        .badge-agri {{ background: #E7F2EA; color: {Colors.POSITIVE}; }}
        .badge-konv {{ background: #EEF1F0; color: {Colors.MUTED}; }}

        /* --- Tabs (Streamlit-Standard, Akzent = primaryColor) ------------------- */
        .stTabs [data-baseweb="tab"] {{ font-weight: 500; }}

        /* --- Sidebar ------------------------------------------------------------ */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {Colors.WASH} 0%, {Colors.PAPER} 60%);
            border-right: 1px solid {Colors.LINE};
        }}
        section[data-testid="stSidebar"] .stRadio label {{ font-weight: 500; }}

        /* --- Markenfarbe erzwingen (Fallback, falls kein Theme greift) -------- */
        :root {{ --primary-color: {Colors.BRAND}; }}
        button[kind="primary"], button[data-testid="stBaseButton-primary"] {{
            background-color: {Colors.BRAND} !important;
            border-color: {Colors.BRAND} !important;
            color: #FFFFFF !important;
        }}
        button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {{
            background-color: #12646E !important;
            border-color: #12646E !important;
        }}
        .stButton > button:hover, .stButton > button:focus:not(:active),
        .stDownloadButton > button:hover,
        .stDownloadButton > button:focus:not(:active) {{
            border-color: {Colors.BRAND} !important;
            color: {Colors.BRAND} !important;
        }}
        .stTabs [data-baseweb="tab-highlight"] {{
            background-color: {Colors.BRAND} !important;
        }}
        div[data-baseweb="slider"] div[role="slider"] {{
            background-color: {Colors.BRAND} !important;
            border-color: {Colors.BRAND} !important;
        }}
        div[data-testid="stSliderThumbValue"] {{ color: {Colors.BRAND} !important; }}
        a, a:visited {{ color: {Colors.BRAND}; }}

        /* --- Buttons -------------------------------------------------------------- */
        .stButton > button, .stDownloadButton > button {{
            border-radius: 10px;
        }}

        /* --- Abschnittstitel ------------------------------------------------------- */
        .section-title {{
            font-weight: 600;
            color: {Colors.INK};
            font-size: 1.05rem;
            margin: 0.4rem 0 0.2rem 0;
        }}

        @media (prefers-reduced-motion: reduce) {{
            .kpi-card, .project-card {{ transition: none; }}
            .kpi-card:hover, .project-card:hover {{ transform: none; }}
        }}
    </style>
    """


def apply_theme() -> None:
    """Registriert das Plotly-Template und injiziert das App-CSS.

    Muss einmal pro Rerun frueh aufgerufen werden (macht der Entry-Point).
    """
    _register_plotly_template()
    st.markdown(_baue_css(), unsafe_allow_html=True)


def section_title(text: str) -> None:
    """Abschnittsueberschrift (schlicht, ohne Marker)."""
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)


def badge(text: str, kind: str = "konv") -> str:
    """HTML-Schnipsel fuer ein Badge ('agri', 'konv' oder 'warn')."""
    return f'<span class="badge badge-{kind}">{text}</span>'
