"""
Tests der erweiterten Analytik (engine/analytics.py) und der
Erloes-Aufteilung in Markterloes und Marktpraemie.

Nutzt die deterministischen Fixtures aus conftest.py (flaches Szenario,
handrechenbare Werte).
"""

from __future__ import annotations

import numpy as np
import pytest

from engine import (
    break_even_zuschlag,
    calculate_lcoe,
    run_irr_heatmap,
    run_monte_carlo,
    run_scenario_comparison,
    run_tornado,
    run_valuation,
)


class TestErloesSplit:
    def test_markt_plus_praemie_ergibt_gesamterloes(self, project, global_assumptions):
        df = run_valuation(project, global_assumptions).cashflow.data
        summe = df["erloes_markt_eur"] + df["erloes_praemie_eur"]
        assert np.allclose(summe, df["erloes_eur"])

    def test_praemie_nach_foerderdauer_null(self, project, global_assumptions):
        df = run_valuation(project, global_assumptions).cashflow.data
        nach_foerderung = df[df["jahr"] > global_assumptions.eag_foerderdauer_jahre]
        assert (nach_foerderung["erloes_praemie_eur"] == 0).all()

    def test_produktion_in_cashflow(self, project, global_assumptions):
        df = run_valuation(project, global_assumptions).cashflow.data
        assert float(df.loc[df["jahr"] == 0, "produktion_kwh"].iloc[0]) == 0.0
        assert (df.loc[df["jahr"] >= 1, "produktion_kwh"] > 0).all()


class TestTornado:
    def test_liefert_alle_treiber_sortiert(self, project, global_assumptions):
        df = run_tornado(project, global_assumptions)
        assert len(df) == 7
        # Aufsteigend nach Spanne sortiert.
        assert df["spanne"].is_monotonic_increasing
        # Basis-IRR ueberall identisch.
        assert df["irr_basis"].nunique() == 1

    def test_eag_rauf_verbessert_irr(self, project, global_assumptions):
        df = run_tornado(project, global_assumptions)
        zeile = df[df["treiber"] == "eag_zuschlag"].iloc[0]
        assert zeile["irr_rauf"] > zeile["irr_basis"] > zeile["irr_runter"]

    def test_capex_rauf_verschlechtert_irr(self, project, global_assumptions):
        df = run_tornado(project, global_assumptions)
        zeile = df[df["treiber"] == "capex"].iloc[0]
        assert zeile["irr_rauf"] < zeile["irr_basis"] < zeile["irr_runter"]


class TestHeatmap:
    def test_raster_vollstaendig(self, project, global_assumptions):
        grid = run_irr_heatmap(
            project, global_assumptions, "eag_zuschlag", "capex", stufen=3
        )
        assert len(grid) == 9
        assert grid["equity_irr"].notna().all()

    def test_gleiche_achsen_verboten(self, project, global_assumptions):
        with pytest.raises(ValueError):
            run_irr_heatmap(project, global_assumptions, "capex", "capex")


class TestMonteCarlo:
    def test_reproduzierbar_mit_seed(self, project, global_assumptions):
        mc1 = run_monte_carlo(project, global_assumptions, n_laeufe=20, seed=7)
        mc2 = run_monte_carlo(project, global_assumptions, n_laeufe=20, seed=7)
        assert np.allclose(mc1.irr, mc2.irr, equal_nan=True)
        assert np.allclose(mc1.npv, mc2.npv)

    def test_sigma_null_ergibt_basis(self, project, global_assumptions):
        basis_irr = run_valuation(project, global_assumptions).kpis.equity_irr
        mc = run_monte_carlo(
            project, global_assumptions, n_laeufe=5,
            sigmas={"produktion": 0.0, "capex": 0.0},
        )
        assert np.allclose(mc.irr, basis_irr)

    def test_bandbreiten_geordnet(self, project, global_assumptions):
        mc = run_monte_carlo(project, global_assumptions, n_laeufe=50)
        assert (mc.kum_p10 <= mc.kum_p50 + 1e-6).all()
        assert (mc.kum_p50 <= mc.kum_p90 + 1e-6).all()

    def test_erfolgswahrscheinlichkeit_grenzen(self, project, global_assumptions):
        mc = run_monte_carlo(project, global_assumptions, n_laeufe=30)
        assert mc.wahrscheinlichkeit_irr_ueber(-0.99) == pytest.approx(1.0)
        assert mc.wahrscheinlichkeit_irr_ueber(5.0) == pytest.approx(0.0)


class TestBreakEven:
    def test_break_even_erreicht_ziel_irr(self, project, global_assumptions):
        basis_irr = run_valuation(project, global_assumptions).kpis.equity_irr
        # Ziel oberhalb der Basis-IRR -> Break-even muss ueber dem
        # aktuellen Zuschlag liegen und das Ziel (nahezu) exakt treffen.
        ziel = basis_irr + 0.02
        gebot = break_even_zuschlag(project, global_assumptions, ziel)
        assert gebot is not None and gebot > project.eag_zuschlagswert_ct_kwh

        variante = project.model_copy(deep=True)
        variante.eag_zuschlagswert_ct_kwh = gebot
        irr = run_valuation(variante, global_assumptions).kpis.equity_irr
        assert irr == pytest.approx(ziel, abs=0.002)

    def test_unerreichbares_ziel_gibt_none(self, project, global_assumptions):
        assert break_even_zuschlag(project, global_assumptions, 5.0) is None

    def test_bereits_erreichtes_ziel_gibt_untergrenze(
        self, project, global_assumptions
    ):
        assert break_even_zuschlag(project, global_assumptions, -0.5) == 0.5


class TestLcoeUndSzenarien:
    def test_lcoe_plausibel(self, project, global_assumptions):
        df = run_valuation(project, global_assumptions).cashflow.data
        lcoe = calculate_lcoe(df, 0.05)
        assert lcoe is not None and 0 < lcoe < 50

    def test_lcoe_steigt_mit_diskontsatz(self, project, global_assumptions):
        # CAPEX faellt frueh an, Energie kommt spaeter - hoeherer
        # Diskontsatz entwertet die Energie staerker als die Kosten.
        df = run_valuation(project, global_assumptions).cashflow.data
        assert calculate_lcoe(df, 0.08) > calculate_lcoe(df, 0.02)

    def test_szenarienvergleich_je_szenario_eine_zeile(
        self, project, global_assumptions
    ):
        vergleich = run_scenario_comparison(project, global_assumptions)
        assert len(vergleich.kennzahlen) == len(
            global_assumptions.marktpreisszenarien
        )
        assert set(vergleich.kum_cashflows.columns) == {"jahr"} | {
            s.name for s in global_assumptions.marktpreisszenarien
        }
