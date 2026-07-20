"""
Tests fuer die konfigurierbaren Modelloptionen:
- Gemeindeabgabe ueber die GESAMTE Projektlaufzeit (Regressionstest)
- Tilgungsfreies Anlaufjahr (On/Off)
- Negativstunden-Modus: Abregelung vs. Rueckfall auf Jahresmarktwert
"""

from __future__ import annotations

from datetime import date

import pytest

from engine import (
    NegativeStundenModus,
    NegativeStundenRegel,
    TilgungsArt,
    run_valuation,
)
from engine.financing import calculate_financing
from engine.kpis import npv_at
from engine.timeline import build_timeline


class TestGemeindeabgabeVolleLaufzeit:
    def test_abgabe_faellt_in_jedem_betriebsjahr_an(self, project, global_assumptions):
        """Regressionstest: Die Gemeindeabgabe (hier 2 €/MWh) wird in JEDEM
        Jahr der Betriebsdauer auf die Produktion gezahlt - vom ersten bis
        zum letzten Betriebsjahr, unabhaengig von Foerder- oder
        Kreditlaufzeit."""
        result = run_valuation(project, global_assumptions)
        df = result.cashflow.data
        betriebsjahre = df[df["jahr"] >= 1]
        assert len(betriebsjahre) == global_assumptions.betriebsdauer_jahre
        # 1 GWh/Jahr x 2 €/MWh = 2.000 €/Jahr, in jedem einzelnen Jahr.
        assert betriebsjahre["gemeindeabgabe_eur"].tolist() == pytest.approx(
            [2000.0] * global_assumptions.betriebsdauer_jahre
        )
        # Auch im allerletzten Betriebsjahr (nach Foerder- UND Kreditende).
        assert betriebsjahre["gemeindeabgabe_eur"].iloc[-1] == pytest.approx(2000.0)


class TestTilgungsfreiesAnlaufjahr:
    def _fin(self, tilgungsfrei: bool, art: TilgungsArt = TilgungsArt.LINEAR):
        timeline = build_timeline(date(2027, 1, 1), 25)
        return calculate_financing(
            timeline, 1_000_000.0, 0.2, 0.04, 20, art,
            tilgungsfreies_anlaufjahr=tilgungsfrei,
        )

    def test_jahr_1_nur_zinsen(self):
        fin = self._fin(True)
        assert fin["tilgung_eur"].iloc[0] == pytest.approx(0.0)
        assert fin["zinsen_eur"].iloc[0] == pytest.approx(800_000 * 0.04)
        assert fin["schuldendienst_eur"].iloc[0] == pytest.approx(800_000 * 0.04)

    def test_jahr_2_zins_noch_auf_voller_kreditsumme(self):
        """Weil Jahr 1 ungetilgt bleibt, ist der Jahresanfangsstand in
        Jahr 2 noch die volle Kreditsumme - genau die Zinsstruktur aus dem
        Referenz-Excel (zweimal voller Zins hintereinander)."""
        fin = self._fin(True)
        assert fin["zinsen_eur"].iloc[1] == pytest.approx(fin["zinsen_eur"].iloc[0])
        assert fin["zinsen_eur"].iloc[2] < fin["zinsen_eur"].iloc[1]

    def test_kredit_wird_trotzdem_vollstaendig_getilgt(self):
        for art in (TilgungsArt.LINEAR, TilgungsArt.ANNUITAET):
            fin = self._fin(True, art)
            assert fin["tilgung_eur"].sum() == pytest.approx(800_000.0)
            # Raten laufen in den Jahren 2..21 (20 Raten), danach nichts mehr.
            assert (fin["tilgung_eur"].iloc[1:21] > 0).all()
            assert fin["darlehensstand_eop_eur"].iloc[20] == pytest.approx(
                0.0, abs=1e-6
            )
            assert (fin["schuldendienst_eur"].iloc[21:] == 0.0).all()

    def test_schalter_aus_entspricht_bisherigem_verhalten(self):
        mit = self._fin(False)
        assert mit["tilgung_eur"].iloc[0] == pytest.approx(40_000.0)
        assert mit["darlehensstand_eop_eur"].iloc[19] == pytest.approx(0.0, abs=1e-6)

    def test_wirkung_auf_projekt_irr(self, project, global_assumptions):
        """Die Verschiebung der ersten Rate ans Laufzeitende erhoeht die
        Equity-IRR (frueher Cashflow wiegt in der IRR am schwersten)."""
        basis = run_valuation(project, global_assumptions).kpis.equity_irr
        global_assumptions.tilgungsfreies_anlaufjahr = True
        mit_anlaufjahr = run_valuation(project, global_assumptions).kpis.equity_irr
        assert mit_anlaufjahr > basis


