"""
Tests des PDF-Ergebnisberichts: Erzeugung aus den deterministischen
Fixtures, Grundstruktur (PDF-Header, Seitenzahl) und Kerninhalte
(Kapiteltitel, Kennzahlen) ueber die extrahierten Seitentexte.
"""

from __future__ import annotations

import io

import pytest

from engine import (
    break_even_zuschlag,
    calculate_lcoe,
    run_monte_carlo,
    run_scenario_comparison,
    run_tornado,
    run_valuation,
)
from engine.kpis import npv_at
from engine.sensitivity import run_eag_sensitivity


@pytest.fixture(scope="module")
def pdf_bytes(request):
    project = request.getfixturevalue("_projekt_modul")
    ga = request.getfixturevalue("_ga_modul")
    from app.report import ReportInputs, build_pdf_report

    result = run_valuation(project, ga)
    inputs = ReportInputs(
        project=project,
        global_assumptions=ga,
        result=result,
        tornado=run_tornado(project, ga),
        eag_sensitivitaet=run_eag_sensitivity(project, ga),
        monte_carlo=run_monte_carlo(project, ga, n_laeufe=40),
        szenarien=run_scenario_comparison(project, ga, 0.08),
        break_even_ct=break_even_zuschlag(project, ga, 0.08),
        lcoe_ct=calculate_lcoe(result.cashflow.data, 0.08),
        npv_eur=npv_at(result.cashflow, 0.08),
        diskontsatz_pct=0.08,
        logo_path=None,
    )
    return build_pdf_report(inputs)


# Modul-weite Kopien der Funktions-Fixtures (der Bericht ist teuer genug,
# um ihn nur einmal je Testmodul zu bauen).
@pytest.fixture(scope="module")
def _projekt_modul():
    from tests.conftest import _baue_projekt

    return _baue_projekt()


@pytest.fixture(scope="module")
def _ga_modul():
    from tests.conftest import _baue_global_assumptions

    return _baue_global_assumptions()


class TestPdfBericht:
    def test_pdf_header_und_groesse(self, pdf_bytes):
        assert pdf_bytes.startswith(b"%PDF")
        assert len(pdf_bytes) > 100_000

    def test_seitenzahl_und_kapitel(self, pdf_bytes):
        pypdf = pytest.importorskip("pypdf")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) >= 12
        text = "\n".join(seite.extract_text() for seite in reader.pages)
        for erwartet in [
            "Wirtschaftlichkeitsanalyse",
            "Management Summary",
            "Ergebnisrechnung",
            "Sensitivitätsanalyse",
            "Monte-Carlo-Simulation",
            "Szenarienvergleich",
            "Annex: Annahmen der Berechnung",
            "Annex: Zeitreihen",
        ]:
            assert erwartet in text, erwartet

    def test_metadaten(self, pdf_bytes):
        pypdf = pytest.importorskip("pypdf")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert "Wirtschaftlichkeitsanalyse" in (reader.metadata.title or "")
