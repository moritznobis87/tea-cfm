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


def _gehe_zu(at: AppTest, key: str) -> AppTest:
    """Navigation ueber die Seitenleiste (Knoepfe statt Radio-Feld)."""
    [b for b in at.button if b.key == key][0].click()
    at.run()
    assert not at.exception
    return at


def _oeffne_projekt(at: AppTest, projekt_id: str | None = None) -> AppTest:
    """Ein Projekt ueber seine Karte im Portfolio oeffnen.

    Ohne Kennung das erste - fuer alles, was nur irgendein Projekt
    braucht.
    """
    knoepfe = [b for b in at.button if b.key and b.key.startswith("open_")]
    if projekt_id is not None:
        knoepfe = [b for b in knoepfe if b.key == f"open_{projekt_id}"]
        assert knoepfe, f"Projekt {projekt_id} steht nicht im Portfolio"
    knoepfe[0].click()
    at.run()
    assert not at.exception
    return at


def _unauffaelliges_projekt() -> str:
    """Kennung eines Projekts, das seine DSCR-Schwellen einhaelt.

    Welches das ist, haengt an den ausgelieferten Projektdaten - die
    aendern sich mit jedem Datenstand. Deshalb wird es bestimmt und
    nicht geraten.
    """
    from app import services

    kandidaten = [
        (services.get_valuation(p.id).kpis.dscr_min, p.id)
        for p in services.list_projects() if p.aktiv
    ]
    assert kandidaten, "keine aktiven Projekte ausgeliefert"
    return max(kandidaten)[1]


def _kpi_markup(at: AppTest, gruppe: str) -> str:
    treffer = [
        m.value for m in at.markdown
        if f'data-kpi-group="{gruppe}"' in m.value and "kpi-leiste" in m.value
    ]
    assert len(treffer) == 1, f"Kennzahlenleiste '{gruppe}' nicht eindeutig"
    return treffer[0]


@pytest.fixture
def at() -> AppTest:
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=60)
    app.run()
    assert not app.exception
    return app


