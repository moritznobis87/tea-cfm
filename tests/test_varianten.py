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
        assert PROJEKT_SPALTEN[1:4] == ["name", "standort", "variante"]

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
        # Der Stern markiert den Leitfall - ohne gesetzte Marke gilt die
        # erste Variante.
        assert reiter[f"variante_{vorlage.id}"] == "★ Basis"
        assert reiter[f"variante_{zweite.id}"] == "Netz high"
        assert "variante_neu" in reiter

    def test_leitfall_laesst_sich_in_der_variantenleiste_setzen(
        self, app_mit_zweiter_variante
    ):
        """Gemeldet: "in den Projekten selber kann man nicht einstellen,
        dass eine Variante der Leitfall ist."

        Die Wahl gab es nur in der Vergleichssicht - dort sucht sie
        niemand. Sie gehoert in die Reiterreihe, die sie betrifft.
        """
        from app import services

        at, vorlage, zweite = app_mit_zweiter_variante
        [b for b in at.button if b.key == f"open_{vorlage.id}"][0].click()
        at.run()
        # Der offene Reiter IST der Leitfall - dann gibt es nichts zu
        # waehlen.
        assert not [b for b in at.button if b.key == "variante_leitfall"]

        [b for b in at.button if b.key == f"variante_{zweite.id}"][0].click()
        at.run()
        knopf = [b for b in at.button if b.key == "variante_leitfall"]
        assert knopf, "Bei der Nebenvariante fehlt die Wahl"
        knopf[0].click()
        at.run()
        assert not at.exception

        varianten = services.varianten_von(services.get_project(zweite.id))
        assert services.leitvariante_von(varianten).id == zweite.id
        reiter = {b.key: b.label for b in at.button
                  if b.key and b.key.startswith("variante_")}
        assert reiter[f"variante_{zweite.id}"] == "★ Netz high"
        assert reiter[f"variante_{vorlage.id}"] == "Basis"

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



class TestLeitvariante:
    """Die Leitvariante ist die Rechnung, die fuer einen Standort gilt.

    Ohne sie zaehlt ein Standort mit drei Sensitivitaeten dreifach: In
    Leistung, Investitionsvolumen und Eigenkapital des Portfolios stuende
    dieselbe Flaeche mehrfach.
    """

    def test_ohne_marke_gilt_die_erste_variante(self, projektordner):
        from app import services

        gruppe = services.gruppiere_nach_standort()["Buchkirchen"]
        assert services.leitvariante_von(gruppe).id == "b1"

    def test_marke_ist_je_standort_exklusiv(self, projektordner):
        from app import services

        services.setze_leitvariante("b3")
        gesetzt = [p.id for p in services.gruppiere_nach_standort()["Buchkirchen"]
                   if p.leitvariante]
        assert gesetzt == ["b3"]
        services.setze_leitvariante("b2")
        gesetzt = [p.id for p in services.gruppiere_nach_standort()["Buchkirchen"]
                   if p.leitvariante]
        assert gesetzt == ["b2"], "zwei Leitfaelle ergaeben zwei Portfoliozahlen"

    def test_je_standort_genau_eine(self, projektordner):
        from app import services

        leit = services.leitvarianten()
        assert len(leit) == len(services.gruppiere_nach_standort())
        assert [p.id for p in leit] == ["a1", "b1", "z1"]

    def test_portfolio_zaehlt_den_standort_einmal(self, projektordner):
        """Die Zahl, um die es geht: drei Buchkirchen-Rechnungen sind ein
        Feld, nicht drei."""
        from app import services

        alle = sum(p.nennleistung_kwp for p in services.list_projects())
        leit = sum(p.nennleistung_kwp for p in services.leitvarianten())
        assert leit < alle
        assert leit == sum(
            services.leitvariante_von(v).nennleistung_kwp
            for v in services.gruppiere_nach_standort().values()
        )

    def test_marke_ueberlebt_den_excel_rundlauf(self):
        p1 = _projekt("Sonnenfeld", "", "a")
        p2 = _projekt("Sonnenfeld", "Netz high", "b")
        p2.leitvariante = True
        gelesen = excel_to_projects(projects_to_excel([p1, p2]))
        assert [p.leitvariante for p in gelesen] == [False, True]

    def test_datei_ohne_spalte_bleibt_lesbar(self):
        """Abwaertskompatibilitaet: Fuer alle frueher gesicherten Dateien
        gilt je Standort die erste Variante."""
        import io

        import pandas as pd

        from app.services import leitvariante_von

        assert "leitvariante" in OPTIONALE_PROJEKT_SPALTEN
        tabelle = pd.read_excel(
            io.BytesIO(projects_to_excel(
                [_projekt("Sonnenfeld", "", "a"),
                 _projekt("Sonnenfeld", "Netz high", "b")]
            )),
            sheet_name="Projekte",
        ).drop(columns=["leitvariante"])
        puffer = io.BytesIO()
        with pd.ExcelWriter(puffer, engine="openpyxl") as writer:
            tabelle.to_excel(writer, sheet_name="Projekte", index=False)

        gelesen = excel_to_projects(puffer.getvalue())
        assert not any(p.leitvariante for p in gelesen)
        assert leitvariante_von(gelesen).id == "a"