class TestNegativeStundenModus:
    @pytest.fixture
    def ga_mit_negstunden(self, global_assumptions):
        szenario = global_assumptions.marktpreisszenarien[0]
        for jahr in szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr:
            szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr[jahr] = 0.10
            szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[jahr] = 0.10
        return global_assumptions

    def test_abregelung_entzieht_komplette_verguetung(
        self, project, ga_mit_negstunden
    ):
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.ABREGELUNG
        df = run_valuation(project, ga_mit_negstunden).cashflow.data
        # Jahr 1: 1 GWh x 90 % x 7 ct = 63.000 €.
        assert df.loc[df["jahr"] == 1, "erloes_eur"].iloc[0] == pytest.approx(63_000.0)

    def test_marktwert_modus_verguetet_negstunden_zum_marktwert(
        self, project, ga_mit_negstunden
    ):
        """Anlage laeuft weiter: 90 % der Menge zum Foerdersatz (7 ct),
        10 % zum Jahresmarktwert (4 ct) - entspricht exakt der
        Spread-Formel des Referenz-Excels:
        Produktion x Satz - Produktion x Anteil x (Satz - Marktwert)."""
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        df = run_valuation(project, ga_mit_negstunden).cashflow.data
        erwartet = 1e6 * (0.9 * 7.0 + 0.1 * 4.0) / 100
        assert df.loc[df["jahr"] == 1, "erloes_eur"].iloc[0] == pytest.approx(erwartet)
        spread_formel = 1e6 * 7.0 / 100 - 1e6 * 0.10 * (7.0 - 4.0) / 100
        assert erwartet == pytest.approx(spread_formel)

    def test_nach_foerderdauer_wirkt_nur_noch_abregelung(
        self, project, ga_mit_negstunden
    ):
        """Nach der Foerderdauer ist der Satz ohnehin der Marktwert: Im
        MARKTWERT-Modus gibt es dann keinen Abzug mehr, im
        ABREGELUNG-Modus entfaellt die Menge weiterhin."""
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        voll = run_valuation(project, ga_mit_negstunden).cashflow.data
        jahr21_voll = voll.loc[voll["jahr"] == 21, "erloes_eur"].iloc[0]
        assert jahr21_voll == pytest.approx(1e6 * 4.0 / 100)

        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.ABREGELUNG
        abgeregelt = run_valuation(project, ga_mit_negstunden).cashflow.data
        jahr21_ab = abgeregelt.loc[abgeregelt["jahr"] == 21, "erloes_eur"].iloc[0]
        assert jahr21_ab == pytest.approx(1e6 * 0.9 * 4.0 / 100)

    def test_marktwert_modus_erhoeht_irr(self, project, ga_mit_negstunden):
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.ABREGELUNG
        irr_ab = run_valuation(project, ga_mit_negstunden).kpis.equity_irr
        ga_mit_negstunden.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        irr_mw = run_valuation(project, ga_mit_negstunden).kpis.equity_irr
        assert irr_mw > irr_ab


class TestNpvAt:
    def test_npv_at_standardsatz_entspricht_kpi(self, project, global_assumptions):
        result = run_valuation(project, global_assumptions)
        assert npv_at(result.cashflow, 0.08) == pytest.approx(result.kpis.npv_eur)

    def test_npv_at_liegt_auf_der_npv_kurve(self, project, global_assumptions):
        result = run_valuation(project, global_assumptions)
        for _, row in result.npv_curve.iloc[::5].iterrows():
            assert npv_at(result.cashflow, row["diskontsatz_pct"]) == pytest.approx(
                row["npv_eur"]
            )