class TestSeitenRendern:
    def test_portfolio_zeigt_kennzahlen_und_projekte(self, at: AppTest):
        # Portfolio-KPI-Leiste (Projekte, MWp, Deckungsbeitrag, EK,
        # Ø IRR) - als HTML-Kacheln mit Auto-Fit-Schrift, gruppiert als
        # "portfolio".
        markup = _kpi_markup(at, "portfolio")
        # Eine Leitkachel (Ø Equity IRR) und vier begleitende.
        assert markup.count('class="kpi-hero"') == 1
        assert markup.count('class="kpi-card"') == 4
        # Die Investitionssumme ist einer Aussage ueber den Erfolg
        # gewichen: Was schaffen diese Projekte zusammen an Wert?
        assert "Deckungsbeitrag kumuliert" in markup
        assert "Capex" not in markup
        oeffnen_buttons = [
            b for b in at.button if b.key and b.key.startswith("open_")
        ]
        assert len(oeffnen_buttons) >= 1

    def test_projektseite_oeffnet_ohne_fehler(self, at: AppTest):
        at = _oeffne_projekt(at)
        markup = _kpi_markup(at, "projekt")
        assert markup.count('class="kpi-hero"') == 1
        assert markup.count('class="kpi-card"') == 4
        # Der Diskontsatz steht in der Kontextzeile und ist dort einstellbar.
        npv_inputs = [
            n for n in at.get("number_input") if n.key == "npv_diskontsatz_pct"
        ]
        assert len(npv_inputs) == 1
        npv_inputs[0].set_value(7.5)
        at.run()
        assert not at.exception
        assert "NPV bei 7,50 %" in _kpi_markup(at, "projekt")
        kontext = [
            m.value for m in at.markdown if 'class="kontextzeile"' in m.value
        ]
        assert kontext and "Diskontsatz 7,50 %" in kontext[0]

    def test_neues_projekt_zeigt_formular(self, at: AppTest):
        _gehe_zu(at, "nav_neu")
        assert not at.exception
        assert len(at.get("number_input")) > 10

    def test_globale_annahmen_rendern(self, at: AppTest):
        _gehe_zu(at, "nav_annahmen")
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
            markup = _kpi_markup(app, "portfolio")
            return re.findall(r'class="kpi-value"[^>]*>([^<]+)<', markup)

        vorher = kpi_werte(at)
        at = _oeffne_projekt(at)
        btn = [b for b in at.button if b.key and b.key.startswith("aktiv_")][0]
        assert btn.label == "Inaktiv schalten", (
            "Projekt war vor dem Test bereits inaktiv - Testisolation verletzt"
        )
        try:
            btn.click()
            at.run()
            assert not at.exception
            [b for b in at.button if b.key == "nav_portfolio"][0].click()
            at.run()
            nachher = kpi_werte(at)
            # Die Projektanzahl ist die erste Begleitkachel und muss dem
            # Inaktiv-Filter folgen.
            assert vorher[0] != nachher[0], (
                "Projektanzahl reagiert nicht auf Inaktiv-Filter"
            )
            assert int(nachher[0]) == int(vorher[0]) - 1
        finally:
            at = _oeffne_projekt(at)
            btn_zurueck = [
                b for b in at.button if b.key and b.key.startswith("aktiv_")
            ][0]
            if btn_zurueck.label == "Aktivieren":
                btn_zurueck.click()
                at.run()

    def test_kennzahl_ohne_schriftanpassung_per_skript(self):
        """Die frueher noetige Messung per JavaScript ist ersatzlos
        entfallen: Die Werte werden gerundet dargestellt und passen damit
        bei fester Schriftgroesse (siehe app/components/kpi.py)."""
        import pathlib

        quelle = pathlib.Path("app/components/kpi.py").read_text(encoding="utf-8")
        assert "ResizeObserver" not in quelle
        assert "<script" not in quelle
        assert "st.iframe" not in quelle

    def test_betraege_werden_gerundet_dargestellt(self):
        from app.formatting import fmt_eur_kompakt

        assert fmt_eur_kompakt(1_243_117) == "1,24 Mio €"
        assert fmt_eur_kompakt(842_600) == "843 Tsd €"
        assert fmt_eur_kompakt(-183_400) == "-183 Tsd €"
        assert fmt_eur_kompakt(-1_183_400) == "-1,18 Mio €"
        assert fmt_eur_kompakt(912) == "912 €"

    def test_steuer_chart_zeigt_steuer_eur(self, project, global_assumptions):
        """Neue Steuerzahlungen-Grafik unter der Betriebskosten-Grafik:
        eigenstaendiges Diagramm, das bislang nirgends existierte (nur
        in der Detailtabelle sichtbar)."""
        from app.components import charts
        from engine import run_valuation

        result = run_valuation(project, global_assumptions)
        fig = charts.tax_chart(result.cashflow.data)
        assert len(fig.data) == 1
        trace = fig.data[0]
        assert list(trace.y) == list(result.cashflow.data["steuer_eur"])
        assert list(trace.x) == list(result.cashflow.data["jahr"])

    def test_kpi_reihenfolge_auf_der_projektseite(self, at: AppTest):
        """Leitkennzahl Equity IRR, danach NPV, Equity Value, CAPEX und
        Enterprise Value.

        Die vier Begleiter stehen zweispaltig und werden zeilenweise
        gefuellt. Mit CAPEX an dritter Stelle liegen Equity Value und
        Enterprise Value in derselben Spalte uebereinander - mit
        Enterprise Value an dritter Stelle stuenden sie ueber Eck.
        """
        import re

        at = _oeffne_projekt(at)
        markup = _kpi_markup(at, "projekt")
        labels = re.findall(r'class="kpi-label">([^<]+)<', markup)
        assert labels[0] == "Equity IRR"
        assert labels[1].startswith("NPV bei")
        assert labels[2:] == ["Equity Value", "CAPEX", "Enterprise Value"]

    def test_equity_und_enterprise_value(self, project, global_assumptions):
        """Equity Value = NPV + Eigenkapitaleinsatz;
        Enterprise Value = Equity Value + aufgenommenes Fremdkapital."""
        from engine import run_valuation
        from engine.kpis import npv_at

        result = run_valuation(project, global_assumptions)
        kpis = result.kpis
        npv = npv_at(result.cashflow, 0.08)

        equity_value = npv + kpis.eigenkapital_eur
        fremdkapital = kpis.capex_total_eur - kpis.eigenkapital_eur
        enterprise_value = equity_value + fremdkapital

        assert equity_value > npv          # Eigenkapital ist immer positiv
        assert fremdkapital == pytest.approx(
            kpis.capex_total_eur * (1 - project.eigenkapitalquote_pct)
        )
        assert enterprise_value == pytest.approx(equity_value + fremdkapital)

    def test_pdf_bericht_zeigt_equity_value_nicht_lcoe(self, project, global_assumptions):
        import io

        from pypdf import PdfReader

        from app import services

        services.save_project(project)
        try:
            pdf = services.build_project_report(project.id, 0.08)
            text = "\n".join(
                s.extract_text() for s in PdfReader(io.BytesIO(pdf)).pages
            )
            assert "EQUITY VALUE" in text
            assert "ENTERPRISE VALUE" in text
            assert "LCOE" not in text
        finally:
            services.delete_project(project.id)

    def test_bubble_chart_leeres_portfolio_stuerzt_nicht_ab(self):
        """Robustheitsluecke gefunden waehrend der Entwicklung dieser
        Version: Bei null aktiven Projekten (z.B. alle ueber den
        Inaktiv-Filter ausgeblendet) war der DataFrame leer und hatte
        keine 'typ'-Spalte - portfolio_bubble_chart() stuerzte mit
        KeyError ab statt eine leere Grafik zu zeigen."""
        import pandas as pd

        from app.components import charts

        fig = charts.portfolio_bubble_chart(pd.DataFrame(), selected_id=None)
        assert len(fig.data) == 0


