"""
Die Speicherbewertung in der Oberflaeche.

Der Dispatch selbst ist in test_storage_dispatch.py und
test_storage_valuation.py geprueft. Hier geht es um die drei Zusagen,
die die Oberflaeche gibt:

    1. Ein Dispatch laeuft NUR auf Knopfdruck. Nichts an dieser Seite
       darf ihn nebenbei ausloesen - er dauert eine halbe Minute.
    2. Ein Ergebnis, das nicht mehr zum Projekt passt, fliesst NICHT in
       die Kennzahlen ein. Lieber keine Speicherzahl als eine falsche.
    3. Die Auslegung ueberlebt jedes Speichern der Parameterspalte.

Punkt 3 ist keine Vorsichtsmassnahme, sondern ein behobener Fehler: Die
Maske baut den Entwurf bei jedem Durchlauf neu aus ihren Widgets, und
`battery` hat keins - es lag ausschliesslich im Overlay. Ohne
ausdrueckliche Durchreichung fiel es auf None zurueck, und ein Speichern
nach einer beliebigen anderen Aenderung loeschte den Speicher.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import PROJECTS_DIR  # noqa: E402
from engine import BatteryConfig, SpeicherModus  # noqa: E402
from engine.io_yaml import load_project_yaml, save_project_yaml  # noqa: E402
from texte import txt  # noqa: E402


def _mit_speicher(**kwargs) -> BatteryConfig:
    """Eine Auslegung - OHNE Preise.

    Die Preise stehen nicht mehr an der Auslegung, sondern in den
    Annahmen (siehe engine/storage/kosten.py). BatteryConfig lehnt sie
    ausdruecklich ab (`extra="forbid"`), damit eine aeltere Projektdatei
    beim Laden scheitert statt einen gesetzten Preis stillschweigend zu
    verlieren.

    Der Verschleisssatz steht hier AUSDRUECKLICH und folgt nicht der
    Ableitung aus dem Zellpreis: Diese Tests rufen `_loese` und
    `dispatch_jahr` direkt auf, also unterhalb der Stelle, an der
    `mit_verschleiss` die Ableitung einsetzt. Ein fester Satz haelt
    ausserdem Raster und Mitoptimierung auf demselben Massstab - genau
    darum geht es in `TestMitoptimierung`.
    """
    vorgabe = dict(
        modus=SpeicherModus.GRUENSTROM, leistung_mw=5.0, kapazitaet_mwh=10.0,
        degradationskosten_eur_mwh=2.0,
    )
    vorgabe.update(kwargs)
    return BatteryConfig(**vorgabe)


# ---------------------------------------------------------------------------
# Preisreihe und Voraussetzungen
# ---------------------------------------------------------------------------


class TestPreisreihe:
    def test_pult_und_tracker_teilen_eine_reihe(self):
        """Der Day-Ahead-Preis ist eine Eigenschaft des Marktes, nicht
        der Aufstaenderung. Zwei Dateien mit identischem Inhalt waeren
        zwei Wahrheiten ueber denselben Markt."""
        from engine.io_preise import reihe_fuer_szenario

        pult = reihe_fuer_szenario("Aurora Q3/26 · Pult · Central")
        tracker = reihe_fuer_szenario("Aurora Q3/26 · Tracker · Central")
        assert pult is not None
        assert pult == tracker

    def test_ohne_bauform_findet_dieselbe_reihe(self):
        """Im Projekt steht der Name ohne Bauform - er muss ebenfalls
        aufloesen."""
        from engine.io_preise import reihe_fuer_szenario

        assert (
            reihe_fuer_szenario("Aurora Q3/26 · Central")
            == reihe_fuer_szenario("Aurora Q3/26 · Pult · Central")
        )

    def test_szenario_ohne_reihe_meldet_none(self):
        """Kein Fehler, sondern ein sauberes None: Aeltere Jahrgaenge
        fuehren keine Stundenpreise, und das ist zulaessig."""
        from engine.io_preise import reihe_fuer_szenario

        assert reihe_fuer_szenario("Enervis 2025") is None
        assert reihe_fuer_szenario("") is None

    def test_fehlgrund_nennt_das_fehlende_stueck(self, project, global_assumptions):
        from app import speicher

        assert speicher.fehlgrund(project, global_assumptions) == (
            "oberflaeche.speicher_fehlt_auslegung"
        )
        project.battery = _mit_speicher()
        # Das Testszenario der Fixture fuehrt keine Stundenpreise.
        assert speicher.fehlgrund(project, global_assumptions) == (
            "oberflaeche.speicher_fehlt_preisreihe"
        )

    def test_abgeschalteter_speicher_zaehlt_wie_keiner(self, project):
        from app import speicher

        project.battery = _mit_speicher(aktiv=False)
        assert not speicher.hat_speicher(project)
        project.battery = _mit_speicher(leistung_mw=0.0)
        assert not speicher.hat_speicher(project)


# ---------------------------------------------------------------------------
# Fingerabdruck
# ---------------------------------------------------------------------------


class TestFingerabdruck:
    """Der Waechter gegen veraltete Zahlen.

    Geprueft wird die Richtung, die zaehlt: Eine Aenderung MUSS den
    Fingerabdruck bewegen. Der umgekehrte Fehler - ein Lauf gilt als
    veraltet, obwohl er noch passte - kostet nur einen Knopfdruck.
    """

    def _fa(self, projekt, ga):
        from app import speicher

        return speicher.fingerabdruck(projekt, ga)

    def test_gleiches_projekt_gleicher_abdruck(self, project, global_assumptions):
        project.battery = _mit_speicher()
        assert self._fa(project, global_assumptions) == self._fa(
            project.model_copy(deep=True), global_assumptions
        )

    @pytest.mark.parametrize(
        "feld,wert",
        [
            ("nennleistung_kwp", 2000.0),
            ("vollbenutzungsstunden_kwh_kwp", 1200.0),
            ("inbetriebnahme_jahr", 2029),
            ("bauform", "Tracker"),
            ("marktpreisszenario", "Aurora Q3/26 · Central"),
        ],
    )
    def test_projektaenderung_bewegt_den_abdruck(
        self, project, global_assumptions, feld, wert
    ):
        project.battery = _mit_speicher()
        vorher = self._fa(project, global_assumptions)
        setattr(project, feld, wert)
        assert self._fa(project, global_assumptions) != vorher, (
            f"{feld} veraendert den Dispatch, bewegt aber den Fingerabdruck nicht"
        )

    @pytest.mark.parametrize(
        "feld,wert",
        [
            ("leistung_mw", 8.0),
            ("kapazitaet_mwh", 20.0),
            ("roundtrip_wirkungsgrad", 0.85),
            ("modus", SpeicherModus.GRAUSTROM),
            ("degradationskosten_eur_mwh", 5.0),
            ("soc_max_pct", 0.9),
            ("aktiv", False),
        ],
    )
    def test_speicheraenderung_bewegt_den_abdruck(
        self, project, global_assumptions, feld, wert
    ):
        project.battery = _mit_speicher()
        vorher = self._fa(project, global_assumptions)
        project.battery = _mit_speicher(**{feld: wert})
        assert self._fa(project, global_assumptions) != vorher, (
            f"battery.{feld} bewegt den Fingerabdruck nicht"
        )

    def test_auch_ein_feld_ohne_dispatchwirkung_bewegt_ihn(
        self, project, global_assumptions
    ):
        """Der Fingerabdruck ist bewusst GROB - er umfasst das ganze
        Projekt. Eine gepflegte Feldliste waere praeziser und in der
        falschen Richtung gefaehrlich: Wer ein Feld vergisst, bekommt
        keinen Fehler, sondern eine Zahl, die zu einem anderen Projekt
        gehoert. Dieser Test haelt die grobe Variante fest."""
        project.battery = _mit_speicher()
        vorher = self._fa(project, global_assumptions)
        project.name = "Ein anderer Name"
        assert self._fa(project, global_assumptions) != vorher


# ---------------------------------------------------------------------------
# Kurzfassung
# ---------------------------------------------------------------------------


class TestKurzfassung:
    def test_karte_und_variantenvergleich_schreiben_gleich(self):
        """Zwei Schreibweisen fuer dieselbe Auslegung waeren eine zu
        viel - der Nutzer sieht beide nebeneinander."""
        from app.components.storage_dialog import zusammenfassung
        from app.components.varianten import _speicher

        b = _mit_speicher(modus=SpeicherModus.GRAUSTROM)
        assert zusammenfassung(b) == _speicher(b)

    def test_ohne_speicher_steht_es_da(self):
        from app.components.storage_dialog import zusammenfassung

        assert zusammenfassung(None) == "Kein Speicher"
        assert zusammenfassung(_mit_speicher(aktiv=False)) == "Kein Speicher"


# ---------------------------------------------------------------------------
# Die Maske
# ---------------------------------------------------------------------------


@pytest.fixture()
def projekt_mit_speicher():
    """Legt einen Speicher an einem ausgelieferten Projekt an und raeumt
    ihn hinterher wieder weg.

    Geschrieben wird in die KOPIE des Datenverzeichnisses (siehe
    tests/conftest.py) - die ausgelieferte Datei bleibt unberuehrt.
    """
    pfad = PROJECTS_DIR / "template-agri.yaml"
    sicherung = pfad.read_bytes()
    projekt = load_project_yaml(pfad)
    projekt.battery = _mit_speicher()
    save_project_yaml(projekt, pfad)
    try:
        yield projekt
    finally:
        pfad.write_bytes(sicherung)


def _app_mit_projekt(projekt_id: str):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=300)
    at.run()
    assert not at.exception, at.exception
    [b for b in at.button if b.key == f"open_{projekt_id}"][0].click()
    at.run()
    assert not at.exception, at.exception
    return at, f"param_{projekt_id}"


class TestMaske:
    def test_speicherkarte_zeigt_die_auslegung(self, projekt_mit_speicher):
        at, _ = _app_mit_projekt("template-agri")
        markdown = " ".join(m.value for m in at.markdown if m.value)
        assert "5,0 MW · 10,0 MWh · Grünstrom" in markdown

    def test_speichern_erhaelt_den_speicher(self, projekt_mit_speicher):
        """Der behobene Fehler. Geaendert wird ein Feld, das mit dem
        Speicher nichts zu tun hat - genau so trat er auf."""
        at, form_key = _app_mit_projekt("template-agri")
        at.session_state[f"{form_key}_ekanteil"] = 33.0
        at.run()
        assert not at.exception, at.exception
        [b for b in at.button if b.key == f"{form_key}__speichern"][0].click()
        at.run()
        assert not at.exception, at.exception

        neu = load_project_yaml(PROJECTS_DIR / "template-agri.yaml")
        assert neu.eigenkapitalquote_pct == pytest.approx(0.33)
        assert neu.battery is not None, "Das Speichern hat den Speicher geloescht"
        assert neu.battery.leistung_mw == pytest.approx(5.0)
        assert neu.battery.kapazitaet_mwh == pytest.approx(10.0)

    def test_overlay_schlaegt_den_gespeicherten_stand(self, projekt_mit_speicher):
        """Der Weg des Dialogs: Er schreibt ins Overlay, und der Entwurf
        muss ihm folgen - ohne dass der Dialog selbst laeuft (st.dialog
        ist ein Fragment und in AppTest nicht bedienbar)."""
        from app.components.project_inspector import overlay_schluessel
        from app.components.storage_dialog import SPEICHER_FELD

        at, form_key = _app_mit_projekt("template-agri")
        at.session_state[overlay_schluessel(form_key)] = {
            SPEICHER_FELD: _mit_speicher(
                leistung_mw=12.0, kapazitaet_mwh=48.0,
                modus=SpeicherModus.GRAUSTROM,
            )
        }
        at.run()
        assert not at.exception, at.exception
        markdown = " ".join(m.value for m in at.markdown if m.value)
        assert "12,0 MW · 48,0 MWh · Graustrom" in markdown

    def test_speicher_laesst_sich_aus_der_maske_entfernen(
        self, projekt_mit_speicher
    ):
        """Die Gegenrichtung: Ein abgeschalteter Speicher muss auch
        wirklich abgeschaltet gespeichert werden - sonst waere die
        Durchreichung eine Einbahnstrasse."""
        from app.components.project_inspector import overlay_schluessel
        from app.components.storage_dialog import SPEICHER_FELD

        at, form_key = _app_mit_projekt("template-agri")
        at.session_state[overlay_schluessel(form_key)] = {
            SPEICHER_FELD: _mit_speicher(aktiv=False)
        }
        at.run()
        [b for b in at.button if b.key == f"{form_key}__speichern"][0].click()
        at.run()
        assert not at.exception, at.exception
        neu = load_project_yaml(PROJECTS_DIR / "template-agri.yaml")
        assert neu.battery is not None
        assert neu.battery.aktiv is False


# ---------------------------------------------------------------------------
# Der Reiter
# ---------------------------------------------------------------------------


def _zum_speicherreiter(at, projekt_id: str = "template-agri"):
    """Wechselt in den Speicher-Reiter.

    Gesetzt wird der WIDGET-Zustand der Reiterreihe und nicht der Merker
    des Routers: Ein Widget gewinnt gegen einen programmatisch gesetzten
    Vorgabewert, der Router-Merker wuerde also beim naechsten Durchlauf
    von der Reiterreihe wieder ueberschrieben. Dieselbe Lehre steht in
    test_einspeisekurve._bereich.
    """
    from app import router
    from texte import txt

    assert "speicher" in router.PROJEKT_TABS, (
        "Der Reiter muss auch im Router stehen - sonst laesst er sich "
        "nicht ueber die Adresszeile ansteuern"
    )
    at.session_state[f"tabwahl_{projekt_id}"] = txt(
        "oberflaeche.projekt_tab_speicher"
    )
    at.run()
    assert not at.exception, at.exception
    return at


class TestReiter:
    def test_ohne_speicher_steht_ein_hinweis_und_kein_knopf(self):
        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        assert [i for i in at.info if "kein Speicher" in i.value]
        assert not [b for b in at.button
                    if b.key and b.key.startswith("speicher_rechnen_")], (
            "Ein Knopf, der nur eine Fehlermeldung erzeugen kann"
        )

    def test_mit_speicher_erscheint_der_knopf(self, projekt_mit_speicher):
        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        assert [b for b in at.button if b.key == "speicher_rechnen_template-agri"]

    def test_ohne_knopfdruck_laeuft_kein_dispatch(self, projekt_mit_speicher):
        """Die wichtigste Zusage dieser Seite.

        Geprueft wird am Ergebnis und nicht an der Laufzeit: Waere der
        Dispatch gelaufen, stuende sein Beitrag im Cashflow. Die Spalte
        ist bei jedem Projekt da (siehe engine/pipeline.py) - sie muss
        hier durchgehend null sein.
        """
        from app import services

        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)

        projekt = load_project_yaml(PROJECTS_DIR / "template-agri.yaml")
        ergebnis = services.get_valuation_fuer(projekt)
        assert ergebnis.cashflow.data["erloes_speicher_eur"].abs().sum() == 0.0
        assert "Speicher" not in ergebnis.cashflow.data.columns

    def test_status_nennt_die_preisdatei(self, projekt_mit_speicher):
        """Welche Preise gerechnet wuerden, ist die erste Rueckfrage zu
        jedem Speicherergebnis - sie gehoert vor den Knopf, nicht
        dahinter."""
        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        beschriftungen = " ".join(c.value for c in at.caption if c.value)
        assert "aurora_q3_26_central.csv.gz" in beschriftungen

    def test_szenario_ohne_stundenpreise_wird_benannt(self, projekt_mit_speicher):
        """Ein Projekt auf einem Jahrgang ohne Stundenpreise bekommt
        keinen Knopf, sondern den Namen des Szenarios - sonst raet der
        Nutzer, welche Datei fehlt."""
        pfad = PROJECTS_DIR / "template-agri.yaml"
        projekt = load_project_yaml(pfad)
        projekt.marktpreisszenario = "Aurora Q1/25 · Central"
        save_project_yaml(projekt, pfad)

        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        warnungen = " ".join(w.value for w in at.warning if w.value)
        assert "Aurora Q1/25 · Central" in warnungen
        assert not [b for b in at.button
                    if b.key and b.key.startswith("speicher_rechnen_")]


# ---------------------------------------------------------------------------
# Die Naht zur Bewertung
# ---------------------------------------------------------------------------


class TestBewertungsnaht:
    """Was ein Beitrag im Cashflow bewirkt - ohne Solver.

    Der Dispatch selbst dauert eine halbe Minute; diese Naht laesst sich
    mit einem kuenstlichen Beitrag pruefen, und genau das tut
    test_storage_valuation.py auf Engine-Ebene. Hier geht es um den Weg
    durch die Dienstschicht.
    """

    def _beitrag(self, jahre: int, wert: float):
        from engine.storage import SpeicherBeitrag

        return SpeicherBeitrag(
            wertbeitrag_eur_je_jahr=tuple([wert] * jahre),
            capex_eur=1_800_000.0,
            opex_eur_je_jahr=tuple([40_000.0] * jahre),
            jahreswerte=(),
            hinweise=(),
        )

    def test_ohne_beitrag_bleibt_alles_wie_vorher(self):
        from app import services

        projekt = load_project_yaml(PROJECTS_DIR / "template-agri.yaml")
        a = services.get_valuation_fuer(projekt)
        b = services.get_valuation_fuer(projekt, None, "")
        assert a.kpis.equity_irr == b.kpis.equity_irr
        assert a.kpis.npv_eur == b.kpis.npv_eur

    def test_beitrag_wirkt_auf_kennzahlen(self):
        from app import services

        projekt = load_project_yaml(PROJECTS_DIR / "template-agri.yaml")
        ohne = services.get_valuation_fuer(projekt)
        mit = services.get_valuation_fuer(
            projekt, self._beitrag(30, 200_000.0), "testlauf"
        )
        assert mit.kpis.capex_total_eur > ohne.kpis.capex_total_eur
        assert mit.cashflow.data["erloes_speicher_eur"].sum() > 0
        assert "Speicher" in mit.cashflow.data.columns

    def test_die_kennung_gehoert_in_den_cacheschluessel(self):
        """Zwei verschiedene Beitraege duerfen sich nicht gegenseitig aus
        dem Cache beantworten. Ohne die Kennung im Schluessel waere genau
        das der Fall - das Beitragsobjekt selbst geht am Hash vorbei."""
        from app import services

        projekt = load_project_yaml(PROJECTS_DIR / "template-agri.yaml")
        klein = services.get_valuation_fuer(
            projekt, self._beitrag(30, 50_000.0), "klein"
        )
        gross = services.get_valuation_fuer(
            projekt, self._beitrag(30, 500_000.0), "gross"
        )
        assert gross.kpis.npv_eur > klein.kpis.npv_eur


# ---------------------------------------------------------------------------
# Der Foerderanteil
# ---------------------------------------------------------------------------


class TestFoerderanteil:
    """Die Spalte, die der Dispatch braucht.

    Innerhalb der Foerderdauer bemisst sich die Marktpraemie am
    REFERENZmarktwert und nicht am erzielten Preis - der Grenzerloes
    einer verschobenen MWh ist dann die reine Preisdifferenz. Danach
    zaehlt der Preis selbst. Ohne diese Spalte muesste die Foerderdauer
    ein zweites Mal hergeleitet werden.
    """

    def _revenue(self, project, global_assumptions, jahre=25):
        from datetime import date

        from engine.energy import calculate_energy_production
        from engine.pipeline import resolve_assumptions
        from engine.revenue import calculate_revenue
        from engine.timeline import build_timeline

        global_assumptions.betriebsdauer_jahre = jahre
        a = resolve_assumptions(project, global_assumptions)
        tl = build_timeline(
            date(a.inbetriebnahme_jahr, a.inbetriebnahme_monat, 1), jahre
        )
        return calculate_revenue(tl, calculate_energy_production(tl, a), a), a

    def test_spalte_existiert_und_liegt_zwischen_null_und_eins(
        self, project, global_assumptions
    ):
        revenue, _ = self._revenue(project, global_assumptions)
        anteil = revenue["foerderanteil"].to_numpy()
        assert len(anteil) == 25
        assert anteil.min() >= 0.0
        assert anteil.max() <= 1.0

    def test_innerhalb_der_foerderdauer_eins_danach_null(
        self, project, global_assumptions
    ):
        """Inbetriebnahme im Januar: Die Foerderdauer endet dann mit
        einem vollen Betriebsjahr, ohne Rumpfjahr."""
        project.inbetriebnahme_monat = 1
        global_assumptions.eag_foerderdauer_jahre = 20
        revenue, _ = self._revenue(project, global_assumptions)
        anteil = revenue["foerderanteil"].to_numpy()
        assert anteil[0] == pytest.approx(1.0)
        assert anteil[19] == pytest.approx(1.0)
        assert anteil[20] == pytest.approx(0.0)

    def test_dezemberanschluss_erzeugt_ein_rumpfjahr(
        self, project, global_assumptions
    ):
        """Die Foerderdauer zaehlt in MONATEN. Bei Anschluss im Dezember
        laeuft sie mitten im 21. Betriebsjahr aus - der Anteil liegt dort
        zwischen null und eins."""
        project.inbetriebnahme_monat = 12
        global_assumptions.eag_foerderdauer_jahre = 20
        revenue, _ = self._revenue(project, global_assumptions)
        anteil = revenue["foerderanteil"].to_numpy()
        assert 0.0 < anteil[20] < 1.0
        assert anteil[21] == pytest.approx(0.0)


def test_speicherbeitrag_ohne_lauf_ist_none(project, global_assumptions):
    """Die Zusage in einem Satz: Ohne gerechneten Lauf gibt es keinen
    Beitrag - und damit keine Speicherzahl in den Kennzahlen."""
    from app import speicher

    project.battery = _mit_speicher()
    assert speicher.beitrag(project, global_assumptions) is None
    assert speicher.lauf(project, global_assumptions) is None
    assert speicher.letzter_lauf(project) is None
    assert speicher.veraltet(project, global_assumptions) is False


def test_projektmodell_haelt_den_speicher_ueber_yaml(tmp_path, project):
    """Ein Speicher muss das Speichern und Laden ueberstehen - sonst
    nuetzt die beste Maske nichts."""
    projekt = project
    projekt.battery = _mit_speicher(
        modus=SpeicherModus.GRAUSTROM, netzbezug_limit_mw=3.0
    )
    pfad = tmp_path / "p.yaml"
    save_project_yaml(projekt, pfad)
    neu = load_project_yaml(pfad)
    assert neu.battery is not None
    assert neu.battery.modus == SpeicherModus.GRAUSTROM
    assert neu.battery.netzbezug_limit_mw == pytest.approx(3.0)


# ---------------------------------------------------------------------------
# Preise: Erbmechanik und Rechnung
# ---------------------------------------------------------------------------


class TestSpeicherpreise:
    """Was ein Speicher kostet, ist eine MARKTANNAHME.

    Die Auslegung gehoert zum Projekt - sie folgt aus Flaeche,
    Netzanschluss und Vermarktungsidee. Der Preis nicht: Batteriepreise
    fallen Jahr fuer Jahr spuerbar, und stuenden sie an der Auslegung,
    muesste eine Preissenkung in jedem einzelnen Projekt nachgetragen
    werden.
    """

    def test_alte_preisfelder_werden_abgelehnt(self):
        """Eine aeltere Projektdatei soll beim Laden SCHEITERN und nicht
        stillschweigend einen gesetzten Preis verlieren. Genau deshalb
        traegt BatteryConfig `extra="forbid"`."""
        import pydantic

        with pytest.raises(pydantic.ValidationError):
            BatteryConfig(leistung_mw=5.0, capex_energie_eur_kwh=180.0)

    def test_ohne_abweichung_gilt_die_globale_vorgabe(
        self, project, global_assumptions
    ):
        """Ohne eigenes Angebot bleibt `speicher_capex_eur_kw` leer - und
        genau das ist das Signal, das Zwei-Parameter-Modell zu rechnen."""
        from engine.pipeline import resolve_assumptions

        global_assumptions.speicher_capex_leistung_eur_kw = 48.0
        global_assumptions.speicher_capex_energie_eur_kwh = 82.0
        global_assumptions.speicher_opex_eur_kw_jahr = 9.0
        a = resolve_assumptions(project, global_assumptions)
        assert a.speicher_capex_eur_kw is None
        assert a.speicher_capex_leistung_eur_kw == pytest.approx(48.0)
        assert a.speicher_capex_energie_eur_kwh == pytest.approx(82.0)
        assert a.speicher_opex_eur_kw_jahr == pytest.approx(9.0)

    def test_projektabweichung_schlaegt_die_vorgabe(
        self, project, global_assumptions
    ):
        """Ein Projekt mit vorliegendem Angebot weicht ab - alle uebrigen
        folgen weiter dem zentral gepflegten Preismodell."""
        from engine.models import Projektannahmen
        from engine.pipeline import resolve_assumptions
        from engine.storage import capex_eur

        project.annahmen = Projektannahmen(speicher_capex_eur_kw=390.0)
        a = resolve_assumptions(project, global_assumptions)
        assert a.speicher_capex_eur_kw == pytest.approx(390.0)
        # Ein Angebot ist ein Festpreis je kW - das Modell schweigt dann.
        assert capex_eur(
            _mit_speicher(leistung_mw=5.0, kapazitaet_mwh=10.0), a
        ) == pytest.approx(5.0 * 1000 * 390.0)
        # Das nicht abweichende Feld folgt weiterhin der Vorgabe.
        assert a.speicher_opex_eur_kw_jahr == pytest.approx(
            global_assumptions.speicher_opex_eur_kw_jahr
        )

    def test_capex_haengt_an_leistung_UND_kapazitaet(
        self, project, global_assumptions
    ):
        """Die Modellaussage, schriftlich festgehalten: Ein 5-MW-Speicher
        mit vier Stunden Dauer kostet MEHR als derselbe mit zwei Stunden.

        Der Vorlaeufer dieses Tests behauptete das Gegenteil - ein
        Festpreis je kW machte die Kapazitaet unsichtbar, und in der
        Anwendung blieb die Investition beim Verdoppeln der kWh stehen.
        """
        from engine.pipeline import resolve_assumptions
        from engine.storage import capex_eur

        global_assumptions.speicher_capex_leistung_eur_kw = 48.0
        global_assumptions.speicher_capex_energie_eur_kwh = 82.0
        a = resolve_assumptions(project, global_assumptions)
        zwei_stunden = _mit_speicher(leistung_mw=5.0, kapazitaet_mwh=10.0)
        vier_stunden = _mit_speicher(leistung_mw=5.0, kapazitaet_mwh=20.0)
        assert capex_eur(zwei_stunden, a) == pytest.approx(
            5.0 * 1000 * 48.0 + 10.0 * 1000 * 82.0
        )
        # Die doppelte Kapazitaet kostet spuerbar mehr - der Aufschlag
        # ist genau der Energieanteil der zweiten Haelfte.
        assert capex_eur(vier_stunden, a) - capex_eur(
            zwei_stunden, a
        ) == pytest.approx(10.0 * 1000 * 82.0)
        # Die LEISTUNG geht ebenso ein: doppelte Anlage, doppelter Preis.
        assert capex_eur(
            _mit_speicher(leistung_mw=10.0, kapazitaet_mwh=20.0), a
        ) == pytest.approx(2 * capex_eur(zwei_stunden, a))

    def test_spezifische_kosten_fallen_mit_der_dauer(self):
        """Die Kurve im Annahmen-Dialog: je laenger die Dauer, desto
        billiger die kWh - der Leistungsanteil verteilt sich auf mehr
        Energie. Unter den Energieanteil faellt sie nie."""
        from engine.storage.kosten import spezifisch_eur_kwh

        a, b = 48.0, 82.0
        assert spezifisch_eur_kwh(2.0, a, b) == pytest.approx(a / 2.0 + b)
        assert spezifisch_eur_kwh(4.0, a, b) < spezifisch_eur_kwh(2.0, a, b)
        assert spezifisch_eur_kwh(100.0, a, b) > b

    def test_beide_kalibrierungen_sind_hinterlegt(self):
        """Zwei Staende nebeneinander: die Engineering-Sicht (NREL) liegt
        deutlich ueber dem heutigen Turnkey-Markt. Wer die Zahlen
        anfasst, soll die Quelle mit anfassen muessen."""
        from engine.storage.kosten import KALIBRIERUNG_STANDARD, KALIBRIERUNGEN

        assert KALIBRIERUNG_STANDARD in KALIBRIERUNGEN
        for k in KALIBRIERUNGEN.values():
            assert k.quelle and k.geltungsbereich
            assert k.leistung_eur_kw > 0 and k.energie_eur_kwh > 0
        markt = KALIBRIERUNGEN["markt"]
        technik = KALIBRIERUNGEN["engineering"]
        assert technik.leistung_eur_kw > markt.leistung_eur_kw
        assert technik.energie_eur_kwh > markt.energie_eur_kwh

    def test_unwirksamer_speicher_kostet_nichts(
        self, project, global_assumptions
    ):
        """Wer den Speicher abschaltet, um seinen Beitrag zu isolieren,
        will das Projekt OHNE ihn sehen - mit seiner Investition im
        Anlagevermoegen waere es weder das eine noch das andere."""
        from engine.pipeline import resolve_assumptions
        from engine.storage import capex_eur, opex_jahr_eur

        a = resolve_assumptions(project, global_assumptions)
        for aus in (None, _mit_speicher(aktiv=False),
                    _mit_speicher(leistung_mw=0.0)):
            assert capex_eur(aus, a) == 0.0
            assert opex_jahr_eur(aus, a) == 0.0

    def test_opex_haengt_an_der_leistung(self, project, global_assumptions):
        from engine.pipeline import resolve_assumptions
        from engine.storage import opex_jahr_eur

        global_assumptions.speicher_opex_eur_kw_jahr = 8.0
        a = resolve_assumptions(project, global_assumptions)
        assert opex_jahr_eur(_mit_speicher(leistung_mw=5.0), a) == pytest.approx(
            5.0 * 1000 * 8.0
        )

    def test_preisaenderung_bewegt_den_fingerabdruck(
        self, project, global_assumptions
    ):
        """Der Preis geht in CAPEX und OPEX ein und damit in die
        Rendite - ein gerechneter Lauf gehoert danach als veraltet
        gekennzeichnet."""
        from app import speicher
        from engine.models import Projektannahmen

        project.battery = _mit_speicher()
        vorher = speicher.fingerabdruck(project, global_assumptions)
        project.annahmen = Projektannahmen(speicher_capex_eur_kw=390.0)
        assert speicher.fingerabdruck(project, global_assumptions) != vorher

    def test_dialog_und_modell_kennen_dieselben_felder(self):
        """Der Dialog schreibt in die Projektannahmen. Ein dort
        umbenanntes Feld muss hier auffallen und nicht erst, wenn ein
        Nutzer sich wundert, dass sein Preis nicht ankommt."""
        from app.components.storage_dialog import PREISFELDER
        from engine.models import (
            EffectiveAssumptions,
            GlobalAssumptions,
            Projektannahmen,
        )

        for feld in PREISFELDER.values():
            assert feld in Projektannahmen.model_fields, feld
            assert feld in EffectiveAssumptions.model_fields, feld
        # Die globale Vorgabe hinter der Investition ist NICHT dasselbe
        # Feld: das Projekt traegt ein Angebot je kW, die Vorgabe
        # dahinter zwei Parameter. Beide muessen existieren.
        for feld in ("speicher_capex_leistung_eur_kw",
                     "speicher_capex_energie_eur_kwh",
                     "speicher_opex_eur_kw_jahr"):
            assert feld in GlobalAssumptions.model_fields, feld
            assert feld in EffectiveAssumptions.model_fields, feld


# ---------------------------------------------------------------------------
# Verschleisssatz
# ---------------------------------------------------------------------------


class TestVerschleisssatz:
    """Der Verschleiss folgt dem Zellpreis, nicht einer festen Zahl.

    Vorher standen 2,00 EUR/MWh fest im Modell - bei 82 EUR/kWh und 6000
    Zyklen sind es 13,67. Ein Faktor sieben in der Groesse, die
    entscheidet, ob eine Stunde gefahren wird. Und der feste Satz waere
    mit jedem Preisrutsch falscher geworden, ohne dass es jemandem
    auffiele.
    """

    def test_satz_folgt_aus_zellpreis_und_zyklenzahl(self, global_assumptions):
        from engine.storage.kosten import verschleiss_eur_mwh

        ga = global_assumptions.model_copy(update={
            "speicher_capex_energie_eur_kwh": 82.0,
            "speicher_zyklenlebensdauer": 6000,
        })
        # 82 EUR/kWh sind 82_000 EUR/MWh; auf 6000 Zyklen verteilt.
        assert verschleiss_eur_mwh(ga) == pytest.approx(82_000 / 6000)

    def test_billigere_zellen_senken_den_satz(self, global_assumptions):
        from engine.storage.kosten import verschleiss_eur_mwh

        teuer = global_assumptions.model_copy(update={
            "speicher_capex_energie_eur_kwh": 100.0})
        billig = global_assumptions.model_copy(update={
            "speicher_capex_energie_eur_kwh": 50.0})
        assert verschleiss_eur_mwh(billig) == pytest.approx(
            verschleiss_eur_mwh(teuer) / 2
        )

    def test_laengere_lebensdauer_senkt_den_satz(self, global_assumptions):
        from engine.storage.kosten import verschleiss_eur_mwh

        kurz = global_assumptions.model_copy(update={
            "speicher_zyklenlebensdauer": 3000})
        lang = global_assumptions.model_copy(update={
            "speicher_zyklenlebensdauer": 6000})
        assert verschleiss_eur_mwh(lang) == pytest.approx(
            verschleiss_eur_mwh(kurz) / 2
        )

    def test_leeres_feld_wird_abgeleitet(self, project, global_assumptions):
        """Kein eigener Satz am Projekt: Es gilt die Ableitung."""
        from engine.pipeline import resolve_assumptions
        from engine.storage.kosten import mit_verschleiss, verschleiss_eur_mwh

        b = _mit_speicher().model_copy(update={
            "degradationskosten_eur_mwh": None})
        a = resolve_assumptions(project, global_assumptions)
        assert mit_verschleiss(b, a).degradationskosten_eur_mwh == pytest.approx(
            verschleiss_eur_mwh(a)
        )

    def test_eigener_satz_bleibt_stehen(self, project, global_assumptions):
        """Wer eine Zellgarantie vorliegen hat, rechnet mit IHR - die
        Ableitung ist eine Vorgabe und keine Bevormundung."""
        from engine.pipeline import resolve_assumptions
        from engine.storage.kosten import mit_verschleiss

        a = resolve_assumptions(project, global_assumptions)
        b = _mit_speicher(degradationskosten_eur_mwh=5.0)
        assert mit_verschleiss(b, a).degradationskosten_eur_mwh == 5.0

    def test_eine_eingetragene_null_ist_keine_leere_angabe(
        self, project, global_assumptions
    ):
        """Null heisst "dieser Speicher verschleisst nicht" - eine
        Aussage. Waere sie nicht von "nichts eingetragen" zu
        unterscheiden, liesse sich der Satz nie abschalten."""
        from engine.pipeline import resolve_assumptions
        from engine.storage.kosten import mit_verschleiss

        a = resolve_assumptions(project, global_assumptions)
        b = _mit_speicher(degradationskosten_eur_mwh=0.0)
        assert mit_verschleiss(b, a).degradationskosten_eur_mwh == 0.0

    def test_ohne_speicher_bleibt_es_bei_None(self, project, global_assumptions):
        from engine.pipeline import resolve_assumptions
        from engine.storage.kosten import mit_verschleiss

        a = resolve_assumptions(project, global_assumptions)
        assert mit_verschleiss(None, a) is None

    def test_die_zyklenzahl_erbt_aus_den_globalen_annahmen(
        self, project, global_assumptions
    ):
        from engine.pipeline import resolve_assumptions

        ga = global_assumptions.model_copy(update={
            "speicher_zyklenlebensdauer": 4500})
        assert resolve_assumptions(project, ga).speicher_zyklenlebensdauer == 4500

    def test_hoeherer_satz_bremst_die_fahrweise(self, project, global_assumptions):
        """Die Probe aufs Ganze: Der Satz ist kein Buchhaltungsposten,
        er veraendert die Bahn. Bei sieben Mal so hohem Verschleiss
        werden Stunden nicht mehr gefahren, deren Spread ihn nicht
        deckt."""
        from engine.storage.dispatch import dispatch_jahr

        pv, preis = _kurzes_jahr()

        def durchsatz(satz):
            ergebnis = dispatch_jahr(
                pv_mw=pv, preis_eur_mwh=preis, grenzerloes_eur_mwh=preis,
                batterie=_mit_speicher(degradationskosten_eur_mwh=satz),
                export_limit_mw=3.0,
            )
            return float(ergebnis.spalte("speicher_ins_netz_mw").sum())

        assert durchsatz(60.0) < durchsatz(2.0)


# ---------------------------------------------------------------------------
# Auslegungssuche
# ---------------------------------------------------------------------------


def _kurzes_jahr(stunden: int = 96):
    """Vier Tage PV und Preise - genug fuer eine Aussage, schnell genug
    fuer einen Test.

    Ein volles Jahr braeuchte je Optimierung eine halbe Sekunde; die
    Eigenschaften, um die es hier geht (Monotonie, Unabhaengigkeit des
    Vergleichsfalls), haengen an der STRUKTUR des Modells und nicht an
    der Laenge der Reihe.
    """
    import numpy as np

    t = np.arange(stunden)
    # Tagesgang der Erzeugung, nachts null.
    pv = np.clip(np.sin((t % 24 - 6) / 12 * np.pi), 0, None) * 4.0
    # Preise mit Abendspitze - sonst gaebe es nichts zu verschieben.
    preis = 40.0 + 35.0 * np.sin((t % 24 - 10) / 12 * np.pi)
    return pv, preis


class TestAuslegungsraster:
    """Das Raster selbst - ohne eine einzige Optimierung."""

    def test_kapazitaet_ist_ein_ganzzahliges_vielfaches(self):
        """Die ausdrueckliche Vorgabe: kein 1,146-Stunden-Speicher."""
        from engine.storage import auslegung as au

        for k in au.raster((2.0, 4.0), (2, 4, 12)):
            assert k.kapazitaet_mwh == pytest.approx(
                k.leistung_mw * k.dauer_h
            )
            assert float(k.dauer_h).is_integer()

    def test_die_leistungen_kommen_absolut_in_mw(self):
        """Prozentwerte waren die erste Fassung und die schlechtere:
        "75 %" beantwortet die Frage nicht, solange nicht danebensteht,
        wovon - und genau diese Rueckfrage kam aus der Anwendung, mit
        drei plausiblen Kandidaten (Modulleistung, Einspeiseleistung,
        eingestellter Speicher). In MW stellt sie sich nicht."""
        from engine.storage import auslegung as au

        kandidaten = au.raster((0.9, 1.9), (4,))
        assert [k.leistung_mw for k in kandidaten] == pytest.approx([0.9, 1.9])

    def test_die_stufen_sind_runde_zahlen_in_zehntel_mw(self):
        """Ein Speicher wird nicht auf drei Nachkommastellen bestellt.
        Und die Liste soll runde Zahlen zeigen (0,5 / 1,0 / 1,5 MW),
        nicht die krummen Vielfachen eines Prozentsatzes."""
        from engine.storage import auslegung as au

        for bezug in (0.5, 1.99, 7.0, 10.0, 32.0):
            stufen = au.leistungsstufen(bezug)
            assert stufen, bezug
            for mw in stufen:
                zehntel = mw / au.LEISTUNGSSCHRITT_MW
                assert abs(zehntel - round(zehntel)) < 1e-9, (bezug, mw)
            # Die Liste bleibt bedienbar - keine hundert Eintraege.
            assert 5 <= len(stufen) <= 25, (bezug, len(stufen))
            # Und sie reicht ueber den Anschluss hinaus: Laden aus der
            # PV-Anlage ist nicht durch die Einspeisegrenze beschraenkt.
            assert stufen[-1] > bezug

    def test_die_vorauswahl_spannt_den_anschluss_auf(self):
        from engine.storage import auslegung as au

        standard = au.leistungen_standard(10.0)
        assert len(standard) == 4
        assert standard == tuple(sorted(standard))
        assert standard[-1] == pytest.approx(10.0)
        assert all(s in au.leistungsstufen(10.0) for s in standard)

    def test_der_bezug_ist_das_exportlimit_des_projekts(
        self, project, global_assumptions
    ):
        """Dieselbe Groesse, mit der auch die Kappung gerechnet wird -
        PV und Speicher teilen sich EINEN Anschluss."""
        from app import speicher

        project.nennleistung_kwp = 2840.0
        global_assumptions.einspeiselimit_pct = 0.7
        assert speicher.einspeiseleistung_mw(
            project, global_assumptions
        ) == pytest.approx(2.84 * 0.7)

    def test_die_vorlage_gibt_alles_ausser_der_groesse_vor(self):
        """Das Raster beantwortet die Groessenfrage und keine andere.

        Wuerde es nebenbei die Betriebsart oder den Wirkungsgrad
        veraendern, verglichen die Punkte nicht mehr dieselbe Anlage in
        verschiedenen Groessen, sondern verschiedene Anlagen.
        """
        from engine.storage import auslegung as au

        vorlage = _mit_speicher(
            modus=SpeicherModus.GRAUSTROM, roundtrip_wirkungsgrad=0.83,
            soc_min_pct=0.12, degradationskosten_eur_mwh=6.5,
            netzbezug_limit_mw=2.0,
        )
        b = au.Kandidat(leistungsanteil=0.5, leistung_mw=3.0, dauer_h=4).batterie(
            vorlage
        )
        assert b.leistung_mw == pytest.approx(3.0)
        assert b.kapazitaet_mwh == pytest.approx(12.0)
        for feld in ("modus", "roundtrip_wirkungsgrad", "soc_min_pct",
                     "degradationskosten_eur_mwh", "netzbezug_limit_mw"):
            assert getattr(b, feld) == getattr(vorlage, feld), feld

    def test_ein_abgeschalteter_speicher_wird_als_vorlage_eingeschaltet(self):
        """Sonst rechnete das ganze Raster lauter Nullen - und die Frage
        "lohnt sich hier ueberhaupt einer?" liesse sich nicht stellen."""
        from engine.storage import auslegung as au

        b = au.Kandidat(leistungsanteil=1.0, leistung_mw=2.0, dauer_h=2).batterie(
            _mit_speicher(aktiv=False)
        )
        assert b.aktiv is True and b.wirksam


class TestStuetzjahre:
    """Wo die gerechneten Jahre liegen - und warum dort."""

    def _foerderung(self, jahre: int, bis: int):
        return [1.0 if i < bis else 0.0 for i in range(jahre)]

    def test_kein_block_ueberschreitet_die_foerdergrenze(self):
        """Der Uebergang ist ein Sprung: Innerhalb der Foerderdauer
        bemisst sich die Praemie am Referenzmarktwert, danach zaehlt der
        erzielte Preis. Ein Block ueber die Grenze mittelte zwei
        verschiedene Welten."""
        from engine.storage.auslegung import bloecke

        anteil = self._foerderung(30, 20)
        for anzahl in (2, 3, 4, 6, 8):
            for block in bloecke(anteil, 30, anzahl):
                drin = {anteil[i] > 0.5 for i in block}
                assert len(drin) == 1, (
                    f"Block {block} liegt teils in, teils ausserhalb der "
                    f"Foerderdauer (anzahl={anzahl})"
                )

    def test_jeder_abschnitt_bekommt_mindestens_einen_block(self):
        """Bei zwanzig Foerderjahren und dreissig Betriebsjahren ist die
        Zeit danach ein Drittel der Laufzeit. Sie zu ueberspringen, weil
        zwei Stuetzjahre gewaehlt sind, waere kein Naeherungsfehler,
        sondern ein blinder Fleck."""
        from engine.storage.auslegung import bloecke

        anteil = self._foerderung(30, 20)
        geteilt = bloecke(anteil, 30, 1)
        assert len(geteilt) == 2
        assert {anteil[b[0]] > 0.5 for b in geteilt} == {True, False}

    def test_fruehe_bloecke_sind_kuerzer(self):
        """Gewichtet statt gleich lang - ein Fehler in Jahr 3 verzieht
        die Rendite weit staerker als einer in Jahr 28. Gemessen sank der
        Renditefehler dadurch von 1,15 auf 0,06 Prozentpunkte."""
        from engine.storage.auslegung import bloecke

        geteilt = bloecke(self._foerderung(30, 20), 30, 4)
        in_foerderung = [b for b in geteilt if b[0] < 20]
        assert len(in_foerderung) >= 2
        assert len(in_foerderung[0]) < len(in_foerderung[-1]), (
            "Der erste Block muss weniger Jahre vertreten als der letzte"
        )

    def test_bloecke_decken_jedes_jahr_genau_einmal_ab(self):
        """Ein vergessenes Jahr faellt aus dem Wertbeitrag heraus, ein
        doppelt vertretenes zaehlt zweimal. Beides bliebe in der Summe
        unauffaellig."""
        from engine.storage.auslegung import bloecke

        for anteil, jahre in ((self._foerderung(30, 20), 30),
                              (None, 25), (self._foerderung(12, 12), 12)):
            for anzahl in (1, 2, 3, 5, 40):
                geteilt = bloecke(anteil, jahre, anzahl)
                flach = [i for b in geteilt for i in b]
                assert sorted(flach) == list(range(jahre)), (
                    f"anzahl={anzahl}, jahre={jahre}"
                )

    def test_mehr_stuetzjahre_als_betriebsjahre_gehen_nicht_schief(self):
        from engine.storage.auslegung import bloecke

        geteilt = bloecke(None, 5, 99)
        assert len(geteilt) == 5
        assert all(len(b) == 1 for b in geteilt)


class TestHochrechnung:
    def test_verschleiss_folgt_der_menge_und_nicht_dem_preisniveau(self):
        """Ein pauschaler Faktor auf den Deckungsbeitrag haette den
        Verschleiss mit hochinflationiert. Sein Satz steht aber in
        EUR/MWh und wird im Modell nicht inflationiert - der Speicherwert
        der spaeten Jahre kaeme sonst zu klein heraus."""
        from engine.storage.auslegung import hochrechnen
        from engine.storage.models import StorageJahreswert

        wert = StorageJahreswert(
            jahr=1, kalenderjahr=2030,
            mehrerloes_eur=100_000.0, netzbezugskosten_eur=0.0,
            degradationskosten_eur=20_000.0,
            mehrmenge_kwh=0.0, rueckgewonnene_kappung_kwh=0.0,
            speicher_ladung_mwh=0.0, speicher_entladung_mwh=0.0,
            vollzyklen=0.0,
        )
        # Doppeltes Preisniveau, gleiche Menge.
        assert hochrechnen(
            wert, niveau_stuetze=1.0, niveau_ziel=2.0,
            menge_stuetze=100.0, menge_ziel=100.0,
        ) == pytest.approx(200_000.0 - 20_000.0)
        # Gleiches Preisniveau, doppelte Menge: BEIDE Teile verdoppeln.
        assert hochrechnen(
            wert, niveau_stuetze=1.0, niveau_ziel=1.0,
            menge_stuetze=100.0, menge_ziel=200.0,
        ) == pytest.approx(200_000.0 - 40_000.0)

    def test_das_stuetzjahr_selbst_bleibt_unveraendert(self):
        from engine.storage.auslegung import hochrechnen
        from engine.storage.models import StorageJahreswert

        wert = StorageJahreswert(
            jahr=5, kalenderjahr=2034,
            mehrerloes_eur=80_000.0, netzbezugskosten_eur=5_000.0,
            degradationskosten_eur=12_000.0,
            mehrmenge_kwh=0.0, rueckgewonnene_kappung_kwh=0.0,
            speicher_ladung_mwh=0.0, speicher_entladung_mwh=0.0,
            vollzyklen=0.0,
        )
        assert hochrechnen(
            wert, niveau_stuetze=1.4, niveau_ziel=1.4,
            menge_stuetze=90.0, menge_ziel=90.0,
        ) == pytest.approx(wert.deckungsbeitrag_eur)


class TestVergleichsfall:
    """Der PV-only-Lauf, der je Stuetzjahr nur EINMAL gerechnet wird.

    Die Ersparnis ist die Haelfte der Laufzeit des Rasterlaufs, und sie
    steht und faellt mit einer Behauptung: Der Vergleichsfall haengt an
    keiner Eigenschaft des Speichers. Stimmte das nicht, bekaeme jeder
    Rasterpunkt denselben falschen Massstab - und der Fehler faende sich
    nirgends im Ergebnis wieder.
    """

    def test_er_haengt_nicht_an_der_batterie(self):
        from engine.storage.dispatch import _ABREGELUNG, _loese, vergleichsfall

        pv, preis = _kurzes_jahr()
        erwartet = vergleichsfall(pv, preis, preis, export_limit_mw=3.0)
        for kwargs in ({"leistung_mw": 5.0, "kapazitaet_mwh": 20.0},
                       {"leistung_mw": 0.5, "kapazitaet_mwh": 1.0,
                        "roundtrip_wirkungsgrad": 0.7},
                       {"leistung_mw": 50.0, "kapazitaet_mwh": 200.0,
                        "degradationskosten_eur_mwh": 30.0}):
            aus = _mit_speicher(**kwargs).model_copy(update={"aktiv": False})
            bahn, ziel = _loese(pv, preis, preis, aus, 3.0)
            assert ziel == pytest.approx(erwartet[0])
            assert float(bahn[:, _ABREGELUNG].sum()) == pytest.approx(erwartet[1])

    def test_durchgereicht_kommt_dasselbe_heraus(self):
        """Die Abkuerzung darf keine andere Zahl liefern als der
        gewoehnliche Weg - sonst waere sie keine Abkuerzung, sondern ein
        zweites Modell."""
        from engine.storage import dispatch_jahr, vergleichsfall

        pv, preis = _kurzes_jahr()
        b = _mit_speicher(leistung_mw=2.0, kapazitaet_mwh=8.0)
        ohne_abkuerzung = dispatch_jahr(pv, preis, preis, b, 3.0)
        mit_abkuerzung = dispatch_jahr(
            pv, preis, preis, b, 3.0,
            vergleich=vergleichsfall(pv, preis, preis, 3.0),
        )
        assert mit_abkuerzung.wertbeitrag_eur == pytest.approx(
            ohne_abkuerzung.wertbeitrag_eur
        )
        assert mit_abkuerzung.abregelung_pv_only_mwh == pytest.approx(
            ohne_abkuerzung.abregelung_pv_only_mwh
        )


class TestMonotonie:
    """Mehr Speicher kann nicht weniger wert sein.

    Der zulaessige Bereich eines groesseren Speichers UMFASST den des
    kleineren: Er darf alles, was der kleinere darf, und mehr. Sein
    Optimum kann deshalb nicht darunter liegen. Der Verschleiss aendert
    daran nichts - er steht in der Zielfunktion, und was sich nicht
    lohnt, laesst der Optimierer bleiben.

    Faellt dieser Test, ist etwas an der Formulierung des LP falsch, und
    zwar so, dass es in einem einzelnen Ergebnis nicht auffiele.
    """

    def test_mehr_leistung_ist_nie_schlechter(self):
        from engine.storage import dispatch_jahr, vergleichsfall

        pv, preis = _kurzes_jahr()
        vergleich = vergleichsfall(pv, preis, preis, 3.0)
        werte = [
            dispatch_jahr(
                pv, preis, preis,
                _mit_speicher(leistung_mw=mw, kapazitaet_mwh=8.0), 3.0,
                vergleich=vergleich,
            ).wertbeitrag_eur
            for mw in (0.5, 1.0, 2.0, 4.0)
        ]
        for kleiner, groesser in zip(werte, werte[1:], strict=False):
            assert groesser >= kleiner - 1e-6, werte

    def test_mehr_kapazitaet_ist_nie_schlechter(self):
        from engine.storage import dispatch_jahr, vergleichsfall

        pv, preis = _kurzes_jahr()
        vergleich = vergleichsfall(pv, preis, preis, 3.0)
        werte = [
            dispatch_jahr(
                pv, preis, preis,
                _mit_speicher(leistung_mw=2.0, kapazitaet_mwh=mwh), 3.0,
                vergleich=vergleich,
            ).wertbeitrag_eur
            for mwh in (1.0, 4.0, 8.0, 16.0, 32.0)
        ]
        for kleiner, groesser in zip(werte, werte[1:], strict=False):
            assert groesser >= kleiner - 1e-6, werte


class TestRasterabdruck:
    """Wann ein gerechnetes Raster noch gilt."""

    def test_groesse_des_speichers_zaehlt_nicht(self, project, global_assumptions):
        """Der erste Nutzen der Suche ist, ihr Ergebnis zu uebernehmen -
        und genau das erklaerte ihr eigenes Ergebnis fuer veraltet, wenn
        Leistung und Kapazitaet mitzaehlten."""
        from app import speicher

        project.battery = _mit_speicher(leistung_mw=3.0, kapazitaet_mwh=12.0)
        vorher = speicher.raster_abdruck(
            project, global_assumptions, (0.5, 1.0), (2, 4), 4
        )
        project.battery = _mit_speicher(leistung_mw=7.0, kapazitaet_mwh=42.0)
        assert speicher.raster_abdruck(
            project, global_assumptions, (0.5, 1.0), (2, 4), 4
        ) == vorher

    @pytest.mark.parametrize(
        "feld,wert",
        [
            ("modus", SpeicherModus.GRAUSTROM),
            ("roundtrip_wirkungsgrad", 0.8),
            ("degradationskosten_eur_mwh", 9.0),
            ("soc_max_pct", 0.85),
        ],
    )
    def test_alles_uebrige_am_speicher_zaehlt_sehr_wohl(
        self, project, global_assumptions, feld, wert
    ):
        """Die Ausnahme ist eng: Sie gilt fuer die beiden Groessen, die
        das Raster ersetzt, und fuer keine andere."""
        from app import speicher

        project.battery = _mit_speicher()
        vorher = speicher.raster_abdruck(
            project, global_assumptions, (0.5,), (4,), 4
        )
        project.battery = _mit_speicher(**{feld: wert})
        assert speicher.raster_abdruck(
            project, global_assumptions, (0.5,), (4,), 4
        ) != vorher, f"battery.{feld} bewegt den Rasterabdruck nicht"

    def test_das_raster_selbst_zaehlt(self, project, global_assumptions):
        from app import speicher

        project.battery = _mit_speicher()
        grund = speicher.raster_abdruck(
            project, global_assumptions, (0.5, 1.0), (2, 4), 4
        )
        for anteile, dauern, stuetzjahre in (
            ((0.5, 1.0, 1.5), (2, 4), 4),
            ((0.5, 1.0), (2, 4, 8), 4),
            ((0.5, 1.0), (2, 4), 6),
        ):
            assert speicher.raster_abdruck(
                project, global_assumptions, anteile, dauern, stuetzjahre
            ) != grund

    def test_die_reihenfolge_der_wahl_zaehlt_nicht(
        self, project, global_assumptions
    ):
        """Ein Multiselect gibt die Werte in Klickreihenfolge zurueck.
        Zweimal dasselbe Raster in anderer Reihenfolge zu waehlen, darf
        keinen zweiten Lauf ausloesen."""
        from app import speicher

        project.battery = _mit_speicher()
        assert speicher.raster_abdruck(
            project, global_assumptions, (1.0, 0.5), (4, 2), 4
        ) == speicher.raster_abdruck(
            project, global_assumptions, (0.5, 1.0), (2, 4), 4
        )


class TestAuslegungImReiter:
    def test_der_abschnitt_erscheint_mit_seinen_reglern(
        self, projekt_mit_speicher
    ):
        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        assert [b for b in at.button if b.key == "raster_rechnen_template-agri"]
        schluessel = {m.key for m in at.multiselect}
        assert "raster_leistungen_template-agri" in schluessel
        assert "raster_dauern_template-agri" in schluessel

    def test_ohne_knopfdruck_laeuft_kein_raster(self, projekt_mit_speicher):
        """Dieselbe Zusage wie beim Dispatch, und hier noch wichtiger:
        Ein Rasterlauf dauert Minuten, nicht Sekunden."""
        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        # AppTest reicht den Session-State ohne dict-Schnittstelle
        # durch - `in` und `[]` sind der Weg, `.get` gibt es nicht.
        assert (
            "speicher_raster" not in at.session_state
            or at.session_state["speicher_raster"].get("template-agri", {}) == {}
        )

    def test_ohne_auswahl_kein_knopf(self, projekt_mit_speicher):
        at, _ = _app_mit_projekt("template-agri")
        at.session_state["tabwahl_template-agri"] = txt(
            "oberflaeche.projekt_tab_speicher"
        )
        at.session_state["raster_dauern_template-agri"] = []
        at.run()
        assert not at.exception, at.exception
        assert not [b for b in at.button
                    if b.key == "raster_rechnen_template-agri"]

    def test_ein_kleines_raster_laeuft_und_laesst_sich_uebernehmen(
        self, projekt_mit_speicher
    ):
        """Der ganze Weg in einem Test: rechnen, Optimum anzeigen,
        uebernehmen. Bewusst winzig gehalten (vier Auslegungen, zwei
        Stuetzjahre) - geprueft wird der Weg, nicht die Zahl.

        Uebernommen wird in den ENTWURF und nicht auf die Platte: Die
        Speicherkarte muss die neue Groesse zeigen, die Datei aber noch
        die alte.
        """
        at, form_key = _app_mit_projekt("template-agri")
        at.session_state["tabwahl_template-agri"] = txt(
            "oberflaeche.projekt_tab_speicher"
        )
        at.session_state["raster_leistungen_template-agri"] = [1.0, 2.0]
        at.session_state["raster_dauern_template-agri"] = [2, 4]
        at.session_state["raster_stuetzjahre_template-agri"] = 2
        at.run()
        assert not at.exception, at.exception

        [b for b in at.button if b.key == "raster_rechnen_template-agri"][0].click()
        at.run()
        assert not at.exception, at.exception
        beschriftungen = [m.label for m in at.metric]
        assert "Beste EK-Rendite" in beschriftungen
        assert "Bester Barwert" in beschriftungen

        uebernehmen = [b for b in at.button
                       if b.key == "raster_uebernehmen_template-agri"]
        assert uebernehmen, "Ohne Uebernehmen-Knopf bliebe das Ergebnis folgenlos"
        uebernehmen[0].click()
        at.run()
        assert not at.exception, at.exception

        markdown = " ".join(m.value for m in at.markdown if m.value)
        assert "5,0 MW · 10,0 MWh" not in markdown, (
            "Die Speicherkarte zeigt weiter die alte Auslegung"
        )
        auf_platte = load_project_yaml(PROJECTS_DIR / "template-agri.yaml")
        assert auf_platte.battery.leistung_mw == pytest.approx(5.0), (
            "Uebernehmen darf nur den Entwurf aendern, nicht die Datei"
        )


class TestMitoptimierung:
    """Der Optimierer: Leistung und Kapazitaet als Variablen desselben LP.

    Das Versprechen eines Optimierers ist ein einziges, und es laesst
    sich pruefen: Es gibt keine bessere Loesung. Genau das steht hier -
    nicht "das Ergebnis sieht plausibel aus", sondern: KEIN
    nachgerechneter Punkt schlaegt ihn in seiner eigenen Zielfunktion.
    """

    def _eingabe(self, stunden: int = 168):
        import numpy as np

        from engine.storage.valuation import Jahreseingabe

        pv, preis = _kurzes_jahr(stunden)
        return Jahreseingabe(
            jahr=1, kalenderjahr=2030,
            pv_mw=np.asarray(pv), preise_eur_mwh=np.asarray(preis),
            grenzerloes_eur_mwh=np.asarray(preis),
            export_limit_mw=3.0,
        )

    #: Wofuer das kurze Testjahr steht.
    #:
    #: Die Investition faellt EINMAL an, der Deckungsbeitrag jedes Jahr.
    #: Eine Woche gegen den vollen Kaufpreis zu stellen, ergaebe immer
    #: dasselbe Ergebnis - keinen Speicher -, und der Test pruefte nichts
    #: mehr. Das Gewicht rechnet die Woche deshalb auf eine realistische
    #: Zahl von Betriebsjahren hoch: rund 52 Wochen mal gut ein Dutzend
    #: abgezinster Jahre.
    _GEWICHT = 600.0

    def _kosten(self, assumptions, betriebsjahre, leistung_mw, kapazitaet_mwh):
        from engine.storage.optimum import _barwertfaktoren

        barwert_opex, schild = _barwertfaktoren(
            assumptions, betriebsjahre, 0.08
        )
        return 1000.0 * (
            leistung_mw * (
                assumptions.speicher_capex_leistung_eur_kw * (1.0 - schild)
                + assumptions.speicher_opex_eur_kw_jahr * barwert_opex
            )
            + kapazitaet_mwh
            * assumptions.speicher_capex_energie_eur_kwh * (1.0 - schild)
        )

    def test_kein_punkt_schlaegt_das_optimum(self, project, global_assumptions):
        """Die definierende Eigenschaft. Nachgerechnet werden Punkte rund
        um das gefundene Optimum UND weit daneben - faende sich einer,
        der besser ist, waere der Optimierer keiner."""
        from engine.pipeline import resolve_assumptions
        from engine.storage import dispatch_jahr, optimum_stetig

        a = resolve_assumptions(project, global_assumptions)
        vorlage = _mit_speicher()
        eingabe = self._eingabe()
        gewicht = self._GEWICHT

        optimum = optimum_stetig(
            a, vorlage, [eingabe], [(gewicht, gewicht)],
            betriebsjahre=20, leistung_hoechstens_mw=3.0,
        )
        assert optimum.wirksam, "Auf diesen Preisen muss sich einer lohnen"

        steuer = a.steuersatz_pct
        for faktor_p, faktor_e in [
            (1.0, 1.0), (0.5, 0.5), (2.0, 2.0), (1.0, 0.5), (1.0, 2.0),
            (0.5, 1.0), (2.0, 1.0), (0.25, 4.0), (1.2, 1.2), (0.8, 0.8),
        ]:
            leistung = min(optimum.leistung_mw * faktor_p, 3.0)
            kapazitaet = optimum.kapazitaet_mwh * faktor_e
            if leistung <= 0 or kapazitaet <= 0:
                continue
            ergebnis = dispatch_jahr(
                eingabe.pv_mw, eingabe.preise_eur_mwh,
                eingabe.grenzerloes_eur_mwh,
                vorlage.model_copy(update={
                    "aktiv": True, "leistung_mw": leistung,
                    "kapazitaet_mwh": kapazitaet,
                }),
                eingabe.export_limit_mw,
            )
            wert = (
                (1.0 - steuer) * gewicht * ergebnis.wertbeitrag_eur
                - self._kosten(a, 20, leistung, kapazitaet)
            )
            assert optimum.barwert_eur >= wert - 1.0, (
                f"{leistung:.2f} MW / {kapazitaet:.2f} MWh ist besser "
                f"({wert:,.0f} statt {optimum.barwert_eur:,.0f})"
            )

    def test_die_leistungsgrenze_wird_eingehalten(
        self, project, global_assumptions
    ):
        """Der Deckel ist die Einspeiseleistung. Eine Entladeleistung
        darueber koennte zu keinem Zeitpunkt abfliessen - sie waere kein
        Optimum, sondern ein Rechenartefakt."""
        from engine.pipeline import resolve_assumptions
        from engine.storage import optimum_stetig

        a = resolve_assumptions(project, global_assumptions)
        eingabe = self._eingabe()
        for deckel in (0.5, 1.5):
            optimum = optimum_stetig(
                a, _mit_speicher(), [eingabe], [(self._GEWICHT, self._GEWICHT)],
                betriebsjahre=20, leistung_hoechstens_mw=deckel,
            )
            assert optimum.leistung_mw <= deckel + 1e-6
            # `am_deckel` muss genau dann melden, wenn der Deckel auch
            # wirklich bindet. Ein Punkt am Rand ist kein Optimum,
            # sondern die Stelle, an der der Netzanschluss aufhoert -
            # und die Meldung darf weder fehlen noch zu frueh kommen.
            assert optimum.am_deckel == (
                optimum.leistung_mw >= deckel - 1e-6
            )

    def test_zu_teuer_heisst_kein_speicher(self, project, global_assumptions):
        """Ein Optimum bei null ist eine Antwort und kein Fehler: Bei
        diesen Preisen ist der beste Speicher der, den es nicht gibt."""
        from engine.pipeline import resolve_assumptions
        from engine.storage import optimum_stetig

        global_assumptions.speicher_capex_leistung_eur_kw = 50_000.0
        global_assumptions.speicher_capex_energie_eur_kwh = 50_000.0
        a = resolve_assumptions(project, global_assumptions)
        optimum = optimum_stetig(
            a, _mit_speicher(), [self._eingabe()], [(self._GEWICHT, self._GEWICHT)],
            betriebsjahre=20, leistung_hoechstens_mw=3.0,
        )
        assert not optimum.wirksam
        assert optimum.leistung_mw == pytest.approx(0.0, abs=1e-6)

    def test_billiger_heisst_nie_kleiner(self, project, global_assumptions):
        """Monotonie in der anderen Richtung: Sinkt der Zellpreis, kann
        die optimale Kapazitaet nicht fallen. Faellt sie doch, stimmt
        etwas an der Zielfunktion nicht."""
        from engine.pipeline import resolve_assumptions
        from engine.storage import optimum_stetig

        eingabe = self._eingabe()
        kapazitaeten = []
        for preis in (200.0, 120.0, 60.0):
            global_assumptions.speicher_capex_energie_eur_kwh = preis
            a = resolve_assumptions(project, global_assumptions)
            kapazitaeten.append(optimum_stetig(
                a, _mit_speicher(), [eingabe], [(self._GEWICHT, self._GEWICHT)],
                betriebsjahre=20, leistung_hoechstens_mw=3.0,
            ).kapazitaet_mwh)
        for teurer, billiger in zip(
            kapazitaeten, kapazitaeten[1:], strict=False
        ):
            assert billiger >= teurer - 1e-6, kapazitaeten

    def test_das_optimum_wird_im_vollen_cashflow_nachgerechnet(self):
        """Der Optimierer maximiert den Barwert des Speichers vor
        Fremdkapital. Was seine Auslegung im Modell dieser Anwendung
        wert ist, sagt erst der Cashflow - und deshalb steht sie im
        Ergebnis mit ihren eigenen Kennzahlen."""
        from engine.storage.auslegung import Rasterergebnis

        assert "optimum" in Rasterergebnis.__dataclass_fields__
        assert "optimum_punkt" in Rasterergebnis.__dataclass_fields__


class TestNurDauer:
    """Feste Leistung, gesucht ist allein die Dauer.

    Der Fall des Graustromspeichers: Was aus dem Netz bezogen werden
    darf, steht im Netzanschlussvertrag. Die Leistung ist dann keine
    Entwurfsgroesse mehr, sondern eine Eingabe - und aus dem
    zweidimensionalen Problem wird ein eindimensionales, das der
    Optimierer exakt loest.
    """

    _GEWICHT = 600.0

    def _eingabe(self, stunden: int = 168):
        import numpy as np

        from engine.storage.valuation import Jahreseingabe

        pv, preis = _kurzes_jahr(stunden)
        return Jahreseingabe(
            jahr=1, kalenderjahr=2030,
            pv_mw=np.asarray(pv), preise_eur_mwh=np.asarray(preis),
            grenzerloes_eur_mwh=np.asarray(preis),
            export_limit_mw=3.0,
        )

    def _optimum(self, assumptions, fest: float):
        from engine.storage import optimum_stetig

        return optimum_stetig(
            assumptions, _mit_speicher(), [self._eingabe()],
            [(self._GEWICHT, self._GEWICHT)],
            betriebsjahre=20, leistung_fest_mw=fest,
        )

    def test_die_leistung_bleibt_exakt_stehen(
        self, project, global_assumptions
    ):
        from engine.pipeline import resolve_assumptions

        a = resolve_assumptions(project, global_assumptions)
        for fest in (0.8, 2.0, 2.5):
            optimum = self._optimum(a, fest)
            assert optimum.leistung_mw == pytest.approx(fest)
            assert optimum.kapazitaet_mwh > 0

    def test_eine_feste_leistung_ist_kein_deckel(
        self, project, global_assumptions
    ):
        """`am_deckel` meldet, dass der Netzanschluss die Auslegung
        beschneidet. Bei vorgegebener Leistung gibt es nichts zu
        beschneiden - die Meldung waere dort schlicht falsch."""
        from engine.pipeline import resolve_assumptions

        a = resolve_assumptions(project, global_assumptions)
        optimum = self._optimum(a, 2.0)
        assert optimum.leistung_fest
        assert not optimum.am_deckel
        assert optimum.leistung_deckel_mw is None

    def test_keine_kapazitaet_schlaegt_die_gefundene(
        self, project, global_assumptions
    ):
        """Dieselbe definierende Eigenschaft wie in zwei Dimensionen,
        hier in einer: Bei fester Leistung gibt es keine bessere
        Kapazitaet als die gefundene."""
        from engine.pipeline import resolve_assumptions
        from engine.storage import dispatch_jahr
        from engine.storage.optimum import _barwertfaktoren

        a = resolve_assumptions(project, global_assumptions)
        fest = 2.0
        optimum = self._optimum(a, fest)
        assert optimum.wirksam

        barwert_opex, schild = _barwertfaktoren(a, 20, 0.08)
        eingabe = self._eingabe()
        for faktor in (0.25, 0.5, 0.8, 1.25, 2.0, 4.0):
            kapazitaet = optimum.kapazitaet_mwh * faktor
            ergebnis = dispatch_jahr(
                eingabe.pv_mw, eingabe.preise_eur_mwh,
                eingabe.grenzerloes_eur_mwh,
                _mit_speicher(leistung_mw=fest, kapazitaet_mwh=kapazitaet),
                eingabe.export_limit_mw,
            )
            kosten = 1000.0 * (
                fest * (
                    a.speicher_capex_leistung_eur_kw * (1.0 - schild)
                    + a.speicher_opex_eur_kw_jahr * barwert_opex
                )
                + kapazitaet
                * a.speicher_capex_energie_eur_kwh * (1.0 - schild)
            )
            wert = (
                (1.0 - a.steuersatz_pct) * self._GEWICHT
                * ergebnis.wertbeitrag_eur - kosten
            )
            assert optimum.barwert_eur >= wert - 1.0, (
                f"{kapazitaet:.2f} MWh ist besser ({wert:,.0f} statt "
                f"{optimum.barwert_eur:,.0f})"
            )

    def test_die_leistung_zaehlt_jetzt_im_abdruck(
        self, project, global_assumptions
    ):
        """Der Unterschied zum zweidimensionalen Modus, und er ist
        wesentlich: Dort ERSETZT das Raster die Leistung und darf sie
        deshalb ignorieren. Hier ist sie Eingabe - wer sie aendert,
        stellt eine andere Frage, und die alte Antwort veraltet."""
        from app import speicher

        project.battery = _mit_speicher(leistung_mw=3.0)
        vorher = speicher.raster_abdruck(
            project, global_assumptions, (1.0,), (2, 4), 4,
            speicher.MODUS_NUR_DAUER,
        )
        project.battery = _mit_speicher(leistung_mw=5.0)
        assert speicher.raster_abdruck(
            project, global_assumptions, (1.0,), (2, 4), 4,
            speicher.MODUS_NUR_DAUER,
        ) != vorher

    def test_die_kapazitaet_zaehlt_weiterhin_nicht(
        self, project, global_assumptions
    ):
        """Sie ist auch hier das, was die Suche ersetzt."""
        from app import speicher

        project.battery = _mit_speicher(leistung_mw=3.0, kapazitaet_mwh=6.0)
        vorher = speicher.raster_abdruck(
            project, global_assumptions, (1.0,), (2, 4), 4,
            speicher.MODUS_NUR_DAUER,
        )
        project.battery = _mit_speicher(leistung_mw=3.0, kapazitaet_mwh=30.0)
        assert speicher.raster_abdruck(
            project, global_assumptions, (1.0,), (2, 4), 4,
            speicher.MODUS_NUR_DAUER,
        ) == vorher

    def test_der_modus_selbst_zaehlt(self, project, global_assumptions):
        """Zwei Modi sind zwei Fragen - ihre Antworten duerfen sich
        nicht denselben Platz teilen."""
        from app import speicher

        project.battery = _mit_speicher()
        assert speicher.raster_abdruck(
            project, global_assumptions, (1.0,), (2, 4), 4,
            speicher.MODUS_BEIDES,
        ) != speicher.raster_abdruck(
            project, global_assumptions, (1.0,), (2, 4), 4,
            speicher.MODUS_NUR_DAUER,
        )


@pytest.fixture()
def graustromprojekt():
    """Ein Graustromspeicher am ausgelieferten Vorlagenprojekt."""
    pfad = PROJECTS_DIR / "template-agri.yaml"
    sicherung = pfad.read_bytes()
    projekt = load_project_yaml(pfad)
    projekt.battery = _mit_speicher(
        modus=SpeicherModus.GRAUSTROM, leistung_mw=3.0, kapazitaet_mwh=12.0,
        netzbezug_limit_mw=3.0,
    )
    save_project_yaml(projekt, pfad)
    try:
        yield projekt
    finally:
        pfad.write_bytes(sicherung)


class TestNurDauerImReiter:
    def test_graustrom_sucht_von_sich_aus_nur_die_dauer(
        self, graustromprojekt
    ):
        """Vorbelegt nach der Betriebsart: Beim Graustromspeicher steht
        die Leistung im Netzanschlussvertrag."""
        from app import speicher

        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        modus = [r for r in at.radio if r.key == "raster_modus_template-agri"]
        assert modus and modus[0].value == speicher.MODUS_NUR_DAUER
        # Kein Leistungsregler - die Leistung ist hier Eingabe.
        assert not [m for m in at.multiselect
                    if m.key == "raster_leistungen_template-agri"]
        assert [m for m in at.metric if m.label == "Feste Leistung"]

    def test_gruenstrom_sucht_beides(self, projekt_mit_speicher):
        from app import speicher

        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        modus = [r for r in at.radio if r.key == "raster_modus_template-agri"]
        assert modus and modus[0].value == speicher.MODUS_BEIDES
        assert [m for m in at.multiselect
                if m.key == "raster_leistungen_template-agri"]

    def test_ohne_leistung_kein_knopf(self, graustromprojekt):
        """Ein Knopf, der nur eine Fehlermeldung erzeugen kann, sollte
        gar nicht erst anklickbar sein - dieselbe Regel wie beim
        Dispatch."""
        pfad = PROJECTS_DIR / "template-agri.yaml"
        projekt = load_project_yaml(pfad)
        projekt.battery = _mit_speicher(
            modus=SpeicherModus.GRAUSTROM, leistung_mw=0.0,
        )
        save_project_yaml(projekt, pfad)

        at, _ = _app_mit_projekt("template-agri")
        _zum_speicherreiter(at)
        assert not [b for b in at.button
                    if b.key == "raster_rechnen_template-agri"]

    def test_der_lauf_haelt_die_leistung_fest(self, graustromprojekt):
        """Der ganze Weg: Jeder Rasterpunkt und das Optimum tragen
        dieselbe, vorgegebene Leistung."""
        at, _ = _app_mit_projekt("template-agri")
        at.session_state["tabwahl_template-agri"] = txt(
            "oberflaeche.projekt_tab_speicher"
        )
        at.session_state["raster_dauern_template-agri"] = [2, 4]
        at.session_state["raster_stuetzjahre_template-agri"] = 2
        at.run()
        assert not at.exception, at.exception
        [b for b in at.button if b.key == "raster_rechnen_template-agri"][0].click()
        at.run()
        assert not at.exception, at.exception

        laeufe = at.session_state["speicher_raster"]["template-agri"]
        ergebnis = list(laeufe.values())[-1]
        assert [p.kandidat.dauer_h for p in ergebnis.punkte] == [2, 4]
        for punkt in ergebnis.punkte:
            assert punkt.kandidat.leistung_mw == pytest.approx(3.0)
        assert ergebnis.optimum is not None
        assert ergebnis.optimum.leistung_mw == pytest.approx(3.0)
        assert ergebnis.optimum.leistung_fest


class TestModuswechsel:
    """Was passiert, wenn nach einem Lauf der Modus wechselt.

    Der Lauf bleibt sichtbar - als veraltet gekennzeichnet, denn er
    beantwortet jetzt eine andere Frage als die gestellte. Gezeichnet
    werden muss er aber nach SEINER Frage: Ein Raster mit vier Leistungen
    ist eine Flaeche, auch wenn der Schalter darueber inzwischen auf
    "nur die Dauer" steht. Anders herum entstuende eine Linie ueber der
    Dauer, die je Dauer vier Werte haette.
    """

    def test_die_darstellung_folgt_dem_ergebnis_nicht_dem_schalter(
        self, graustromprojekt
    ):
        from engine.storage.auslegung import Kandidat

        at, _ = _app_mit_projekt("template-agri")
        at.session_state["tabwahl_template-agri"] = txt(
            "oberflaeche.projekt_tab_speicher"
        )
        at.session_state["raster_dauern_template-agri"] = [2, 4]
        at.session_state["raster_stuetzjahre_template-agri"] = 2
        at.run()
        [b for b in at.button if b.key == "raster_rechnen_template-agri"][0].click()
        at.run()
        assert not at.exception, at.exception

        # Jetzt auf "Leistung und Dauer" umstellen - das Ergebnis
        # stammt aus dem anderen Modus und muss trotzdem zeichenbar
        # bleiben.
        from app import speicher

        at.session_state["raster_modus_template-agri"] = speicher.MODUS_BEIDES
        at.run()
        assert not at.exception, at.exception
        assert [w for w in at.warning if "seit dem Rasterlauf" in (w.value or "")]

        # Und die Ableitung selbst: eine Leistung heisst Kurve, mehrere
        # heissen Flaeche.
        eine = [Kandidat(leistungsanteil=1.0, leistung_mw=3.0, dauer_h=d)
                for d in (2, 4)]
        mehrere = [Kandidat(leistungsanteil=a, leistung_mw=3.0 * a, dauer_h=2)
                   for a in (0.5, 1.0)]
        assert len({k.leistung_mw for k in eine}) == 1
        assert len({k.leistung_mw for k in mehrere}) > 1


class TestBezugsgroesse:
    """Worauf sich die Prozentwerte beziehen.

    Genau hier lauert ein Missverstaendnis, und es ist keins, das man
    sich ausdenken muesste: Es wurde in der Anwendung gestellt. Die
    Prozentwerte meinen die EINSPEISELEISTUNG - nicht die Modulleistung
    und nicht den bereits eingestellten Speicher. Beides faellt nur
    zusammen, wenn keine Einspeisegrenze hinterlegt ist, und die globale
    Vorbelegung sind 70 Prozent (in Oesterreich die Regel, in
    Deutschland nicht).
    """

    def _mit(self, projekt, ga, kwp: float, grenze: float | None):
        from engine.models import Projektannahmen

        projekt.nennleistung_kwp = kwp
        projekt.annahmen = Projektannahmen(einspeiselimit_pct=grenze)
        return projekt, ga

    def test_die_grenze_bestimmt_die_hundert_prozent(
        self, project, global_assumptions
    ):
        from app import speicher

        projekt, ga = self._mit(project, global_assumptions, 10_000.0, 0.70)
        assert speicher.einspeiseleistung_mw(projekt, ga) == pytest.approx(7.0)

    def test_hundert_prozent_grenze_gibt_die_volle_modulleistung(
        self, project, global_assumptions
    ):
        """Der Weg fuer ein deutsches Projekt in einem sonst
        oesterreichischen Portfolio: Die Grenze am PROJEKT auf 100 %
        stellen. Global auf null zu gehen wuerde die uebrigen Projekte
        mitnehmen."""
        from app import speicher

        projekt, ga = self._mit(project, global_assumptions, 10_000.0, 1.0)
        assert speicher.einspeiseleistung_mw(projekt, ga) == pytest.approx(10.0)

    def test_ohne_projektangabe_gilt_die_globale_vorbelegung(
        self, project, global_assumptions
    ):
        """None heisst "folgt der Vorgabe" und nicht "keine Grenze" -
        die Erbmechanik, und genau daran ist die Frage entstanden."""
        from app import speicher

        global_assumptions.einspeiselimit_pct = 0.70
        projekt, ga = self._mit(project, global_assumptions, 10_000.0, None)
        assert speicher.einspeiseleistung_mw(projekt, ga) == pytest.approx(7.0)

    def test_der_eingestellte_speicher_ist_NICHT_die_bezugsgroesse(
        self, project, global_assumptions
    ):
        """Die Frage, die gestellt wurde: Sind 100 % der angelegte
        7,5-MW-Speicher? Nein - sonst haenge das Raster an dem Wert, den
        es gerade ersetzen soll."""
        from app import speicher

        projekt, ga = self._mit(project, global_assumptions, 10_000.0, 1.0)
        projekt.battery = _mit_speicher(leistung_mw=7.5, kapazitaet_mwh=15.0)
        assert speicher.einspeiseleistung_mw(projekt, ga) == pytest.approx(10.0)

    def test_das_raster_rechnet_mit_dieser_bezugsgroesse(
        self, project, global_assumptions
    ):
        from app import speicher
        from engine.storage import (
            leistungen_standard,
            leistungsstufen,
            raster,
        )

        projekt, ga = self._mit(project, global_assumptions, 10_000.0, 0.70)
        bezug = speicher.einspeiseleistung_mw(projekt, ga)
        assert bezug == pytest.approx(7.0)
        # Die Stufen richten sich nach dem Anschluss, stehen aber in MW.
        stufen = leistungsstufen(bezug)
        assert leistungen_standard(bezug)[-1] == pytest.approx(7.0)
        kandidaten = raster(stufen[:3], (4,), einspeiseleistung_mw=bezug)
        assert [k.leistung_mw for k in kandidaten] == pytest.approx(
            list(stufen[:3])
        )


class TestKapitalkostenfaktor:
    """Was ein Euro Speicherinvestition den Projektbarwert wirklich kostet.

    Der Optimierer rechnete zuvor mit `1 - Abschreibungsschild` und
    unterstellte damit eine unverschuldete Investition. Gemessen an
    einem Projekt mit 20 % Eigenkapital und 4,2 % Fremdkapitalzins lag
    er damit um ein Viertel daneben - systematisch zugunsten zu kleiner
    Speicher. Diese Tests halten die Richtung fest, nicht die zweite
    Nachkommastelle: Der genaue Wert haengt an Steuer, Tilgungsprofil
    und Laufzeit und darf sich mit ihnen aendern.
    """

    def _faktor(self, project, ga, quote: float, zins: float = 0.042):
        from engine.pipeline import resolve_assumptions
        from engine.storage import kapitalkostenfaktor

        project.eigenkapitalquote_pct = quote
        project.fremdkapitalzins_pct = zins
        a = resolve_assumptions(project, ga)
        return kapitalkostenfaktor(a, project.id, 10_000_000.0), a

    def test_ohne_gewinn_kein_abschreibungsschild(
        self, project, global_assumptions
    ):
        """Der Befund, der die Messung ueberhaupt rechtfertigt.

        Die Formel zieht das Abschreibungsschild pauschal ab und
        unterstellt damit, dass es sich verrechnen laesst. Das setzt
        steuerpflichtigen GEWINN voraus. Das Testprojekt erwirtschaftet
        ueber 25 Jahre rund 775.000 EUR steuerliches Ergebnis; eine
        Investition von 10 Mio EUR bringt ueber 20 Jahre 10 Mio EUR
        Abschreibung mit. Der weitaus groesste Teil davon trifft auf
        keinen Gewinn und verpufft.

        Gemessen liegt der Faktor deshalb bei rund 1,0 statt bei den
        0,89 der Formel - die Investition kostet hier fast ihren vollen
        Betrag. Genau das kann eine geschlossene Formel nicht wissen.
        """
        from engine.storage.optimum import _barwertfaktoren

        faktor, a = self._faktor(project, global_assumptions, 1.0)
        _, schild = _barwertfaktoren(a, a.betriebsdauer_jahre, 0.08)
        assert faktor > 1.0 - schild, (
            "Ohne verrechenbaren Gewinn darf das Schild nicht voll wirken"
        )
        assert faktor == pytest.approx(1.0, abs=0.05)

    def test_mehr_fremdkapital_macht_die_investition_billiger(
        self, project, global_assumptions
    ):
        """Wer unter dem Diskontsatz leiht, verdient an der Differenz."""
        faktoren = [
            self._faktor(project, global_assumptions, quote)[0]
            for quote in (1.0, 0.6, 0.4, 0.2)
        ]
        for hoeher, niedriger in zip(faktoren, faktoren[1:], strict=False):
            assert niedriger < hoeher, faktoren

    def test_beim_diskontsatz_verschwindet_der_vorteil(
        self, project, global_assumptions
    ):
        """Kostet das Fremdkapital so viel wie der Diskontsatz, ist an
        der Finanzierung nichts mehr zu verdienen - dann kostet die
        Investition dasselbe wie ohne Fremdkapital. Das ist die Probe
        darauf, dass hier wirklich die Zinsdifferenz wirkt und nicht
        irgendein Rechenfehler."""
        billig, _ = self._faktor(project, global_assumptions, 0.2, zins=0.02)
        teuer, _ = self._faktor(project, global_assumptions, 0.2, zins=0.08)
        ohne_fk, _ = self._faktor(project, global_assumptions, 1.0)
        assert billig < teuer
        assert teuer == pytest.approx(ohne_fk, rel=0.03)

    def test_ohne_investition_kein_faktor(self, project, global_assumptions):
        """Eine Division durch null waere hier besonders unangenehm: Sie
        traefe den Fall "noch kein Speicher eingerichtet"."""
        from engine.pipeline import resolve_assumptions
        from engine.storage import kapitalkostenfaktor

        a = resolve_assumptions(project, global_assumptions)
        assert kapitalkostenfaktor(a, project.id, 0.0) == 1.0
        assert kapitalkostenfaktor(a, project.id, -5.0) == 1.0

    @pytest.mark.langsam
    def test_der_faktor_verschiebt_das_optimum_nach_oben(
        self, project, global_assumptions
    ):
        """Die eigentliche Wirkung: Billigeres Kapital heisst groesserer
        Speicher. Gemessen am Vorlagenprojekt verschob sich das Optimum
        von 7,27 h auf 8,09 h - und traf damit das Barwertoptimum des
        Rasters bei 8 h, das es zuvor um eine Stufe verfehlte."""
        import numpy as np

        from engine.pipeline import resolve_assumptions
        from engine.storage import optimum_stetig
        from engine.storage.valuation import Jahreseingabe

        pv, preis = _kurzes_jahr(168)
        eingabe = Jahreseingabe(
            jahr=1, kalenderjahr=2030,
            pv_mw=np.asarray(pv), preise_eur_mwh=np.asarray(preis),
            grenzerloes_eur_mwh=np.asarray(preis), export_limit_mw=3.0,
        )
        a = resolve_assumptions(project, global_assumptions)
        gewicht = [(600.0, 600.0)]

        teuer = optimum_stetig(
            a, _mit_speicher(), [eingabe], gewicht,
            betriebsjahre=20, leistung_fest_mw=2.0,
        )
        billig = optimum_stetig(
            a, _mit_speicher(), [eingabe], gewicht,
            betriebsjahre=20, leistung_fest_mw=2.0,
            kapitalkostenfaktor=teuer.kapitalkostenfaktor * 0.7,
        )
        assert billig.kapazitaet_mwh > teuer.kapazitaet_mwh
        assert billig.barwert_eur > teuer.barwert_eur

    def test_der_faktor_steht_im_ergebnis(self):
        """Er gehoert ausgewiesen: Eine Auslegung, die auf einem
        Finanzierungsvorteil beruht, sieht man das nicht an."""
        from engine.storage import StetigesOptimum

        assert "kapitalkostenfaktor" in StetigesOptimum.__dataclass_fields__
