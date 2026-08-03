"""
Standort und Variante (Sensitivitaet).

Hintergrund: Sensitivitaeten entstanden bisher als Kopien mit dem Namen
"... (Kopie)" - technisch eigenstaendige Projekte, die die Projektliste
fuellten, ohne dass ihr anzusehen war, welche Eintraege denselben
Standort meinen. Ein Projekt traegt jetzt zwei Namen: den Standort und
die Variante. Die Seitenleiste fuehrt Standorte, die Varianten stehen
als Reiterreihe im Projektfenster.

Die Rechenregeln bleiben davon unberuehrt - die Variante ist ein reines
Ordnungsmerkmal.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import PVProject  # noqa: E402
from engine.io_excel import (  # noqa: E402
    OPTIONALE_PROJEKT_SPALTEN,
    PROJEKT_SPALTEN,
    excel_to_projects,
    projects_to_excel,
)
from engine.io_yaml import load_project_yaml, save_project_yaml  # noqa: E402

VORLAGE = ROOT / "data" / "projects" / "template-agri.yaml"


def _projekt(name: str, variante: str = "", pid: str | None = None) -> PVProject:
    p = load_project_yaml(VORLAGE).model_copy(deep=True)
    p.name, p.variante = name, variante
    p.id = pid or f"{name}-{variante}".strip("-").lower().replace(" ", "-")
    return p


class TestModell:
    def test_variante_ist_optional(self):
        assert _projekt("Sonnenfeld").variante == ""

    def test_anzeigename_nennt_die_variante_nur_wenn_es_eine_gibt(self):
        assert _projekt("Sonnenfeld").anzeigename == "Sonnenfeld"
        assert (
            _projekt("Sonnenfeld", "Netz high").anzeigename
            == "Sonnenfeld · Netz high"
        )

    def test_grundfall_heisst_in_der_oberflaeche_basis(self):
        assert _projekt("Sonnenfeld").variantenlabel == "Basis"
        assert _projekt("Sonnenfeld", "Ziel").variantenlabel == "Ziel"

    def test_leerzeichen_werden_abgeschnitten(self):
        # Sonst zerfaellt ein Standort in zwei Gruppen, ohne dass man den
        # Unterschied sieht.
        felder = load_project_yaml(VORLAGE).model_dump()
        felder.update(name="  Sonnenfeld ", variante=" Netz low ")
        p = PVProject.model_validate(felder)
        assert p.name == "Sonnenfeld"
        assert p.variante == "Netz low"

    def test_variante_aendert_die_bewertung_nicht(self):
        from engine import run_valuation
        from engine.io_yaml import load_global_assumptions_yaml

        ga = load_global_assumptions_yaml(
            ROOT / "data" / "global_assumptions.yaml"
        )
        ohne = run_valuation(_projekt("Sonnenfeld"), ga)
        mit = run_valuation(_projekt("Sonnenfeld", "Netz high"), ga)
        assert ohne.kpis.equity_irr == mit.kpis.equity_irr


class TestExcel:
    def test_spalte_steht_direkt_hinter_dem_namen(self):
        assert PROJEKT_SPALTEN[1:3] == ["name", "variante"]

    def test_rundlauf(self):
        projekte = [
            _projekt("Sonnenfeld", "Netz high", "a"),
            _projekt("Sonnenfeld", "", "b"),
        ]
        gelesen = excel_to_projects(projects_to_excel(projekte))
        assert [(p.name, p.variante) for p in gelesen] == [
            ("Sonnenfeld", "Netz high"),
            ("Sonnenfeld", ""),
        ]

    def test_datei_ohne_variantenspalte_bleibt_lesbar(self):
        """Abwaertskompatibilitaet: Alle frueher gesicherten Dateien
        kennen die Spalte nicht - jede Zeile ist dann der Grundfall."""
        import io

        import pandas as pd

        assert "variante" in OPTIONALE_PROJEKT_SPALTEN
        tabelle = pd.read_excel(
            io.BytesIO(projects_to_excel([_projekt("Sonnenfeld", "Netz high")])),
            sheet_name="Projekte",
        ).drop(columns=["variante"])
        puffer = io.BytesIO()
        with pd.ExcelWriter(puffer, engine="openpyxl") as writer:
            tabelle.to_excel(writer, sheet_name="Projekte", index=False)

        gelesen = excel_to_projects(puffer.getvalue())
        assert gelesen[0].variante == ""

    def test_leere_zelle_wird_nicht_zur_zeichenkette_nan(self):
        """pandas liest eine leere Zelle als NaN; str(NaN) waere 'nan'
        und stuende als Variantenname in der Oberflaeche."""
        gelesen = excel_to_projects(
            projects_to_excel([_projekt("Sonnenfeld"), _projekt("Feld B", "X")])
        )
        assert gelesen[0].variante == ""


@pytest.fixture
def projektordner(tmp_path, monkeypatch):
    """Ein eigener Projektordner mit drei Standorten, davon einer mit
    drei Varianten."""
    from app import services

    for name, variante, pid in [
        ("Buchkirchen", "", "b1"),
        ("Buchkirchen", "8000er Pacht", "b2"),
        ("Buchkirchen", "Netz high", "b3"),
        ("Amstetten", "", "a1"),
        ("Zwentendorf", "Ziel", "z1"),
    ]:
        save_project_yaml(_projekt(name, variante, pid), tmp_path / f"{pid}.yaml")
    monkeypatch.setattr(services, "PROJECTS_DIR", tmp_path)
    return tmp_path


class TestGruppierung:
    def test_reihenfolge_standort_dann_variante_grundfall_zuerst(
        self, projektordner
    ):
        from app import services

        assert list(services.list_project_files()) == [
            "a1", "b1", "b2", "b3", "z1",
        ]

    def test_gruppen_folgen_den_standorten(self, projektordner):
        from app import services

        gruppen = services.gruppiere_nach_standort()
        assert list(gruppen) == ["Amstetten", "Buchkirchen", "Zwentendorf"]
        assert [p.variantenlabel for p in gruppen["Buchkirchen"]] == [
            "Basis", "8000er Pacht", "Netz high",
        ]

    def test_varianten_von_liefert_die_geschwister(self, projektordner):
        from app import services

        projekt = services.get_project("b2")
        assert [p.id for p in services.varianten_von(projekt)] == ["b1", "b2", "b3"]

    def test_einzelner_standort_ist_seine_eigene_gruppe(self, projektordner):
        from app import services

        projekt = services.get_project("a1")
        assert [p.id for p in services.varianten_von(projekt)] == ["a1"]


class TestKopieren:
    def test_kopie_bleibt_am_standort(self, projektordner):
        """Frueher entstand 'Buchkirchen (Kopie)' - ein zweiter Standort
        mit fast gleichem Namen. Genau daraus wuchs die unuebersichtliche
        Projektliste."""
        from app import services

        kopie = services.duplicate_project("b1")
        assert kopie.name == "Buchkirchen"
        assert kopie.variante == "Variante"
        assert len(services.gruppiere_nach_standort()["Buchkirchen"]) == 4

    def test_zweite_kopie_bekommt_einen_freien_namen(self, projektordner):
        from app import services

        services.duplicate_project("b1")
        zweite = services.duplicate_project("b1")
        assert zweite.variante == "Variante 2"

    def test_kopie_uebernimmt_alle_rechenwerte(self, projektordner):
        from app import services

        original = services.get_project("b2")
        kopie = services.duplicate_project("b2")
        unveraendert = original.model_dump(exclude={"id", "variante"})
        assert kopie.model_dump(exclude={"id", "variante"}) == unveraendert



class TestOberflaeche:
    """Die Seitenleiste fuehrt Standorte, das Projektfenster die
    Varianten. Der Test laeuft gegen den echten Projektordner und legt
    ihn danach wieder her - AppTest kennt keinen eigenen Datenpfad."""

    @pytest.fixture
    def app_mit_zweiter_variante(self, tmp_path):
        import shutil

        from streamlit.testing.v1 import AppTest

        from app.config import PROJECTS_DIR

        sicherung = tmp_path / "projects"
        shutil.copytree(PROJECTS_DIR, sicherung)
        vorlage = load_project_yaml(PROJECTS_DIR / "template-agri.yaml")
        zweite = vorlage.model_copy(deep=True)
        zweite.id, zweite.variante = "template-agri-netz-high", "Netz high"
        save_project_yaml(zweite, PROJECTS_DIR / f"{zweite.id}.yaml")
        try:
            app = AppTest.from_file(
                str(ROOT / "streamlit_app.py"), default_timeout=90
            )
            app.run()
            assert not app.exception
            yield app, vorlage, zweite
        finally:
            for datei in PROJECTS_DIR.glob("*.yaml"):
                datei.unlink()
            for datei in sicherung.glob("*.yaml"):
                shutil.copy(datei, PROJECTS_DIR / datei.name)

    def test_seitenleiste_fuehrt_standorte_nicht_varianten(
        self, app_mit_zweiter_variante
    ):
        from app import services

        at, vorlage, zweite = app_mit_zweiter_variante
        eintraege = [b for b in at.button
                     if b.key and b.key.startswith("projektwahl_")]
        assert len(eintraege) == len(services.gruppiere_nach_standort())
        # Beide Varianten stecken hinter EINEM Eintrag, dessen
        # Beschriftung ihre Zahl nennt.
        beschriftung = [b.label for b in eintraege if vorlage.name in b.label][0]
        assert beschriftung.endswith("·2")

    def test_variantenleiste_zeigt_alle_varianten_des_standorts(
        self, app_mit_zweiter_variante
    ):
        at, vorlage, zweite = app_mit_zweiter_variante
        [b for b in at.button if b.key == f"open_{vorlage.id}"][0].click()
        at.run()
        assert not at.exception

        reiter = {b.key: b.label for b in at.button
                  if b.key and b.key.startswith("variante_")}
        assert reiter[f"variante_{vorlage.id}"] == "Basis"
        assert reiter[f"variante_{zweite.id}"] == "Netz high"
        assert "variante_neu" in reiter

    def test_reiter_wechselt_die_offene_variante(self, app_mit_zweiter_variante):
        from app.router import _STATE_ID

        at, vorlage, zweite = app_mit_zweiter_variante
        [b for b in at.button if b.key == f"open_{vorlage.id}"][0].click()
        at.run()
        [b for b in at.button if b.key == f"variante_{zweite.id}"][0].click()
        at.run()
        assert not at.exception
        assert at.session_state[_STATE_ID] == zweite.id


class TestLoeschen:
    """Gemeldet: "Das Loeschen der neu erstellten Varianten klappt nicht."

    Geloescht wurde tatsaechlich - nur entstand die Rueckfrage erst nach
    der Arbeitsflaeche und stand deshalb unterhalb von Kennzahlen,
    Diagrammen und Parameterspalte. Wer im Ueberlaufmenue "Loeschen"
    waehlte, sah oben nichts geschehen.
    """

    def test_rueckfrage_entsteht_vor_der_arbeitsflaeche(self):
        quelle = (ROOT / "app" / "views" / "project_page.py").read_text(
            encoding="utf-8"
        )
        rumpf = quelle[quelle.index("def render_project_page("):]
        assert rumpf.index("_loeschbestaetigung(") < rumpf.index(
            "col_ergebnis, col_parameter = st.columns("
        ), "Die Loeschabfrage wuerde wieder unter der Arbeitsflaeche landen"

    def test_neue_variante_laesst_sich_loeschen(self, tmp_path):
        import shutil

        from streamlit.testing.v1 import AppTest

        from app.config import PROJECTS_DIR
        from app.router import _STATE_ID

        sicherung = tmp_path / "projects"
        shutil.copytree(PROJECTS_DIR, sicherung)
        try:
            at = AppTest.from_file(str(ROOT / "streamlit_app.py"),
                                   default_timeout=90)
            at.run()
            erstes = [b.key for b in at.button
                      if b.key and b.key.startswith("open_")][0]
            [b for b in at.button if b.key == erstes][0].click()
            at.run()
            herkunft = at.session_state[_STATE_ID]

            [b for b in at.button if b.key == "variante_neu"][0].click()
            at.run()
            neue = at.session_state[_STATE_ID]
            assert (PROJECTS_DIR / f"{neue}.yaml").exists()

            [b for b in at.button if b.key == f"del_{neue}"][0].click()
            at.run()
            assert any("löschen" in w.value for w in at.warning)

            [b for b in at.button if b.key == f"del_ok_{neue}"][0].click()
            at.run()
            assert not at.exception
            assert not (PROJECTS_DIR / f"{neue}.yaml").exists()
            # Der Standort bleibt geoeffnet - es gibt dort noch eine
            # Rechnung, ein Sprung ins Portfolio waere unnoetig.
            assert at.session_state[_STATE_ID] == herkunft
        finally:
            for datei in PROJECTS_DIR.glob("*.yaml"):
                datei.unlink()
            for datei in sicherung.glob("*.yaml"):
                shutil.copy(datei, PROJECTS_DIR / datei.name)