class TestDokumentationsKnopf:
    """Hilfe-Knopf in der Kopfzeile: laedt die Rechenweg-Dokumentation
    als PDF herunter (siehe streamlit_app.py)."""

    def test_kopfzeile_bietet_dokumentation_zum_download(self, at: AppTest):
        knoepfe = [
            k for k in at.get("download_button")
            if k.proto.id.startswith("dokumentation_download")
            or k.proto.help.startswith("Rechenmodell-Dokumentation")
        ]
        assert len(knoepfe) == 1, "Hilfe-Knopf fehlt in der Kopfzeile"
        assert knoepfe[0].proto.help  # uebersetzter Tooltip vorhanden

    def test_ausgelieferte_datei_ist_ein_pdf(self):
        from app import services

        daten = services.get_dokumentation_pdf()
        assert daten is not None, "docs/rechenmodell/Rechenmodell.pdf fehlt"
        assert daten[:5] == b"%PDF-", "keine gueltige PDF-Datei"

    def test_logo_wird_ohne_weissen_rand_gesetzt(self):
        """Die Markendatei steht auf viel Weissraum; unbeschnitten
        bestimmt dieser die Hoehe der Kopfzeile (siehe app.branding)."""
        import io

        from PIL import Image

        from app.branding import MARKEN, logo_bild

        marke = MARKEN["valyze"]
        original = Image.open(marke["logo"])
        beschnitten = logo_bild(marke)
        assert isinstance(beschnitten, bytes)
        neu = Image.open(io.BytesIO(beschnitten))
        # Der Schriftzug belegt nur einen Bruchteil der Originalhoehe.
        assert neu.height < original.height * 0.5
        assert neu.width < original.width


