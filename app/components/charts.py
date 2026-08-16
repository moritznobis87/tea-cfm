"""
Alle Plotly-Diagramme der App als reine Builder-Funktionen
(DataFrame rein, Figure raus - kein Streamlit-Import).

Vorteile dieser Trennung:
- Views bleiben schlank und lesbar,
- jedes Diagramm ist isoliert testbar,
- Farb- und Formatentscheidungen kommen zentral aus app.theme.
"""

from __future__ import annotations

import os as _os

import pandas as pd
import plotly.graph_objects as go

from app.formatting import fmt_number, fmt_pct
from app.theme import Colors, mit_alpha
from texte import txt

_EUR_HOVER = "%{y:,.0f} €"


def _signed_colors(values: pd.Series) -> list[str]:
    """Tuerkis fuer Zufluesse, Navy fuer Abfluesse - einheitlich in allen
    Cashflow-Darstellungen.

    Die Richtung steht bereits in der Lage des Balkens zur Nulllinie;
    die Farbe muss sie nicht ein zweites Mal behaupten. Fuer Gruen und
    Rot bleiben damit die Faelle, in denen wirklich etwas nicht stimmt:
    die Unterdeckung im DSCR-Verlauf und die Zielverfehlung in der
    IRR-Heatmap."""
    return [Colors.BRAND if v >= 0 else Colors.INK_SOFT for v in values]


def revenue_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        x=df["jahr"], y=df["erloes_eur"], name=txt("diagramme.serie_umsatzerloese"),
        marker_color=Colors.BRAND, hovertemplate=_EUR_HOVER + "<extra></extra>",
    )
    fig.update_layout(
        yaxis_title="€", xaxis_title=txt("diagramme.achse_betriebsjahr"), height=360, showlegend=False
    )
    return fig

def tax_chart(df: pd.DataFrame) -> go.Figure:
    """Steuerzahlungen je Betriebsjahr - eigenständiges Diagramm direkt
    unter der Betriebskosten-Grafik, da Steuer bislang in keinem
    Diagramm sichtbar war (nur in der Detailtabelle)."""
    fig = go.Figure()
    fig.add_bar(
        x=df["jahr"], y=df["steuer_eur"], name=txt("diagramme.serie_steuern"),
        marker_color=Colors.INK_SOFT, hovertemplate=_EUR_HOVER + "<extra></extra>",
    )
    fig.update_layout(
        yaxis_title="€", xaxis_title=txt("diagramme.achse_betriebsjahr"),
        height=360, showlegend=False,
    )
    return fig


def opex_stacked_chart(df: pd.DataFrame, opex_posten: list[str]) -> go.Figure:
    """Betriebskosten als gestapelte Balken - eine Position je
    Legendeneintrag (per Klick ein-/ausblendbar), Gemeindeabgabe und
    Direktvermarktung als eigene produktionsbasierte Positionen."""
    fig = go.Figure()
    for i, posten in enumerate(opex_posten):
        fig.add_bar(
            x=df["jahr"], y=df[posten], name=posten,
            marker_color=Colors.OPEX_SCALE[i % len(Colors.OPEX_SCALE)],
            hovertemplate=_EUR_HOVER + "<extra>%{fullData.name}</extra>",
        )
    fig.add_bar(
        x=df["jahr"], y=df["gemeindeabgabe_eur"],
        name=txt("diagramme.serie_gemeindeabgabe"),
        marker_color=Colors.INK,
        hovertemplate=_EUR_HOVER
        + f"<extra>{txt('diagramme.serie_gemeindeabgabe')}</extra>",
    )
    fig.add_bar(
        x=df["jahr"], y=df["direktvermarktungskosten_eur"],
        name=txt("diagramme.serie_direktvermarktung"),
        marker_color=Colors.INK_SOFT,
        hovertemplate=_EUR_HOVER
        + f"<extra>{txt('diagramme.serie_direktvermarktung')}</extra>",
    )
    fig.update_layout(
        barmode="stack", yaxis_title="€", xaxis_title=txt("diagramme.achse_betriebsjahr"), height=420
    )
    return fig


def operating_cashflow_chart(df: pd.DataFrame) -> go.Figure:
    """Vereinfachter operativer Cashflow (Erloese - Betriebskosten), vor
    Zinsen und Steuer."""
    werte = df["erloes_eur"] - df["opex_gesamt_eur"]
    fig = go.Figure()
    fig.add_bar(
        x=df["jahr"], y=werte, name="Operativer Cashflow",
        marker_color=_signed_colors(werte),
        hovertemplate=_EUR_HOVER + "<extra></extra>",
    )
    fig.update_layout(
        yaxis_title="€", xaxis_title=txt("diagramme.achse_betriebsjahr"), height=360, showlegend=False
    )
    return fig


def financing_cashflow_chart(df: pd.DataFrame) -> go.Figure:
    """Kreditaufnahme (Jahr 0) vs. laufende Tilgung. Zinsen sind bewusst
    nicht enthalten - sie sind Teil des operativen Cashflows."""
    kreditaufnahme = df["cf_finanzierung_eur"] + df["tilgung_eur"]
    fig = go.Figure()
    fig.add_bar(
        x=df["jahr"], y=kreditaufnahme, name=txt("diagramme.serie_kreditaufnahme"),
        marker_color=Colors.BRAND, hovertemplate=_EUR_HOVER + "<extra></extra>",
    )
    fig.add_bar(
        x=df["jahr"], y=-df["tilgung_eur"], name=txt("diagramme.serie_tilgung"),
        marker_color=Colors.INK_SOFT, hovertemplate=_EUR_HOVER + "<extra></extra>",
    )
    fig.update_layout(
        barmode="relative", yaxis_title="€", xaxis_title="Jahr", height=420
    )
    return fig


def total_cashflow_chart(df: pd.DataFrame) -> go.Figure:
    """Gesamt-Cashflow je Jahr (Balken) plus kumulierte Kurve (Linie,
    rechte Achse)."""
    fig = go.Figure()
    fig.add_bar(
        x=df["jahr"], y=df["cf_gesamt_eur"], name=txt("diagramme.achse_cashflow_jahr"),
        marker_color=_signed_colors(df["cf_gesamt_eur"]),
        hovertemplate=_EUR_HOVER + "<extra></extra>",
    )
    fig.add_scatter(
        x=df["jahr"], y=df["cf_kumuliert_eur"], name="Kumulierter Cashflow",
        mode="lines+markers", line=dict(color=Colors.INK, width=2), yaxis="y2",
        hovertemplate=_EUR_HOVER + "<extra>kumuliert</extra>",
    )
    fig.update_layout(
        yaxis=dict(title=txt("diagramme.achse_cashflow_jahr_eur")),
        yaxis2=dict(
            title="Kumuliert in €", overlaying="y", side="right", showgrid=False
        ),
        xaxis_title="Jahr",
        height=440,
    )
    return fig


def dscr_chart(dscr_df: pd.DataFrame) -> go.Figure:
    """Schuldendienstdeckung je Betriebsjahr.

    Nur die Unterdeckung ist eingefaerbt: Ein Balkenfeld in Warnfarbe,
    obwohl jedes Jahr die Deckung einhaelt, sagt nichts - die Ausnahme
    soll auffallen, nicht der Normalfall.
    """
    fig = go.Figure()
    fig.add_bar(
        x=dscr_df["jahr"], y=dscr_df["dscr"], name="DSCR",
        marker_color=[
            Colors.NEGATIVE if v < 1.0 else Colors.BRAND for v in dscr_df["dscr"]
        ],
        hovertemplate="%{y:,.2f}x<extra></extra>",
    )
    fig.add_hline(
        y=1.0, line_dash="dot", line_color=Colors.MUTED,
        annotation_text=txt("diagramme.serie_dscr_grenze"),
    )
    fig.update_layout(
        xaxis_title=txt("diagramme.achse_betriebsjahr"), yaxis_title=txt("diagramme.achse_dscr"),
        height=420, showlegend=False,
    )
    return fig


