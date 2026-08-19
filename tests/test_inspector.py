"""
Project Inspector und Vermarktungsdialog.

Der Kern ist die Trennung dreier Zustaende, und jeder Test hier prueft
genau einen Uebergang zwischen ihnen:

    Dialog (dlg_*)  --uebernehmen-->  Entwurf  --speichern-->  YAML
                    --abbrechen-->    (unveraendert)

Warum das so genau geprueft wird: Der Entwurf ist in dieser Anwendung
kein eigenes Objekt, sondern der WIDGET-Zustand selbst. Ein Bereich, der
in einen Dialog wandert, verliert diesen Traeger - dafuer gibt es das
Overlay (siehe app/components/project_inspector.py). Faellt es aus,
verschwinden PPA-Angaben stillschweigend beim naechsten Durchlauf, und
das faellt in der Rendite erst Wochen spaeter auf.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def projekte_gesichert(tmp_path):
    """Die Tests speichern echte Projekte - danach wird zurueckgelegt."""
    from app.config import PROJECTS_DIR

    sicherung = tmp_path / "projects"
    shutil.copytree(PROJECTS_DIR, sicherung)
    try:
        yield
    finally:
        for datei in PROJECTS_DIR.glob("*.yaml"):
            datei.unlink()
        for datei in sicherung.glob("*.yaml"):
            shutil.copy(datei, PROJECTS_DIR / datei.name)


def _projektseite(timeout: int = 120):
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=timeout)
    at.run()
    knopf = [b.key for b in at.button if b.key and b.key.startswith("open_")][0]
    [b for b in at.button if b.key == knopf][0].click()
    at.run()
    assert not at.exception, at.exception
    projekt_id = knopf.removeprefix("open_")
    return at, f"param_{projekt_id}", projekt_id


def _oeffne_dialog(at, form_key):
    [b for b in at.button if b.key == f"{form_key}__dlg_vermarktung"][0].click()
    at.run()
    assert not at.exception, at.exception
    return at


def _stelle_ppa_ein(at, form_key, anteil: int):
    """Den PPA-Anteil im Dialog setzen.

    Voraussetzung ist ein Projekt, das bereits hybrid vermarktet - sonst
    steht der Umschalter auf "Nur Marktprämie" und der Regler ist
    gesperrt, wie es die Oberflaeche vorsieht (siehe Fixture
    `projekt_mit_ppa`).
    """
    [g for g in at.get("button_group")
     if g.key == f"dlg_{form_key}_mix"][0].select("hybrid")
    at.run()
    [s for s in at.get("slider")
     if s.key == f"dlg_{form_key}_anteil"][0].set_value(anteil)
    at.run()
    assert not at.exception, at.exception
    return at


@pytest.fixture
def projekt_mit_ppa(projekte_gesichert):
    """Setzt im ersten Projekt einen PPA-Anteil - der Dialog startet
    damit im Hybridmodus, und der Regler laesst sich bewegen."""
    from app import services

    # Genau das Projekt, das _projektseite() oeffnet: Die Kacheln zeigen
    # LEITVARIANTEN, und die muss nicht die alphabetisch erste sein.
    at = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=120)
    at.run()
    knopf = [b.key for b in at.button if b.key and b.key.startswith("open_")][0]
    projekt_id = knopf.removeprefix("open_")

    projekt = services.get_project(projekt_id)
    projekt.ppa_anteil_pct = 0.2
    projekt.ppa_preis_eur_mwh = 68.0
    services.save_project(projekt, services.list_project_files()[projekt_id])
    return projekt_id


def _knopf(at, key):
    return [b for b in at.button if b.key == key][0]


def _hat_offene_aenderungen(at) -> bool:
    """Am Speichern-Knopf abgelesen: Er ist gesperrt, solange nichts
    offen ist. Robuster als die Statuszeile, die nur Text ist."""
    gesperrt = {b.key: b.disabled for b in at.button if b.key and "__" in b.key}
    return gesperrt.get("__speichern_platzhalter") is None and not all(
        v for k, v in gesperrt.items() if k.endswith("__speichern")
    )


class TestInspectorGrundzustand:
    def test_frisch_geoeffnet_ohne_aenderungen(self):
        """Der wichtigste Test der ganzen Datei: Ein Projekt zu OEFFNEN
        darf nichts aendern. Meldet die Spalte hier etwas, sind es
        Rundungsartefakte oder ein Feld, das seine Vorbelegung nicht
        findet - beides waere in jeder Sitzung sofort im Weg."""
        at, _, _ = _projektseite()
        assert any(
            "keine offenen Änderungen" in c.value for c in at.caption
        )

    def test_karten_sind_lesbar_ohne_bedienung(self):
        """Der Inspector soll auf einen Blick lesbar sein - jede Karte
        traegt ihre Kurzfassung im Markup, nicht erst nach dem Aufklappen."""
        at, _, _ = _projektseite()
        karten = [m.value for m in at.markdown if "inspector-karte" in m.value]
        assert len(karten) >= 6, "Themenkarten fehlen"
        assert all("inspector-karte-zeile" in k for k in karten)

    def test_quick_adjust_traegt_die_vier_groessen(self):
        at, form_key, _ = _projektseite()
        keys = {n.key for n in at.get("number_input") if n.key}
        for feld in ("leistung_live", "vbh_live", "epc", "fkzins"):
            assert f"{form_key}_{feld}" in keys, feld


class TestQuickAdjust:
    def test_aenderung_wirkt_sofort_und_speichert_nicht(self, projekte_gesichert):
        from app import services

        at, form_key, projekt_id = _projektseite()
        vorher = services.get_project(projekt_id).nennleistung_kwp

        feld = [n for n in at.get("number_input")
                if n.key == f"{form_key}_leistung_live"][0]
        feld.set_value(feld.value + 500.0)
        at.run()
        assert not at.exception, at.exception

        assert _hat_offene_aenderungen(at)
        # Auf der Platte hat sich nichts geruehrt.
        assert services.get_project(projekt_id).nennleistung_kwp == vorher

    def test_verwerfen_stellt_den_gespeicherten_stand_her(self, projekte_gesichert):
        at, form_key, _ = _projektseite()
        feld = [n for n in at.get("number_input")
                if n.key == f"{form_key}_leistung_live"][0]
        ausgang = feld.value
        feld.set_value(ausgang + 500.0)
        at.run()
        assert _hat_offene_aenderungen(at)

        _knopf(at, f"{form_key}__verwerfen").click()
        at.run()
        assert not at.exception, at.exception
        assert not _hat_offene_aenderungen(at)
        wieder = [n for n in at.get("number_input")
                  if n.key == f"{form_key}_leistung_live"][0]
        assert wieder.value == ausgang

    def test_speichern_persistiert(self, projekte_gesichert):
        from app import services

        at, form_key, projekt_id = _projektseite()
        feld = [n for n in at.get("number_input")
                if n.key == f"{form_key}_leistung_live"][0]
        neu = feld.value + 500.0
        feld.set_value(neu)
        at.run()

        _knopf(at, f"{form_key}__speichern").click()
        at.run()
        assert not at.exception, at.exception
        assert services.get_project(projekt_id).nennleistung_kwp == pytest.approx(neu)
        # Und danach meldet die Spalte nichts Offenes mehr.
        assert not _hat_offene_aenderungen(at)


class TestVermarktungsdialog:
    def test_oeffnen_aendert_nichts(self):
        at, form_key, _ = _projektseite()
        at = _oeffne_dialog(at, form_key)
        assert not _hat_offene_aenderungen(at)

    def test_dialog_zeigt_live_impact(self):
        at, form_key, _ = _projektseite()
        at = _oeffne_dialog(at, form_key)
        kacheln = [m.value for m in at.markdown
                   if '<div class="impact-kachel">' in m.value]
        assert len(kacheln) == 2, "Equity IRR und Equity Value erwartet"
        assert all("gespeichertem Stand" in k or "saved" in k for k in kacheln)

    def test_aenderung_im_dialog_wirkt_noch_nicht_auf_den_entwurf(self, projekt_mit_ppa):
        """Solange der Dialog offen ist, ist sein Zustand ein eigener -
        sonst waere "Abbrechen" wirkungslos."""
        at, form_key, _ = _projektseite()
        at = _oeffne_dialog(at, form_key)

        at = _stelle_ppa_ein(at, form_key, 40)
        assert not _hat_offene_aenderungen(at)

    def test_abbrechen_laesst_den_entwurf_unberuehrt(self, projekt_mit_ppa):
        at, form_key, _ = _projektseite()
        at = _oeffne_dialog(at, form_key)
        at = _stelle_ppa_ein(at, form_key, 40)

        _knopf(at, f"dlgbtn_{form_key}_ab").click()
        at.run()
        assert not at.exception, at.exception
        assert not _hat_offene_aenderungen(at)

    def test_uebernehmen_fuehrt_in_den_entwurf(self, projekt_mit_ppa):
        at, form_key, _ = _projektseite()
        at = _oeffne_dialog(at, form_key)
        at = _stelle_ppa_ein(at, form_key, 40)

        _knopf(at, f"dlgbtn_{form_key}_ok").click()
        at.run()
        assert not at.exception, at.exception
        assert _hat_offene_aenderungen(at)
        # Die Karte zeigt den uebernommenen Stand.
        karten = [m.value for m in at.markdown if "inspector-karte" in m.value]
        assert any("40" in k and "PPA" in k for k in karten)

    def test_uebernehmen_speichert_noch_nicht(self, projekt_mit_ppa):
        """Der Punkt, auf den es bei der Bedienung ankommt: Uebernehmen
        ist NICHT Speichern."""
        from app import services

        at, form_key, projekt_id = _projektseite()
        vorher = services.get_project(projekt_id).ppa_anteil_pct

        at = _oeffne_dialog(at, form_key)
        at = _stelle_ppa_ein(at, form_key, 40)
        _knopf(at, f"dlgbtn_{form_key}_ok").click()
        at.run()

        assert services.get_project(projekt_id).ppa_anteil_pct == vorher


class TestOverlayMechanik:
    """Das Overlay direkt - ohne Oberflaeche.

    Die Zustandsuebergaenge sind ueber die Oberflaeche geprueft; hier
    steht die Regel selbst, die sie traegt: Was im Overlay liegt, hat
    Vorrang vor dem gespeicherten Stand, und "Verwerfen" raeumt es mit
    ab, weil es denselben Praefix traegt wie die Widgets.
    """

    def test_leeres_overlay_liefert_die_vorgabe(self):
        from app.components.project_inspector import overlay_leeren, overlay_wert

        overlay_leeren("param_test")
        assert overlay_wert("param_test", "ppa_anteil_pct", 0.25) == 0.25

    def test_gesetzter_wert_hat_vorrang(self):
        from app.components.project_inspector import (
            overlay_leeren,
            overlay_setzen,
            overlay_wert,
        )

        overlay_leeren("param_test")
        overlay_setzen("param_test", {"ppa_anteil_pct": 0.4})
        assert overlay_wert("param_test", "ppa_anteil_pct", 0.0) == 0.4
        overlay_leeren("param_test")

    def test_verwirf_entwurf_raeumt_das_overlay(self):
        """Der Praefix ist der Vertrag: Faellt er auseinander, ueberlebte
        eine uebernommene PPA-Aenderung das Verwerfen."""
        import streamlit as st

        from app.components.project_form import verwirf_entwurf
        from app.components.project_inspector import (
            overlay_schluessel,
            overlay_setzen,
        )

        overlay_setzen("param_test", {"ppa_anteil_pct": 0.4})
        assert overlay_schluessel("param_test") in st.session_state
        verwirf_entwurf("param_test")
        assert overlay_schluessel("param_test") not in st.session_state


class TestVariantenBleibenGetrennt:
    """Widget-Schluessel und Overlay tragen beide die Projekt-Id - zwei
    Varianten desselben Standorts koennen sich nicht ins Gehege kommen."""

    def test_schluessel_trennen_die_varianten(self):
        from app import services
        from app.components.project_inspector import (
            overlay_leeren,
            overlay_setzen,
            overlay_wert,
        )

        projekte = services.list_projects()
        standorte: dict[str, list] = {}
        for p in projekte:
            standorte.setdefault(p.name, []).append(p)
        mehrere = [v for v in standorte.values() if len(v) > 1]
        if not mehrere:
            pytest.skip("Kein Standort mit mehreren Varianten im Bestand")
        eine, andere = mehrere[0][0].id, mehrere[0][1].id

        overlay_leeren(f"param_{eine}")
        overlay_leeren(f"param_{andere}")
        overlay_setzen(f"param_{eine}", {"ppa_anteil_pct": 0.4})
        assert overlay_wert(f"param_{eine}", "ppa_anteil_pct", 0.0) == 0.4
        assert overlay_wert(f"param_{andere}", "ppa_anteil_pct", 0.0) == 0.0
        overlay_leeren(f"param_{eine}")


class TestMarktsystem:
    """Im Deutschlandmodus darf im Dialog nichts Oesterreichisches
    stehenbleiben - die Beschriftung kommt aus dem Marktsystem."""

    def test_dialog_nennt_das_geltende_marktsystem(self):
        from app import services
        from app.views.assumptions import _MARKT_SYSTEME

        at, form_key, _ = _projektseite()
        at = _oeffne_dialog(at, form_key)
        ga = services.get_global_assumptions()
        from texte import txt

        erwartet = txt(_MARKT_SYSTEME[ga.markt_system][1])
        beschriftungen = [m.label for m in at.get("metric")]
        assert any(erwartet in b for b in beschriftungen), beschriftungen