class TestUnterschiede:
    """Die Unterschiedstabelle wird aus den Projektdaten abgeleitet - sie
    ist die Antwort auf "was hatte ich hier eigentlich geaendert?"."""

    def test_nur_abweichende_felder(self):
        from app.components.varianten import unterschiede

        a = _projekt("Sonnenfeld", "Basis", "a")
        b = _projekt("Sonnenfeld", "Netz high", "b")
        b.capex.netzanschluss_eur = a.capex.netzanschluss_eur + 50_000
        b.pacht_eur_kwp_jahr = a.pacht_eur_kwp_jahr + 2

        felder = {u.feld for u in unterschiede([a, b], a)}
        assert felder == {"capex.netzanschluss_eur", "pacht_eur_kwp_jahr"}

    def test_abweichung_bezieht_sich_auf_die_referenz(self):
        from app.components.varianten import unterschiede

        a = _projekt("Sonnenfeld", "Basis", "a")
        b = _projekt("Sonnenfeld", "Hoch", "b")
        b.eag_zuschlagswert_ct_kwh = a.eag_zuschlagswert_ct_kwh + 1

        gegen_a = unterschiede([a, b], a)[0]
        assert gegen_a.abweichend == [False, True]
        gegen_b = unterschiede([a, b], b)[0]
        assert gegen_b.abweichend == [True, False]

    def test_identische_varianten_ergeben_keine_zeile(self):
        from app.components.varianten import unterschiede

        a = _projekt("Sonnenfeld", "Basis", "a")
        b = _projekt("Sonnenfeld", "Kopie", "b")
        assert unterschiede([a, b], a) == []

    def test_alle_projektfelder_sind_abgedeckt(self):
        """Regressionsschutz: Ein spaeter ergaenztes Projektfeld darf
        nicht still aus dem Vergleich fallen."""
        from app.components.varianten import geprueft_alle_felder

        assert geprueft_alle_felder([_projekt("Sonnenfeld")]) == set()

    def test_freie_positionen_als_summe(self):
        """Frei benannte Positionen haben je Projekt andere Namen - ein
        Feldvergleich ergaebe eine Tabelle ohne gemeinsame Zeilen."""
        from app.components.varianten import unterschiede
        from engine import CapexPosition

        a = _projekt("Sonnenfeld", "Basis", "a")
        b = _projekt("Sonnenfeld", "Mit Zusatz", "b")
        b.capex.zusatzpositionen = [
            CapexPosition(name="Kampfmittelräumung", betrag_eur=25_000)
        ]
        zeile = [u for u in unterschiede([a, b], a)
                 if u.feld == "capex.zusatzpositionen"]
        assert len(zeile) == 1
        assert zeile[0].abweichend == [False, True]


class TestVergleichssicht:
    """Die fuenfte Sicht der Projektseite."""

    def test_vergleich_ist_eine_eigene_adresse(self):
        from app import router
        from app.views.project_page import _TABS

        assert "vergleich" in router.PROJEKT_TABS
        assert tuple(code for code, _ in _TABS) == router.PROJEKT_TABS

    def test_parameterspalte_entfaellt_im_vergleich(self):
        """Der Vergleich zeigt alle Varianten, die Parameterspalte
        bearbeitet nur die eine geoeffnete - nebeneinander naehme sie ein
        Viertel der Breite fuer eine Eingabe, die nichts beitraegt."""
        quelle = (ROOT / "app" / "views" / "project_page.py").read_text(
            encoding="utf-8"
        )
        rumpf = quelle[quelle.index("def render_project_page("):]
        assert 'ist_vergleich = router.aktueller_tab() == "vergleich"' in rumpf
        assert rumpf.index("if ist_vergleich:") < rumpf.index(
            "render_parameter_spalte("
        )


