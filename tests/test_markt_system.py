"""
Tests des Marktsystem-Schalters (Oesterreich EAG / Deutschland EEG):
Modellfelder und Serialisierung, Flaggen-Buttons auf der Seite
"Globale Annahmen" mit Paket-Umstellung (Negativpreis-Regel,
Steuermodus, Zinsmethode), marktabhaengiger Kopfzeilen-Untertitel
sowie die deutsche Variante der Seite "Marktpraemie" (manueller
Zuschlagswert, ausgegrautes empirisches Modell).
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from engine import (
    GlobalAssumptions,
    MarktSystem,
    NegativeStundenRegel,
    TaxModus,
    ZinsMethode,
)

_ROOT = Path(__file__).resolve().parent.parent
_GA_PFAD = _ROOT / "data" / "global_assumptions.yaml"


@pytest.fixture()
def _ga_datei_gesichert():
    """Sichert data/global_assumptions.yaml und stellt sie nach dem Test
    wieder her - die AppTest-Faelle klicken echte Buttons, die die Datei
    speichern (gewollt: der Schalter wirkt sofort und global)."""
    sicherung = _GA_PFAD.read_bytes()
    try:
        yield
    finally:
        _GA_PFAD.write_bytes(sicherung)
        # Services-Caches leeren, damit Folgetests den Originalzustand sehen.
        from app import services

        services._load_global_assumptions_cached.clear()


def _app() -> "AppTest":  # noqa: F821
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(_ROOT / "streamlit_app.py"), default_timeout=300)
    at.run()
    assert not at.exception, at.exception
    return at


class TestModell:
    def test_standard_ist_oesterreich(self):
        ga = GlobalAssumptions(afa_nutzungsdauer_jahre=20)
        assert ga.markt_system == MarktSystem.OESTERREICH
        assert ga.de_marktpraemie_erwartet_ct_kwh == 5.0

    def test_serialisierung_roundtrip(self):
        ga = GlobalAssumptions(
            afa_nutzungsdauer_jahre=20,
            markt_system=MarktSystem.DEUTSCHLAND,
            de_marktpraemie_erwartet_ct_kwh=4.7,
            tax_modus=TaxModus.GEWERBESTEUER_DE,
        )
        daten = ga.model_dump(mode="json")
        assert daten["markt_system"] == "deutschland"
        ga2 = GlobalAssumptions.model_validate(daten)
        assert ga2.markt_system == MarktSystem.DEUTSCHLAND
        assert ga2.de_marktpraemie_erwartet_ct_kwh == 4.7

    def test_bestandsdatei_ohne_feld_laedt_mit_standard(self):
        from engine.io_yaml import load_global_assumptions_yaml

        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.markt_system in MarktSystem


class TestFlaggenSchalter:
    def test_beide_flaggen_buttons_vorhanden(self, _ga_datei_gesichert):
        at = _app()
        at.sidebar.radio[0].set_value("annahmen")
        at.run()
        assert not at.exception
        schluessel = {b.key for b in at.button if b.key}
        assert {"marktsystem_at", "marktsystem_de"} <= schluessel

    def test_deutsche_flaggendatei_vorhanden_und_gueltig(self):
        from PIL import Image

        from app.config import FLAGS_DIR

        pfad = FLAGS_DIR / "de.png"
        assert pfad.exists()
        with Image.open(pfad) as bild:
            assert bild.format == "PNG"
            assert bild.size == (240, 160)  # wie die uebrigen Flaggen

    def test_klick_deutschland_stellt_paket_um(self, _ga_datei_gesichert):
        from engine.io_yaml import load_global_assumptions_yaml

        at = _app()
        at.sidebar.radio[0].set_value("annahmen")
        at.run()
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        assert not at.exception, at.exception

        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.markt_system == MarktSystem.DEUTSCHLAND
        assert ga.negative_stunden_regel == NegativeStundenRegel.EINE_STUNDE
        assert ga.tax_modus == TaxModus.GEWERBESTEUER_DE
        assert ga.zinsmethode == ZinsMethode.DEUTSCH

    def test_klick_oesterreich_stellt_zurueck(self, _ga_datei_gesichert):
        from engine.io_yaml import load_global_assumptions_yaml

        at = _app()
        at.sidebar.radio[0].set_value("annahmen")
        at.run()
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        [b for b in at.button if b.key == "marktsystem_at"][0].click()
        at.run()
        assert not at.exception, at.exception

        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.markt_system == MarktSystem.OESTERREICH
        assert ga.negative_stunden_regel == NegativeStundenRegel.SECHS_STUNDEN
        assert ga.tax_modus == TaxModus.AFA_KOERPERSCHAFTSTEUER
        assert ga.afa_nutzungsdauer_jahre is not None
        assert ga.zinsmethode == ZinsMethode.OESTERREICH


class TestKopfzeilenTitel:
    def test_oesterreich_zeigt_eag_untertitel(self, _ga_datei_gesichert):
        at = _app()
        md = " ".join(m.value for m in at.markdown if m.value)
        assert "EAG-Marktprämienmodell, Österreich" in md
        assert "EEG-Marktprämienmodell, Deutschland" not in md

    def test_deutschland_zeigt_eeg_untertitel(self, _ga_datei_gesichert):
        at = _app()
        at.sidebar.radio[0].set_value("annahmen")
        at.run()
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        assert not at.exception
        md = " ".join(m.value for m in at.markdown if m.value)
        assert "EEG-Marktprämienmodell, Deutschland" in md
        assert "EAG-Marktprämienmodell, Österreich" not in md


class TestMarktpraemienSeiteDeutschland:
    def test_oesterreich_zeigt_empirisches_modell_ohne_manuelle_eingabe(
        self, _ga_datei_gesichert
    ):
        at = _app()
        at.sidebar.radio[0].set_value("auktion")
        at.run()
        assert not at.exception
        assert not any(
            n.key == "de_marktpraemie_wert" for n in at.number_input
        )
        md = " ".join(m.value for m in at.markdown if m.value)
        assert "EAG-Ausschreibungssimulation" in md

    def test_deutschland_zeigt_manuelle_eingabe_und_hinweis(
        self, _ga_datei_gesichert
    ):
        at = _app()
        at.sidebar.radio[0].set_value("annahmen")
        at.run()
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        at.sidebar.radio[0].set_value("auktion")
        at.run()
        assert not at.exception, at.exception

        eingaben = [n for n in at.number_input if n.key == "de_marktpraemie_wert"]
        assert len(eingaben) == 1
        md = " ".join(m.value for m in at.markdown if m.value)
        assert "EEG-Marktprämie" in md
        # Empirisches Modell weiterhin (ausgegraut) als Referenz gerendert.
        assert "EAG-Ausschreibungssimulation" in md
        # CSS-Regel fuer den ausgegrauten Container ist eingebettet.
        assert "auktion_empirie_ausgegraut" in md

    def test_manueller_wert_wird_gespeichert_und_uebergeben(
        self, _ga_datei_gesichert
    ):
        from engine.io_yaml import load_global_assumptions_yaml

        at = _app()
        at.sidebar.radio[0].set_value("annahmen")
        at.run()
        [b for b in at.button if b.key == "marktsystem_de"][0].click()
        at.run()
        at.sidebar.radio[0].set_value("auktion")
        at.run()
        eingabe = [n for n in at.number_input if n.key == "de_marktpraemie_wert"][0]
        eingabe.set_value(4.75)
        at.run()
        assert not at.exception, at.exception

        ga = load_global_assumptions_yaml(_GA_PFAD)
        assert ga.de_marktpraemie_erwartet_ct_kwh == pytest.approx(4.75)
        from app.views.auktion import STATE_EMPFOHLENES_GEBOT

        assert at.session_state[STATE_EMPFOHLENES_GEBOT] == pytest.approx(4.75)
