"""Tests fuer die UI-nahen, aber Streamlit-freien Hilfsfunktionen."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.formatting import (  # noqa: E402
    fmt_ct_kwh,
    fmt_dscr,
    fmt_eur,
    fmt_number,
    fmt_pct,
)
from app.services import make_project_id  # noqa: E402


class TestFormatting:
    def test_deutsche_tausender_und_dezimaltrennung(self):
        assert fmt_number(1234567.891, 2) == "1.234.567,89"
        assert fmt_eur(1234567) == "1.234.567 €"

    def test_prozent_aus_anteil(self):
        assert fmt_pct(0.0743) == "7,43 %"
        assert fmt_pct(0.2, 0) == "20 %"

    def test_none_wird_zu_na(self):
        assert fmt_pct(None) == "n/a"
        assert fmt_eur(None) == "n/a"
        assert fmt_dscr(None) == "n/a"

    def test_einheiten(self):
        assert fmt_ct_kwh(7.2) == "7,20 ct/kWh"
        assert fmt_dscr(1.254) == "1,25x"


class TestProjectId:
    def test_umlaute_und_sonderzeichen(self):
        assert (
            make_project_id("Sonnenfeld Süd (Bauabschnitt 2)", set())
            == "sonnenfeld-sued-bauabschnitt-2"
        )

    def test_kollision_erhaelt_laufnummer(self):
        existing = {"sonnenfeld", "sonnenfeld-2"}
        assert make_project_id("Sonnenfeld", existing) == "sonnenfeld-3"

    def test_leerer_name_faellt_auf_default(self):
        assert make_project_id("!!!", set()) == "projekt"


class TestEquityWaterfallHover:
    """Regressionstest fuer das Hover-Verhalten des Wasserfalldiagramms:
    Bei Plotly-Waterfall-Traces liefert %{y} die kumulierte Endposition
    des Balkens auf der Y-Achse - angezeigt werden muss aber die Hoehe
    des Balkens selbst (%{delta}, vorzeichenbehaftet, in Euro)."""

    def _figure(self, project, global_assumptions):
        from app.components.charts import equity_waterfall_chart
        from engine import run_valuation

        result = run_valuation(project, global_assumptions)
        return equity_waterfall_chart(result.cashflow.data)

    def test_hover_zeigt_balkenhoehe_statt_achsenwert(
        self, project, global_assumptions
    ):
        fig = self._figure(project, global_assumptions)
        trace = fig.data[0]
        assert trace.type == "waterfall"
        assert "%{delta" in trace.hovertemplate
        assert "%{y" not in trace.hovertemplate
        assert "€" in trace.hovertemplate

    def test_balkenhoehen_bleiben_fachlich_korrekt(
        self, project, global_assumptions
    ):
        """Die y-Eingabewerte des Traces (= die Deltas, aus denen Plotly
        die Balken aufbaut) sind unveraendert: Erloese positiv, Kosten-
        positionen negativ, Totals als 0 markiert."""
        from engine import run_valuation

        result = run_valuation(project, global_assumptions)
        df = result.cashflow.data
        fig = self._figure(project, global_assumptions)
        trace = fig.data[0]
        y = list(trace.y)
        assert y[0] == pytest.approx(float(df["erloes_eur"].sum()))
        assert y[1] == pytest.approx(-float(df["opex_gesamt_eur"].sum()))
        assert y[4] == 0 and y[8] == 0  # Totals berechnet Plotly selbst
        assert list(trace.measure).count("total") == 2