def npv_curve_chart(npv_df: pd.DataFrame, equity_irr: float | None) -> go.Figure:
    fig = go.Figure()
    fig.add_scatter(
        x=npv_df["diskontsatz_pct"] * 100, y=npv_df["npv_eur"],
        mode="lines+markers", name="NPV", line=dict(color=Colors.INK),
        hovertemplate="Diskontsatz %{x:,.1f} %: %{y:,.0f} €<extra></extra>",
    )
    fig.add_hline(y=0, line_dash="dot", line_color="gray")
    if equity_irr is not None:
        # IRR ist per Definition die Nullstelle der NPV-Kurve.
        fig.add_vline(
            x=equity_irr * 100, line_dash="dot", line_color=Colors.BRAND,
            annotation_text="IRR",
        )
    fig.update_layout(
        xaxis_title=txt("diagramme.achse_diskontsatz_pct"), yaxis_title=txt("diagramme.achse_npv_eur"), height=420
    )
    return fig


def eag_sensitivity_chart(sens_df: pd.DataFrame) -> go.Figure:
    """IRR ueber dem variierten EAG-Zuschlagswert (±5 %/±2,5 %/Basis).

    Die Stufen stehen in engine.sensitivity.DEFAULT_VARIANTEN_PCT; diese
    Funktion zeichnet, was ihr uebergeben wird.

    Defensiv: einzelne Varianten koennen eine nicht berechenbare IRR
    (None) liefern, wenn der Cashflow keinen Vorzeichenwechsel mehr hat
    (z.B. durchgehend negativ im tiefsten Downside).
    """
    irr_werte = pd.to_numeric(sens_df["equity_irr"], errors="coerce")
    irr_pct = (irr_werte * 100).tolist()
    eag_werte = sens_df["eag_zuschlagswert_ct_kwh"].astype(float).tolist()
    varianten = sens_df["variante"].astype(str).tolist()
    beschriftungen = [
        fmt_pct(v) if v is not None and pd.notna(v) else "n/a"
        for v in sens_df["equity_irr"]
    ]

    fig = go.Figure()
    fig.add_bar(
        x=eag_werte,
        y=irr_pct,
        width=0.15,
        marker_color=[
            Colors.INK if v == "Basis" else Colors.SOFT for v in varianten
        ],
        customdata=varianten,
        hovertemplate="%{customdata}: %{x:,.2f} ct/kWh → %{text}<extra></extra>",
        text=beschriftungen,
        # Sichtbare Beschriftung kommt ausschliesslich ueber die
        # Annotationen unten - "textposition=outside" wuerde bei negativer
        # IRR unterhalb des Balkens landen (Plotly richtet sich nach dem
        # Vorzeichen); yshift ist dagegen ein reiner Pixel-Offset und sitzt
        # immer oberhalb der Balkenspitze.
        textposition="none",
    )
    for x_wert, y_wert, text in zip(eag_werte, irr_pct, beschriftungen, strict=True):
        fig.add_annotation(
            x=x_wert, y=y_wert if pd.notna(y_wert) else 0,
            text=text, showarrow=False, yshift=14,
            font=dict(size=12, color=Colors.INK),
        )
    fig.update_layout(
        xaxis=dict(
            title="EAG-Zuschlagswert (ct/kWh)",
            tickmode="array", tickvals=eag_werte, tickformat=".2f",
        ),
        yaxis=dict(title="EK-Rendite", ticksuffix=" %"),
        height=380,
        showlegend=False,
    )
    return fig


# ===========================================================================
# Erweiterte Diagramme (v3): Waterfall, Erlösanalyse, Finanzierung,
# Tornado, Heatmap, Monte Carlo, Szenarien, Portfolio
# ===========================================================================


def equity_waterfall_chart(df: pd.DataFrame) -> go.Figure:
    """Brücke über die Gesamtlaufzeit: von den Umsatzerlösen zum
    kumulierten Equity-Cashflow des Projekts."""
    erloese = float(df["erloes_eur"].sum())
    opex = -float(df["opex_gesamt_eur"].sum())
    zinsen = -float(df["zinsen_eur"].sum())
    steuern = -float(df["steuer_eur"].sum())
    capex = float(df["cf_invest_eur"].sum())          # negativ
    kredit = float(df.loc[df["jahr"] == 0, "cf_finanzierung_eur"].iloc[0])
    tilgung = -float(df["tilgung_eur"].sum())

    fig = go.Figure(
        go.Waterfall(
            orientation="v",
            measure=[
                "relative", "relative", "relative", "relative", "total",
                "relative", "relative", "relative", "total",
            ],
            x=[
                txt("diagramme.serie_umsatzerloese"),
                txt("diagramme.serie_betriebskosten"),
                txt("diagramme.serie_zinsen_waterfall"),
                txt("diagramme.serie_steuern"),
                txt("diagramme.serie_operativer_cf"),
                txt("diagramme.serie_investition"),
                txt("diagramme.serie_kreditaufnahme"),
                txt("diagramme.serie_tilgung"),
                txt("diagramme.serie_equity_cashflow"),
            ],
            y=[erloese, opex, zinsen, steuern, 0, capex, kredit, tilgung, 0],
            connector=dict(line=dict(color=Colors.LINE, width=1)),
            increasing=dict(marker_color=Colors.BRAND),
            decreasing=dict(marker_color=Colors.INK_SOFT),
            totals=dict(marker_color=Colors.INK),
            # Bewusst %{delta} statt %{y}: Bei Waterfall-Traces liefert
            # %{y} die kumulierte Endposition des Balkens auf der
            # Y-Achse - fuer den Betrachter unbrauchbar. %{delta} ist
            # die (vorzeichenbehaftete) Hoehe des Balkens selbst; bei
            # Total-Balken (initial = 0) entspricht delta dem Endwert,
            # die Vorlage passt also fuer beide Balkentypen.
            hovertemplate="%{delta:,.0f} €<extra>%{x}</extra>",
        )
    )
    fig.update_layout(height=440, showlegend=False, yaxis_title="€ (Summe Laufzeit)")
    return fig


def _legendennamen(namen: list[str]) -> dict[str, str]:
    """Kuerzt die gemeinsame Herkunft aus den Legendennamen heraus.

    Aus einer Aurora-Arbeitsmappe entstehen Szenarien wie „Aurora Q3/26
    GER · Pult · Central": In der Legende steht dreimal derselbe Stamm
    und einmal der Unterschied, auf den es ankommt. Gekuerzt wird nur an
    einer Trennstelle („·" oder Leerzeichen) und nur, wenn alle Namen
    danach noch verschieden und nicht leer sind - sonst waere die
    Zuordnung dahin.
    """
    if len(namen) < 2:
        return {n: n for n in namen}
    gemeinsam = _os.path.commonprefix(namen)
    schnitt = max(gemeinsam.rfind("·"), gemeinsam.rfind(" "))
    if schnitt < 0:
        return {n: n for n in namen}
    stamm = gemeinsam[: schnitt + 1]
    gekuerzt = {n: n[len(stamm):].strip() for n in namen}
    if any(not k for k in gekuerzt.values()) or len(set(gekuerzt.values())) != len(namen):
        return {n: n for n in namen}
    return gekuerzt