class TestKovenantenStatus:
    """DSCR-Schwellen im Projekt-Dashboard (siehe engine/covenants.py):
    Die DSCR-Kachel wurde durch eine Statusaussage ersetzt, die auch
    beantwortet, ob ein Nachschuss aus eigener Kraft gedeckt ist."""

    def test_unauffaelliges_projekt_meldet_eingehaltene_schwellen(
        self, at: AppTest
    ):
        at = _oeffne_projekt(at, _unauffaelliges_projekt())
        assert not at.exception
        texte = [s.value for s in at.success]
        assert any("DSCR" in t for t in texte), texte

    def test_verletzung_wird_als_fehler_ausgewiesen(
        self, project, global_assumptions
    ):
        """Bei sehr hoher Fremdkapitalquote reicht der Cashflow den
        Schuldendienst nicht - das muss als Nachschussbedarf mit
        externem Kapital erscheinen."""
        from engine import run_valuation

        project.eigenkapitalquote_pct = 0.02
        project.fremdkapitalzins_pct = 0.09
        analyse = run_valuation(project, global_assumptions).kovenanten

        assert analyse.hat_event_of_default
        assert analyse.nachschuss_gesamt_eur > 0
        assert analyse.braucht_externes_kapital


class TestInvestkostenUmschalter:
    """Jedes Investkosten-Feld hat einen eigenen Umschalter zwischen
    spezifischer Eingabe (€/kWp, Vorbelegung) und Gesamtbetrag (€) -
    siehe app/components/project_form.py."""

    def _formular(self, at: AppTest) -> AppTest:
        _gehe_zu(at, "nav_neu")
        assert not at.exception
        return at

    def test_jedes_feld_hat_einen_eigenen_schalter(self, at: AppTest):
        at = self._formular(at)
        schalter = [t for t in at.get("toggle")
                    if t.key and t.key.endswith("_absolut")]
        # Neun CAPEX-Positionen (EPC ... Poenale + Puffer).
        assert len(schalter) == 9
        assert all(s.value is False for s in schalter), "Vorbelegung ist €/kWp"

    def test_umschalten_rechnet_den_eingegebenen_wert_um(self, at: AppTest):
        at = self._formular(at)
        leistung = [n for n in at.get("number_input")
                    if n.key == "neues_projekt_leistung_live"][0].value
        epc_vorher = [n for n in at.get("number_input")
                      if n.key == "neues_projekt_epc"][0].value

        [t for t in at.get("toggle") if t.key == "neues_projekt_epc_absolut"][0] \
            .set_value(True)
        at.run()
        assert not at.exception

        epc_nachher = [n for n in at.get("number_input")
                       if n.key == "neues_projekt_epc"][0]
        assert epc_nachher.value == pytest.approx(epc_vorher * leistung, rel=1e-6)
        assert "(€)" in epc_nachher.label

    def test_schalter_wirken_unabhaengig_voneinander(self, at: AppTest):
        at = self._formular(at)
        [t for t in at.get("toggle") if t.key == "neues_projekt_epc_absolut"][0] \
            .set_value(True)
        at.run()
        andere = [n for n in at.get("number_input")
                  if n.key == "neues_projekt_netz"][0]
        assert "(€/kWp)" in andere.label


