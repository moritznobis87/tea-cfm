"""
Einspeisekurven je Bauform - Herkunft, Normierung und Umschalter.

Die zwoelf Monatsanteile stammen aus PVGIS: Monatsertrag einer
1-kWp-Anlage, je einmal fuer die Pultaufstaenderung und den Tracker
(engine/models.PVGIS_MONATSERTRAG_KWH_KWP). Die Rohwerte stehen im
Modell, die Kurve entsteht durch Normierung - beides wird hier
geprueft, weil eine still verrutschte Kurve die Monatsrechnung
verfaelscht, ohne irgendwo aufzufallen.

Am Ende steht das Praemienmodell des Laenderschalters: Oesterreich
rechnet mit dem Toleranzband des EAG, Deutschland mit dem einseitigen
CfD des EEG.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from engine.models import (
    EINSPEISEKURVE_STANDARD_BAUFORM,
    EINSPEISEKURVE_STANDARD_PCT,
    EINSPEISEKURVEN_JE_BAUFORM,
    PVGIS_MONATSERTRAG_KWH_KWP,
    GlobalAssumptions,
)

_ROOT = Path(__file__).resolve().parent.parent
_GA_PFAD = _ROOT / "data" / "global_assumptions.yaml"


class TestRohwerte:
    """Die PVGIS-Ertraege sind die Quelle - sie muessen stimmen, alles
    Weitere folgt daraus."""

    @pytest.mark.parametrize("bauform", ["Pult", "Tracker"])
    def test_zwoelf_monatswerte(self, bauform):
        """PVGIS haengt an die zwoelf Monate eine Mittelwertzeile an -
        wird sie mitgelesen, waere ein dreizehnter Monat im Modell."""
        assert len(PVGIS_MONATSERTRAG_KWH_KWP[bauform]) == 12
        assert all(w > 0 for w in PVGIS_MONATSERTRAG_KWH_KWP[bauform])

    def test_jahresertraege(self):
        pult = sum(PVGIS_MONATSERTRAG_KWH_KWP["Pult"])
        tracker = sum(PVGIS_MONATSERTRAG_KWH_KWP["Tracker"])
        assert pult == pytest.approx(1148.47, abs=0.01)
        assert tracker == pytest.approx(1429.35, abs=0.01)

    def test_nachfuehrgewinn(self):
        """Rund ein Viertel mehr Ertrag - die Groessenordnung einer
        einachsigen Nachfuehrung."""
        pult = sum(PVGIS_MONATSERTRAG_KWH_KWP["Pult"])
        tracker = sum(PVGIS_MONATSERTRAG_KWH_KWP["Tracker"])
        assert 0.15 < tracker / pult - 1 < 0.35

    def test_nachfuehrgewinn_ist_im_sommer_groesser(self):
        """Lange Tage, weiter Azimutschwenk: Im Juli traegt die
        Nachfuehrung mehr als im Dezember. Waere es umgekehrt, waeren
        die beiden Reihen vermutlich vertauscht."""
        pult = PVGIS_MONATSERTRAG_KWH_KWP["Pult"]
        tracker = PVGIS_MONATSERTRAG_KWH_KWP["Tracker"]
        juli = tracker[6] / pult[6]
        dezember = tracker[11] / pult[11]
        assert juli > dezember
        # In jedem Monat gewinnt die Nachfuehrung.
        assert all(t > p for t, p in zip(tracker, pult, strict=True))


class TestKurven:
    @pytest.mark.parametrize("bauform", ["Pult", "Tracker"])
    def test_normierung(self, bauform):
        kurve = EINSPEISEKURVEN_JE_BAUFORM[bauform]
        assert len(kurve) == 12
        assert sum(kurve) == pytest.approx(1.0)
        assert all(w > 0 for w in kurve)

    @pytest.mark.parametrize("bauform", ["Pult", "Tracker"])
    def test_kurve_entspricht_den_rohwerten(self, bauform):
        roh = PVGIS_MONATSERTRAG_KWH_KWP[bauform]
        kurve = EINSPEISEKURVEN_JE_BAUFORM[bauform]
        erwartet = [w / sum(roh) for w in roh]
        assert kurve == pytest.approx(erwartet)

    def test_standard_ist_die_pult_kurve(self):
        assert EINSPEISEKURVE_STANDARD_BAUFORM == "Pult"
        assert EINSPEISEKURVE_STANDARD_PCT == EINSPEISEKURVEN_JE_BAUFORM["Pult"]

    def test_juli_ist_der_stärkste_monat(self):
        for kurve in EINSPEISEKURVEN_JE_BAUFORM.values():
            assert kurve.index(max(kurve)) == 6
            assert kurve.index(min(kurve)) == 11

    def test_tracker_ist_sommerlastiger(self):
        """Weil der Nachfuehrgewinn im Sommer groesser ist, verschiebt
        sich die Kurve dorthin - sonst waere die Unterscheidung der
        Bauformen fuer die Monatsrechnung ohne Wirkung."""
        pult = EINSPEISEKURVEN_JE_BAUFORM["Pult"]
        tracker = EINSPEISEKURVEN_JE_BAUFORM["Tracker"]
        assert tracker != pult
        assert sum(tracker[5:8]) > sum(pult[5:8])       # Juni bis August
        assert sum(tracker[10:]) < sum(pult[10:])       # November, Dezember

    def test_globale_annahmen_bringen_beide_kurven_mit(self):
        vorgabe = GlobalAssumptions.model_fields[
            "einspeisekurven_je_bauform"
        ].default_factory()
        assert set(vorgabe) == set(EINSPEISEKURVEN_JE_BAUFORM)
        # Eigene Kopien - ein Projekt darf die Vorlage nicht veraendern.
        vorgabe["Pult"][0] = 0.99
        assert EINSPEISEKURVEN_JE_BAUFORM["Pult"][0] != 0.99

    def test_ausgelieferte_annahmen_nutzen_die_pult_kurve(self):
        from engine.io_yaml import load_global_assumptions_yaml

        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.einspeisekurve_bauform == "Pult"
        assert set(ga.einspeisekurven_je_bauform) == set(EINSPEISEKURVEN_JE_BAUFORM)
        assert ga.einspeisekurve_pct_je_monat == pytest.approx(
            EINSPEISEKURVEN_JE_BAUFORM["Pult"], abs=5e-7
        )


class TestSpeichern:
    def test_kurven_ueberstehen_yaml(self, tmp_path, global_assumptions):
        from engine.io_yaml import (
            load_global_assumptions_yaml,
            save_global_assumptions_yaml,
        )

        ga = global_assumptions
        ga.einspeisekurve_bauform = "Tracker"
        ga.einspeisekurve_pct_je_monat = list(EINSPEISEKURVEN_JE_BAUFORM["Tracker"])

        pfad = tmp_path / "ga.yaml"
        save_global_assumptions_yaml(ga, pfad)
        gelesen = load_global_assumptions_yaml(pfad)
        assert gelesen.einspeisekurve_bauform == "Tracker"
        assert gelesen.einspeisekurven_je_bauform["Pult"] == pytest.approx(
            EINSPEISEKURVEN_JE_BAUFORM["Pult"]
        )
        assert gelesen.einspeisekurve_pct_je_monat == pytest.approx(
            EINSPEISEKURVEN_JE_BAUFORM["Tracker"]
        )


@pytest.fixture()
def _ga_datei_gesichert():
    """Wie in test_markt_system.py: Der Umschalter speichert sofort."""
    sicherung = _GA_PFAD.read_bytes()
    try:
        yield
    finally:
        _GA_PFAD.write_bytes(sicherung)
        from app import services

        services._load_global_assumptions_cached.clear()


def _app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(_ROOT / "streamlit_app.py"), default_timeout=300)
    at.run()
    assert not at.exception, at.exception
    return at


def _navigiere(at, key: str):
    [b for b in at.button if b.key == key][0].click()
    at.run()
    return at


class TestUmschalter:
    def test_wechsel_auf_tracker_setzt_die_kurve(self, _ga_datei_gesichert):
        from engine.io_yaml import load_global_assumptions_yaml

        at = _app()
        _navigiere(at, "nav_annahmen")
        at.session_state["einspeisekurve_bauform_wahl"] = "Tracker"
        at.run()
        assert not at.exception, at.exception

        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.einspeisekurve_bauform == "Tracker"
        # In der Datei stehen sechs Nachkommastellen.
        assert ga.einspeisekurve_pct_je_monat == pytest.approx(
            EINSPEISEKURVEN_JE_BAUFORM["Tracker"], abs=5e-7
        )


class TestGrosshandelspreis:
    """Der Grosshandelspreis kommt aus dem Aurora-Import und traegt die
    Direktvermarktungskosten im Modus RELATIV_GROSSHANDEL - er muss
    sichtbar sein und darf beim Speichern nicht verschwinden."""

    def _mit_grosshandelspreis(self):
        """Ein Szenario mit Grosshandelspreis vorbereiten - die
        ausgelieferten stammen aus der Zeit davor."""
        from engine.io_yaml import (
            load_global_assumptions_yaml,
            save_global_assumptions_yaml,
        )

        ga = load_global_assumptions_yaml(_GA_PFAD)
        szenario = ga.marktpreisszenarien[0]
        jahre = sorted(szenario.marktwert_solar_ct_kwh_je_kalenderjahr)[:3]
        szenario.baseload_ct_kwh_je_kalenderjahr = {
            j: 8.0 + i for i, j in enumerate(jahre)
        }
        szenario.baseload_ct_kwh_je_monat = {jahre[0]: [8.0] * 12}
        save_global_assumptions_yaml(ga, _GA_PFAD)
        from app import services

        services._load_global_assumptions_cached.clear()
        return szenario.name, jahre

    def test_ohne_kurve_steht_ein_hinweis(self, _ga_datei_gesichert):
        """Aeltere Szenarien fuehren keinen Grosshandelspreis - dann
        soll ein Hinweis stehen und kein leeres Diagramm."""
        from engine.io_yaml import (
            load_global_assumptions_yaml,
            save_global_assumptions_yaml,
        )

        ga = load_global_assumptions_yaml(_GA_PFAD)
        for szenario in ga.marktpreisszenarien:
            szenario.baseload_ct_kwh_je_kalenderjahr = {}
            szenario.baseload_ct_kwh_je_monat = {}
        save_global_assumptions_yaml(ga, _GA_PFAD)
        from app import services

        services._load_global_assumptions_cached.clear()

        at = _app()
        _navigiere(at, "nav_annahmen")
        assert not at.exception, at.exception
        assert [i for i in at.info if "Großhandelspreis" in i.value]

    def test_kurve_wird_geplottet(self, _ga_datei_gesichert):
        self._mit_grosshandelspreis()
        at = _app()
        _navigiere(at, "nav_annahmen")
        assert not at.exception, at.exception
        # Drei Diagramme statt zwei: Marktwert, Grosshandelspreis,
        # Anteil negativer Stunden.
        assert len(at.get("plotly_chart")) >= 3
        assert not [i for i in at.info if "Großhandelspreis" in i.value]

    def test_speichern_verliert_die_kurven_nicht(self, _ga_datei_gesichert):
        """Der Editor zeigt nur Jahreswerte; das Szenario wird beim
        Speichern daraus neu gebaut. Die Monatsreihe muss dabei
        mitgenommen werden - sonst faellt sie still heraus."""
        from engine.io_yaml import load_global_assumptions_yaml

        name, jahre = self._mit_grosshandelspreis()
        at = _app()
        _navigiere(at, "nav_annahmen")
        # Erst mit aufgeklappten Zahlen wird das Szenario neu gebaut.
        from engine.io_aurora import zerlege_szenarioname

        # Der Schalter haengt am Jahrgang, nicht an der einzelnen Kurve.
        stamm = zerlege_szenarioname(name)[0]
        at.session_state[f"kurven_zahlen_{stamm}"] = True
        at.run()
        [b for b in at.button if "peichern" in (b.label or "")][0].click()
        at.run()
        assert not at.exception, at.exception

        gelesen = load_global_assumptions_yaml(_GA_PFAD)
        neu = [s for s in gelesen.marktpreisszenarien if s.name == name][0]
        assert neu.baseload_ct_kwh_je_kalenderjahr[jahre[0]] == pytest.approx(8.0)
        assert neu.baseload_ct_kwh_je_kalenderjahr[jahre[2]] == pytest.approx(10.0)
        assert neu.baseload_ct_kwh_je_monat[jahre[0]] == pytest.approx([8.0] * 12)


class TestSzenarienreiter:
    """Ein Reiter je Jahrgang, nicht je Kurve: Aus einer Arbeitsmappe
    entstehen sechs Szenarien, und sechs Jahrgaenge ergaeben sonst eine
    Reiterleiste, die man scrollen muss."""

    def test_reiter_fuehren_jahrgaenge(self, _ga_datei_gesichert):
        from engine.io_aurora import zerlege_szenarioname
        from engine.io_yaml import load_global_assumptions_yaml

        ga = load_global_assumptions_yaml(_GA_PFAD)
        erwartet = list(dict.fromkeys(
            zerlege_szenarioname(s.name)[0] for s in ga.marktpreisszenarien
        ))

        at = _app()
        _navigiere(at, "nav_annahmen")
        assert not at.exception, at.exception
        beschriftungen = {
            e.label for e in at.get("tab") if e.label
        }
        for stamm in erwartet:
            assert stamm in beschriftungen
        # Die einzelne Kurve steht nicht mehr in der Reiterleiste.
        assert "Aurora Q3/26 · Pult · Central" not in beschriftungen

    def test_auswahl_im_reiter_wechselt_die_kurve(self, _ga_datei_gesichert):
        """Bauform und Preisszenario werden im Reiter gewaehlt - die
        Tabelle muss der Auswahl folgen."""
        at = _app()
        _navigiere(at, "nav_annahmen")
        at.session_state["kurven_zahlen_Aurora Q3/26"] = True
        at.session_state["familie_preis_Aurora Q3/26"] = "High"
        at.run()
        assert not at.exception, at.exception
        schluessel = {k for k in at.session_state.filtered_state
                      if k.startswith("kurven_editor_")}
        assert "kurven_editor_Aurora Q3/26 · Pult · High" in schluessel


class TestMarktsystemSetztPraemienmodell:
    """Oesterreich rechnet mit dem Toleranzband des EAG, Deutschland mit
    dem einseitigen CfD des EEG - der Laenderschalter stellt das mit um."""

    def test_deutschland_setzt_einseitigen_cfd(self, _ga_datei_gesichert):
        from engine.io_yaml import load_global_assumptions_yaml
        from engine.models import PraemienModell

        at = _app()
        _navigiere(at, "nav_annahmen")
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        assert not at.exception, at.exception
        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.praemien_modell == PraemienModell.EINSEITIG_CFD

    def test_oesterreich_setzt_toleranzband(self, _ga_datei_gesichert):
        from engine.io_yaml import load_global_assumptions_yaml
        from engine.models import PraemienModell

        at = _app()
        _navigiere(at, "nav_annahmen")
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        [b for b in at.button if b.key == "marktsystem_at"][0].click()
        at.run()
        assert not at.exception, at.exception
        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.praemien_modell == PraemienModell.EAG_TOLERANZBAND

    def test_standard_der_globalen_annahmen_ist_oesterreichisch(self):
        from engine.models import MarktSystem, PraemienModell

        felder = GlobalAssumptions.model_fields
        assert felder["markt_system"].default == MarktSystem.OESTERREICH
        assert felder["praemien_modell"].default == PraemienModell.EAG_TOLERANZBAND


class TestBauformAlsProjektfeld:
    """Die Bauform gehoert zum Projekt, nicht zum Szenarionamen.

    Bis v5.14 stand sie im Namen ("Aurora Q3/26 · Pult · Central") und
    las sich damit wie eine Marktmeinung - dabei ist sie eine
    Eigenschaft der Anlage. Sie entscheidet ueber zwei Kurven: die
    Einspeisekurve und die Marktwertkurve des gewaehlten Jahrgangs.
    """

    def _projekt(self, **kw):
        from engine.models import AnlagenTyp, PVProject

        felder = dict(
            id="p", name="P", anlagentyp=AnlagenTyp.AGRI_PV,
            nennleistung_kwp=5000.0, vollbenutzungsstunden_kwh_kwp=1050.0,
            pacht_eur_kwp_jahr=4.0, fremdkapitalzins_pct=0.042,
            eigenkapitalquote_pct=0.2, eag_zuschlagswert_ct_kwh=6.5,
        )
        felder.update(kw)
        return PVProject(**felder)

    def test_altbestand_wandert_aus_dem_namen_ins_feld(self):
        """Gespeicherte Projekte tragen die Bauform noch im
        Szenarionamen - beim Laden wandert sie ins Feld, und der Name
        verliert sie."""
        projekt = self._projekt(
            marktpreisszenario="Aurora Q3/26 · Tracker · Central"
        )
        assert projekt.bauform == "Tracker"
        assert projekt.marktpreisszenario == "Aurora Q3/26 · Central"

    def test_handgepflegter_name_bleibt_unberuehrt(self):
        projekt = self._projekt(marktpreisszenario="Enervis 2025")
        assert projekt.marktpreisszenario == "Enervis 2025"
        assert projekt.bauform == "Pult"

    def test_unbekannte_bauform_faellt_auf(self):
        """Sie faende weder Einspeise- noch Marktwertkurve und rechnete
        stillschweigend mit der Vorgabe weiter."""
        import pytest as _pytest

        with _pytest.raises(ValueError, match="Bauform"):
            self._projekt(bauform="Schräg")

    def test_bauform_bestimmt_die_einspeisekurve(self):
        from engine.models import EINSPEISEKURVEN_JE_BAUFORM
        from engine.pipeline import resolve_assumptions

        ga = GlobalAssumptions(afa_nutzungsdauer_jahre=20)
        for bauform in EINSPEISEKURVEN_JE_BAUFORM:
            ea = resolve_assumptions(self._projekt(bauform=bauform), ga)
            assert ea.einspeisekurve_pct_je_monat == pytest.approx(
                EINSPEISEKURVEN_JE_BAUFORM[bauform]
            )

    def test_handkurve_hat_vorrang(self):
        """Eine von Hand bearbeitete Kurve (keine Bauform hinterlegt)
        darf nicht stillschweigend durch eine Vorlage ersetzt werden."""
        from engine.pipeline import resolve_assumptions

        ga = GlobalAssumptions(afa_nutzungsdauer_jahre=20)
        ga.einspeisekurve_bauform = ""
        ga.einspeisekurve_pct_je_monat = [1 / 12] * 12
        ea = resolve_assumptions(self._projekt(bauform="Tracker"), ga)
        assert ea.einspeisekurve_pct_je_monat == pytest.approx([1 / 12] * 12)

    def test_bauform_waehlt_die_marktwertkurve(self):
        """Beide Kurven eines Jahrgangs liegen nebeneinander - welche
        gerechnet wird, entscheidet das Projekt."""
        from pathlib import Path as _P

        from engine.io_yaml import load_global_assumptions_yaml
        from engine.pipeline import resolve_assumptions

        ga = load_global_assumptions_yaml(
            _P(__file__).parent.parent / "data" / "global_assumptions.yaml"
        )
        namen = {
            bauform: resolve_assumptions(
                self._projekt(bauform=bauform,
                              marktpreisszenario="Aurora Q3/26 · Central"),
                ga,
            ).marktpreisszenario_name
            for bauform in ("Pult", "Tracker")
        }
        assert namen == {
            "Pult": "Aurora Q3/26 · Pult · Central",
            "Tracker": "Aurora Q3/26 · Tracker · Central",
        }

    def test_auswahl_zeigt_jeden_jahrgang_einmal(self):
        """Aus Pult- und Tracker-Variante wird ein Eintrag - die Bauform
        steht im Projekt."""
        from pathlib import Path as _P

        from engine.io_aurora import szenario_auswahl
        from engine.io_yaml import load_global_assumptions_yaml

        ga = load_global_assumptions_yaml(
            _P(__file__).parent.parent / "data" / "global_assumptions.yaml"
        )
        auswahl = szenario_auswahl(ga)
        assert auswahl[0] == "Aurora Q3/26 · Central"
        assert all("Pult" not in n and "Tracker" not in n for n in auswahl)
        assert len(auswahl) == len(set(auswahl))
        assert "Enervis 2025" in auswahl
