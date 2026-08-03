"""
Visuelles Fundament der App: Design-Tokens, CSS und ein zentrales
Plotly-Template.

Designsprache: Valyze-Türkis als einziger Markenakzent (Interaktion,
Auswahl, Kopfzeilen-Band) auf ruhigem Navy-Ink; durchgaengig Inter
(fixiert ueber .streamlit/config.toml), KPI-Werte mit tabellarischen
Ziffern. Türkis und Navy sind direkt aus dem Valyze-Logo
abgeleitet (siehe assets/valyze_logo.png).

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
    """Farbpalette: Valyze-Türkis als Markenakzent auf ruhigem Navy-Ink -
    beide direkt aus dem Logo-Farbverlauf abgeleitet (assets/valyze_logo.png:
    Türkis #1F9CAC im Verlauf, Navy #14253B im Icon-Hintergrund). Die
    übrigen Töne sind rechnerisch (gleicher Farbton, angepasste
    Helligkeit/Sättigung) aus Navy hergeleitet, damit die ganze Palette
    aus einer Familie stammt statt einzelner geschätzter Werte."""

    BRAND = "#167B88"          # Valyze-Türkis - Akzent, Auswahl, Primary-Buttons
    INK = "#14304F"            # Tiefes Navy - Ueberschriften, Linien
    INK_SOFT = "#2B4F77"       # hellere Ink-Stufe (Sekundaerserien)
    MUTED = "#5C636A"          # Sekundaertext
    LINE = "#E1E4E8"           # Rahmen, Trennlinien
    WASH = "#F6F7F9"           # Kartenhintergrund
    PAPER = "#FFFFFF"

    POSITIVE = "#2E7D32"       # Zufluesse, "im gruenen Bereich"
    NEGATIVE = "#C0392B"       # Abfluesse, Unterdeckung
    NEUTRAL = "#8A97A6"        # Sekundaere Serien (z.B. Tilgung, Varianten)

    #: Ruhiger Zwischenton der Markenfamilie - Vergleichswerte, die weder
    #: Leitgroesse noch Warnung sind (Randbereiche einer Verteilung,
    #: Nebenvarianten eines Szenarienvergleichs).
    SOFT = "#B9CFD2"

    #: Gestufte Blau-Tuerkis-Toene fuer gestapelte Kostenpositionen.
    #: Frueher Warmtoene (Rot/Orange) - die lasen sich neben Navy und
    #: Tuerkis wie eine Warnung, obwohl Betriebskosten nichts Kritisches
    #: sind. Die Stufen laufen von hell nach dunkel, damit auch viele
    #: Positionen im Stapel unterscheidbar bleiben. Der dunkelste Ton
    #: haelt bewusst Abstand zu INK/INK_SOFT - Gemeindeabgabe und
    #: Direktvermarktung schliessen im Stapel direkt an und muessen
    #: unterscheidbar bleiben.
    OPEX_SCALE = [
        "#CFE0E3", "#A6C7CD", "#7FAEB7", "#5A95A1", "#3B7C8B",
        "#2A6373", "#1E4C5C", "#89B4BC",
    ]

    #: Serienfarben fuer Mehrlinienvergleiche - ausschliesslich aus der
    #: Markenfamilie. Frueher lag hier ein Gruen mit drin; als Serienfarbe
    #: einer beliebigen Variante legte es eine Bewertung nahe, die der
    #: Vergleich nicht trifft.
    SERIES = ["#14304F", "#167B88", "#2B4F77", "#B9CFD2", "#8A97A6"]

    #: Kategoriale Palette fuer Aufteilungen mit vielen Segmenten
    #: (Investitionsstruktur, Szenarienvergleich). Abwechselnd dunkel und
    #: hell, damit benachbarte Segmente auch bei kleinen Flaechen
    #: auseinanderzuhalten sind.
    KATEGORIE = [
        "#14304F", "#167B88", "#2B4F77", "#7FAEB7", "#3B7C8B",
        "#A6C7CD", "#1E4C5C", "#5A95A1", "#CFE0E3", "#8A97A6",
    ]

    #: Aufgehellte Markenfarbe fuer Auswahlflaechen (aktiver
    #: Navigationseintrag, aktive Sicht, Kopf der Parameterspalte).
    #: Wird in wende_farben_an() aus BRAND neu berechnet, damit der
    #: Markenschalter auch die Auswahlflaeche mitnimmt.
    SELECT = "#E4F0F1"

    #: Divergierende Skala fuer die IRR-Heatmap (rot = unter Ziel,
    #: gruen = ueber Ziel - semantisch, kein Dekor).
    HEAT_SCALE = [
        [0.0, "#C0392B"], [0.5, "#F2F1ED"], [1.0, "#2E7D32"],
    ]


def mit_alpha(hexfarbe: str, alpha: float) -> str:
    """Farbe als rgba-Zeichenkette - fuer halbtransparente Flaechen.

    Damit stehen auch Fuellungen im Tokensystem: Vorher waren sie als
    rgba-Literale in charts.py eingetragen und blieben bei einer
    Farbumstellung stehen.
    """
    r, g, b = (int(hexfarbe[i:i + 2], 16) for i in (1, 3, 5))
    return f"rgba({r}, {g}, {b}, {alpha})"


def _aufhellen(hexfarbe: str, anteil: float) -> str:
    """Mischt eine Farbe mit Weiss (anteil = Restanteil der Farbe)."""
    r, g, b = (int(hexfarbe[i:i + 2], 16) for i in (1, 3, 5))
    misch = lambda k: round(k * anteil + 255 * (1 - anteil))  # noqa: E731
    return f"#{misch(r):02X}{misch(g):02X}{misch(b):02X}"


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
    Colors.SELECT = _aufhellen(Colors.BRAND, 0.13)
    Colors.SOFT = _aufhellen(Colors.BRAND, 0.32)
    Colors.SERIES = [Colors.INK, Colors.BRAND, Colors.INK_SOFT,
                     Colors.SOFT, Colors.NEUTRAL]
    Colors.KATEGORIE = [
        Colors.INK, Colors.BRAND, Colors.INK_SOFT,
        _aufhellen(Colors.BRAND, 0.55), _aufhellen(Colors.BRAND, 0.8),
        _aufhellen(Colors.INK, 0.45), _aufhellen(Colors.BRAND, 1.0),
        _aufhellen(Colors.INK_SOFT, 0.6), Colors.SOFT, Colors.NEUTRAL,
    ]


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
        /* Streamlits eigene Kopfleiste (header[data-testid="stHeader"]) ist
           60px hoch, deckend weiss und liegt ueber dem Inhalt. Der obere
           Rand muss sie freihalten, sonst verschwindet das erste Element -
           sichtbar wurde das an der Kopfzeile, sobald ihr Untertitel auf
           zwei Zeilen umbrach und der Titel nach oben rutschte. */
        .block-container {{ padding-top: 4rem; max-width: 1280px; }}

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

        /* Die Werte werden gerundet dargestellt (siehe app/formatting.py:
           fmt_eur_kompakt), deshalb genuegen feste Schriftgroessen - das
           frueher noetige Mess-Skript zur nachtraeglichen Verkleinerung
           entfaellt. */
        .kpi-leiste {{
            display: grid;
            grid-template-columns: minmax(280px, 0.9fr) 2fr;
            gap: 14px;
            margin: 0.35rem 0 1rem 0;
        }}
        .kpi-begleiter {{
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
        }}
        .kpi-row {{
            display: grid;
            grid-auto-flow: column;
            grid-auto-columns: 1fr;
            gap: 12px;
            margin: 0.35rem 0 0.9rem 0;
        }}
        /* In schmalen Fenstern wird aus der zweispaltigen Leiste ein
           Stapel; die Begleiter bleiben zu zweit nebeneinander. */
        @media (max-width: 1150px) {{
            .kpi-leiste {{ grid-template-columns: 1fr; }}
            .kpi-row {{
                grid-auto-flow: row;
                grid-template-columns: repeat(3, minmax(0, 1fr));
            }}
        }}
        @media (max-width: 780px) {{
            .kpi-begleiter {{ grid-template-columns: 1fr; }}
            .kpi-row {{
                grid-auto-flow: row;
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }}
        }}

        .kpi-card, .kpi-hero {{
            position: relative;
            background: linear-gradient(180deg, {Colors.PAPER} 0%, {Colors.WASH} 100%);
            border: 1px solid {Colors.LINE};
            border-radius: 12px;
            padding: 14px 16px 12px 16px;
            min-width: 0;               /* erlaubt Schrumpfen in der Grid-Zelle */
            overflow: hidden;
            transition: transform 140ms ease, box-shadow 140ms ease;
        }}
        .kpi-card::before, .kpi-hero::before {{
            content: "";
            position: absolute;
            top: 0; left: 0; bottom: 0;
            width: 3px;
            background: {Colors.NEUTRAL};
        }}
        .kpi-hero {{
            border-color: {Colors.BRAND};
            box-shadow: 0 0 0 1px {Colors.BRAND};
            padding: 16px 20px 14px 22px;
            display: flex;
            flex-direction: column;
        }}
        .kpi-hero::before {{ width: 4px; background: {Colors.BRAND}; }}
        .kpi-card:hover, .kpi-hero:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 18px rgba(20, 48, 79, 0.10);
        }}
        .kpi-hero:hover {{
            box-shadow: 0 0 0 1px {Colors.BRAND}, 0 6px 18px rgba(20, 48, 79, 0.10);
        }}
        .kpi-label {{
            color: {Colors.MUTED};
            font-size: 0.74rem;
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.06em;
            margin-bottom: 2px;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        /* Wert und Einordnung untereinander statt nebeneinander: Neben
           der Parameterspalte sind die Begleitkacheln schmal, und der
           Zusatz wurde sonst nach zwei Zeichen abgeschnitten. */
        .kpi-zeile {{
            display: flex;
            flex-direction: column;
            align-items: flex-start;
        }}
        .kpi-value {{
            font-variant-numeric: tabular-nums;
            color: {Colors.INK};
            font-weight: 700;
            font-size: 1.5rem;
            line-height: 1.3;
            white-space: nowrap;
        }}
        .kpi-sub {{
            color: {Colors.MUTED};
            font-size: 0.72rem;
            line-height: 1.2;
            max-width: 100%;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
        .kpi-hero-value {{
            font-variant-numeric: tabular-nums;
            color: {Colors.INK};
            font-weight: 700;
            font-size: 2.6rem;
            line-height: 1.15;
            white-space: nowrap;
        }}
        .kpi-delta {{
            display: inline-block;
            align-self: flex-start;
            margin-top: 6px;
            padding: 2px 10px;
            border-radius: 999px;
            background: #E6F1EC;
            color: {Colors.POSITIVE};
            font-size: 0.72rem;
            font-weight: 600;
        }}
        .kpi-delta.negativ {{ background: #FBEBE9; color: {Colors.NEGATIVE}; }}
        /* Einordnung: Balken bis zum Wert, Marke bei der Zielgroesse -
           beantwortet "gut oder schlecht?" ohne eine zweite Zahl. */
        .kpi-ziel {{ margin-top: 12px; }}
        .kpi-ziel-bahn {{
            position: relative;
            height: 5px;
            border-radius: 3px;
            background: #E5EAED;
        }}
        .kpi-ziel-fuell {{
            position: absolute; top: 0; left: 0; bottom: 0;
            border-radius: 3px;
            background: {Colors.BRAND};
        }}
        .kpi-ziel-marke {{
            position: absolute;
            top: -4px; bottom: -4px;
            width: 2px;
            background: {Colors.INK};
        }}
        .kpi-ziel-label {{
            color: {Colors.MUTED};
            font-size: 0.7rem;
            margin-top: 4px;
        }}
        .kpi-fuss {{
            color: {Colors.MUTED};
            font-size: 0.72rem;
            margin-top: auto;
            padding-top: 10px;
        }}

        /* --- Sichtenauswahl (Ergebnis | Finanzierung | Risiko | Annahmen) ----
           Streamlits Segmentwahl bringt je Segment einen eigenen Rahmen mit;
           das liest sich als Knopfreihe, nicht als Sichtenwechsel. Hier:
           eine gemeinsame Grundlinie, die aktive Sicht tuerkis hinterlegt
           mit dunklerem Strich darunter - dieselbe Sprache wie der aktive
           Eintrag in der Seitenleiste. */
        div[data-testid="stButtonGroup"] {{
            border-bottom: 1px solid {Colors.LINE};
            gap: 0 !important;
        }}
        div[data-testid="stButtonGroup"] button {{
            border: none !important;
            border-radius: 6px 6px 0 0 !important;
            background: transparent !important;
            color: {Colors.MUTED} !important;
            font-weight: 500 !important;
            box-shadow: none !important;
        }}
        div[data-testid="stButtonGroup"] button:hover {{
            background: {Colors.WASH} !important;
            color: {Colors.INK} !important;
        }}
        div[data-testid="stButtonGroup"] button[aria-checked="true"] {{
            background: {Colors.SELECT} !important;
            color: {Colors.INK} !important;
            font-weight: 600 !important;
            box-shadow: inset 0 -2px 0 {Colors.BRAND} !important;
        }}

        /* --- Parameterspalte --------------------------------------------------
           Eigene Flaeche mit Markenrand: Die Spalte ist Eingabebereich, das
           uebrige Blatt zeigt Ergebnisse. Ohne Rahmen verschwimmt beides. */
        .st-key-parameterbox {{
            border: 1.5px solid {Colors.BRAND};
            border-radius: 12px;
            padding: 0 16px 14px 16px;
            background: {Colors.PAPER};
        }}
        .parameter-kopf {{
            margin: 0 -16px 12px -16px;
            padding: 10px 16px;
            background: {Colors.SELECT};
            border-radius: 10px 10px 0 0;
            color: {Colors.INK};
            font-weight: 700;
            font-size: 0.95rem;
            letter-spacing: 0.01em;
        }}

        /* --- Kontextzeile ------------------------------------------------------ */
        /* Marktsystem, Szenario und Diskontsatz gelten app-weit. Sie stehen
           hier sichtbar, statt als kleines Eingabefeld irgendwo auf der
           Seite - sonst verschiebt man unbemerkt die Vergleichsbasis. */
        .kontextzeile {{
            background: {Colors.WASH};
            border: 1px solid {Colors.LINE};
            border-radius: 8px;
            padding: 7px 14px;
            color: {Colors.MUTED};
            font-size: 0.84rem;
            margin: 0.2rem 0 0.6rem 0;
        }}
        .kontextzeile b {{ color: {Colors.INK}; font-weight: 600; }}

        /* --- Brotkrume --------------------------------------------------------- */
        .brotkrume {{
            font-size: 0.82rem;
            color: {Colors.MUTED};
            margin-bottom: 2px;
        }}
        .brotkrume b {{ color: {Colors.BRAND}; font-weight: 600; }}

        /* --- Projektkarten ---------------------------------------------------- */
        /* Feste Hoehe: Ohne sie richtet sich jede Karte nach der Laenge
           ihres Projektnamens, und die Oeffnen-Knoepfe einer Reihe stehen
           auf verschiedenen Hoehen. */
        .project-card {{
            position: relative;
            display: flex;
            flex-direction: column;
            gap: 3px;
            height: 152px;
            border: 1px solid {Colors.LINE};
            border-radius: 12px;
            padding: 12px 16px 10px 16px;
            margin-bottom: 8px;
            background: {Colors.PAPER};
            overflow: hidden;
            transition: transform 140ms ease, box-shadow 140ms ease,
                        border-color 140ms ease;
        }}
        /* Name und Kennzeichen in einer Zeile; der Name wird bei Bedarf
           gekuerzt, der vollstaendige steht im Tooltip der Karte. */
        .project-card .card-kopf {{
            display: flex;
            align-items: baseline;
            justify-content: space-between;
            gap: 8px;
            min-width: 0;
        }}
        .project-card .card-badges {{ flex: 0 0 auto; }}
        .project-card .card-kpi-zeile {{
            display: flex;
            align-items: baseline;
            gap: 6px;
            margin-top: 4px;
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
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            min-width: 0;
        }}
        .project-card .card-sub {{
            color: {Colors.MUTED};
            font-size: 0.84em;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}
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

        /* --- Tabs (Portfolio-Analytik, Auktionsmodul) --------------------------
           Gleiche Sprache wie die Sichtenauswahl der Projektseite: aktive
           Sicht tuerkis hinterlegt, dunklerer Strich darunter. */
        .stTabs [data-baseweb="tab"] {{
            font-weight: 500;
            color: {Colors.MUTED};
            border-radius: 6px 6px 0 0;
        }}
        .stTabs [data-baseweb="tab"]:hover {{ background: {Colors.WASH}; }}
        .stTabs [data-baseweb="tab"][aria-selected="true"] {{
            background: {Colors.SELECT};
            color: {Colors.INK};
            font-weight: 600;
        }}

        /* --- Sidebar ------------------------------------------------------------ */
        section[data-testid="stSidebar"] {{
            background: linear-gradient(180deg, {Colors.WASH} 0%, {Colors.PAPER} 60%);
            border-right: 1px solid {Colors.LINE};
        }}
        section[data-testid="stSidebar"] .stRadio label {{ font-weight: 500; }}

        /* Navigationseintraege sind Ortswechsel, keine Formularauswahl:
           linksbuendig, ohne Rahmen, der aktive Eintrag hervorgehoben
           (siehe app/components/sidebar.py). */
        .nav-gruppe {{
            color: {Colors.MUTED};
            font-size: 0.68rem;
            font-weight: 700;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            margin: 1.1rem 0 0.3rem 0.15rem;
        }}
        /* Knoepfe mit Hilfetext haengen bei Streamlit unter einem
           Tooltip-Traeger - der Knopf ist dann KEIN direktes Kind von
           .stButton mehr. Die Auswahl kommt deshalb ohne Kindkombinator
           aus, sonst greift die Gestaltung genau bei den Eintraegen nicht,
           die einen Hilfetext haben. */
        section[data-testid="stSidebar"] [data-testid="stTooltipHoverTarget"] {{
            width: 100%;
        }}
        section[data-testid="stSidebar"] button[kind="tertiary"] {{
            justify-content: flex-start;
            text-align: left;
            border: none;
            background: transparent;
            color: {Colors.MUTED};
            font-weight: 400;
            padding: 0.28rem 0.7rem;
            /* Links eckig: Der Aktiv-Balken sitzt an dieser Kante und
               wuerde von einer Rundung zu einem Bogen beschnitten. */
            border-radius: 0 8px 8px 0;
            min-height: 0;
            width: 100%;
        }}
        section[data-testid="stSidebar"] button[kind="tertiary"]:hover {{
            background: {Colors.WASH} !important;
            color: {Colors.INK} !important;
        }}
        /* Streamlit zentriert den Beschriftungstext im Knopf. Fuer eine
           Navigationsliste muss er linksbuendig stehen, sonst wandert er
           mit der Laenge des Projektnamens hin und her. */
        section[data-testid="stSidebar"] button[kind="tertiary"] div,
        section[data-testid="stSidebar"] button[kind="tertiary"] span,
        section[data-testid="stSidebar"] button[kind="tertiary"] p {{
            width: 100%;
            min-width: 0;
            justify-content: flex-start;
            text-align: left;
        }}
        /* Eine Zeile je Eintrag: Lange Projektnamen brechen sonst mitten
           im Wort um und machen aus der Liste unterschiedlich hohe
           Bloecke. Der vollstaendige Name steht im Tooltip. */
        section[data-testid="stSidebar"] button[kind="tertiary"] p {{
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }}

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
        /* Die Markenfarbe oben wird mit !important gesetzt und wuerde sonst
           auch fuer gesperrte Knoepfe gelten - "Speichern" saehe dann
           anklickbar aus, obwohl es nichts zu speichern gibt. */
        button[kind="primary"]:disabled,
        button[data-testid="stBaseButton-primary"]:disabled {{
            background-color: {Colors.SOFT} !important;
            border-color: {Colors.SOFT} !important;
            color: {Colors.PAPER} !important;
            opacity: 0.7;
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
