"""Tests fuer Zeitachse, Energieproduktion und Betriebskosten."""

from __future__ import annotations

from datetime import date

import numpy as np
import pytest

from engine import OpexItem
from engine.energy import calculate_energy_production
from engine.opex import calculate_opex
from engine.pipeline import resolve_assumptions
from engine.timeline import build_timeline


class TestTimeline:
    def test_jahresstart_januar_hat_volle_prorata(self):
        timeline = build_timeline(date(2027, 1, 1), 3)
        assert len(timeline) == 3
        assert timeline["pro_rata_faktor"].iloc[0] == pytest.approx(1.0)
        assert bool(timeline["ist_letztes_jahr"].iloc[-1]) is True

    def test_unterjaehriger_start_hat_anteiliges_erstes_jahr(self):
        # Start 1. Juli -> zweites Halbjahr = 184 Tage.
        timeline = build_timeline(date(2027, 7, 1), 2)
        assert timeline["pro_rata_faktor"].iloc[0] == pytest.approx(184 / 365)
        assert timeline["pro_rata_faktor"].iloc[1] == pytest.approx(1.0)

    def test_laufzeit_null_wird_abgelehnt(self):
        with pytest.raises(ValueError):
            build_timeline(date(2027, 1, 1), 0)


class TestEnergy:
    def test_produktion_ohne_degradation(self, project, global_assumptions):
        assumptions = resolve_assumptions(project, global_assumptions)
        timeline = build_timeline(date(2027, 1, 1), 3)
        energy = calculate_energy_production(timeline, assumptions)
        # 1.000 kWp * 1.000 kWh/kWp = 1 GWh in jedem vollen Jahr.
        assert energy["produktion_kwh"].tolist() == pytest.approx([1e6, 1e6, 1e6])

    def test_degradation_wirkt_ab_jahr_zwei(self, project, global_assumptions):
        global_assumptions.degradation_pct_pa = 0.005
        assumptions = resolve_assumptions(project, global_assumptions)
        timeline = build_timeline(date(2027, 1, 1), 3)
        energy = calculate_energy_production(timeline, assumptions)
        assert energy["produktion_kwh"].iloc[0] == pytest.approx(1e6)
        assert energy["produktion_kwh"].iloc[1] == pytest.approx(1e6 * 0.995)
        assert energy["produktion_kwh"].iloc[2] == pytest.approx(1e6 * 0.995**2)


class TestOpex:
    def test_indexierung_startet_ab_konfiguriertem_jahr(self):
        timeline = build_timeline(date(2027, 1, 1), 3)
        import pandas as pd

        energy = pd.DataFrame({"jahr": [1, 2, 3], "produktion_kwh": [0.0, 0.0, 0.0]})
        items = [
            OpexItem(
                name="Wartung", basiswert_eur_kwp=2.0,
                index_pct_pa=0.02, indexierung_ab_jahr=2,
            )
        ]
        opex = calculate_opex(timeline, items, 1000.0, energy)
        # Jahr 1 und 2: Basis 2.000 €; ab Jahr 3 ein Indexschritt.
        assert opex["Wartung"].iloc[0] == pytest.approx(2000.0)
        assert opex["Wartung"].iloc[1] == pytest.approx(2000.0)
        assert opex["Wartung"].iloc[2] == pytest.approx(2000.0 * 1.02)

    def test_gleichnamige_positionen_werden_addiert(self):
        timeline = build_timeline(date(2027, 1, 1), 1)
        import pandas as pd

        energy = pd.DataFrame({"jahr": [1], "produktion_kwh": [0.0]})
        items = [
            OpexItem(name="Pacht", basiswert_eur_kwp=1.0),
            OpexItem(name="Pacht", basiswert_eur_kwp=2.0),
        ]
        opex = calculate_opex(timeline, items, 1000.0, energy)
        assert opex["Pacht"].iloc[0] == pytest.approx(3000.0)
        # Nur EINE Spalte je Bezeichnung (eindeutiger Legendeneintrag).
        assert list(opex.columns).count("Pacht") == 1

    def test_produktionsbasierte_abgaben(self):
        timeline = build_timeline(date(2027, 1, 1), 1)
        import pandas as pd

        energy = pd.DataFrame({"jahr": [1], "produktion_kwh": [1e6]})
        opex = calculate_opex(
            timeline, [], 1000.0, energy,
            gemeindeabgabe_eur_kwh=0.002,
            direktvermarktungskosten_eur_kwh=0.001,
        )
        assert opex["gemeindeabgabe_eur"].iloc[0] == pytest.approx(2000.0)
        assert opex["direktvermarktungskosten_eur"].iloc[0] == pytest.approx(1000.0)
        assert opex["opex_gesamt_eur"].iloc[0] == pytest.approx(3000.0)