class TestFreieKostenpositionen:
    """Zusaetzliche Invest- und Betriebskostenpositionen mit frei
    gewaehlter Bezeichnung - je eine dynamische Tabelle im Projektformular
    (app/components/project_form.py)."""

    def _formular(self, at: AppTest) -> AppTest:
        _gehe_zu(at, "nav_neu")
        assert not at.exception
        return at

    def test_beide_bloecke_starten_zugeklappt(self, at: AppTest):
        """Zusatzpositionen sind der Ausnahmefall - die Tabellen sollen die
        Maske nicht dauerhaft belasten."""
        at = self._formular(at)
        schalter = {
            t.key: t.value for t in at.get("toggle")
            if t.key and t.key.endswith("_zusatz_anzeigen")
        }
        assert schalter == {
            "neues_projekt_capex_zusatz_anzeigen": False,
            "neues_projekt_opex_zusatz_anzeigen": False,
        }
        # Der dynamische Editor erscheint im AppTest-Baum als "dataframe".
        keys = {e.key for e in at.get("dataframe") if e.key}
        assert "neues_projekt_capex_zusatz" not in keys
        assert "neues_projekt_opex_zusatz" not in keys

    def test_schalter_blendet_die_tabelle_ein(self, at: AppTest):
        at = self._formular(at)
        [t for t in at.get("toggle")
         if t.key == "neues_projekt_capex_zusatz_anzeigen"][0].set_value(True)
        at.run()
        assert not at.exception

        keys = {e.key for e in at.get("dataframe") if e.key}
        assert "neues_projekt_capex_zusatz" in keys
        # Der zweite Block bleibt davon unberuehrt.
        assert "neues_projekt_opex_zusatz" not in keys

        editor = [e for e in at.get("dataframe")
                  if e.key == "neues_projekt_capex_zusatz"][0]
        assert editor.value.empty
        assert list(editor.value.columns) == ["Position", "Wert"]

    def test_zeilen_ohne_bezeichnung_werden_verworfen(self):
        """Eine leere Zeile im Editor (Nutzer klickt '+', tippt nichts)
        darf kein namenloses Modellobjekt erzeugen."""
        import pandas as pd

        from app.components.project_form import _bereinige_positionen

        roh = pd.DataFrame(
            [{"Position": "Zaun", "Wert": 25_000.0},
             {"Position": "", "Wert": 100.0},
             {"Position": "  ", "Wert": None},
             {"Position": "Kran", "Wert": None}]
        )
        assert _bereinige_positionen(roh) == [
            {"Position": "Zaun", "Wert": 25_000.0},
            {"Position": "Kran", "Wert": 0.0},
        ]

    def test_reservierter_name_wird_am_formular_gemeldet(self):
        """Jede Betriebskostenposition wird zu einer Spalte der
        Cashflow-Zeitreihe - ein reservierter Name muss als Hinweis am
        Formular erscheinen, nicht als Streamlit-Fehlerseite."""
        from app.components.project_form import _namensfehler

        assert _namensfehler([{"Position": "Zaun", "Wert": 1.0}]) is None
        meldung = _namensfehler([{"Position": "opex_gesamt_eur", "Wert": 1.0}])
        assert meldung and "opex_gesamt_eur" in meldung


class TestKopfzeileUndKacheln:
    """Zwei gemeldete Darstellungsfehler in schmalen Fenstern (siehe
    app/theme.py): der Kopfzeilentitel verschwand hinter Streamlits
    eigener Kopfleiste, und die KPI-Werte wurden abgeschnitten."""

    def _css(self) -> str:
        import pathlib

        return pathlib.Path("app/theme.py").read_text(encoding="utf-8")

    def test_inhalt_beginnt_unter_streamlits_kopfleiste(self):
        """Streamlits header[data-testid='stHeader'] ist 60px hoch und
        deckend - der obere Rand muss ihn freihalten."""
        import re

        treffer = re.search(r"\.block-container \{\{ padding-top: ([\d.]+)rem",
                            self._css())
        assert treffer, "padding-top der .block-container nicht gefunden"
        assert float(treffer.group(1)) * 16 >= 60

    def test_kpi_zeile_bricht_in_schmalen_fenstern_um(self):
        css = self._css()
        assert "@media (max-width: 1150px)" in css
        assert "grid-template-columns: repeat(3, minmax(0, 1fr))" in css
        assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in css