def szenarien_linien_chart(
    reihen: list[tuple[str, dict[int, float]]],
    y_titel: str,
    einheit: str,
    faktor: float = 1.0,
    nachkommastellen: int = 2,
) -> go.Figure:
    """Eine Linie je Marktpreisszenario ueber dem Kalenderjahr.

    Der Vergleich ist die eigentliche Frage an eine Szenariosammlung:
    Wie weit liegen die Prognosen auseinander, und ab wann? In einer
    Tabelle mit 36 Zeilen je Szenario ist das nicht zu sehen - vier
    Linien in einem Bild beantworten es auf einen Blick.

    reihen: (Szenarioname, {Kalenderjahr: Wert}). Leere Reihen werden
    uebergangen; ein Szenario ohne Kurve hat nichts zu zeigen.
    """
    fig = go.Figure()
    gezeigt = [(name, kurve) for name, kurve in reihen if kurve]
    kuerzel = _legendennamen([name for name, _ in gezeigt])
    for i, (name, kurve) in enumerate(gezeigt):
        jahre = sorted(kurve)
        fig.add_scatter(
            x=jahre, y=[kurve[j] * faktor for j in jahre], mode="lines",
            name=kuerzel[name],
            line=dict(color=Colors.SERIES[i % len(Colors.SERIES)], width=2.2),
            hovertemplate=(
                # Im Tooltip der volle Name: Die Legende kuerzt nur die
                # gemeinsame Herkunft weg, die Zuordnung muss eindeutig
                # bleiben.
                f"{name}<br>%{{x}}: %{{y:,.{nachkommastellen}f}} {einheit}"
                "<extra></extra>"
            ),
        )
    fig.update_layout(
        # Die Legende steht ueber dem Bild und braucht je vier Eintraege
        # eine Zeile mehr - ohne Zuschlag schrumpfte die Zeichenflaeche
        # mit jedem weiteren Szenario.
        height=320 + 18 * max(0, (len(gezeigt) - 1) // 2),
        xaxis_title=txt("diagramme.achse_kalenderjahr"),
        # Prozentzeichen an die Achse, andere Einheiten nicht: "20"
        # allein liest sich wie eine absolute Menge, waehrend "5 ct/kWh"
        # an jedem Strich nur die Einheit aus dem Achsentitel
        # wiederholt.
        yaxis=dict(title=y_titel, ticksuffix=" %" if einheit == "%" else ""),
        margin=dict(t=30, b=40),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0),
    )
    return fig


def verguetung_chart(
    df: pd.DataFrame, eag_zuschlag_ct: float, foerderdauer_jahre: int
) -> go.Figure:
    """Vergütungssatz vs. nominaler Marktwert über die Laufzeit. Die Fläche
    zwischen den Kurven ist die Marktprämie; die gestrichelte Linie zeigt
    den nominal fixen EAG-Zuschlagswert, die Markierung das Förderende."""
    betrieb = df[df["jahr"] >= 1]
    fig = go.Figure()
    # Der Grosshandelspreis als Hintergrund, sofern das Szenario ihn
    # kennt: Der Abstand zum Marktwert Solar IST der
    # Kannibalisierungseffekt - eine Aussage, die keine Kennzahl der
    # Seite sonst zeigt.
    if "baseload_nominal_ct_kwh" in betrieb.columns and float(
        betrieb["baseload_nominal_ct_kwh"].abs().sum()
    ):
        fig.add_scatter(
            x=betrieb["jahr"], y=betrieb["baseload_nominal_ct_kwh"],
            name=txt("diagramme.serie_baseload"), mode="lines",
            line=dict(color=Colors.MUTED, width=1.6, dash="dot"),
            hovertemplate=(
                "%{y:,.2f} ct/kWh<extra>"
                + txt("diagramme.serie_baseload")
                + "</extra>"
            ),
        )
    fig.add_scatter(
        x=betrieb["jahr"], y=betrieb["marktwert_nominal_ct_kwh"],
        name="Marktwert Solar (nominal)", mode="lines",
        line=dict(color=Colors.SOFT, width=2),
        hovertemplate="%{y:,.2f} ct/kWh<extra>Marktwert nominal</extra>",
    )
    fig.add_scatter(
        x=betrieb["jahr"], y=betrieb["verguetungssatz_ct_kwh"],
        name=txt("diagramme.serie_verguetungssatz"), mode="lines",
        line=dict(color=Colors.INK, width=2.5),
        fill="tonexty", fillcolor=mit_alpha(Colors.SOFT, 0.45),
        hovertemplate="%{y:,.2f} ct/kWh<extra>" + txt("diagramme.serie_verguetungssatz") + "</extra>",
    )
    fig.add_hline(
        y=eag_zuschlag_ct, line_dash="dot", line_color=Colors.BRAND,
        annotation_text=txt("diagramme.annotation_eag_zuschlagswert_fix"),
        annotation_font_color=Colors.BRAND,
    )
    fig.add_vline(
        x=foerderdauer_jahre + 0.5, line_dash="dash", line_color=Colors.MUTED,
        annotation_text=txt("diagramme.serie_foerderende"), annotation_position="top",
    )
    fig.update_layout(
        height=420, xaxis_title=txt("diagramme.achse_betriebsjahr"), yaxis_title="ct/kWh",
        hovermode="x unified",
    )
    return fig


def revenue_split_chart(df: pd.DataFrame) -> go.Figure:
    """Erlöse nach Herkunft: Merchant, PPA, Marktprämie - und, falls das
    Fördermodell eine vorsieht, die Rückzahlung als Balken unter der
    Nulllinie.

    Zeigt, wie lange das Projekt am Fördertropf hängt und wann der Markt
    trägt. PPA und Rückzahlung erscheinen nur, wenn es sie gibt: Eine
    Legende mit zwei dauerhaft leeren Einträgen behauptet eine Struktur,
    die das Projekt nicht hat."""
    betrieb = df[df["jahr"] >= 1]
    fig = go.Figure()

    def _hat(spalte: str) -> bool:
        return spalte in betrieb.columns and float(betrieb[spalte].abs().sum()) > 0

    if _hat("erloes_ppa_eur"):
        merchant = betrieb["erloes_merchant_eur"]
        fig.add_bar(
            x=betrieb["jahr"], y=betrieb["erloes_ppa_eur"],
            name=txt("diagramme.serie_erloes_ppa"), marker_color=Colors.SERIES[2],
            hovertemplate=_EUR_HOVER
            + f"<extra>{txt('diagramme.serie_erloes_ppa')}</extra>",
        )
    else:
        merchant = betrieb["erloes_markt_eur"]
    fig.add_bar(
        x=betrieb["jahr"], y=merchant, name=txt("diagramme.serie_markterloes"),
        marker_color=Colors.BRAND,
        hovertemplate=_EUR_HOVER + f"<extra>{txt('diagramme.serie_markterloes')}</extra>",
    )
    fig.add_bar(
        x=betrieb["jahr"], y=betrieb["erloes_praemie_eur"], name=txt("diagramme.serie_marktpraemie") + " (EAG)",
        marker_color=Colors.INK_SOFT,
        hovertemplate=_EUR_HOVER + f"<extra>{txt('diagramme.serie_marktpraemie')}</extra>",
    )
    if _hat("rueckzahlung_eur"):
        fig.add_bar(
            x=betrieb["jahr"], y=-betrieb["rueckzahlung_eur"],
            name=txt("diagramme.serie_rueckzahlung"), marker_color=Colors.NEGATIVE,
            hovertemplate=_EUR_HOVER
            + f"<extra>{txt('diagramme.serie_rueckzahlung')}</extra>",
        )
    fig.update_layout(
        barmode="relative", height=400, xaxis_title=txt("diagramme.achse_betriebsjahr"), yaxis_title="€",
        hovermode="x unified",
    )
    return fig


def debt_profile_chart(df: pd.DataFrame, fremdkapital_eur: float) -> go.Figure:
    """Schuldenprofil: Restschuld (Fläche) sowie Zinsen und Tilgung
    (gestapelte Balken = Schuldendienst) über die Kreditlaufzeit."""
    betrieb = df[df["jahr"] >= 1].copy()
    restschuld = fremdkapital_eur - betrieb["tilgung_eur"].cumsum()
    fig = go.Figure()
    fig.add_scatter(
        x=betrieb["jahr"], y=restschuld.clip(lower=0), name="Restschuld",
        mode="lines", line=dict(color=Colors.INK, width=2),
        fill="tozeroy", fillcolor=mit_alpha(Colors.INK, 0.10),
        hovertemplate=_EUR_HOVER + "<extra>Restschuld</extra>",
    )
    fig.add_bar(
        x=betrieb["jahr"], y=betrieb["zinsen_eur"], name=txt("diagramme.serie_zinsen"),
        marker_color=Colors.BRAND,
        hovertemplate=_EUR_HOVER + "<extra>Zinsen</extra>",
    )
    fig.add_bar(
        x=betrieb["jahr"], y=betrieb["tilgung_eur"], name=txt("diagramme.serie_tilgung"),
        marker_color=Colors.INK_SOFT,
        hovertemplate=_EUR_HOVER + "<extra>Tilgung</extra>",
    )
    fig.update_layout(
        barmode="stack", height=420, xaxis_title=txt("diagramme.achse_betriebsjahr"), yaxis_title="€",
        hovermode="x unified",
    )
    return fig


