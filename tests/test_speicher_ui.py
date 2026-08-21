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


def _mit_speicher(**kwargs) -> BatteryConfig:
    """Eine Auslegung - OHNE Preise.

    Die Preise stehen nicht mehr an der Auslegung, sondern in den
    Annahmen (siehe engine/storage/kosten.py). BatteryConfig lehnt sie
    ausdruecklich ab (`extra="forbid"`), damit eine aeltere Projektdatei
    beim Laden scheitert statt einen gesetzten Preis stillschweigend zu
    verlieren.
    """
    vorgabe = dict(
        modus=SpeicherModus.GRUENSTROM, leistung_mw=5.0, kapazitaet_mwh=10.0,
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
        from engine.pipeline import resolve_assumptions

        global_assumptions.speicher_capex_eur_kw = 500.0
        global_assumptions.speicher_opex_eur_kw_jahr = 9.0
        a = resolve_assumptions(project, global_assumptions)
        assert a.speicher_capex_eur_kw == pytest.approx(500.0)
        assert a.speicher_opex_eur_kw_jahr == pytest.approx(9.0)

    def test_projektabweichung_schlaegt_die_vorgabe(
        self, project, global_assumptions
    ):
        """Ein Projekt mit vorliegendem Angebot weicht ab - alle uebrigen
        folgen weiter dem zentral gepflegten Preis."""
        from engine.models import Projektannahmen
        from engine.pipeline import resolve_assumptions

        global_assumptions.speicher_capex_eur_kw = 500.0
        project.annahmen = Projektannahmen(speicher_capex_eur_kw=390.0)
        a = resolve_assumptions(project, global_assumptions)
        assert a.speicher_capex_eur_kw == pytest.approx(390.0)
        # Das nicht abweichende Feld folgt weiterhin der Vorgabe.
        assert a.speicher_opex_eur_kw_jahr == pytest.approx(
            global_assumptions.speicher_opex_eur_kw_jahr
        )

    def test_capex_haengt_an_der_leistung_nicht_an_der_kapazitaet(
        self, project, global_assumptions
    ):
        """Die bewusste Vereinfachung, schriftlich festgehalten: Ein
        5-MW-Speicher kostet gleich viel, ob er zwei oder vier Stunden
        durchhaelt. Wer das aendert, aendert eine Modellaussage - und
        dieser Test faellt ihm dabei auf."""
        from engine.pipeline import resolve_assumptions
        from engine.storage import capex_eur

        global_assumptions.speicher_capex_eur_kw = 450.0
        a = resolve_assumptions(project, global_assumptions)
        zwei_stunden = _mit_speicher(leistung_mw=5.0, kapazitaet_mwh=10.0)
        vier_stunden = _mit_speicher(leistung_mw=5.0, kapazitaet_mwh=20.0)
        assert capex_eur(zwei_stunden, a) == pytest.approx(5.0 * 1000 * 450.0)
        assert capex_eur(vier_stunden, a) == capex_eur(zwei_stunden, a)
        # Die LEISTUNG geht dagegen sehr wohl ein.
        assert capex_eur(_mit_speicher(leistung_mw=10.0), a) == pytest.approx(
            2 * capex_eur(zwei_stunden, a)
        )

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
        from engine.models import GlobalAssumptions, Projektannahmen

        for feld in PREISFELDER.values():
            assert feld in Projektannahmen.model_fields, feld
            assert feld in GlobalAssumptions.model_fields, (
                f"{feld} hat keine globale Vorgabe"
            )