class TestIoRoundtripNeueFelder:
    def test_excel_roundtrip_mit_nicht_defaults(self, global_assumptions):
        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )

        global_assumptions.tilgungsfreies_anlaufjahr = True
        global_assumptions.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        geladen = excel_to_global_assumptions(
            global_assumptions_to_excel(global_assumptions)
        )
        assert geladen.tilgungsfreies_anlaufjahr is True
        assert geladen.negative_stunden_modus == NegativeStundenModus.MARKTWERT

    def test_yaml_roundtrip_mit_nicht_defaults(self, global_assumptions, tmp_path):
        from engine.io_yaml import (
            load_global_assumptions_yaml,
            save_global_assumptions_yaml,
        )

        global_assumptions.tilgungsfreies_anlaufjahr = True
        global_assumptions.negative_stunden_modus = NegativeStundenModus.MARKTWERT
        pfad = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(global_assumptions, pfad)
        geladen = load_global_assumptions_yaml(pfad)
        assert geladen == global_assumptions


class TestNegativeStundenRegel:
    """6h-Regel (Oesterreich, Standard) vs. 1h-Regel (Deutschland): die
    Regel waehlt aus, welche Negativmengen-Zeitreihe des Szenarios
    angewendet wird."""

    @pytest.fixture
    def ga_mit_getrennten_kurven(self, global_assumptions):
        szenario = global_assumptions.marktpreisszenarien[0]
        for jahr in szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr:
            szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr[jahr] = 0.05
            szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[jahr] = 0.20
        return global_assumptions

    def test_standard_ist_6h(self, global_assumptions):
        assert (
            global_assumptions.negative_stunden_regel
            == NegativeStundenRegel.SECHS_STUNDEN
        )

    def test_1h_regel_reduziert_erloese_staerker(
        self, project, ga_mit_getrennten_kurven
    ):
        ga = ga_mit_getrennten_kurven
        erloes_6h = run_valuation(project, ga).cashflow.data["erloes_eur"].sum()
        ga.negative_stunden_regel = NegativeStundenRegel.EINE_STUNDE
        erloes_1h = run_valuation(project, ga).cashflow.data["erloes_eur"].sum()
        assert erloes_1h < erloes_6h

    def test_regel_waehlt_exakt_die_kurve(self, project, ga_mit_getrennten_kurven):
        from engine.pipeline import resolve_assumptions

        ga = ga_mit_getrennten_kurven
        ea_6h = resolve_assumptions(project, ga)
        assert set(ea_6h.anteil_negativer_stunden_pct_je_kalenderjahr.values()) == {
            0.05
        }
        ga.negative_stunden_regel = NegativeStundenRegel.EINE_STUNDE
        ea_1h = resolve_assumptions(project, ga)
        assert set(ea_1h.anteil_negativer_stunden_pct_je_kalenderjahr.values()) == {
            0.20
        }

    def test_legacy_kurve_wandert_in_beide_regeln(self):
        from engine import MarktpreisSzenario

        szenario = MarktpreisSzenario(
            name="Alt",
            marktwert_solar_ct_kwh_je_kalenderjahr={2030: 4.0},
            anteil_negativer_stunden_pct_je_kalenderjahr={2030: 0.08},
        )
        assert szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr == {2030: 0.08}
        assert szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr == {2030: 0.08}

    def test_excel_roundtrip_getrennte_kurven_und_regel(self, global_assumptions):
        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )

        ga = global_assumptions.model_copy(deep=True)
        szenario = ga.marktpreisszenarien[0]
        for jahr in szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr:
            szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr[jahr] = 0.06
            szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[jahr] = 0.18
        ga.negative_stunden_regel = NegativeStundenRegel.EINE_STUNDE

        geladen = excel_to_global_assumptions(global_assumptions_to_excel(ga))
        s = geladen.marktpreisszenarien[0]
        for wert in s.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr.values():
            assert wert == pytest.approx(0.06)
        for wert in s.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr.values():
            assert wert == pytest.approx(0.18)
        assert geladen.negative_stunden_regel == NegativeStundenRegel.EINE_STUNDE