class TestStandortbezeichnung:
    """Projektkennung und Standort sind zwei Namen mit zwei Aufgaben.

    Die Kennung ("OÖ_St.Georgen_Spitzwieser") steht in der Seitenleiste
    und identifiziert; der Standort ("St. Georgen") beschriftet
    Diagramme. Als Punktbeschriftung ist die Kennung zu lang - bei
    dreissig Projekten ueberlagern sich die Namen.
    """

    def test_roemische_ziffern(self):
        from app.services import roemisch

        assert [roemisch(i) for i in (1, 2, 3, 4, 5, 9, 12)] == [
            "I", "II", "III", "IV", "V", "IX", "XII",
        ]

    def test_einzelner_standort_ohne_nummer(self):
        from app.services import standort_labels

        a = _projekt("OÖ_St.Georgen_Spitzwieser", "", "a")
        a.standort = "St. Georgen"
        assert standort_labels([a]) == {"OÖ_St.Georgen_Spitzwieser": "St. Georgen"}

    def test_mehrere_projekte_am_ort_werden_nummeriert(self):
        from app.services import standort_labels

        a = _projekt("OÖ_St.Georgen_Spitzwieser", "", "a")
        b = _projekt("OÖ_St.Georgen_Huber", "", "b")
        a.standort = b.standort = "St. Georgen"
        labels = standort_labels([a, b])
        assert labels["OÖ_St.Georgen_Spitzwieser"] == "St. Georgen I"
        assert labels["OÖ_St.Georgen_Huber"] == "St. Georgen II"

    def test_varianten_zaehlen_nicht_als_zweites_projekt(self):
        """Drei Sensitivitaeten sind ein Feld - sie duerfen keine
        Nummerierung ausloesen."""
        from app.services import standort_labels

        varianten = []
        for i, name in enumerate(["", "Netz high", "Ziel"]):
            v = _projekt("OÖ_St.Georgen_Spitzwieser", name, f"v{i}")
            v.standort = "St. Georgen"
            varianten.append(v)
        assert set(standort_labels(varianten).values()) == {"St. Georgen"}

    def test_ohne_standort_bleibt_die_kennung(self):
        """Ein nie gepflegter Bestand verliert keine Beschriftung."""
        from app.services import standort_labels

        a = _projekt("OÖ_St.Georgen_Spitzwieser", "", "a")
        assert standort_labels([a]) == {
            "OÖ_St.Georgen_Spitzwieser": "OÖ_St.Georgen_Spitzwieser"
        }

    def test_excel_fuehrt_die_spalte(self):
        assert PROJEKT_SPALTEN[1:4] == ["name", "standort", "variante"]
        assert "standort" in OPTIONALE_PROJEKT_SPALTEN

        a = _projekt("OÖ_St.Georgen_Spitzwieser", "", "a")
        a.standort = "St. Georgen"
        gelesen = excel_to_projects(projects_to_excel([a]))
        assert gelesen[0].standort == "St. Georgen"

    def test_datei_ohne_standortspalte_bleibt_lesbar(self):
        import io

        import pandas as pd

        a = _projekt("Sonnenfeld", "", "a")
        a.standort = "Sonnenfeld"
        tabelle = pd.read_excel(
            io.BytesIO(projects_to_excel([a])), sheet_name="Projekte"
        ).drop(columns=["standort"])
        puffer = io.BytesIO()
        with pd.ExcelWriter(puffer, engine="openpyxl") as writer:
            tabelle.to_excel(writer, sheet_name="Projekte", index=False)
        assert excel_to_projects(puffer.getvalue())[0].standort == ""


