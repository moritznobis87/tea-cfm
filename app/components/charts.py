"""
Alle Plotly-Diagramme der App als reine Builder-Funktionen
(DataFrame rein, Figure raus - kein Streamlit-Import).

Vorteile dieser Trennung:
- Views bleiben schlank und lesbar,
- jedes Diagramm ist isoliert testbar,
- Farb- und Formatentscheidungen kommen zentral aus app.theme.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from app.formatting import fmt_pct
from app.theme import Colors
from texte import txt

_EUR_HOVER = "%{y:,.0f} €"


def _signed_colors(values: pd.Series) -> list[str]:
    """Gruen fuer Zufluesse, Rot fuer Abfluesse - einheitlich in allen
    Cashflow-Darstellungen."""
    return [Colors.POSITIVE if v >= 0 else Colors.NEGATIVE for v in values]


def revenue_chart(df: pd.DataFrame) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(
        x=df["jahr"], y=df["erloes_eur"], name=txt("diagramme.serie_umsatzerloese"),
        marker_color=Colors.POSITIVE, hovertemplate=_EUR_HOVER + "<extra></extra>",
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
        marker_color=Colors.NEGATIVE, hovertemplate=_EUR_HOVER + "<extra></extra>",
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
        marker_color=Colors.POSITIVE, hovertemplate=_EUR_HOVER + "<extra></extra>",
    )
    fig.add_bar(
        x=df["jahr"], y=-df["tilgung_eur"], name=txt("diagramme.serie_tilgung"),
        marker_color=Colors.NEUTRAL, hovertemplate=_EUR_HOVER + "<extra></extra>",
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
    fig = go.Figure()
    fig.add_bar(
        x=dscr_df["jahr"], y=dscr_df["dscr"], name="DSCR",
        marker_color=[
            Colors.NEGATIVE if v < 1.0 else Colors.POSITIVE for v in dscr_df["dscr"]
        ],
        hovertemplate="%{y:,.2f}x<extra></extra>",
    )
    fig.add_hline(
        y=1.0, line_dash="dot", line_color="gray",
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
            x=equity_irr * 100, line_dash="dot", line_color=Colors.POSITIVE,
            annotation_text="IRR",
        )
    fig.update_layout(
        xaxis_title=txt("diagramme.achse_diskontsatz_pct"), yaxis_title=txt("diagramme.achse_npv_eur"), height=420
    )
    return fig


def eag_sensitivity_chart(sens_df: pd.DataFrame) -> go.Figure:
    """IRR ueber dem variierten EAG-Zuschlagswert (±10 %/±5 %/Basis).

    Defensiv: einzelne Varianten koennen eine nicht berechenbare IRR
    (None) liefern, wenn der Cashflow keinen Vorzeichenwechsel mehr hat
    (z.B. durchgehend negativ bei einem -10%-Downside).
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
            Colors.POSITIVE if v == "Basis" else Colors.NEUTRAL for v in varianten
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
            increasing=dict(marker_color=Colors.POSITIVE),
            decreasing=dict(marker_color=Colors.NEGATIVE),
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


