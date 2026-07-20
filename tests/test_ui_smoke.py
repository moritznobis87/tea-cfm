"""
UI-Smoke-Tests mit Streamlits AppTest-Framework: rendert jede Seite der
App headless und stellt sicher, dass kein Rerun mit einer Exception endet.

Diese Tests sind bewusst grob (kein Pixel-Vergleich) - sie fangen die
haeufigste Fehlerklasse ab: eine Umstrukturierung, ein umbenannter
Session-State-Key oder ein geaendertes Engine-Schema, das erst beim
Rendern einer bestimmten Seite auffliegt.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.fixture
def at() -> AppTest:
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    app.run()
    assert not app.exception
    return app


class TestSeitenRendern:
    def test_portfolio_zeigt_kennzahlen_und_projekte(self, at: AppTest):
        # Portfolio-KPI-Leiste (Projekte, MWp, Invest, EK, Ø IRR) - als
        # HTML-Kacheln mit Auto-Fit-Schrift, gruppiert als "portfolio".
        kpi_html = [
            m.value for m in at.markdown if 'data-kpi-group="portfolio"' in m.value
        ]
        assert len(kpi_html) == 1
        assert kpi_html[0].count('class="kpi-card"') == 5
        oeffnen_buttons = [
            b for b in at.button if b.key and b.key.startswith("open_")
        ]
        assert len(oeffnen_buttons) >= 1

    def test_projekt_dashboard_oeffnet_ohne_fehler(self, at: AppTest):
        oeffnen_buttons = [
            b for b in at.button if b.key and b.key.startswith("open_")
        ]
        oeffnen_buttons[0].click()
        at.run()
        assert not at.exception
        # 5 Projekt-KPIs als Kachelgruppe "projekt".
        projekt_kpis = [
            m.value for m in at.markdown if 'data-kpi-group="projekt"' in m.value
        ]
        assert len(projekt_kpis) == 1
        assert projekt_kpis[0].count('class="kpi-card"') == 5
        # NPV-Diskontsatz-Eingabe vorhanden und wirksam (Label folgt Wert).
        npv_inputs = [
            n for n in at.get("number_input") if n.key == "npv_diskontsatz_pct"
        ]
        assert len(npv_inputs) == 1
        npv_inputs[0].set_value(7.5)
        at.run()
        assert not at.exception
        projekt_kpis = [
            m.value for m in at.markdown if 'data-kpi-group="projekt"' in m.value
        ]
        assert "NPV bei 7,50 %" in projekt_kpis[0]

    def test_neues_projekt_zeigt_formular(self, at: AppTest):
        at.sidebar.radio[0].set_value("neu")
        at.run()
        assert not at.exception
        assert len(at.get("number_input")) > 10

    def test_globale_annahmen_rendern(self, at: AppTest):
        at.sidebar.radio[0].set_value("annahmen")
        at.run()
        assert not at.exception


class TestKPIUndChartBugfixes:
    """Regressionstests fuer drei gemeldete Fehler: Gemeindeabgabe im
    gestapelten Betriebskosten-Chart farblich nicht unterscheidbar von
    Nachbarpositionen, Projektanzahl-KPI reagiert nicht auf den
    Inaktiv-Filter, Schriftgroessen-Skript der KPI-Kacheln ohne
    Ellipsis-Sicherheitsnetz."""

    def test_gemeindeabgabe_farblich_unterscheidbar(self, project, global_assumptions):
        """Gemeindeabgabe/Direktvermarktung erhalten Farben ausserhalb der
        OPEX_SCALE-Warmtonfamilie, damit sie sich nicht mit den
        Standard-OPEX-Segmenten (Pacht, Sonstiges etc.) optisch
        vermischen - unabhaengig von der Anzahl konfigurierter
        Standardpositionen."""
        from app.components import charts
        from app.theme import Colors
        from engine import run_valuation

        result = run_valuation(project, global_assumptions)
        fig = charts.opex_stacked_chart(
            result.cashflow.data, result.cashflow.opex_posten
        )
        namen = {tr.name: tr.marker.color for tr in fig.data}
        assert namen["Gemeindeabgabe"] not in Colors.OPEX_SCALE
        assert namen["Direktvermarktung"] not in Colors.OPEX_SCALE
        assert namen["Gemeindeabgabe"] != namen["Direktvermarktung"]
        # Beide klar von der letzten (dunkelsten) OPEX-Warmton-Farbe
        # unterscheidbar, mit der sie im Stack direkt angrenzen.
        assert namen["Gemeindeabgabe"] not in (
            Colors.OPEX_SCALE[len(result.cashflow.opex_posten) - 1 :]
        )

    def test_gemeindeabgabe_werte_im_chart_vorhanden(
        self, project, global_assumptions
    ):
        """Die Datenwerte selbst waren nie das Problem - Regressionsschutz,
        dass der Trace weiterhin die korrekten, nicht-trivialen Werte
        traegt."""
        from app.components import charts
        from engine import run_valuation

        result = run_valuation(project, global_assumptions)
        fig = charts.opex_stacked_chart(
            result.cashflow.data, result.cashflow.opex_posten
        )
        trace = next(tr for tr in fig.data if tr.name == "Gemeindeabgabe")
        assert any(v and v > 0 for v in trace.y)

    def test_projektanzahl_kpi_respektiert_inaktiv_filter(self, at):
        """Kernbug: die 'Projekte'-Kachel zaehlte immer alle Projekte,
        unabhaengig vom Inaktiv-Status - jetzt folgt sie derselben
        gefilterten Basis wie die uebrigen Portfolio-KPIs.

        Der Toggle schreibt auf die echte Projektdatei auf der Platte
        (data/projects/*.yaml) - try/finally stellt sicher, dass der
        Ausgangszustand unabhaengig vom Testergebnis wiederhergestellt
        wird, damit nachfolgende Tests nicht von einem versehentlich
        inaktiv gebliebenen Projekt beeinflusst werden."""
        import re

        def kpi_werte(app):
            markup = " ".join(
                m.value for m in app.markdown
                if m.value and "kpi-value" in m.value
            )
            return re.findall(r'data-kpi-group="portfolio"[^>]*>([^<]+)<', markup)

        vorher = kpi_werte(at)
        [b for b in at.button if b.key and b.key.startswith("open_")][0].click()
        at.run()
        assert not at.exception
        btn = [b for b in at.button if b.key and b.key.startswith("aktiv_")][0]
        assert btn.label == "Inaktiv schalten", (
            "Projekt war vor dem Test bereits inaktiv - Testisolation verletzt"
        )
        try:
            btn.click()
            at.run()
            assert not at.exception
            nachher = kpi_werte(at)
            # Alle fuenf KPIs (inkl. Projektanzahl an Position 0) muessen
            # sich gemeinsam veraendern, wenn ein Projekt inaktiv wird.
            assert vorher[0] != nachher[0], (
                "Projektanzahl reagiert nicht auf Inaktiv-Filter"
            )
            assert int(nachher[0]) == int(vorher[0]) - 1
        finally:
            btn_zurueck = [
                b for b in at.button if b.key and b.key.startswith("aktiv_")
            ][0]
            if btn_zurueck.label == "Aktivieren":
                btn_zurueck.click()
                at.run()

    def test_kpi_value_hat_ellipsis_sicherheitsnetz(self):
        """CSS-Sicherheitsnetz: falls die JS-Anpassung einen Reflow einmal
        nicht rechtzeitig einholt, muss der Wert sauber mit '…'
        abgeschnitten werden statt hart (unleserlich) geclippt."""
        from app.theme import _CSS

        block = _CSS[_CSS.index(".kpi-card .kpi-value"):]
        block = block[:block.index("}")]
        assert "text-overflow: ellipsis" in block
        assert "overflow: hidden" in block

    def test_kpi_fit_skript_beobachtet_layoutwechsel(self):
        """Das Schriftgroessen-Skript verlaesst sich nicht mehr nur auf
        feste Timeouts, sondern beobachtet Groessen-/DOM-Aenderungen
        aktiv weiter (Sidebar/Tab/Expander-Wechsel, spaetere Reruns)."""
        from app.components.kpi import _FIT_SCRIPT

        assert "ResizeObserver" in _FIT_SCRIPT
        assert "MutationObserver" in _FIT_SCRIPT