class TestLandkarteUndRangliste:
    """Zwei Reiter statt einer ueberladenen Punktwolke."""

    def _tabelle(self):
        import pandas as pd

        return pd.DataFrame(
            [
                {"id": "b1", "name": "Buchkirchen", "kennung": "OÖ_Buchkirchen",
                 "variante": "Basis", "leitfall": True, "varianten": "<br>…",
                 "typ": "Agri-PV", "kwp": 2800, "irr_pct": 9.8,
                 "invest_eur_kwp": 596, "npv_eur": 900_000.0},
                {"id": "b2", "name": "Buchkirchen", "kennung": "OÖ_Buchkirchen",
                 "variante": "Netz high", "leitfall": False, "varianten": "",
                 "typ": "Agri-PV", "kwp": 2800, "irr_pct": 6.5,
                 "invest_eur_kwp": 640, "npv_eur": -150_000.0},
                {"id": "a1", "name": "Amstetten", "kennung": "NÖ_Amstetten",
                 "variante": "Basis", "leitfall": True, "varianten": "",
                 "typ": "Agri-PV", "kwp": 2000, "irr_pct": 12.0,
                 "invest_eur_kwp": 540, "npv_eur": 480_000.0},
            ]
        )

    def test_ohne_fokus_nur_leitvarianten(self):
        """Die uebrigen Rechnungen stehen im Tooltip, nicht als eigene
        Blase - sonst waechst die Punktwolke mit jeder Sensitivitaet."""
        from app.components import charts

        fig = charts.portfolio_bubble_chart(self._tabelle(), None)
        punkte = [s for s in fig.data if s.mode == "markers+text"]
        gezeigt = {n for s in punkte for n in s.customdata[:, 1]}
        assert gezeigt == {"OÖ_Buchkirchen", "NÖ_Amstetten"}
        assert not [s for s in fig.data if s.mode == "lines"]

    def test_fokus_klappt_genau_einen_standort_auf(self):
        from app.components import charts

        fig = charts.portfolio_bubble_chart(
            self._tabelle(), None, fokus="OÖ_Buchkirchen"
        )
        assert len([s for s in fig.data if s.mode == "lines"]) == 1
        punkte = next(s for s in fig.data if s.mode == "markers+text")
        beschriftet = {t for t in punkte.text if t}
        # Im Fokus stehen die Variantennamen, sonst nichts.
        assert beschriftet == {"Basis", "Netz high"}

    def test_rangliste_ist_sortiert_und_zeigt_die_spanne(self):
        from app.components import charts

        fig = charts.portfolio_rangliste_chart(
            [
                {"label": "Buchkirchen", "kennung": "OÖ_Buchkirchen",
                 "leit_id": "b1", "leit_irr": 9.8,
                 "varianten": [("Basis", 9.8), ("Netz high", 6.5)]},
                {"label": "Amstetten", "kennung": "NÖ_Amstetten",
                 "leit_id": "a1", "leit_irr": 12.0,
                 "varianten": [("Basis", 12.0)]},
            ],
            ziel_pct=0.08,
        )
        # Aufsteigend, damit die beste Zeile oben steht.
        assert list(fig.layout.yaxis.categoryarray) == ["Buchkirchen", "Amstetten"]
        spannen = [s for s in fig.data if s.mode == "lines"]
        assert len(spannen) == 1 and list(spannen[0].x) == [6.5, 9.8]

    def test_x_achse_laesst_sich_auf_den_deckungsbeitrag_stellen(self):
        """Rendite ueber Betrag statt ueber Effizienz.

        Zwei Fragen, zwei Antworten: Beim spezifischen Invest liegt
        Amstetten vorn (540 €/kWp), beim Deckungsbeitrag Buchkirchen
        (900 T€) - genau deshalb der Umschalter.
        """
        from app.components import charts

        fig = charts.portfolio_bubble_chart(
            self._tabelle(), None, x_feld="npv_eur"
        )
        punkte = next(s for s in fig.data if s.mode == "markers+text")
        assert sorted(punkte.x) == [480_000.0, 900_000.0]
        assert "NPV" in fig.layout.xaxis.title.text

    def test_nulllinie_nur_bei_negativem_deckungsbeitrag(self):
        """Die Null trennt Wertschaffung von Wertvernichtung - aber nur,
        wenn ueberhaupt ein sichtbarer Punkt links davon liegt."""
        from app.components import charts

        ohne = charts.portfolio_bubble_chart(
            self._tabelle(), None, x_feld="npv_eur"
        )
        assert not ohne.layout.shapes

        mit = charts.portfolio_bubble_chart(
            self._tabelle(), None, fokus="OÖ_Buchkirchen", x_feld="npv_eur"
        )
        assert len(mit.layout.shapes) == 1

    def test_unbekannte_achse_faellt_auf_die_voreinstellung_zurueck(self):
        """Der Wunsch kommt aus einem Widget - ein abgewaehltes Segment
        liefert None und darf die Karte nicht zerlegen."""
        from app.components import charts

        fig = charts.portfolio_bubble_chart(
            self._tabelle(), None, x_feld="gibt_es_nicht"
        )
        punkte = next(s for s in fig.data if s.mode == "markers+text")
        assert sorted(punkte.x) == [480_000.0, 900_000.0]

    def test_achse_ohne_spalte_bricht_nicht(self):
        """Aeltere Aufrufer liefern die NPV-Spalte nicht mit - dann gilt
        die naechste vorhandene Achse statt eines KeyError."""
        from app.components import charts

        tabelle = self._tabelle().drop(columns=["npv_eur"])
        fig = charts.portfolio_bubble_chart(tabelle, None, x_feld="npv_eur")
        punkte = next(s for s in fig.data if s.mode == "markers+text")
        assert sorted(punkte.x) == [540, 596]