def capex_donut_chart(posten: dict[str, float]) -> go.Figure:
    """Investitionsstruktur als Donut (nur Positionen > 0)."""
    aktiv = {k: v for k, v in posten.items() if v > 0}
    fig = go.Figure(
        go.Pie(
            labels=list(aktiv.keys()),
            values=list(aktiv.values()),
            hole=0.55,
            marker=dict(colors=Colors.KATEGORIE + Colors.OPEX_SCALE),
            textinfo="percent",
            hovertemplate="%{label}: %{value:,.0f} € (%{percent})<extra></extra>",
        )
    )
    fig.update_layout(height=340, margin=dict(t=10, b=10))
    return fig


def kapitalstruktur_donut_chart(ek_eur: float, fk_eur: float) -> go.Figure:
    fig = go.Figure(
        go.Pie(
            labels=[txt("diagramme.serie_eigenkapital"), txt("diagramme.serie_fremdkapital")],
            values=[max(ek_eur, 0), max(fk_eur, 0)],
            hole=0.55,
            marker=dict(colors=[Colors.INK, Colors.BRAND]),
            textinfo="label+percent",
            hovertemplate="%{label}: %{value:,.0f} €<extra></extra>",
        )
    )
    fig.update_layout(height=340, margin=dict(t=10, b=10), showlegend=False)
    return fig


def tornado_chart(tornado_df: pd.DataFrame) -> go.Figure:
    """Tornado-Diagramm: IRR-Wirkung der Einzelvariation jedes Treibers
    (±10 %), sortiert nach Spannweite - zeigt auf einen Blick, welche
    Annahmen das Ergebnis wirklich bewegen."""
    basis = tornado_df["irr_basis"].iloc[0]
    basis_pct = (basis or 0) * 100

    fig = go.Figure()
    for _, zeile in tornado_df.iterrows():
        runter = (zeile["irr_runter"] or 0) * 100
        rauf = (zeile["irr_rauf"] or 0) * 100
        # Balken vom Basiswert zu beiden Varianten.
        fig.add_bar(
            y=[zeile["name"]], x=[runter - basis_pct], base=basis_pct,
            orientation="h", marker_color=Colors.INK_SOFT, width=0.55,
            hovertemplate=f"−10 %: {runter:,.2f} % IRR<extra>{zeile['name']}</extra>".replace(",", "X").replace(".", ",").replace("X", "."),
            showlegend=False,
        )
        fig.add_bar(
            y=[zeile["name"]], x=[rauf - basis_pct], base=basis_pct,
            orientation="h", marker_color=Colors.BRAND, width=0.55,
            hovertemplate=f"+10 %: {rauf:,.2f} % IRR<extra>{zeile['name']}</extra>".replace(",", "X").replace(".", ",").replace("X", "."),
            showlegend=False,
        )
    fig.add_vline(
        x=basis_pct, line_color=Colors.INK, line_width=2,
        annotation_text=f"Basis {fmt_pct(basis)}", annotation_position="top",
    )
    fig.update_layout(
        barmode="overlay", height=380,
        xaxis=dict(title="EK-Rendite", ticksuffix=" %"),
        yaxis=dict(title=""),
    )
    return fig


def irr_heatmap_chart(
    grid_df: pd.DataFrame, label_x: str, label_y: str, ziel_irr: float | None = None
) -> go.Figure:
    """IRR über ein 2D-Raster zweier Treiber. Zellen mit IRR unter dem
    Ziel erscheinen rot, darüber grün - der Übergang markiert die
    Break-even-Grenze."""
    pivot = grid_df.pivot(index="faktor_y", columns="faktor_x", values="equity_irr")
    z = pivot.to_numpy() * 100
    x_labels = [f"{(f - 1) * 100:+.0f} %".replace(".", ",") for f in pivot.columns]
    y_labels = [f"{(f - 1) * 100:+.0f} %".replace(".", ",") for f in pivot.index]

    fig = go.Figure(
        go.Heatmap(
            z=z, x=x_labels, y=y_labels,
            colorscale=Colors.HEAT_SCALE,
            zmid=(ziel_irr or 0.08) * 100,
            texttemplate="%{z:.1f}",
            textfont=dict(size=11, family="Inter, sans-serif"),
            colorbar=dict(title="IRR %", ticksuffix=" %"),
            hovertemplate=(
                label_x + " %{x} · " + label_y + " %{y}: %{z:.2f} % IRR<extra></extra>"
            ),
        )
    )
    fig.update_layout(
        height=460,
        xaxis_title=f"Δ {label_x}",
        yaxis_title=f"Δ {label_y}",
    )
    return fig


def mc_irr_histogram(irr_werte, p10: float, p50: float, p90: float) -> go.Figure:
    """Verteilung der EK-Rendite aus der Monte-Carlo-Simulation mit
    P10/P50/P90-Markierungen."""
    fig = go.Figure()
    fig.add_histogram(
        x=[v * 100 for v in irr_werte], nbinsx=40,
        marker=dict(color=Colors.BRAND, line=dict(color=Colors.PAPER, width=1)),
        hovertemplate="%{x} %: %{y} " + txt("diagramme.achse_anzahl_laeufe") + "<extra></extra>",
    )
    for wert, name, farbe in [
        # Quantile sind Lagemasse, keine Bewertung - deshalb Abstufungen
        # derselben Familie statt Rot/Gruen.
        (p10, "P10", Colors.INK_SOFT),
        (p50, "P50", Colors.INK),
        (p90, "P90", Colors.BRAND),
    ]:
        fig.add_vline(
            x=wert * 100, line_dash="dash", line_color=farbe,
            annotation_text=f"{name} {fmt_pct(wert)}", annotation_font_color=farbe,
        )
    fig.update_layout(
        height=400, xaxis=dict(title=txt("diagramme.achse_irr_kurz"), ticksuffix=" %"),
        yaxis_title=txt("diagramme.achse_anzahl_laeufe"), showlegend=False, bargap=0.05,
    )
    return fig


def mc_fan_chart(mc) -> go.Figure:
    """Fächerdiagramm des kumulierten Equity-Cashflows: P10-P90- und
    P25-P75-Band um den Median - die Bandbreite des Vermögensaufbaus."""
    jahre = mc.jahre
    fig = go.Figure()
    # Äußeres Band (P10-P90)
    fig.add_scatter(
        x=jahre, y=mc.kum_p90, mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    )
    fig.add_scatter(
        x=jahre, y=mc.kum_p10, mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor=mit_alpha(Colors.INK, 0.10),
        name="P10–P90", hovertemplate=_EUR_HOVER + "<extra>P10</extra>",
    )
    # Inneres Band (P25-P75)
    fig.add_scatter(
        x=jahre, y=mc.kum_p75, mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    )
    fig.add_scatter(
        x=jahre, y=mc.kum_p25, mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor=mit_alpha(Colors.INK, 0.22),
        name="P25–P75", hovertemplate=_EUR_HOVER + "<extra>P25</extra>",
    )
    fig.add_scatter(
        x=jahre, y=mc.kum_p50, mode="lines", name="Median (P50)",
        line=dict(color=Colors.INK, width=2.5),
        hovertemplate=_EUR_HOVER + "<extra>Median</extra>",
    )
    fig.add_hline(y=0, line_dash="dot", line_color=Colors.MUTED)
    fig.update_layout(
        height=420, xaxis_title=txt("diagramme.achse_jahr_kurz"), yaxis_title=txt("diagramme.achse_kumulierter_cf"),
        hovermode="x unified",
    )
    return fig