class TestDirektvermarktungsModus:
    def test_relativ_marktwert_berechnet_anteil(self, project, global_assumptions):
        """Im Relativ-Modus: DV-Kosten = Produktion x Marktwert(nominal) x
        Anteil - Jahr fuer Jahr exakt."""
        from engine import DirektvermarktungsModus, run_valuation

        ga = global_assumptions.model_copy(deep=True)
        ga.direktvermarktung_modus = DirektvermarktungsModus.RELATIV_MARKTWERT
        ga.direktvermarktung_pct_marktwert = 0.10

        df = run_valuation(project, ga).cashflow.data
        betrieb = df[df["jahr"] >= 1]
        erwartet = (
            betrieb["produktion_kwh"]
            * betrieb["marktwert_nominal_ct_kwh"]
            / 100.0
            * 0.10
        )
        assert np.allclose(betrieb["direktvermarktungskosten_eur"], erwartet)

    def test_absolut_bleibt_unveraendert(self, project, global_assumptions):
        """Der Standard-Modus ABSOLUT rechnet exakt wie bisher: fester
        EUR/kWh-Satz auf die erzeugte Menge."""
        from engine import run_valuation

        df = run_valuation(project, global_assumptions).cashflow.data
        betrieb = df[df["jahr"] >= 1]
        satz = project.direktvermarktungskosten_eur_mwh / 1000
        assert np.allclose(
            betrieb["direktvermarktungskosten_eur"],
            betrieb["produktion_kwh"] * satz,
        )

    def test_modus_aendert_irr(self, project, global_assumptions):
        """Ein spuerbarer Marktwert-Anteil (10 %) muss die Rendite gegen-
        ueber 1 EUR/MWh absolut deutlich druecken."""
        from engine import DirektvermarktungsModus, run_valuation

        irr_absolut = run_valuation(project, global_assumptions).kpis.equity_irr
        ga = global_assumptions.model_copy(deep=True)
        ga.direktvermarktung_modus = DirektvermarktungsModus.RELATIV_MARKTWERT
        ga.direktvermarktung_pct_marktwert = 0.10
        irr_relativ = run_valuation(project, ga).kpis.equity_irr
        assert irr_relativ < irr_absolut

    def test_yaml_roundtrip_mit_modus(self, tmp_path, global_assumptions):
        from engine import DirektvermarktungsModus
        from engine.io_yaml import (
            load_global_assumptions_yaml,
            save_global_assumptions_yaml,
        )

        ga = global_assumptions.model_copy(deep=True)
        ga.direktvermarktung_modus = DirektvermarktungsModus.RELATIV_MARKTWERT
        ga.direktvermarktung_pct_marktwert = 0.07
        pfad = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(ga, pfad)
        geladen = load_global_assumptions_yaml(pfad)
        assert geladen.direktvermarktung_modus == DirektvermarktungsModus.RELATIV_MARKTWERT
        assert geladen.direktvermarktung_pct_marktwert == 0.07

    def test_excel_roundtrip_mit_modus(self, global_assumptions):
        from engine import DirektvermarktungsModus
        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )

        ga = global_assumptions.model_copy(deep=True)
        ga.direktvermarktung_modus = DirektvermarktungsModus.RELATIV_MARKTWERT
        ga.direktvermarktung_pct_marktwert = 0.12
        geladen = excel_to_global_assumptions(global_assumptions_to_excel(ga))
        assert geladen.direktvermarktung_modus == DirektvermarktungsModus.RELATIV_MARKTWERT
        assert geladen.direktvermarktung_pct_marktwert == pytest.approx(0.12)
