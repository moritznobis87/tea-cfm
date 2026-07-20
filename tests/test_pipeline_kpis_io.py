"""
End-to-End-Tests: komplette Bewertungspipeline, KPIs, Sensitivitaet
sowie YAML-/Excel-Roundtrips (Speichern -> Laden -> identisches Objekt).
"""

from __future__ import annotations

from datetime import date

import pytest

from engine import run_eag_sensitivity, run_valuation
from engine.io_excel import (
    excel_to_global_assumptions,
    excel_to_projects,
    global_assumptions_to_excel,
    projects_to_excel,
)
from engine.io_yaml import (
    load_global_assumptions_yaml,
    load_project_yaml,
    save_global_assumptions_yaml,
    save_project_yaml,
)
from engine.kpis import _xirr, _xnpv


class TestPipeline:
    def test_cashflow_konsistenz(self, project, global_assumptions):
        result = run_valuation(project, global_assumptions)
        df = result.cashflow.data

        # Jahr 0 + 25 Betriebsjahre.
        assert len(df) == 26
        # Gesamt-CF = Summe der drei Kategorien, kumuliert = laufende Summe.
        summe = df["cf_operativ_eur"] + df["cf_invest_eur"] + df["cf_finanzierung_eur"]
        assert df["cf_gesamt_eur"].tolist() == pytest.approx(summe.tolist())
        assert df["cf_kumuliert_eur"].iloc[-1] == pytest.approx(
            df["cf_gesamt_eur"].sum()
        )
        # Jahr 0: EK-Abfluss = CAPEX - Kreditaufnahme = 20 % von 550.000 €.
        assert df["cf_gesamt_eur"].iloc[0] == pytest.approx(-110_000.0)
        assert result.kpis.eigenkapital_eur == pytest.approx(110_000.0)
        assert result.kpis.capex_total_eur == pytest.approx(550_000.0)

    def test_kpis_sind_plausibel(self, project, global_assumptions):
        result = run_valuation(project, global_assumptions)
        kpis = result.kpis
        # 7 ct Verguetung bei 550 €/kWp Invest -> deutlich positives Projekt.
        assert kpis.equity_irr is not None and kpis.equity_irr > 0.05
        assert kpis.npv_eur > 0
        assert kpis.payback_jahre is not None
        assert kpis.dscr_min is not None and kpis.dscr_min > 0

    def test_npv_kurve_ist_monoton_fallend(self, project, global_assumptions):
        result = run_valuation(project, global_assumptions)
        npv = result.npv_curve["npv_eur"]
        assert (npv.diff().dropna() < 0).all()

    def test_fehlendes_szenario_faellt_auf_erstes_zurueck(
        self, project, global_assumptions
    ):
        project.marktpreisszenario = "gibt-es-nicht"
        result = run_valuation(project, global_assumptions)
        assert (
            result.effective_assumptions.marktpreisszenario_name == "Testszenario"
        )


class TestXirr:
    def test_xnpv_bei_rate_null_ist_summe(self):
        cashflows = [-100.0, 60.0, 60.0]
        dates = [date(2027, 1, 1), date(2027, 12, 31), date(2028, 12, 31)]
        assert _xnpv(0.0, cashflows, dates) == pytest.approx(20.0)

    def test_xirr_bekannter_fall(self):
        # -100 heute, +110 in exakt 365 Tagen -> IRR = 10 %.
        cashflows = [-100.0, 110.0]
        dates = [date(2027, 1, 1), date(2028, 1, 1)]
        assert _xirr(cashflows, dates) == pytest.approx(0.10, abs=1e-6)

    def test_xirr_ohne_vorzeichenwechsel_ist_none(self):
        dates = [date(2027, 1, 1), date(2028, 1, 1)]
        assert _xirr([-100.0, -50.0], dates) is None
        assert _xirr([100.0, 50.0], dates) is None

    def test_xirr_sehr_hohe_rendite_wird_gefunden(self):
        """Erweiterte Suchintervalle: auch IRR > 1000 % (Faktor 11 in einem
        Jahr) darf nicht in `None` enden."""
        cashflows = [-1.0, 12.0]
        dates = [date(2027, 1, 1), date(2028, 1, 1)]
        irr = _xirr(cashflows, dates)
        assert irr == pytest.approx(11.0, rel=1e-4)


