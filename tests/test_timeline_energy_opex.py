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


class TestZinsmethode:
    """Zinsberechnungsmethode fuer das (moeglicherweise unterjaehrige)
    erste Betriebsjahr: deutsche (30/360) vs. oesterreichische
    (act/365) Konvention - siehe engine.timeline.erstjahr_zins_pro_rata
    und engine.financing.calculate_financing."""

    def test_januar_start_beide_methoden_voller_faktor(self):
        from engine.models import ZinsMethode
        from engine.timeline import erstjahr_zins_pro_rata

        for methode in (ZinsMethode.OESTERREICH, ZinsMethode.DEUTSCH):
            assert erstjahr_zins_pro_rata(date(2028, 1, 1), methode) == pytest.approx(1.0)

    def test_oesterreich_deckt_sich_mit_produktions_pro_rata(self):
        """Dieselbe taggenaue Logik wie build_timeline()'s
        pro_rata_faktor fuer das erste Jahr - keine zweite,
        abweichende Zeitachse fuer die Finanzierung."""
        from engine.models import ZinsMethode
        from engine.timeline import build_timeline, erstjahr_zins_pro_rata

        for monat in (3, 6, 9, 12):
            start = date(2028, monat, 1)
            timeline = build_timeline(start, 2)
            faktor_timeline = timeline["pro_rata_faktor"].iloc[0]
            faktor_zins = erstjahr_zins_pro_rata(start, ZinsMethode.OESTERREICH)
            assert faktor_zins == pytest.approx(faktor_timeline)

    def test_deutsch_30_360_rechenformel(self):
        from engine.models import ZinsMethode
        from engine.timeline import erstjahr_zins_pro_rata

        # Juni: Restmonate inkl. Juni = 7 -> 7*30/360
        assert erstjahr_zins_pro_rata(
            date(2028, 6, 15), ZinsMethode.DEUTSCH
        ) == pytest.approx(7 * 30 / 360)
        # Dezember: nur 1 Restmonat -> 30/360
        assert erstjahr_zins_pro_rata(
            date(2028, 12, 1), ZinsMethode.DEUTSCH
        ) == pytest.approx(30 / 360)
        # 30/360 ignoriert den Tag im Monat (kaufmaennische Konvention).
        assert erstjahr_zins_pro_rata(
            date(2028, 6, 1), ZinsMethode.DEUTSCH
        ) == erstjahr_zins_pro_rata(date(2028, 6, 30), ZinsMethode.DEUTSCH)

    def test_deutsch_und_oesterreich_nah_beieinander_aber_nicht_gleich(self):
        from engine.models import ZinsMethode
        from engine.timeline import erstjahr_zins_pro_rata

        start = date(2028, 6, 1)
        at = erstjahr_zins_pro_rata(start, ZinsMethode.OESTERREICH)
        de = erstjahr_zins_pro_rata(start, ZinsMethode.DEUTSCH)
        assert at != de
        assert abs(at - de) < 0.01

    def test_financing_wendet_faktor_nur_auf_erstes_jahr_an(self):
        from engine.financing import calculate_financing
        from engine.models import TilgungsArt
        from engine.timeline import build_timeline

        timeline = build_timeline(date(2028, 7, 1), 3)
        voll = calculate_financing(
            timeline, 1_000_000, 0.2, 0.05, 3, TilgungsArt.ANNUITAET,
            erstjahr_zins_faktor=1.0,
        )
        halb = calculate_financing(
            timeline, 1_000_000, 0.2, 0.05, 3, TilgungsArt.ANNUITAET,
            erstjahr_zins_faktor=0.5,
        )
        # Jahr 1: Zinsen exakt halbiert.
        assert halb["zinsen_eur"].iloc[0] == pytest.approx(
            voll["zinsen_eur"].iloc[0] * 0.5
        )
        # Folgejahre (2, 3): NICHT vom Faktor betroffen (nur jahr==1
        # wird reduziert) - beide Reihen duerfen ab Jahr 2 aber wegen
        # der unterschiedlichen Tilgungshoehe in Jahr 1 divergieren,
        # der Faktor selbst wird aber nicht mehr angewendet:
        assert halb["darlehensstand_bop_eur"].iloc[0] == pytest.approx(
            voll["darlehensstand_bop_eur"].iloc[0]
        )

    def test_pipeline_reduziert_zinsen_bei_unterjaehrigem_start(
        self, project, global_assumptions
    ):
        """End-to-End: ein Projekt mit Inbetriebnahme im Juni zahlt im
        ersten Betriebsjahr deutlich weniger Zinsen als eines mit
        Inbetriebnahme im Januar (identische sonstige Annahmen) - vor
        dieser Aenderung wurde immer ein volles Jahr Zinsen berechnet,
        unabhaengig vom Inbetriebnahmemonat."""
        from engine.pipeline import run_valuation

        project.inbetriebnahme_monat = 1
        r_januar = run_valuation(project, global_assumptions)
        zinsen_januar = r_januar.cashflow.data.query("jahr == 1")["zinsen_eur"].iloc[0]

        project.inbetriebnahme_monat = 6
        r_juni = run_valuation(project, global_assumptions)
        zinsen_juni = r_juni.cashflow.data.query("jahr == 1")["zinsen_eur"].iloc[0]

        assert zinsen_juni < zinsen_januar
        # Grobe Erwartung: knapp die Haelfte (Juni -> ca. 7/12 Jahr).
        assert 0.5 < zinsen_juni / zinsen_januar < 0.65

    def test_deutsch_vs_oesterreich_wirkt_sich_auf_irr_aus(
        self, project, global_assumptions
    ):
        from engine.models import ZinsMethode
        from engine.pipeline import run_valuation

        project.inbetriebnahme_monat = 6
        global_assumptions.zinsmethode = ZinsMethode.OESTERREICH
        r_at = run_valuation(project, global_assumptions)
        global_assumptions.zinsmethode = ZinsMethode.DEUTSCH
        r_de = run_valuation(project, global_assumptions)

        assert r_at.kpis.equity_irr != r_de.kpis.equity_irr
        # Die Methoden liegen dicht beieinander - kein grosser Sprung.
        assert abs(r_at.kpis.equity_irr - r_de.kpis.equity_irr) < 0.01

    def test_januar_start_beide_methoden_identisches_ergebnis(
        self, project, global_assumptions
    ):
        """Fuer volle Kalenderjahre (Inbetriebnahme im Januar) darf die
        Methodenwahl keinen Unterschied machen."""
        from engine.models import ZinsMethode
        from engine.pipeline import run_valuation

        project.inbetriebnahme_monat = 1
        global_assumptions.zinsmethode = ZinsMethode.OESTERREICH
        r_at = run_valuation(project, global_assumptions)
        global_assumptions.zinsmethode = ZinsMethode.DEUTSCH
        r_de = run_valuation(project, global_assumptions)

        assert r_at.kpis.equity_irr == pytest.approx(r_de.kpis.equity_irr)

    def test_yaml_roundtrip(self, tmp_path):
        from engine.io_yaml import (
            load_global_assumptions_yaml,
            save_global_assumptions_yaml,
        )
        from engine.models import ZinsMethode

        ga = load_global_assumptions_yaml("data/global_assumptions.yaml")
        ga.zinsmethode = ZinsMethode.DEUTSCH
        pfad = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(ga, str(pfad))
        ga2 = load_global_assumptions_yaml(str(pfad))
        assert ga2.zinsmethode == ZinsMethode.DEUTSCH

    def test_excel_roundtrip(self):
        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )
        from engine.io_yaml import load_global_assumptions_yaml
        from engine.models import ZinsMethode

        ga = load_global_assumptions_yaml("data/global_assumptions.yaml")
        ga.zinsmethode = ZinsMethode.DEUTSCH
        ga2 = excel_to_global_assumptions(global_assumptions_to_excel(ga))
        assert ga2.zinsmethode == ZinsMethode.DEUTSCH

    def test_excel_ohne_zinsmethode_spalte_faellt_auf_oesterreich_zurueck(self):
        """Rueckwaertskompatibilitaet: aeltere exportierte Excel-Dateien
        ohne die neue Zeile duerfen beim Import nicht scheitern."""
        import io

        from openpyxl import load_workbook

        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )
        from engine.io_yaml import load_global_assumptions_yaml
        from engine.models import ZinsMethode

        ga = load_global_assumptions_yaml("data/global_assumptions.yaml")
        xl = global_assumptions_to_excel(ga)
        wb = load_workbook(io.BytesIO(xl))
        ws = wb["Einstellungen"]
        for row in ws.iter_rows():
            if row[0].value == "zinsmethode":
                ws.delete_rows(row[0].row)
                break
        puffer = io.BytesIO()
        wb.save(puffer)
        ga2 = excel_to_global_assumptions(puffer.getvalue())
        assert ga2.zinsmethode == ZinsMethode.OESTERREICH


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