def scenario_bar_chart(kennzahlen: pd.DataFrame) -> go.Figure:
    """IRR je Marktpreisszenario (Balken) mit NPV im Hover."""
    fig = go.Figure()
    irr_pct = [(v or 0) * 100 for v in kennzahlen["equity_irr"]]
    fig.add_bar(
        x=kennzahlen["szenario"], y=irr_pct,
        marker_color=[Colors.KATEGORIE[i % len(Colors.KATEGORIE)]
                      for i in range(len(kennzahlen))],
        text=[fmt_pct(v) for v in kennzahlen["equity_irr"]],
        textposition="outside",
        customdata=kennzahlen["npv_eur"],
        hovertemplate="%{x}: %{text} IRR · NPV %{customdata:,.0f} €<extra></extra>",
    )
    fig.update_layout(
        height=380, yaxis=dict(title="EK-Rendite", ticksuffix=" %"),
        showlegend=False,
    )
    return fig


def scenario_cum_chart(kum_df: pd.DataFrame) -> go.Figure:
    """Kumulierter Equity-Cashflow je Szenario im Zeitverlauf."""
    fig = go.Figure()
    for i, spalte in enumerate([c for c in kum_df.columns if c != "jahr"]):
        fig.add_scatter(
            x=kum_df["jahr"], y=kum_df[spalte], name=spalte, mode="lines",
            line=dict(color=Colors.KATEGORIE[i % len(Colors.KATEGORIE)], width=2),
            hovertemplate=_EUR_HOVER + f"<extra>{spalte}</extra>",
        )
    fig.add_hline(y=0, line_dash="dot", line_color=Colors.MUTED)
    fig.update_layout(
        height=400, xaxis_title=txt("diagramme.achse_jahr_kurz"), yaxis_title=txt("diagramme.achse_kumulierter_cf"),
        hovermode="x unified",
    )
    return fig


def varianten_dscr_chart(
    reihen: list[tuple[str, pd.DataFrame]],
    cash_trap: float,
    event_of_default: float,
) -> go.Figure:
    """DSCR je Betriebsjahr, eine Linie je Variante.

    Die Kennzahl, an der Sensitivitaeten am deutlichsten auseinander
    laufen - und die einzige, bei der eine einzelne Zahl (der Minimalwert)
    verschweigt, ob die Unterdeckung ein Ausreisser oder ein Dauerzustand
    ist. Die beiden Kovenantenschwellen stehen als waagrechte Linien.
    """
    fig = go.Figure()
    for i, (label, df) in enumerate(reihen):
        gueltig = df[df["dscr"].notna()]
        fig.add_scatter(
            x=gueltig["jahr"], y=gueltig["dscr"], mode="lines", name=label,
            line=dict(color=Colors.SERIES[i % len(Colors.SERIES)], width=2.2),
            hovertemplate=f"{label}<br>Jahr %{{x}}: %{{y:,.2f}}x<extra></extra>",
        )
    # Die Schwellen kommen aus den Globalen Annahmen, nicht aus dem
    # Diagramm - sonst zeigte das Bild eine andere Grenze als die
    # Kovenantenpruefung darueber.
    for wert, farbe, schluessel in [
        (cash_trap, Colors.MUTED, "diagramme.serie_cash_trap"),
        (event_of_default, Colors.NEGATIVE, "diagramme.serie_event_of_default"),
    ]:
        fig.add_hline(
            y=wert, line=dict(color=farbe, width=1.2, dash="dash"),
            annotation_text=txt(schluessel, wert=fmt_number(wert, 2)),
            annotation_position="top right",
            annotation_font=dict(size=10, color=farbe),
        )
    fig.update_layout(
        height=340, xaxis_title=txt("diagramme.achse_betriebsjahr"),
        yaxis=dict(title=txt("diagramme.achse_dscr"), ticksuffix="x"),
    )
    return fig


def varianten_kumuliert_chart(reihen: list[tuple[str, pd.DataFrame]]) -> go.Figure:
    """Kumulierter Cashflow je Variante.

    Der Schnittpunkt mit der Nulllinie ist der Payback, der Endwert das
    Gesamtergebnis - zwei Aussagen in einem Bild, und beide in derselben
    Einheit.
    """
    fig = go.Figure()
    for i, (label, df) in enumerate(reihen):
        fig.add_scatter(
            x=df["jahr"], y=df["cf_kumuliert_eur"], mode="lines", name=label,
            line=dict(color=Colors.SERIES[i % len(Colors.SERIES)], width=2.4),
            hovertemplate=f"{label}<br>Jahr %{{x}}: %{{y:,.0f}} €<extra></extra>",
        )
    fig.add_hline(y=0, line=dict(color=Colors.INK, width=1.2))
    fig.update_layout(
        height=340, xaxis_title=txt("diagramme.achse_betriebsjahr"),
        yaxis=dict(title=txt("diagramme.achse_kumulierter_cf")),
    )
    return fig


#: Geschaetzte Groesse einer Punktbeschriftung in Achsenanteilen. Die
#: Schrift ist 11 px hoch, ein Zeichen rund 6 px breit; die Zeichenflaeche
#: misst etwa 900 x 380 px. Genauer geht es nicht: Wo der Text am Ende
#: steht, weiss erst der Browser - Plotly rechnet in Pixeln, wir hier in
#: Datenkoordinaten.
_LABEL_ZEICHENBREITE = 0.007
_LABEL_HOEHE = 0.04
#: Platz, den die GROESSTE Blase belegt - dort soll kein fremdes Label
#: liegen. Rund 46 px im Durchmesser.
_BLASE_BREITE, _BLASE_HOEHE = 0.05, 0.12
#: Kleinste Blase (sizemin=8 px) im Verhaeltnis zur groessten. Zwischen
#: beiden skaliert der Radius mit der Wurzel der Leistung - Plotly
#: bemisst die FLAECHE nach dem Wert (sizemode="area").
_BLASE_MINDESTANTEIL = 8.0 / 46.0

#: Ausweichplaetze in der Reihenfolge, in der sie probiert werden.
#: (Plotly-Position, Versatz in x, Versatz in y, Ausrichtung)
_LABEL_PLAETZE = [
    ("top center", 0.0, 1.0), ("bottom center", 0.0, -1.0),
    ("middle right", 1.0, 0.0), ("middle left", -1.0, 0.0),
    ("top right", 0.8, 0.8), ("bottom left", -0.8, -0.8),
    ("top left", -0.8, 0.8), ("bottom right", 0.8, -0.8),
]


#: Wie weit ein Label ueber die Zeichenflaeche hinausragen darf. Plotly
#: schneidet daran ab, ein wenig Ueberstand vertraegt der Rand aber.
_RAND = 0.04


def _im_bild(kasten: tuple) -> bool:
    x, y, hb, hh = kasten
    return (x - hb >= -_RAND and x + hb <= 1 + _RAND
            and y - hh >= -_RAND and y + hh <= 1 + _RAND)


def _ueberlappt(a: tuple, b: tuple) -> bool:
    """Zwei Rechtecke (x, y, halbe Breite, halbe Hoehe)."""
    return (abs(a[0] - b[0]) < a[2] + b[2]) and (abs(a[1] - b[1]) < a[3] + b[3])


def _ueberdeckung(a: tuple, b: tuple) -> float:
    """Gemeinsame Flaeche zweier Rechtecke - das Mass, nach dem der
    Notplatz gewaehlt wird, wenn gar kein freier Platz bleibt."""
    breite = min(a[0] + a[2], b[0] + b[2]) - max(a[0] - a[2], b[0] - b[2])
    hoehe = min(a[1] + a[3], b[1] + b[3]) - max(a[1] - a[3], b[1] - b[3])
    return max(breite, 0.0) * max(hoehe, 0.0)


