"""
Tests des PDF-Ergebnisberichts: Erzeugung aus den deterministischen
Fixtures, Grundstruktur (PDF-Header, Seitenzahl) und Kerninhalte
(Kapiteltitel, Kennzahlen) ueber die extrahierten Seitentexte.
"""

from __future__ import annotations

import io
import re

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
        ]:
            assert erwartet in text, erwartet

    def test_ohne_speicher_kein_speicherkapitel(self, pdf_bytes):
        """Das Kapitel ist bedingt - und die Nummerierung muss trotzdem
        lueckenlos sein. Frueher standen die Nummern als feste
        Zeichenketten im Text; ein bedingtes Kapitel in der Mitte haette
        entweder eine Luecke oder zwei gleiche Nummern erzeugt."""
        pypdf = pytest.importorskip("pypdf")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(seite.extract_text() for seite in reader.pages)
        assert "Batteriespeicher" not in text
        for nummer, titel in ((1, "Management Summary"), (2, "Ergebnisrechnung"),
                              (4, "Finanzierung")):
            assert f"{nummer}   {titel}" in text or f"{nummer}" in text

    def test_preisdaten_stehen_nicht_mehr_im_bericht(self, pdf_bytes):
        """Annex B fuehrte die Marktwert-Zeitreihen ALLER hinterlegten
        Szenarien auf. Das ist Marktdatenbestand des Hauses und gehoert
        nicht in ein Gutachten ueber ein einzelnes Projekt - erst recht
        nicht in eines, das aus dem Haus geht."""
        pypdf = pytest.importorskip("pypdf")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        text = "\n".join(seite.extract_text() for seite in reader.pages)
        assert "Annex: Zeitreihen" not in text
        assert "Marktwerte aller hinterlegten Szenarien" not in text

    def test_metadaten(self, pdf_bytes):
        pypdf = pytest.importorskip("pypdf")
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        assert "Wirtschaftlichkeitsanalyse" in (reader.metadata.title or "")


@pytest.fixture(scope="module")
def pdf_text_freie_positionen(_projekt_modul, _ga_modul):
    """Bericht eines Projekts mit frei benannten Zusatzpositionen."""
    pypdf = pytest.importorskip("pypdf")
    from app.report import ReportInputs, build_pdf_report
    from engine import CapexPosition, OpexItem

    p = _projekt_modul.model_copy(deep=True)
    p.capex.zusatzpositionen = [
        CapexPosition(name="Wildschutzzaun", betrag_eur=25_000.0)
    ]
    p.zusatz_opex = [OpexItem(name="Fernueberwachung", basiswert_eur_kwp=2.0)]

    result = run_valuation(p, _ga_modul)
    inputs = ReportInputs(
        project=p,
        global_assumptions=_ga_modul,
        result=result,
        tornado=run_tornado(p, _ga_modul),
        eag_sensitivitaet=run_eag_sensitivity(p, _ga_modul),
        monte_carlo=run_monte_carlo(p, _ga_modul, n_laeufe=20),
        szenarien=run_scenario_comparison(p, _ga_modul, 0.08),
        break_even_ct=break_even_zuschlag(p, _ga_modul, 0.08),
        lcoe_ct=calculate_lcoe(result.cashflow.data, 0.08),
        npv_eur=npv_at(result.cashflow, 0.08),
        diskontsatz_pct=0.08,
        logo_path=None,
    )
    reader = pypdf.PdfReader(io.BytesIO(build_pdf_report(inputs)))
    return "\n".join(seite.extract_text() for seite in reader.pages)


class TestFreiePositionenImBericht:
    """Frei benannte Zusatzpositionen muessen im Bericht sichtbar sein -
    in der CAPEX-Aufstellung des Annex A und in der Positionsliste der
    Betriebskosten."""

    def test_zusatz_capex_erscheint(self, pdf_text_freie_positionen):
        assert "Wildschutzzaun" in pdf_text_freie_positionen

    def test_zusatz_opex_erscheint(self, pdf_text_freie_positionen):
        assert "Fernueberwachung" in pdf_text_freie_positionen