class TestAurora626Standarddaten:
    """Das ausgelieferte Aurora-6/26-Szenario: erstes (Standard-)Szenario
    mit getrennten 6h/1h-Zeitreihen aus der Marktpreisstudie."""

    @pytest.fixture
    def ausgeliefert(self):
        from pathlib import Path

        from engine.io_yaml import load_global_assumptions_yaml

        return load_global_assumptions_yaml(
            Path(__file__).parent.parent / "data" / "global_assumptions.yaml"
        )

    def test_aurora_626_ist_erstes_szenario(self, ausgeliefert):
        assert ausgeliefert.marktpreisszenarien[0].name == "Aurora 6/26"

    def test_aurora_szenarien_vor_enervis(self, ausgeliefert):
        namen = [s.name for s in ausgeliefert.marktpreisszenarien]
        assert namen[-1] == "Enervis 2025"
        assert all(n.startswith("Aurora") for n in namen[:-1])

    def test_aurora_626_stuetzwerte(self, ausgeliefert):
        a = ausgeliefert.marktpreisszenarien[0]
        assert a.marktwert_solar_ct_kwh_je_kalenderjahr[2027] == pytest.approx(4.25)
        assert a.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr[2027] == pytest.approx(0.13)
        assert a.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[2027] == pytest.approx(0.18)
        # 1h erfasst nie weniger Menge als 6h
        for jahr, wert_6h in a.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr.items():
            assert a.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[jahr] >= wert_6h
        # Voller Horizont (2025/2026 mit 2027-Werten aufgefuellt)
        assert min(a.marktwert_solar_ct_kwh_je_kalenderjahr) == 2025
        assert max(a.marktwert_solar_ct_kwh_je_kalenderjahr) == 2060