def beschriftungsplaetze(punkte: list[dict]) -> dict[str, str]:
    """Weist jedem Punkt eine kollisionsfreie Textposition zu.

    Plotly kennt kein Ausweichen: Jede Beschriftung sitzt starr an ihrer
    Position, und bei eng beieinanderliegenden Projekten schieben sich
    die Namen uebereinander. Hier wird deshalb der Reihe nach der erste
    Platz gesucht, der weder eine andere Beschriftung noch eine fremde
    Blase trifft - und wenn keiner frei ist, bleibt der Name weg. Er
    steht ohnehin im Hover; ein unlesbarer Textklumpen hilft niemandem.

    punkte: {id, text, nx, ny} mit nx/ny als Anteil der Achsenlaenge
    (0-1), dazu optional hx/hy = halbe Ausdehnung der eigenen Blase.
    Diese Angabe ist wichtiger, als sie aussieht: Plotly setzt den Text
    unmittelbar an den Rand des MARKERS, nicht in festem Abstand zum
    Datenpunkt. Rechnet man mit einer Einheitsblase, sitzt das Label
    einer grossen Blase in Wahrheit viel hoeher als angenommen - und
    genau dort, wo das Label der kleinen Nachbarblase liegt.

    Wichtigster Punkt zuerst - er bekommt den besten Platz.

    Rueckgabe: {id: Plotly-Textposition}; "" bedeutet: nicht beschriften.
    """
    def _halb(p) -> tuple[float, float]:
        return (p.get("hx", _BLASE_BREITE / 2), p.get("hy", _BLASE_HOEHE / 2))

    blasen = [(p["nx"], p["ny"], *_halb(p)) for p in punkte]
    labels: list[tuple] = []
    plaetze: dict[str, str] = {}
    for punkt in punkte:
        if not punkt["text"]:
            plaetze[punkt["id"]] = ""
            continue
        halbe_breite = _LABEL_ZEICHENBREITE * len(punkt["text"]) / 2
        hx, hy = _halb(punkt)

        def kasten_fuer(dx, dy, hb=halbe_breite, p=punkt, hx=hx, hy=hy):
            return (
                p["nx"] + dx * (hb + hx),
                p["ny"] + dy * (_LABEL_HOEHE / 2 + hy),
                hb, _LABEL_HOEHE / 2,
            )

        # Gesucht ist ein Platz, der weder Text noch fremde Blase trifft.
        # Ein Platz auf einer fremden Blase ist der Notbehelf - dann aber
        # der am wenigsten verdeckte, sonst frisst die Nachbarblase die
        # letzten Buchstaben ("LivingBricx"). Schrift auf Schrift bleibt
        # ausgeschlossen: Sie ist gar nicht mehr lesbar. In jedem Fall
        # muss der Text INNERHALB der Zeichenflaeche bleiben - am Rand
        # schneidet Plotly ihn ab.
        gewaehlt, gewaehlter_kasten = "", None
        notbehelf = None
        for position, dx, dy in _LABEL_PLAETZE:
            kasten = kasten_fuer(dx, dy)
            if not _im_bild(kasten):
                continue
            if any(_ueberlappt(kasten, h) for h in labels):
                continue
            verdeckt = sum(_ueberdeckung(kasten, b) for b in blasen)
            if verdeckt == 0.0:
                gewaehlt, gewaehlter_kasten = position, kasten
                break
            if notbehelf is None or verdeckt < notbehelf[0]:
                notbehelf = (verdeckt, position, kasten)
        if not gewaehlt and notbehelf is not None:
            _, gewaehlt, gewaehlter_kasten = notbehelf
        if gewaehlt:
            labels.append(gewaehlter_kasten)
        plaetze[punkt["id"]] = gewaehlt
    return plaetze


#: Waehlbare x-Achsen der Landkarte: Spalte -> (Titelschluessel,
#: Hover-Format). Beide Achsen beantworten verschiedene Fragen und
#: widersprechen einander regelmaessig: Das spezifische Invest sagt, wie
#: teuer eine Kilowattstunde Leistung eingekauft wird - eine Frage der
#: Effizienz, unabhaengig von der Projektgroesse. Der Deckungsbeitrag
#: (NPV) sagt, wie viel Geld am Ende uebrig bleibt - da liegt ein grosses
#: mittelmaessiges Projekt vor einem kleinen exzellenten. Wer knappes
#: Kapital verteilt, schaut auf das erste; wer den Portfoliowert
#: maximiert, auf das zweite.
LANDKARTE_ACHSEN: dict[str, tuple[str, str]] = {
    "invest_eur_kwp": ("diagramme.achse_spezifisches_invest", "%{x:,.0f} €/kWp"),
    "npv_eur": ("diagramme.achse_deckungsbeitrag", "%{x:,.0f} €"),
}

#: Voreinstellung der x-Achse: der Deckungsbeitrag. Die erste Frage an
#: eine Pipeline ist, welches Projekt wie viel Wert schafft - das
#: spezifische Invest ordnet danach ein, wie effizient es das tut.
LANDKARTE_X_STANDARD = "npv_eur"


def portfolio_bubble_chart(
    df: pd.DataFrame,
    selected_id: str | None,
    fokus: str | None = None,
    x_feld: str = LANDKARTE_X_STANDARD,
) -> go.Figure:
    """Rendite-Risiko-Landkarte: EK-Rendite ueber einer waehlbaren
    x-Achse (spezifisches Invest oder Deckungsbeitrag, siehe
    `LANDKARTE_ACHSEN`), Blasengroesse = Anlagenleistung, Farbe =
    Anlagentyp.

    Gezeigt wird je Projekt nur die LEITVARIANTE. Die uebrigen Rechnungen
    stehen im Hover - zwoelf Blasen mit sechs Verbindungslinien waren mit
    wachsender Pipeline nicht mehr zu lesen, und die Namen ueberlagerten
    einander.

    fokus: Projektkennung, deren Varianten aufgeklappt werden. Nur dieser
    eine Standort zeigt dann alle Rechnungen samt Pfad; alle uebrigen
    treten zurueck. Das skaliert: Ob sechs oder sechzig blasse Punkte im
    Hintergrund liegen, aendert an der Lesbarkeit nichts.

    Erwartete Spalten: id, name (Beschriftung), kennung, typ, kwp,
    irr_pct, invest_eur_kwp, npv_eur, leitfall (bool), varianten
    (Hover-Text).

    Robust gegenueber einem leeren DataFrame - eine leere Figure ohne
    Fehler statt eines KeyError beim Spaltenzugriff."""
    fig = go.Figure()
    # Eine unbekannte Achse faellt auf die Voreinstellung zurueck: Der
    # Wunsch kommt aus einem Widget, und ein leerer Wert (abgewaehltes
    # Segment) darf die Karte nicht zerlegen. Fehlt die Spalte der
    # Voreinstellung - ein aelterer Aufrufer liefert sie nicht mit -,
    # gilt die naechste vorhandene.
    if x_feld not in LANDKARTE_ACHSEN or x_feld not in df.columns:
        x_feld = next(
            (feld for feld in (LANDKARTE_X_STANDARD, *LANDKARTE_ACHSEN)
             if feld in df.columns),
            LANDKARTE_X_STANDARD,
        )
    x_titel, x_hover = LANDKARTE_ACHSEN[x_feld]
    if df.empty:
        fig.update_layout(height=420)
        return fig

    im_fokus = df["kennung"] == fokus if fokus else df["kennung"].isin([])
    sichtbar = df[df["leitfall"] | im_fokus]

    # Pfad nur fuer den fokussierten Standort - eine Linie statt sechs.
    if fokus and im_fokus.sum() > 1:
        geordnet = df[im_fokus].sort_values(x_feld)
        fig.add_scatter(
            x=geordnet[x_feld], y=geordnet["irr_pct"], mode="lines",
            line=dict(color=Colors.BRAND, width=1.8),
            hoverinfo="skip", showlegend=False,
        )

    # Beschriftungen einmal ueber ALLE sichtbaren Punkte planen - die
    # Aufteilung nach Anlagentyp weiter unten ist eine Frage der Farbe,
    # nicht der Platzierung. Der groesste Punkt kommt zuerst dran.
    def _spanne(spalte):
        werte = sichtbar[spalte]
        weite = float(werte.max() - werte.min())
        return float(werte.min()), (weite or 1.0)

    x0, xw = _spanne(x_feld)
    y0, yw = _spanne("irr_pct")
    groesste = float(df["kwp"].max()) or 1.0

    def _blasenanteil(kwp: float) -> float:
        """Radius dieser Blase im Verhaeltnis zur groessten - dieselbe
        Wurzelskala, die Plotly aus sizemode="area" ableitet."""
        return max((float(kwp) / groesste) ** 0.5, _BLASE_MINDESTANTEIL)

    geplant = [
        {
            "id": z["id"],
            "text": (
                (z["variante"] if (fokus and z["kennung"] == fokus) else z["name"])
                if (not fokus) or z["kennung"] == fokus else ""
            ),
            "nx": (z[x_feld] - x0) / xw,
            "ny": (z["irr_pct"] - y0) / yw,
            "hx": _BLASE_BREITE / 2 * _blasenanteil(z["kwp"]),
            "hy": _BLASE_HOEHE / 2 * _blasenanteil(z["kwp"]),
        }
        for _, z in sichtbar.sort_values("kwp", ascending=False).iterrows()
    ]
    positionen = beschriftungsplaetze(geplant)
    texte = {p["id"]: p["text"] for p in geplant}

    for typ, farbe in [("Agri-PV", Colors.BRAND), ("Konventionell", Colors.INK_SOFT)]:
        teil = sichtbar[sichtbar["typ"] == typ]
        if teil.empty:
            continue
        gedimmt = bool(fokus)
        beschriftung, deckkraft, textfarben, textlagen = [], [], [], []
        for _, z in teil.iterrows():
            aktiv = (not gedimmt) or z["kennung"] == fokus
            lage = positionen.get(z["id"], "")
            # Ohne freien Platz bleibt der Name weg - er steht im Hover,
            # ein Textklumpen hilft niemandem.
            beschriftung.append(texte.get(z["id"], "") if lage else "")
            textlagen.append(lage or "top center")
            deckkraft.append(0.75 if aktiv else 0.18)
            textfarben.append(Colors.BRAND if (fokus and aktiv) else Colors.MUTED)
        fig.add_scatter(
            x=teil[x_feld], y=teil["irr_pct"],
            mode="markers+text", name=typ,
            text=beschriftung, textposition=textlagen,
            textfont=dict(size=11, color=textfarben),
            customdata=teil[["kwp", "kennung", "varianten"]],
            marker=dict(
                size=teil["kwp"], sizemode="area",
                sizeref=2.0 * df["kwp"].max() / (46.0**2), sizemin=8,
                color=farbe, opacity=deckkraft,
                line=dict(
                    width=[3 if pid == selected_id else 1 for pid in teil["id"]],
                    color=[
                        Colors.BRAND if pid == selected_id else Colors.PAPER
                        for pid in teil["id"]
                    ],
                ),
            ),
            hovertemplate=(
                f"<b>%{{customdata[1]}}</b><br>{x_hover} · %{{y:,.2f}} % IRR · "
                "%{customdata[0]:,.0f} kWp%{customdata[2]}<extra></extra>"
            ),
        )
    fig.update_layout(
        height=460,
        xaxis_title=txt(x_titel),
        yaxis=dict(title=txt("diagramme.achse_ek_rendite"), ticksuffix=" %"),
    )
    # Beim Deckungsbeitrag markiert die Null die Schwelle, ab der ein
    # Projekt seine Kapitalkosten verdient - links davon vernichtet es
    # Wert. Beim spezifischen Invest gibt es keine solche Grenze.
    if x_feld == "npv_eur" and float(sichtbar[x_feld].min()) < 0:
        fig.add_vline(x=0, line=dict(color=Colors.NEGATIVE, width=1.2,
                                     dash="dot"))
    return fig