def verguetung_chart(
    df: pd.DataFrame, eag_zuschlag_ct: float, foerderdauer_jahre: int
) -> go.Figure:
    """Vergütungssatz vs. nominaler Marktwert über die Laufzeit. Die Fläche
    zwischen den Kurven ist die Marktprämie; die gestrichelte Linie zeigt
    den nominal fixen EAG-Zuschlagswert, die Markierung das Förderende."""
    betrieb = df[df["jahr"] >= 1]
    fig = go.Figure()
    fig.add_scatter(
        x=betrieb["jahr"], y=betrieb["marktwert_nominal_ct_kwh"],
        name="Marktwert Solar (nominal)", mode="lines",
        line=dict(color=Colors.NEUTRAL, width=2),
        hovertemplate="%{y:,.2f} ct/kWh<extra>Marktwert nominal</extra>",
    )
    fig.add_scatter(
        x=betrieb["jahr"], y=betrieb["verguetungssatz_ct_kwh"],
        name=txt("diagramme.serie_verguetungssatz"), mode="lines",
        line=dict(color=Colors.INK, width=2.5),
        fill="tonexty", fillcolor="rgba(138, 151, 166, 0.25)",
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
    """Erlöse aufgeteilt in Markterlös (Verkauf zum Marktwert) und
    Marktprämie (EAG-Zuschuss) - zeigt, wie lange das Projekt am
    Fördertropf hängt und wann der Markt trägt."""
    betrieb = df[df["jahr"] >= 1]
    fig = go.Figure()
    fig.add_bar(
        x=betrieb["jahr"], y=betrieb["erloes_markt_eur"], name=txt("diagramme.serie_markterloes"),
        marker_color=Colors.POSITIVE,
        hovertemplate=_EUR_HOVER + f"<extra>{txt('diagramme.serie_markterloes')}</extra>",
    )
    fig.add_bar(
        x=betrieb["jahr"], y=betrieb["erloes_praemie_eur"], name=txt("diagramme.serie_marktpraemie") + " (EAG)",
        marker_color=Colors.NEUTRAL,
        hovertemplate=_EUR_HOVER + f"<extra>{txt('diagramme.serie_marktpraemie')}</extra>",
    )
    fig.update_layout(
        barmode="stack", height=400, xaxis_title=txt("diagramme.achse_betriebsjahr"), yaxis_title="€",
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
        fill="tozeroy", fillcolor="rgba(20, 48, 79, 0.10)",
        hovertemplate=_EUR_HOVER + "<extra>Restschuld</extra>",
    )
    fig.add_bar(
        x=betrieb["jahr"], y=betrieb["zinsen_eur"], name=txt("diagramme.serie_zinsen"),
        marker_color=Colors.BRAND,
        hovertemplate=_EUR_HOVER + "<extra>Zinsen</extra>",
    )
    fig.add_bar(
        x=betrieb["jahr"], y=betrieb["tilgung_eur"], name=txt("diagramme.serie_tilgung"),
        marker_color=Colors.NEUTRAL,
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
            marker=dict(colors=Colors.SERIES + Colors.OPEX_SCALE),
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
            marker=dict(colors=[Colors.INK, Colors.NEUTRAL]),
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
            orientation="h", marker_color=Colors.NEGATIVE, width=0.55,
            hovertemplate=f"−10 %: {runter:,.2f} % IRR<extra>{zeile['name']}</extra>".replace(",", "X").replace(".", ",").replace("X", "."),
            showlegend=False,
        )
        fig.add_bar(
            y=[zeile["name"]], x=[rauf - basis_pct], base=basis_pct,
            orientation="h", marker_color=Colors.POSITIVE, width=0.55,
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
        marker=dict(color=Colors.NEUTRAL, line=dict(color=Colors.PAPER, width=1)),
        hovertemplate="%{x} %: %{y} " + txt("diagramme.achse_anzahl_laeufe") + "<extra></extra>",
    )
    for wert, name, farbe in [
        (p10, "P10", Colors.NEGATIVE),
        (p50, "P50", Colors.INK),
        (p90, "P90", Colors.POSITIVE),
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
        fill="tonexty", fillcolor="rgba(20, 48, 79, 0.10)",
        name="P10–P90", hovertemplate=_EUR_HOVER + "<extra>P10</extra>",
    )
    # Inneres Band (P25-P75)
    fig.add_scatter(
        x=jahre, y=mc.kum_p75, mode="lines", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    )
    fig.add_scatter(
        x=jahre, y=mc.kum_p25, mode="lines", line=dict(width=0),
        fill="tonexty", fillcolor="rgba(20, 48, 79, 0.22)",
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
        marker_color=[Colors.SERIES[i % len(Colors.SERIES)] for i in range(len(kennzahlen))],
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
            line=dict(color=Colors.SERIES[i % len(Colors.SERIES)], width=2),
            hovertemplate=_EUR_HOVER + f"<extra>{spalte}</extra>",
        )
    fig.add_hline(y=0, line_dash="dot", line_color=Colors.MUTED)
    fig.update_layout(
        height=400, xaxis_title=txt("diagramme.achse_jahr_kurz"), yaxis_title=txt("diagramme.achse_kumulierter_cf"),
        hovermode="x unified",
    )
    return fig


def portfolio_bubble_chart(df: pd.DataFrame, selected_id: str | None) -> go.Figure:
    """Rendite-Risiko-Landkarte des Portfolios: spezifisches Invest
    (€/kWp) gegen EK-Rendite, Blasengröße = Anlagenleistung, Farbe =
    Anlagentyp. Das ausgewählte Projekt ist rot umrandet.

    Robust gegenueber einem leeren DataFrame (z.B. wenn alle Projekte
    ueber den Inaktiv-Filter ausgeblendet sind) - eine leere Figure
    ohne Fehler statt eines KeyError beim Spaltenzugriff."""
    fig = go.Figure()
    if df.empty:
        fig.update_layout(height=420)
        return fig
    for typ, farbe in [("Agri-PV", Colors.POSITIVE), ("Konventionell", Colors.NEUTRAL)]:
        teil = df[df["typ"] == typ]
        if teil.empty:
            continue
        fig.add_scatter(
            x=teil["invest_eur_kwp"], y=teil["irr_pct"],
            mode="markers+text", name=typ,
            text=teil["name"], textposition="top center",
            textfont=dict(size=11, color=Colors.MUTED),
            marker=dict(
                size=teil["kwp"], sizemode="area",
                sizeref=2.0 * df["kwp"].max() / (46.0**2), sizemin=8,
                color=farbe, opacity=0.75,
                line=dict(
                    width=[3 if pid == selected_id else 1 for pid in teil["id"]],
                    color=[
                        Colors.BRAND if pid == selected_id else Colors.PAPER
                        for pid in teil["id"]
                    ],
                ),
            ),
            customdata=teil[["kwp"]],
            hovertemplate=(
                "%{text}<br>%{x:,.0f} €/kWp · %{y:,.2f} % IRR · "
                "%{customdata[0]:,.0f} kWp<extra></extra>"
            ),
        )
    fig.update_layout(
        height=460,
        xaxis_title="Spezifisches Invest (€/kWp)",
        yaxis=dict(title="EK-Rendite", ticksuffix=" %"),
    )
    return fig


def portfolio_ranking_chart(df: pd.DataFrame, selected_id: str | None) -> go.Figure:
    """Projekt-Ranking nach EK-Rendite (horizontal, aufsteigend sortiert)."""
    sortiert = df.sort_values("irr_pct", ascending=True)
    farben = [
        Colors.BRAND if pid == selected_id else Colors.INK_SOFT
        for pid in sortiert["id"]
    ]
    fig = go.Figure(
        go.Bar(
            x=sortiert["irr_pct"], y=sortiert["name"], orientation="h",
            marker_color=farben,
            text=[f"{v:,.2f} %".replace(".", ",") for v in sortiert["irr_pct"]],
            textposition="outside",
            hovertemplate="%{y}: %{x:,.2f} % IRR<extra></extra>",
        )
    )
    fig.update_layout(
        height=max(220, 60 + 42 * len(sortiert)),
        xaxis=dict(title="EK-Rendite", ticksuffix=" %"),
        yaxis_title="", showlegend=False,
    )
    return fig


# ===========================================================================
# Ausschreibungssimulation (EAG-Gebotsmodell)
# ===========================================================================


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
                    mode="lines+markers", line=dict(color=Colors.NEUTRAL, width=1.5),
                    hovertemplate="%{y:,.2f} ct/kWh<extra>Min</extra>")
    quote = df["bezuschlagt_mw"] / df["ausgeschrieben_mw"] * 100
    fig.add_bar(x=x, y=quote, name=txt("diagramme.serie_bezuschlagungsquote"), yaxis="y2",
                marker_color="rgba(138, 151, 166, 0.35)",
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
        fillcolor="rgba(138, 151, 166, 0.16)", line_width=0,
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
        fillcolor="rgba(20, 48, 79, 0.14)", name=txt("diagramme.serie_zuschlagswerte"),
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
        fig.add_vline(x=empfohlen_ct, line_color=Colors.POSITIVE, line_width=2,
                      annotation_text=txt("diagramme.annotation_empfohlenes_gebot"),
                      annotation_font_color=Colors.POSITIVE,
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
        farbe = _mix(Colors.NEUTRAL, Colors.BRAND, i / max(len(fits) - 1, 1))
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