@pytest.fixture(scope="module")
def pdf_mit_speicher(_projekt_modul, _ga_modul):
    """Bericht eines Projekts mit gerechnetem Speicher.

    Der Beitrag wird hier von Hand gesetzt statt gerechnet: Ein
    Mehrjahresdispatch kostet eine halbe Minute, und geprueft wird die
    DARSTELLUNG, nicht die Optimierung. Die Zahlen sind bewusst rund und
    von aussen nachvollziehbar.
    """
    pytest.importorskip("pypdf")
    from app.report import ReportInputs, build_pdf_report
    from engine import BatteryConfig, SpeicherModus
    from engine.pipeline import resolve_assumptions, run_valuation_from_assumptions
    from engine.storage import SpeicherBeitrag
    from engine.storage.models import StorageJahreswert

    p = _projekt_modul.model_copy(deep=True)
    p.battery = BatteryConfig(
        modus=SpeicherModus.GRUENSTROM, leistung_mw=2.0, kapazitaet_mwh=8.0,
    )
    a = resolve_assumptions(p, _ga_modul)
    n = a.betriebsdauer_jahre
    beitrag = SpeicherBeitrag(
        wertbeitrag_eur_je_jahr=tuple(180_000.0 for _ in range(n)),
        capex_eur=752_000.0,
        opex_eur_je_jahr=tuple(16_000.0 for _ in range(n)),
        jahreswerte=tuple(
            StorageJahreswert(
                jahr=j, kalenderjahr=2030 + j,
                mehrerloes_eur=200_000.0, netzbezugskosten_eur=0.0,
                degradationskosten_eur=20_000.0,
                mehrmenge_kwh=900_000.0, rueckgewonnene_kappung_kwh=400_000.0,
                speicher_ladung_mwh=2_600.0, speicher_entladung_mwh=2_400.0,
                vollzyklen=330.0,
            )
            for j in (1, 5, 12, 22)
        ),
        hinweise=(),
    )
    ohne = run_valuation_from_assumptions(a, p.id, compute_npv_curve=False)
    # Die NPV-Kurve wird gebraucht: Kapitel 2 zeichnet sie.
    mit = run_valuation_from_assumptions(a, p.id, speicher=beitrag)
    inputs = ReportInputs(
        project=p,
        global_assumptions=_ga_modul,
        result=mit,
        tornado=run_tornado(p, _ga_modul),
        eag_sensitivitaet=run_eag_sensitivity(p, _ga_modul),
        monte_carlo=run_monte_carlo(p, _ga_modul, n_laeufe=40),
        szenarien=run_scenario_comparison(p, _ga_modul, 0.08),
        break_even_ct=break_even_zuschlag(p, _ga_modul, 0.08),
        lcoe_ct=calculate_lcoe(mit.cashflow.data, 0.08),
        npv_eur=npv_at(mit.cashflow, 0.08),
        diskontsatz_pct=0.08,
        speicher=beitrag,
        kpis_ohne_speicher=ohne.kpis,
    )
    import pypdf

    reader = pypdf.PdfReader(io.BytesIO(build_pdf_report(inputs)))
    roh = "\n".join(seite.extract_text() for seite in reader.pages)
    # Der Satz bricht Zeilen mitten im Satz um; ein Test auf einen ganzen
    # Satz scheitert sonst an der Stelle, an der der Umbruch faellt.
    return re.sub(r"\s+", " ", roh)


class TestSpeicherkapitel:
    def test_das_kapitel_erscheint_mit_der_auslegung(self, pdf_mit_speicher):
        assert "Batteriespeicher" in pdf_mit_speicher
        assert "2,0 MW" in pdf_mit_speicher
        assert "8,0 MWh" in pdf_mit_speicher

    def test_die_wirkung_auf_die_rendite_steht_dabei(self, pdf_mit_speicher):
        """Ein Speicherwert ohne seinen Bezugspunkt ist keine Aussage -
        deshalb wird die Rendite MIT gegen die OHNE gehalten."""
        assert "Wirkung auf EK-Rendite" in pdf_mit_speicher
        assert "%-Pkt." in pdf_mit_speicher

    def test_die_day_ahead_beschraenkung_steht_im_bericht(
        self, pdf_mit_speicher
    ):
        """Der wichtigste Vorbehalt des ganzen Kapitels. Ein Gutachten,
        das einen Speicherwert nennt, ohne zu sagen, an welchem Markt er
        verdient wird, laedt zu einer Fehllesung ein - Regelenergie und
        Intraday sind bei realen Projekten oft der groessere Teil."""
        assert "Day-Ahead" in pdf_mit_speicher
        assert "perfekte Voraussicht" in pdf_mit_speicher

    def test_der_geltungsbereich_ist_benannt(self, pdf_mit_speicher):
        """Sensitivitaet, Risiko und Szenarien rechnen OHNE den Speicher.
        Das muss dabeistehen, sonst liest sich eine Tornado-Grafik wie
        eine Aussage ueber das Projekt mit Speicher."""
        assert "Sensitivitätsanalyse, Risikoanalyse und Szenarienvergleich" \
            in pdf_mit_speicher

    def test_der_verschleisssatz_und_seine_herkunft_stehen_dabei(
        self, pdf_mit_speicher, _ga_modul
    ):
        """Der Satz entscheidet mit, wie oft gefahren wird - und er
        steht in keiner Kachel. Wer den Speicherwert nachrechnen will,
        braucht ihn, und er braucht die Zyklenzahl, aus der er stammt.

        Die Erwartung wird GERECHNET und nicht abgeschrieben: Sinkt der
        Zellpreis in den Annahmen, soll der Test die neue Zahl im
        Bericht sehen wollen und nicht die alte."""
        from app.formatting import fmt_number
        from engine.storage.kosten import verschleiss_eur_mwh

        satz = fmt_number(verschleiss_eur_mwh(_ga_modul), 2)
        assert f"{satz} €/MWh Durchsatz" in pdf_mit_speicher
        assert (
            f"{fmt_number(_ga_modul.speicher_zyklenlebensdauer, 0)} Vollzyklen"
            in pdf_mit_speicher
        )

    def test_die_kapitelnummern_bleiben_lueckenlos(self, pdf_mit_speicher):
        """Mit dem zusaetzlichen Kapitel verschieben sich alle folgenden
        Nummern. Genau dafuer gibt es den Zaehler."""
        treffer = re.search(r"(\d+)\s+Batteriespeicher", pdf_mit_speicher)
        assert treffer, "Speicherkapitel ohne Nummer"
        nummer = int(treffer.group(1))
        # Es steht zwischen Erloesen und Finanzierung - lueckenlos.
        assert re.search(rf"{nummer - 1}\s+Erlöse und Förderung",
                         pdf_mit_speicher)
        assert re.search(rf"{nummer + 1}\s+Finanzierung", pdf_mit_speicher)