class TestSensitivity:
    def test_fuenf_varianten_mit_basis(self, project, global_assumptions):
        sens = run_eag_sensitivity(project, global_assumptions)
        assert len(sens) == 5
        assert "Basis" in sens["variante"].tolist()
        basis = sens[sens["variante"] == "Basis"].iloc[0]
        assert basis["eag_zuschlagswert_ct_kwh"] == pytest.approx(7.0)
        # Hoeherer Zuschlag -> hoehere (oder gleiche) IRR: monotone Ordnung.
        sortiert = sens.sort_values("delta_pct")
        irr = sortiert["equity_irr"].tolist()
        assert all(a <= b + 1e-12 for a, b in zip(irr, irr[1:], strict=False))


class TestIoRoundtrip:
    def test_projekt_yaml_roundtrip(self, project, tmp_path):
        pfad = tmp_path / "projekt.yaml"
        save_project_yaml(project, pfad)
        geladen = load_project_yaml(pfad)
        assert geladen == project

    def test_global_assumptions_yaml_roundtrip(self, global_assumptions, tmp_path):
        pfad = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(global_assumptions, pfad)
        geladen = load_global_assumptions_yaml(pfad)
        assert geladen == global_assumptions

    def test_projekte_excel_roundtrip(self, project):
        excel_bytes = projects_to_excel([project])
        geladen = excel_to_projects(excel_bytes)
        assert len(geladen) == 1
        assert geladen[0] == project

    def test_global_assumptions_excel_roundtrip(self, global_assumptions):
        excel_bytes = global_assumptions_to_excel(global_assumptions)
        geladen = excel_to_global_assumptions(excel_bytes)
        assert geladen.steuersatz_pct == pytest.approx(
            global_assumptions.steuersatz_pct
        )
        assert geladen.szenario_namen == global_assumptions.szenario_namen
        szenario_alt = global_assumptions.marktpreisszenarien[0]
        szenario_neu = geladen.marktpreisszenarien[0]
        assert szenario_neu.marktwert_solar_ct_kwh_je_kalenderjahr == pytest.approx(
            szenario_alt.marktwert_solar_ct_kwh_je_kalenderjahr
        )


class TestCapexWidmungGenehmigung:
    def test_summe_enthaelt_widmung_und_genehmigung(self):
        from engine import CapexBreakdown

        capex = CapexBreakdown(
            epc_eur=1_000_000, widmung_eur=10_000, genehmigung_eur=80_000
        )
        assert capex.summe_eur == 1_090_000

    def test_excel_roundtrip_neue_capex_felder(self, project):
        from engine.io_excel import excel_to_projects, projects_to_excel

        p = project.model_copy(deep=True)
        p.capex.widmung_eur = 10_000
        p.capex.genehmigung_eur = 80_000
        geladen = excel_to_projects(projects_to_excel([p]))[0]
        assert geladen.capex.widmung_eur == 10_000
        assert geladen.capex.genehmigung_eur == 80_000
        assert geladen.capex.summe_eur == p.capex.summe_eur


class TestDownloadDateinamenFolgenAktuellemNamen:
    """Regressionstest fuer den gemeldeten Bug: nach Duplizieren + Um-
    benennen zeigte der PDF-/Excel-Dateiname weiter den alten (id-
    basierten) Namen, obwohl der Berichtstitel korrekt war. Die interne
    Projekt-ID bleibt bei Umbenennung bewusst stabil (Dateiidentitaet);
    Download-Dateinamen muessen aber dem AKTUELLEN Namen folgen."""

    def test_slugify_folgt_dem_aktuellen_namen(self):
        from app.services import slugify

        assert slugify("Template Agri") == "template-agri"
        assert slugify("Solarpark Nord") == "solarpark-nord"

    def test_id_bleibt_bei_umbenennung_stabil_slug_aendert_sich(self, project):
        from app.services import make_project_id, slugify

        urspruengliche_id = make_project_id(project.name, existing_ids=set())
        umbenannt = project.model_copy(update={"name": "Solarpark Nord"})
        # Die id (Dateiidentitaet) wird beim Umbenennen NICHT neu vergeben -
        # das simuliert den Edit-Flow, der existing.id beibehaelt.
        assert umbenannt.id == project.id == "testprojekt"
        # Der Downloadname (slugify) folgt dagegen dem neuen Namen und
        # weicht damit bewusst von der id ab.
        assert slugify(umbenannt.name) == "solarpark-nord"
        assert slugify(umbenannt.name) != urspruengliche_id