class TestKostenInflation:
    """Die globale Kosteninflation wirkt auf ALLE Kostenpositionen ohne
    eigene Preislogik: Pacht, Gemeindeabgabe und Direktvermarktung
    (absoluter Modus) eskalieren ab dem 2. Betriebsjahr; die Standard-
    OPEX-Positionen tragen ihre eigene Indexierung (Auslieferung: 2 %/a
    ab Jahr 1); Direktvermarktung im Relativ-Modus folgt bereits dem
    nominalen Marktwert."""

    def _opex(self, project, ga):
        from engine import run_valuation

        return run_valuation(project, ga).cashflow.data

    def test_gemeindeabgabe_und_dv_eskalieren(self, project, global_assumptions):
        ga = global_assumptions.model_copy(deep=True)
        ga.kosten_inflation_pct_pa = 0.02
        df = self._opex(project, ga)
        basis = self._opex(project, global_assumptions)  # Inflation 0
        for spalte in ("gemeindeabgabe_eur", "direktvermarktungskosten_eur"):
            j1 = df.loc[df["jahr"] == 1, spalte].iloc[0]
            j11 = df.loc[df["jahr"] == 11, spalte].iloc[0]
            j1_flach = basis.loc[basis["jahr"] == 1, spalte].iloc[0]
            j11_flach = basis.loc[basis["jahr"] == 11, spalte].iloc[0]
            # Jahr 1 = Preisstand Inbetriebnahme (unveraendert)
            assert j1 == pytest.approx(j1_flach)
            # Jahr 11: Faktor 1,02^10 gegenueber der flachen Basis
            # (Produktionsdegradation kuerzt sich im Quotienten heraus)
            assert j11 / j11_flach == pytest.approx(1.02**10, rel=1e-9)

    def test_pacht_eskaliert(self, project, global_assumptions):
        ga = global_assumptions.model_copy(deep=True)
        ga.kosten_inflation_pct_pa = 0.03
        df = self._opex(project, ga)
        pacht_j1 = df.loc[df["jahr"] == 1, "Pacht"].iloc[0]
        pacht_j2 = df.loc[df["jahr"] == 2, "Pacht"].iloc[0]
        assert pacht_j1 == pytest.approx(
            project.pacht_eur_kwp_jahr * project.nennleistung_kwp
        )
        assert pacht_j2 == pytest.approx(pacht_j1 * 1.03)

    def test_dv_relativ_unberuehrt(self, project, global_assumptions):
        """Im Relativ-Modus folgen die DV-Kosten dem nominalen Marktwert -
        die Kosteninflation darf NICHT zusaetzlich wirken."""
        from engine import DirektvermarktungsModus

        ga = global_assumptions.model_copy(deep=True)
        ga.direktvermarktung_modus = DirektvermarktungsModus.RELATIV_MARKTWERT
        mit = ga.model_copy(deep=True)
        mit.kosten_inflation_pct_pa = 0.05
        df_ohne = self._opex(project, ga)
        df_mit = self._opex(project, mit)
        assert df_ohne["direktvermarktungskosten_eur"].sum() == pytest.approx(
            df_mit["direktvermarktungskosten_eur"].sum()
        )

    def test_inflation_senkt_irr(self, project, global_assumptions):
        from engine import run_valuation

        ga = global_assumptions.model_copy(deep=True)
        ga.kosten_inflation_pct_pa = 0.03
        assert (
            run_valuation(project, ga).kpis.equity_irr
            < run_valuation(project, global_assumptions).kpis.equity_irr
        )

    def test_excel_roundtrip_und_auslieferung(self, global_assumptions):
        from pathlib import Path

        from engine.io_excel import (
            excel_to_global_assumptions,
            global_assumptions_to_excel,
        )
        from engine.io_yaml import load_global_assumptions_yaml

        ga = global_assumptions.model_copy(deep=True)
        ga.kosten_inflation_pct_pa = 0.025
        geladen = excel_to_global_assumptions(global_assumptions_to_excel(ga))
        assert geladen.kosten_inflation_pct_pa == pytest.approx(0.025)

        ausgeliefert = load_global_assumptions_yaml(
            Path(__file__).parent.parent / "data" / "global_assumptions.yaml"
        )
        assert ausgeliefert.kosten_inflation_pct_pa == pytest.approx(0.02)
        # Alle Standard-OPEX-Positionen konsistent indexiert (2 %/a ab Jahr 1)
        for item in ausgeliefert.opex_standard:
            assert item.index_pct_pa == pytest.approx(0.02)
            assert item.indexierung_ab_jahr == 1


class TestProjektInaktiv:
    """Inaktive Projekte bleiben erhalten (Pipeline-Bereinigung ohne
    Loeschen): Standard aktiv, Persistenz ueber YAML- und Excel-
    Roundtrip, Legacy-Dateien ohne Feld laden als aktiv."""

    def test_standard_aktiv_und_yaml_roundtrip(self, project, tmp_path):
        from engine.io_yaml import load_project_yaml, save_project_yaml

        assert project.aktiv is True
        project.aktiv = False
        pfad = tmp_path / "p.yaml"
        save_project_yaml(project, pfad)
        assert load_project_yaml(pfad).aktiv is False
        # Legacy-Datei ohne Feld -> aktiv
        inhalt = pfad.read_text()
        pfad.write_text("\n".join(
            z for z in inhalt.splitlines() if not z.startswith("aktiv:")
        ))
        assert load_project_yaml(pfad).aktiv is True

    def test_excel_roundtrip(self, project):
        from engine.io_excel import excel_to_projects, projects_to_excel

        inaktiv = project.model_copy(deep=True)
        inaktiv.id = "p-inaktiv"
        inaktiv.aktiv = False
        geladen = excel_to_projects(projects_to_excel([project, inaktiv]))
        nach_id = {p.id: p for p in geladen}
        assert nach_id[project.id].aktiv is True
        assert nach_id["p-inaktiv"].aktiv is False