def portfolio_rangliste_chart(
    zeilen: list[dict], ziel_pct: float, selected_id: str | None = None
) -> go.Figure:
    """Eine Zeile je Projekt, nach Rendite sortiert.

    Der Ausweg aus dem Beschriftungsproblem: Die Namen stehen in der
    Achse und koennen sich nicht ueberlagern - auch bei vierzig
    Projekten nicht. Die Varianten liegen als offene Punkte auf
    derselben Zeile, verbunden durch die Spanne.

    zeilen: je Projekt {label, kennung, leit_irr, leit_id, varianten:
    [(variantenname, irr)]}.
    """
    fig = go.Figure()
    if not zeilen:
        fig.update_layout(height=220)
        return fig

    geordnet = sorted(zeilen, key=lambda z: z["leit_irr"] or 0)
    y = [z["label"] for z in geordnet]

    for i, z in enumerate(geordnet):
        werte = [irr for _, irr in z["varianten"] if irr is not None]
        if len(werte) > 1:
            fig.add_scatter(
                x=[min(werte), max(werte)], y=[y[i], y[i]], mode="lines",
                line=dict(color=Colors.SOFT, width=5),
                hoverinfo="skip", showlegend=False,
            )
    neben = [
        (z["label"], name, irr)
        for z in geordnet for name, irr in z["varianten"]
        if irr is not None and irr != z["leit_irr"]
    ]
    if neben:
        fig.add_scatter(
            x=[irr for _, _, irr in neben], y=[label for label, _, _ in neben],
            mode="markers", name="Varianten",
            marker=dict(size=9, color=Colors.PAPER,
                        line=dict(color=Colors.BRAND, width=1.6)),
            customdata=[name for _, name, _ in neben],
            hovertemplate="%{customdata}: %{x:,.2f} %<extra></extra>",
        )
    fig.add_scatter(
        x=[z["leit_irr"] for z in geordnet], y=y, mode="markers+text",
        name="Leitvariante",
        marker=dict(
            size=15, color=Colors.BRAND,
            line=dict(
                width=[3 if z["leit_id"] == selected_id else 0 for z in geordnet],
                color=Colors.INK,
            ),
        ),
        text=[f"{(z['leit_irr'] or 0):,.2f} %".replace(".", ",") for z in geordnet],
        textposition="middle right", textfont=dict(size=11, color=Colors.INK),
        customdata=[z["kennung"] for z in geordnet],
        hovertemplate="<b>%{customdata}</b>: %{x:,.2f} % IRR<extra></extra>",
    )
    fig.add_vline(
        x=ziel_pct * 100, line=dict(color=Colors.BRAND, width=1.2, dash="dash"),
        annotation_text=f"Ziel {ziel_pct * 100:,.1f} %".replace(".", ","),
        annotation_position="top", annotation_font=dict(size=10, color=Colors.BRAND),
    )
    fig.update_layout(
        height=max(240, 70 + 46 * len(geordnet)),
        xaxis=dict(title="EK-Rendite", ticksuffix=" %"),
        # Reihenfolge explizit setzen: Plotly ordnet Kategorien sonst nach
        # ihrem ERSTEN Auftreten - und das sind die Spannenbalken, die es
        # nur bei Projekten mit mehreren Varianten gibt. Die Rangfolge
        # waere damit keine.
        yaxis=dict(title="", type="category", categoryorder="array",
                   categoryarray=y),
        showlegend=False,
        margin=dict(r=70),
    )
    return fig


def auktion_historie_chart(df: pd.DataFrame) -> go.Figure:
    """Historische Ausschreibungsergebnisse: Preisobergrenze, Min/Mittel/
    Max der Zuschlagswerte (linke Achse) und Bezuschlagungsquote (rechts).
    Unterzeichnete Runden sind grau hinterlegt."""
    fig = go.Figure()
    x = df["datum"]
    fig.add_scatter(x=x, y=df["preisobergrenze_ct"], name=txt("diagramme.serie_preisobergrenze"),
                    mode="lines", line=dict(color=Colors.BRAND, dash="dot", width=2),
                    hovertemplate="%{y:,.2f} ct/kWh<extra>Obergrenze</extra>")
    fig.add_scatter(x=x, y=df["zuschlag_max_ct"], name=txt("diagramme.serie_hoechster_zuschlag"),
                    mode="lines+markers", line=dict(color=Colors.INK, width=2),
                    hovertemplate="%{y:,.2f} ct/kWh<extra>Max</extra>")
    fig.add_scatter(x=x, y=df["zuschlag_mittel_ct"], name=txt("diagramme.serie_mittlerer_zuschlag"),
                    mode="lines+markers", line=dict(color=Colors.INK_SOFT, width=2),
                    hovertemplate="%{y:,.2f} ct/kWh<extra>Mittel</extra>")
    fig.add_scatter(x=x, y=df["zuschlag_min_ct"], name=txt("diagramme.serie_niedrigster_zuschlag"),
                    mode="lines+markers", line=dict(color=Colors.SOFT, width=1.5),
                    hovertemplate="%{y:,.2f} ct/kWh<extra>Min</extra>")
    quote = df["bezuschlagt_mw"] / df["ausgeschrieben_mw"] * 100
    fig.add_bar(x=x, y=quote, name=txt("diagramme.serie_bezuschlagungsquote"), yaxis="y2",
                marker_color=mit_alpha(Colors.SOFT, 0.55),
                hovertemplate="%{y:,.0f} %<extra>Bezuschlagungsquote</extra>")
    fig.update_layout(
        height=460, hovermode="x unified",
        yaxis=dict(title="ct/kWh"),
        yaxis2=dict(title="Bezuschlagt (%)", overlaying="y", side="right",
                    range=[0, 210], showgrid=False),
    )
    return fig


