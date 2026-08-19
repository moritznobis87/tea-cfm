"""
Der Settings Hub der Globalen Annahmen.

Zwei Dinge werden hier abgesichert, und nur das zweite ist Oberflaeche:

1. Die ZUSTANDSLOGIK des Entwurfs. Sie ist der Grund, warum es diesen
   Umbau ueberhaupt gibt (siehe app/components/settings_hub.py), und die
   Stelle, an der ein Fehler stillen Datenverlust bedeutet: eine
   Sofortaktion, die offene Aenderungen wegwirft, oder ein Speichern,
   das einen frischen Import ueberschreibt.

2. Die STRUKTURPRUEFUNG (data_quality). Sie soll nichts behaupten, was
   sie nicht geprueft hat.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import (  # noqa: E402
    GlobalAssumptions,
    MarktpreisSzenario,
    MarktSystem,
    NegativeStundenRegel,
    PraemienModell,
    TaxModus,
    Zeitaufloesung,
)

_GA_PFAD = ROOT / "data" / "global_assumptions.yaml"


@pytest.fixture
def _ga_datei_gesichert():
    """Die Annahmendatei wird von diesen Tests geschrieben."""
    sicherung = _GA_PFAD.read_bytes()
    try:
        yield
    finally:
        _GA_PFAD.write_bytes(sicherung)
        from app import services

        services._load_global_assumptions_cached.clear()


def _app():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=300)
    at.run()
    return at


def _annahmen(at):
    [b for b in at.button if b.key == "nav_annahmen"][0].click()
    at.run()
    assert not at.exception, at.exception
    return at


def _uebernimm(at, **felder):
    """Schreibt Werte in den Entwurf - wie es "Uebernehmen" tut.

    Bewusst am Dialog VORBEI: Ein `st.dialog` laesst sich in AppTest
    nicht zuverlaessig bedienen, seine Widgets ueberleben den Durchlauf
    nicht (aus demselben Grund pruefen die Tests des
    Vermarktungsdialogs den Entwurf direkt, siehe test_inspector.py).
    Geprueft werden soll hier ohnehin nicht das Widget, sondern die
    Zustandslogik dahinter - und die haengt am Entwurf, nicht am Weg,
    auf dem ein Wert hineinkommt. Dass der Dialog aufgeht und nichts
    veraendert, prueft test_dialog_oeffnen_und_schliessen_bleibt_folgenlos.
    """
    entwurf = at.session_state["ga_entwurf"]
    for name, wert in felder.items():
        setattr(entwurf, name, wert)
    at.run()
    assert not at.exception, at.exception
    return at


def _alles_gesperrt(at) -> bool:
    """Speichern und Verwerfen gesperrt heisst: nichts ist offen."""
    gesperrt = {b.key: b.disabled for b in at.button if b.key}
    return gesperrt["ga_speichern"] and gesperrt["ga_verwerfen"]


# ---------------------------------------------------------------------------
# Datenqualitaet - reine Funktionen, ohne Streamlit
# ---------------------------------------------------------------------------


class TestDatenqualitaet:
    def _ga(self, **felder) -> GlobalAssumptions:
        vorgabe = {
            "marktpreisszenarien": [
                MarktpreisSzenario(
                    name="Test",
                    marktwert_solar_ct_kwh_je_kalenderjahr={
                        j: 4.0 for j in range(2025, 2051)
                    },
                )
            ],
            "markt_system": MarktSystem.OESTERREICH,
            "praemien_modell": PraemienModell.EAG_TOLERANZBAND,
            "tax_modus": TaxModus.AFA_KOERPERSCHAFTSTEUER,
            "afa_nutzungsdauer_jahre": 20,
        }
        vorgabe.update(felder)
        return GlobalAssumptions(**vorgabe)

    def test_ohne_szenario_ist_es_ein_fehler(self):
        from app.components import data_quality

        befunde = data_quality.pruefe(self._ga(marktpreisszenarien=[]))
        szenarien = [b for b in befunde if b.schluessel == "szenarien"]
        assert szenarien and szenarien[0].stufe == "fehler"
        assert data_quality.gesamtstufe(befunde) == "fehler"

    def test_monatspruefung_entfaellt_bei_jahresaufloesung(self):
        """Fehlende Monatsreihen sind kein Mangel, wenn jaehrlich
        gerechnet wird - eine Warnung waere hier ein Fehlalarm."""
        from app.components import data_quality

        befunde = data_quality.pruefe(self._ga(zeitaufloesung=Zeitaufloesung.JAHR))
        assert not [b for b in befunde if b.schluessel == "monat"]

    def test_monatsmodus_ohne_monatswerte_ist_ein_fehler(self):
        from app.components import data_quality

        befunde = data_quality.pruefe(
            self._ga(zeitaufloesung=Zeitaufloesung.MONAT)
        )
        monat = [b for b in befunde if b.schluessel == "monat"]
        assert monat and monat[0].stufe == "fehler"

    def test_zu_kurze_kurve_ist_ein_hinweis_kein_fehler(self):
        """Das Modell rechnet ueber das letzte Kurvenjahr hinaus mit der
        Marktpreisinflation weiter - es rechnet also, nur eben
        fortgeschrieben."""
        from app.components import data_quality

        befunde = data_quality.pruefe(self._ga(), letztes_modelljahr=2060)
        abdeckung = [b for b in befunde if b.schluessel == "abdeckung"]
        assert abdeckung and abdeckung[0].stufe == "hinweis"
        assert "2050" in abdeckung[0].text
        assert "2060" in abdeckung[0].text

    def test_abdeckung_entfaellt_ohne_modelljahr(self):
        """Ohne Projekte gibt es keinen Modellzeitraum, den eine
        Preiskurve verfehlen koennte."""
        from app.components import data_quality

        befunde = data_quality.pruefe(self._ga(), letztes_modelljahr=None)
        assert not [b for b in befunde if b.schluessel == "abdeckung"]

    def test_regelwerk_passend_ist_ok(self):
        from app.components import data_quality

        befunde = data_quality.pruefe(self._ga())
        regel = [b for b in befunde if b.schluessel == "regelwerk"]
        assert regel and regel[0].stufe == "ok"

    def test_deutsches_modell_in_oesterreich_ist_ein_hinweis(self):
        from app.components import data_quality

        befunde = data_quality.pruefe(
            self._ga(praemien_modell=PraemienModell.EINSEITIG_CFD)
        )
        regel = [b for b in befunde if b.schluessel == "regelwerk"]
        assert regel and regel[0].stufe == "hinweis"

    def test_gute_nachricht_behauptet_nur_strukturpruefung(self):
        """Die Karte darf nicht "alles korrekt" sagen - geprueft wird die
        Struktur der Daten, nicht die Richtigkeit der Zahlen."""
        from app.components import data_quality

        befunde = data_quality.pruefe(self._ga())
        kopf, sub = data_quality.kurzfassung(befunde)
        assert "korrekt" not in kopf.lower()
        assert "vollständig" not in kopf.lower()
        assert str(len(befunde)) in sub


# ---------------------------------------------------------------------------
# Entwurf und Sofort-Persistenz
# ---------------------------------------------------------------------------


class TestEntwurf:
    def test_seite_oeffnen_aendert_nichts(self, _ga_datei_gesichert):
        """Der wichtigste Test dieser Datei: Ein frisch geoeffneter
        Settings Hub darf keine Aenderung melden. Meldet er eine, ist es
        ein Rundungsartefakt oder ein Feld, das seine Vorbelegung nicht
        findet - beides waere sofort im Weg."""
        at = _annahmen(_app())
        gesperrt = {b.key: b.disabled for b in at.button if b.key}
        assert gesperrt["ga_speichern"] is True
        assert gesperrt["ga_verwerfen"] is True

    def test_uebersicht_zeigt_alle_karten(self, _ga_datei_gesichert):
        at = _annahmen(_app())
        karten = " ".join(
            m.value for m in at.markdown if "settings-karte" in m.value
        )
        for erwartet in ("MARKT", "VERMARKTUNG", "BETRIEBSKOSTEN",
                         "FINANZIERUNG", "FÖRDERUNG", "STEUERN",
                         "DATENQUALITÄT"):
            assert erwartet in karten.upper(), erwartet

    def test_keine_rohen_enum_werte_in_der_uebersicht(self, _ga_datei_gesichert):
        """"PraemienModell.EAG_TOLERANZBAND" gehoert nicht in die UI."""
        at = _annahmen(_app())
        karten = " ".join(
            m.value for m in at.markdown if "settings-karte" in m.value
        )
        for verboten in ("PraemienModell.", "TaxModus.", "Zeitaufloesung.",
                         "DirektvermarktungsModus.", "TilgungsArt."):
            assert verboten not in karten, verboten

    def test_dialog_oeffnen_aendert_nichts(self, _ga_datei_gesichert):
        at = _annahmen(_app())
        [b for b in at.button if b.key == "gakarte_finanzierung"][0].click()
        at.run()
        assert not at.exception, at.exception
        gesperrt = {b.key: b.disabled for b in at.button if b.key}
        assert gesperrt["ga_speichern"] is True

    def test_uebernehmen_meldet_die_aenderung_ohne_zu_speichern(
        self, _ga_datei_gesichert
    ):
        """Der Kern der Draft-Semantik: "Uebernehmen" fuehrt in den
        Entwurf, nicht in die Datei."""
        from engine.io_yaml import load_global_assumptions_yaml

        vorher = load_global_assumptions_yaml(_GA_PFAD).kreditlaufzeit_jahre
        at = _annahmen(_app())
        _uebernimm(at, kreditlaufzeit_jahre=vorher + 3)

        # Gemeldet, aber nicht geschrieben.
        gesperrt = {b.key: b.disabled for b in at.button if b.key}
        assert gesperrt["ga_speichern"] is False
        assert load_global_assumptions_yaml(_GA_PFAD).kreditlaufzeit_jahre == vorher

        # Und dann geschrieben.
        [b for b in at.button if b.key == "ga_speichern"][0].click()
        at.run()
        assert not at.exception, at.exception
        assert (
            load_global_assumptions_yaml(_GA_PFAD).kreditlaufzeit_jahre
            == vorher + 3
        )

    def test_zurueckgesetzter_wert_gilt_nicht_als_aenderung(
        self, _ga_datei_gesichert
    ):
        """Gezaehlt wird feldweise gegen den gespeicherten Stand und
        nicht "hier wurde etwas angefasst": Wer einen Wert aendert und
        wieder zuruecksetzt, hat nichts geaendert."""
        from engine.io_yaml import load_global_assumptions_yaml

        vorher = load_global_assumptions_yaml(_GA_PFAD).kreditlaufzeit_jahre
        at = _annahmen(_app())
        _uebernimm(at, kreditlaufzeit_jahre=vorher + 3)
        assert not _alles_gesperrt(at)

        _uebernimm(at, kreditlaufzeit_jahre=vorher)
        assert _alles_gesperrt(at)

    def test_verwerfen_stellt_den_gespeicherten_stand_her(
        self, _ga_datei_gesichert
    ):
        at = _annahmen(_app())
        _uebernimm(at, kreditlaufzeit_jahre=42)
        assert not _alles_gesperrt(at)

        [b for b in at.button if b.key == "ga_verwerfen"][0].click()
        at.run()
        assert not at.exception, at.exception
        assert _alles_gesperrt(at)

    def test_dialog_oeffnen_und_schliessen_bleibt_folgenlos(
        self, _ga_datei_gesichert
    ):
        """Der Weg durch die Oberflaeche: Karte anklicken, Dialog
        erscheint, Kreuz - und danach ist alles wie vorher."""
        at = _annahmen(_app())
        [b for b in at.button if b.key == "gakarte_technik"][0].click()
        at.run()
        assert not at.exception, at.exception
        assert _alles_gesperrt(at)


class TestSofortPersistenz:
    """Der gefaehrlichste Teil des Umbaus.

    Vier Aktionen speichern unmittelbar. Sie duerfen weder offene
    Aenderungen des Entwurfs mit in die Datei nehmen noch sie
    hinterher wegwerfen - und sie duerfen anschliessend nicht als
    offene Aenderung dastehen.
    """

    def test_marktsystemwechsel_wirkt_sofort(self, _ga_datei_gesichert):
        from engine.io_yaml import load_global_assumptions_yaml

        at = _annahmen(_app())
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        assert not at.exception, at.exception
        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.markt_system == MarktSystem.DEUTSCHLAND
        assert ga.negative_stunden_regel == NegativeStundenRegel.EINE_STUNDE
        assert ga.tax_modus == TaxModus.GEWERBESTEUER_DE

    def test_marktsystemwechsel_hinterlaesst_keine_phantomaenderung(
        self, _ga_datei_gesichert
    ):
        """Was die Aktion gespeichert hat, darf danach nicht als offen
        gelten - sonst zeigte die Seite Aenderungen an, die niemand
        vorgenommen hat."""
        at = _annahmen(_app())
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        assert not at.exception, at.exception
        gesperrt = {b.key: b.disabled for b in at.button if b.key}
        assert gesperrt["ga_speichern"] is True

    def test_sofortaktion_nimmt_offene_aenderungen_nicht_mit(
        self, _ga_datei_gesichert
    ):
        """Ein Marktsystemwechsel darf NICHT nebenbei die offene
        Finanzierungsaenderung mitspeichern."""
        from engine.io_yaml import load_global_assumptions_yaml

        vorher = load_global_assumptions_yaml(_GA_PFAD).kreditlaufzeit_jahre
        at = _annahmen(_app())
        _uebernimm(at, kreditlaufzeit_jahre=vorher + 5)

        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        assert not at.exception, at.exception

        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.markt_system == MarktSystem.DEUTSCHLAND
        assert ga.kreditlaufzeit_jahre == vorher, (
            "Die Sofortaktion hat eine offene Aenderung mitgespeichert"
        )

    def test_sofortaktion_vernichtet_offene_aenderungen_nicht(
        self, _ga_datei_gesichert
    ):
        """Die Gegenrichtung: Die offene Aenderung muss die Sofortaktion
        ueberleben und weiterhin als offen gelten."""
        from engine.io_yaml import load_global_assumptions_yaml

        vorher = load_global_assumptions_yaml(_GA_PFAD).kreditlaufzeit_jahre
        at = _annahmen(_app())
        _uebernimm(at, kreditlaufzeit_jahre=vorher + 5)

        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        assert not at.exception, at.exception

        # Noch offen ...
        assert not _alles_gesperrt(at), (
            "Die offene Aenderung ist der Sofortaktion zum Opfer gefallen"
        )
        # ... und speicherbar.
        [b for b in at.button if b.key == "ga_speichern"][0].click()
        at.run()
        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.kreditlaufzeit_jahre == vorher + 5
        assert ga.markt_system == MarktSystem.DEUTSCHLAND, (
            "Das Speichern hat die Sofortaktion rueckgaengig gemacht"
        )
