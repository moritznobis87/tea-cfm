"""Tests fuer die EAG-Marktpraemienlogik (gleitende Marktpraemie)."""

from __future__ import annotations

from datetime import date

import pytest

from engine.energy import calculate_energy_production
from engine.pipeline import resolve_assumptions
from engine.revenue import calculate_revenue
from engine.timeline import build_timeline


def _revenue_fuer(project, global_assumptions, jahre: int = 25):
    assumptions = resolve_assumptions(project, global_assumptions)
    timeline = build_timeline(date(project.inbetriebnahme_jahr, 1, 1), jahre)
    energy = calculate_energy_production(timeline, assumptions)
    return calculate_revenue(timeline, energy, assumptions)


class TestEagMarktpraemie:
    def test_foerderdauer_zahlt_max_aus_marktwert_und_zuschlag(
        self, project, global_assumptions
    ):
        """Marktwert 4 ct < Zuschlag 7 ct -> waehrend der Foerderdauer gilt
        der Zuschlagswert, danach der Marktwert."""
        revenue = _revenue_fuer(project, global_assumptions)
        innerhalb = revenue[revenue["jahr"] <= 20]
        danach = revenue[revenue["jahr"] > 20]
        assert innerhalb["verguetungssatz_ct_kwh"].tolist() == pytest.approx([7.0] * 20)
        assert danach["verguetungssatz_ct_kwh"].tolist() == pytest.approx([4.0] * 5)

    def test_marktwert_ueber_zuschlag_zahlt_marktwert(
        self, project, global_assumptions
    ):
        project.eag_zuschlagswert_ct_kwh = 3.0  # unter dem Marktwert von 4 ct
        revenue = _revenue_fuer(project, global_assumptions)
        assert revenue["verguetungssatz_ct_kwh"].tolist() == pytest.approx([4.0] * 25)

    def test_konventionell_erhaelt_25_prozent_abschlag(
        self, project, global_assumptions
    ):
        from engine import AnlagenTyp

        project.anlagentyp = AnlagenTyp.KONVENTIONELL
        assert project.eag_zuschlagswert_effektiv_ct_kwh == pytest.approx(7.0 * 0.75)

    def test_negative_stunden_reduzieren_verguetete_menge(
        self, project, global_assumptions
    ):
        # 10 % negative Stunden in jedem Jahr -> 10 % weniger Erloes.
        szenario = global_assumptions.marktpreisszenarien[0]
        for jahr in szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr:
            szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr[jahr] = 0.10
            szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[jahr] = 0.10
        revenue = _revenue_fuer(project, global_assumptions)
        # Jahr 1: 1 GWh * 90 % * 7 ct = 63.000 €.
        assert revenue["erloes_eur"].iloc[0] == pytest.approx(63_000.0)

    def test_gewichtung_null_blendet_negative_stunden_aus(
        self, project, global_assumptions
    ):
        szenario = global_assumptions.marktpreisszenarien[0]
        for jahr in szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr:
            szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr[jahr] = 0.10
            szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[jahr] = 0.10
        global_assumptions.negative_stunden_gewichtung_pct = 0.0
        revenue = _revenue_fuer(project, global_assumptions)
        assert revenue["erloes_eur"].iloc[0] == pytest.approx(70_000.0)

    def test_inflation_wirkt_nur_auf_marktwert_nicht_auf_zuschlag(
        self, project, global_assumptions
    ):
        """Der EAG-Zuschlag ist gesetzlich nominal fix - inflationiert wird
        nur der Marktwert. Bei 2 % Inflation ueberschreitet der nominale
        Marktwert (Basis 4 ct real) den Zuschlag von 7 ct erst nach ueber
        25 Jahren, vorher bleibt der Satz bei 7 ct."""
        global_assumptions.marktpreis_inflation_pct_pa = 0.02
        revenue = _revenue_fuer(project, global_assumptions)
        jahr1 = revenue.iloc[0]
        # Kalenderjahr 2027, Basisjahr 2025 -> Faktor 1,02².
        assert jahr1["marktwert_nominal_ct_kwh"] == pytest.approx(4.0 * 1.02**2)
        assert jahr1["verguetungssatz_ct_kwh"] == pytest.approx(7.0)

    def test_kalenderjahr_clamping_am_kurvenrand(self, project, global_assumptions):
        """Projekte, die ueber das letzte Kurvenjahr hinauslaufen, rechnen
        mit dem letzten bekannten Randwert weiter (kein Extrapolieren,
        kein Absturz)."""
        project.inbetriebnahme_jahr = 2059  # Kurve endet 2060
        revenue = _revenue_fuer(project, global_assumptions, jahre=5)
        assert revenue["marktwert_real_ct_kwh"].tolist() == pytest.approx([4.0] * 5)