class TestBeschriftungsplaetze:
    """Namen weichen einander aus, statt uebereinander zu liegen.

    Plotly kennt kein Ausweichen: Eine Textposition sitzt starr an ihrem
    Punkt. Bei eng beieinanderliegenden Projekten schoben sich die Namen
    deshalb ineinander ("LivingBrick" ueber "Schäffern").
    """

    def _kaesten(self, punkte, plaetze):
        """Die belegten Rechtecke zu einer Platzierung - dieselbe
        Rechnung wie im Modul, hier als unabhaengige Gegenprobe."""
        from app.components import charts

        kaesten = []
        for p in punkte:
            lage = plaetze[p["id"]]
            if not lage:
                continue
            dx, dy = next(
                (x, y) for pos, x, y in charts._LABEL_PLAETZE if pos == lage
            )
            hb = charts._LABEL_ZEICHENBREITE * len(p["text"]) / 2
            kaesten.append((
                p["nx"] + dx * (hb + charts._BLASE_BREITE / 2),
                p["ny"] + dy * (charts._LABEL_HOEHE / 2 + charts._BLASE_HOEHE / 2),
                hb, charts._LABEL_HOEHE / 2,
            ))
        return kaesten

    def test_dicht_beieinander_und_trotzdem_lesbar(self):
        from app.components import charts

        punkte = [
            {"id": "a", "text": "Schäffern", "nx": 0.05, "ny": 0.83},
            {"id": "b", "text": "LivingBrick", "nx": 0.01, "ny": 0.85},
            {"id": "c", "text": "St. Agatha", "nx": 0.34, "ny": 0.86},
            {"id": "d", "text": "Ziprein", "nx": 0.34, "ny": 0.88},
        ]
        plaetze = charts.beschriftungsplaetze(punkte)
        assert all(plaetze[p["id"]] for p in punkte), "kein Name faellt weg"
        kaesten = self._kaesten(punkte, plaetze)
        for i, a in enumerate(kaesten):
            for b in kaesten[i + 1:]:
                assert not charts._ueberlappt(a, b)

    def test_kein_name_ragt_aus_der_zeichenflaeche(self):
        """Plotly schneidet am Rand ab - aus "LivingBrick" wurde
        "...gBricx"."""
        from app.components import charts

        punkte = [
            {"id": "links", "text": "Waldneukirchen", "nx": 0.0, "ny": 0.5},
            {"id": "rechts", "text": "Waldneukirchen", "nx": 1.0, "ny": 0.1},
        ]
        plaetze = charts.beschriftungsplaetze(punkte)
        for kasten in self._kaesten(punkte, plaetze):
            assert charts._im_bild(kasten)

    def test_ohne_freien_platz_bleibt_der_name_weg(self):
        """Ein unlesbarer Textklumpen hilft niemandem; der Name steht im
        Hover."""
        from app.components import charts

        punkte = [
            {"id": f"p{i}", "text": "Sankt Georgen an der Gusen",
             "nx": 0.5 + i * 0.004, "ny": 0.5 + i * 0.004}
            for i in range(8)
        ]
        plaetze = charts.beschriftungsplaetze(punkte)
        assert plaetze["p0"], "der erste Punkt bekommt den besten Platz"
        assert any(not lage for lage in plaetze.values())
        kaesten = self._kaesten(punkte, plaetze)
        for i, a in enumerate(kaesten):
            for b in kaesten[i + 1:]:
                assert not charts._ueberlappt(a, b)

    def test_leerer_text_wird_nicht_platziert(self):
        """Ausserhalb des Fokus tragen die Punkte keinen Namen - sie
        duerfen den Platz auch nicht belegen."""
        from app.components import charts

        plaetze = charts.beschriftungsplaetze([
            {"id": "a", "text": "", "nx": 0.5, "ny": 0.5},
            {"id": "b", "text": "Buchkirchen", "nx": 0.5, "ny": 0.55},
        ])
        assert plaetze["a"] == ""
        assert plaetze["b"]