def gebotsdichte_chart(prognose, empfohlen_ct: float | None = None) -> go.Figure:
    """Geschätzte Verteilung der nächsten Runde. Gefüllt: Dichte der
    ZUSCHLAGSWERTE (erfolgreiche Gebote, am Grenzzuschlag der zentralen
    Prognosewelt abgeschnitten) - höchste Dichte knapp unter dem
    Grenzzuschlag, steiler Abfall nach rechts, langsamer linker
    Auslauf. Gestrichelt: Dichte aller Gebote (inkl. nicht
    bezuschlagter). Graues Band: P10-P90 des Grenzzuschlags."""
    import numpy as np

    fig = go.Figure()
    fig.add_vrect(
        x0=float(np.percentile(prognose.pm_sample, 10)),
        x1=float(np.percentile(prognose.pm_sample, 90)),
        fillcolor=mit_alpha(Colors.SOFT, 0.30), line_width=0,
        annotation_text=txt("diagramme.annotation_grenzzuschlag_p10_p90"),
        annotation_position="top left",
        annotation_font=dict(size=10, color=Colors.MUTED),
    )
    fig.add_scatter(
        x=prognose.dichte_x, y=prognose.dichte_y, mode="lines",
        line=dict(color=Colors.MUTED, width=1.5, dash="dot"),
        name=txt("diagramme.serie_alle_gebote"),
        hovertemplate="%{x:,.2f} ct/kWh<extra>Alle Gebote</extra>",
    )
    fig.add_scatter(
        x=prognose.dichte_x, y=prognose.dichte_zuschlag_y, mode="lines",
        line=dict(color=Colors.INK, width=2.2), fill="tozeroy",
        fillcolor=mit_alpha(Colors.INK, 0.14), name=txt("diagramme.serie_zuschlagswerte"),
        hovertemplate="%{x:,.2f} ct/kWh<extra>Zuschlagswerte</extra>",
    )
    fig.add_vline(x=prognose.preisobergrenze_ct, line_color=Colors.BRAND,
                  line_width=2, annotation_text=txt("diagramme.serie_preisobergrenze"),
                  annotation_font_color=Colors.BRAND)
    fig.add_vline(x=prognose.gebot_mittel_ct, line_dash="dash",
                  line_color=Colors.INK_SOFT, annotation_text=txt("diagramme.annotation_erwartungswert"),
                  annotation_position="top left")
    fig.add_vline(x=prognose.gebot_median_ct, line_dash="dot",
                  line_color=Colors.MUTED, annotation_text=txt("diagramme.annotation_median"),
                  annotation_position="bottom left")
    for q in (5, 95):
        fig.add_vline(x=prognose.gebot_quantile[q], line_dash="dot",
                      line_color=Colors.LINE)
    if empfohlen_ct is not None:
        fig.add_vline(x=empfohlen_ct, line_color=Colors.BRAND, line_width=2,
                      annotation_text=txt("diagramme.annotation_empfohlenes_gebot"),
                      annotation_font_color=Colors.BRAND,
                      annotation_position="bottom right")
    fig.update_layout(height=420, xaxis_title=txt("diagramme.achse_gebotswert"),
                      yaxis_title=txt("diagramme.achse_wahrscheinlichkeitsdichte"),
                      legend=dict(orientation="h", y=1.08))
    return fig


def zuschlagskurve_chart(prognose, ziel_prob: float, empfohlen_ct: float) -> go.Figure:
    """Zuschlagswahrscheinlichkeit in Abhängigkeit vom eigenen Gebot
    (Survival-Funktion des prognostizierten Grenzzuschlags) mit dem
    gewählten Arbeitspunkt."""
    import numpy as np

    x = np.linspace(0.4 * prognose.preisobergrenze_ct,
                    prognose.preisobergrenze_ct, 250)
    y = [prognose.zuschlagswahrscheinlichkeit(b) * 100 for b in x]
    fig = go.Figure()
    fig.add_scatter(x=x, y=y, mode="lines", line=dict(color=Colors.INK, width=2.5),
                    hovertemplate="Gebot %{x:,.2f} ct/kWh → %{y:,.0f} %<extra></extra>")
    fig.add_scatter(x=[empfohlen_ct], y=[ziel_prob * 100], mode="markers",
                    marker=dict(color=Colors.BRAND, size=12,
                                line=dict(color="white", width=2)),
                    name=txt("diagramme.serie_arbeitspunkt"), showlegend=False,
                    hovertemplate="Empfehlung %{x:,.2f} ct/kWh bei %{y:,.0f} %<extra></extra>")
    fig.add_hline(y=ziel_prob * 100, line_dash="dot", line_color=Colors.MUTED)
    fig.add_vline(x=empfohlen_ct, line_dash="dot", line_color=Colors.MUTED)
    fig.update_layout(height=420, xaxis_title=txt("diagramme.achse_eigenes_gebot"),
                      yaxis=dict(title="Zuschlagswahrscheinlichkeit",
                                 ticksuffix=" %", range=[0, 104]))
    return fig


def auktion_historische_verteilungen_chart(modell, art: str = "dichte") -> go.Figure:
    """Geschätzte Gebotsverteilungen aller historischen Runden (Parameter
    je Runde aus min/Ø/max kalibriert, da Einzelgebote nicht
    veröffentlicht werden). art: 'dichte' oder 'verteilungsfunktion'.
    Farbverlauf alt (grau) -> neu (rot); unterzeichnete Runden
    gestrichelt."""
    import numpy as np

    def _mix(c1: str, c2: str, t: float) -> str:
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#" + "".join(f"{round(a[i] + (b[i] - a[i]) * t):02x}" for i in range(3))

    fits = sorted(modell.fits, key=lambda f: f.ausschreibung.datum)
    familie = modell.familie
    fig = go.Figure()
    for i, f in enumerate(fits):
        cap = f.ausschreibung.preisobergrenze_ct
        x = np.linspace(0.02 * cap, cap * (1 - 1e-4), 300)
        d = familie.dist(f.mu_rel, f.kappa, cap)
        y = d.pdf(x) if art == "dichte" else d.cdf(x)
        farbe = _mix(Colors.SOFT, Colors.INK, i / max(len(fits) - 1, 1))
        fig.add_scatter(
            x=x, y=y, mode="lines", name=f.ausschreibung.datum.strftime("%m/%Y")
            + (" (unterz.)" if f.ausschreibung.unterzeichnet else ""),
            line=dict(color=farbe, width=2,
                      dash="dot" if f.ausschreibung.unterzeichnet else "solid"),
            hovertemplate="%{x:,.2f} ct/kWh<extra>"
            + f.ausschreibung.datum.strftime("%m/%Y") + "</extra>",
        )
    fig.update_layout(
        height=440, xaxis_title=txt("diagramme.achse_gebotswert"),
        yaxis_title=("Wahrscheinlichkeitsdichte" if art == "dichte"
                     else "F(Gebot) – kumulierte Wahrscheinlichkeit"),
        legend=dict(font=dict(size=10)),
    )
    return fig
