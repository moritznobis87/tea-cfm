"""
Wegsteuerung und Parameterspalte.

Zwei Umbauten werden hier abgesichert: die Seite steht in der Adresse
statt nur im Session-State (app/router.py), und die Projektseite rechnet
Parameteraenderungen sofort durch, ohne sie zu speichern
(app/views/project_page.py).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from streamlit.testing.v1 import AppTest  # noqa: E402


@pytest.fixture
def at() -> AppTest:
    app = AppTest.from_file(str(ROOT / "streamlit_app.py"), default_timeout=90)
    app.run()
    assert not app.exception
    return app


def _klick(at: AppTest, key: str) -> AppTest:
    [b for b in at.button if b.key == key][0].click()
    at.run()
    assert not at.exception
    return at


def _leitwert(at: AppTest) -> str:
    markup = [m.value for m in at.markdown if 'class="kpi-hero-value"' in m.value][0]
    return re.search(r'class="kpi-hero-value">([^<]+)', markup).group(1)


class TestRouter:
    """Die reine Zustandslogik - ohne Browser gibt es keine echten
    Adressparameter, der Session-State bleibt aber massgeblich."""

    def test_startet_im_portfolio(self):
        from app import router

        assert router.STANDARD_SEITE == "portfolio"
        assert "projekt" in router.SEITEN
        assert router.STANDARD_TAB in router.PROJEKT_TABS

    def test_alle_tabs_der_projektseite_sind_bekannt(self):
        from app import router
        from app.views.project_page import _TABS

        assert tuple(code for code, _ in _TABS) == router.PROJEKT_TABS


class TestSeitenwechsel:
    def test_projektwahl_in_der_seitenleiste_oeffnet_die_projektseite(
        self, at: AppTest
    ):
        keys = [b.key for b in at.button if b.key]
        projektknoepfe = [k for k in keys if k.startswith("projektwahl_")]
        assert projektknoepfe, "Projektliste fehlt in der Seitenleiste"
        at = _klick(at, projektknoepfe[0])
        assert any("kontextzeile" in m.value for m in at.markdown)
        assert any('data-kpi-group="projekt"' in m.value for m in at.markdown)

    def test_sichern_bleibt_in_der_navigation(self, at: AppTest):
        """Ausdrueckliche Anforderung: haeufig gebraucht, deshalb ein Klick
        statt eines aufzuklappenden Bereichs."""
        beschriftungen = [d.label for d in at.get("download_button")]
        assert "Projekte sichern" in beschriftungen
        assert "Annahmen sichern" in beschriftungen

    def test_werkzeuge_stehen_in_einer_eigenen_gruppe(self, at: AppTest):
        """Die Ausschreibungsanalyse fuehrt keine Projektdaten und steht
        deshalb nicht gleichrangig neben Portfolio und Annahmen."""
        from app.components.sidebar import _NAV, _WERKZEUGE

        assert [code for code, _ in _NAV] == ["portfolio", "annahmen"]
        assert [code for code, _ in _WERKZEUGE] == ["ausschreibung"]

    def test_auktionsseite_weist_sich_als_analysewerkzeug_aus(self, at: AppTest):
        at = _klick(at, "nav_ausschreibung")
        hinweise = " ".join(i.value for i in at.info)
        assert "Analysewerkzeug" in hinweise
        assert "verändert keine Projektdaten" in hinweise


class TestParameterspalte:
    def _projektseite(self, at: AppTest) -> tuple[AppTest, str]:
        keys = [b.key for b in at.button if b.key and b.key.startswith("open_")]
        at = _klick(at, keys[0])
        projekt_id = keys[0].removeprefix("open_")
        return at, f"param_{projekt_id}"

    def test_frisch_geoeffnet_ohne_offene_aenderungen(self, at: AppTest):
        """Rundungen zwischen Anzeige (€/kWp) und Modell duerfen keine
        Aenderungen vortaeuschen."""
        at, form_key = self._projektseite(at)
        assert any(
            "keine offenen Änderungen" in c.value for c in at.caption
        )
        gesperrt = {
            b.key: b.disabled for b in at.button if b.key and "__" in b.key
        }
        assert gesperrt[f"{form_key}__speichern"] is True
        assert gesperrt[f"{form_key}__verwerfen"] is True

    def test_aenderung_rechnet_sofort_und_speichert_nicht(self, at: AppTest):
        at, form_key = self._projektseite(at)
        vorher = _leitwert(at)

        feld = [n for n in at.get("number_input")
                if n.key == f"{form_key}_ekanteil"][0]
        feld.set_value(feld.value + 15.0)
        at.run()
        assert not at.exception

        assert _leitwert(at) != vorher, "Equity IRR folgt der Eingabe nicht"
        assert any(":orange[" in m.value and "Änderung" in m.value
                   for m in at.markdown)
        assert any("ungespeicherte Änderung" in m.value for m in at.markdown)
        gesperrt = {
            b.key: b.disabled for b in at.button if b.key and "__" in b.key
        }
        assert gesperrt[f"{form_key}__speichern"] is False

        # Verwerfen stellt den gespeicherten Stand wieder her - die Datei
        # auf der Platte wurde nie angefasst.
        _klick(at, f"{form_key}__verwerfen")
        assert _leitwert(at) == vorher

    def test_risikosichten_weisen_auf_den_gespeicherten_stand_hin(
        self, at: AppTest
    ):
        at, form_key = self._projektseite(at)
        feld = [n for n in at.get("number_input")
                if n.key == f"{form_key}_ekanteil"][0]
        feld.set_value(feld.value + 15.0)
        at.run()

        at.get("button_group")[0].set_value("Risiko")
        at.run()
        assert not at.exception
        assert any("gespeicherten Stand" in i.value for i in at.info)

        _klick(at, f"{form_key}__verwerfen")


class TestPachtblock:
    """Gemeldet: Ueberschrift und Umschalter der Pacht standen in der
    Mitte der Spalte, die zugehoerigen Wertfelder erst ganz unten.

    Ursache war die Regel "Umschalter ausserhalb von st.form" - sie
    betrifft aber nur die Umschalter, nicht die Werte. Der Block steht
    jetzt vollstaendig an einer Stelle.
    """

    def _spalte(self, at: AppTest) -> tuple[AppTest, str]:
        keys = [b.key for b in at.button if b.key and b.key.startswith("open_")]
        at = _klick(at, keys[0])
        return at, f"param_{keys[0].removeprefix('open_')}"

    def test_wert_und_konfiguration_gehoeren_zusammen(self, at: AppTest):
        at, form_key = self._spalte(at)
        # Der Wert steht in der Hauptansicht, die Vertragsform im
        # Popover - beide existieren, und zwar im selben Durchlauf.
        werte = {n.key for n in at.get("number_input") if n.key}
        assert f"{form_key}_pacht_ha" in werte or f"{form_key}_pacht_kwp" in werte
        radios = {r.key for r in at.get("radio") if r.key}
        assert f"{form_key}_pachtmodus" in radios
        assert f"{form_key}_pacht_einheit" in radios

    def test_einheit_folgt_dem_projekt(self, at: AppTest):
        """Ein Bestand ohne Flaeche ist in €/kWp gepflegt - ihn im
        €/ha-Modus zu oeffnen, rechnete den Wert ueber eine erfundene
        Flaeche um."""
        from app import services

        at, form_key = self._spalte(at)
        projekt = services.get_project(form_key.removeprefix("param_"))
        einheit = [r for r in at.get("radio")
                   if r.key == f"{form_key}_pacht_einheit"][0].value
        erwartet = "€/ha/Jahr" if projekt.projektflaeche_ha else "€/kWp/Jahr"
        assert einheit == erwartet

    def test_pachtwert_meldet_keine_scheinaenderung(self, at: AppTest):
        """Die €/ha-Anzeige wird auf zwei Nachkommastellen gerundet und
        zurueckgerechnet; auf ganze Euro gerundet wich der €/kWp-Wert so
        weit ab, dass die Seite eine Aenderung meldete."""
        at, _ = self._spalte(at)
        assert any("keine offenen Änderungen" in c.value for c in at.caption)


class TestVierAnsichten:
    def test_segmentwahl_bietet_die_gleichrangigen_sichten(self, at: AppTest):
        """Vier Sichten auf das Projekt, dazu der Variantenvergleich.

        Der Vergleich ist die fuenfte gleichrangige Sicht: Er zeigt
        denselben Standort, nur alle seine Rechnungen nebeneinander.
        """
        keys = [b.key for b in at.button if b.key and b.key.startswith("open_")]
        at = _klick(at, keys[0])
        wahl = at.get("button_group")[0]
        assert wahl.options == [
            "Ergebnis", "Finanzierung", "Risiko", "Annahmen", "Vergleich",
        ]
        assert wahl.value == "Ergebnis"

    @pytest.mark.parametrize(
        "sicht", ["Finanzierung", "Risiko", "Annahmen"]
    )
    def test_jede_sicht_rendert(self, at: AppTest, sicht: str):
        keys = [b.key for b in at.button if b.key and b.key.startswith("open_")]
        at = _klick(at, keys[0])
        at.get("button_group")[0].set_value(sicht)
        at.run()
        assert not at.exception

    def test_portfolio_analytik_ohne_klappfeld(self, at: AppTest):
        """Regel: Tabs sind gleichrangige Sichten, Klappfelder optionales
        Detail - und nie ineinander."""
        quelle = (ROOT / "app" / "views" / "overview.py").read_text(
            encoding="utf-8"
        )
        analytik = quelle[quelle.index("portfolio_analytik_titel"):]
        analytik = analytik[: analytik.index("portfolio_tab_tabelle")]
        assert "st.expander" not in analytik


class TestAlphabetischeReihenfolge:
    """Projekte stehen in Seitenleiste und Kachelübersicht in der
    Reihenfolge ihrer ANGEZEIGTEN Namen.

    Vorher wurde nach Dateinamen sortiert. Der Dateiname folgt der
    Projekt-ID, und die bleibt bei einer Umbenennung bewusst stehen -
    die Liste stand danach in einer Reihenfolge, die mit den sichtbaren
    Namen nichts mehr zu tun hatte.
    """

    def test_sortierschluessel_loest_umlaute_und_grossschreibung_auf(self):
        from app.services import sortierschluessel

        namen = ["Zwentendorf", "Ötscher", "agri", "Agri"]
        assert sorted(namen, key=sortierschluessel) == [
            "agri", "Agri", "Ötscher", "Zwentendorf",
        ]

    def test_liste_folgt_den_projektnamen(self, tmp_path, monkeypatch):
        from app import services
        from engine.io_yaml import load_project_yaml, save_project_yaml

        vorlage = load_project_yaml(ROOT / "data" / "projects" / "template-agri.yaml")
        # Dateinamen (= IDs) bewusst gegenlaeufig zur Anzeige waehlen.
        for pid, name in [
            ("aaa", "Zwentendorf Nord"),
            ("mmm", "Ötscher Süd"),
            ("zzz", "Agri West"),
        ]:
            kopie = vorlage.model_copy(deep=True)
            kopie.id, kopie.name = pid, name
            save_project_yaml(kopie, tmp_path / f"{pid}.yaml")

        monkeypatch.setattr(services, "PROJECTS_DIR", tmp_path)
        assert list(services.list_project_files()) == ["zzz", "mmm", "aaa"]

    def test_seitenleiste_und_kacheln_zeigen_dieselbe_reihenfolge(self, at: AppTest):
        seitenleiste = [
            b.key.removeprefix("projektwahl_")
            for b in at.button
            if b.key and b.key.startswith("projektwahl_")
        ]
        kacheln = [
            b.key.removeprefix("open_")
            for b in at.button
            if b.key and b.key.startswith("open_")
        ]
        assert seitenleiste == kacheln


class TestProjektUmbenennen:
    """Gemeldet: Der Titel eines Projekts liess sich nicht mehr aendern.

    Das Feld stand danach an erster Stelle der Parameterspalte. Seit der
    Aufraeumrunde steht es nicht mehr dort: Name und Standort sind keine
    What-if-Groessen und kosteten in der schmalen Live-Spalte dauerhaft
    Platz. Sie stehen jetzt im Ueberlaufmenue des Projektkopfs, der
    Variantenname in der Reiterreihe - beide speichern sofort statt ueber
    den Entwurf.
    """

    def test_stammdaten_stehen_nicht_mehr_in_der_parameterspalte(
        self, at: AppTest
    ):
        keys = [b.key for b in at.button if b.key and b.key.startswith("open_")]
        at = _klick(at, keys[0])
        projekt_id = keys[0].removeprefix("open_")

        spaltenfelder = {t.key for t in at.get("text_input") if t.key}
        for feld in ("name", "standort", "variante"):
            assert f"param_{projekt_id}_{feld}" not in spaltenfelder

    def test_umbenennen_im_ueberlaufmenue_speichert_sofort(
        self, at: AppTest, tmp_path
    ):
        import shutil

        from app.config import PROJECTS_DIR

        sicherung = tmp_path / "projects"
        shutil.copytree(PROJECTS_DIR, sicherung)
        try:
            keys = [b.key for b in at.button
                    if b.key and b.key.startswith("open_")]
            at = _klick(at, keys[0])
            projekt_id = keys[0].removeprefix("open_")

            feld = [t for t in at.get("text_input")
                    if t.key == f"stammdaten_name_{projekt_id}"][0]
            feld.set_value("Umbenannt im Test")
            at.run()
            assert not at.exception
            # Der Name gehoert nicht zum Entwurf - die Rechnung bleibt
            # unveraendert, es steht keine offene Aenderung an.
            assert not any(":orange[" in m.value and "Änderung" in m.value
                           for m in at.markdown)

            _klick(at, f"stammdaten_speichern_{projekt_id}")
            assert any(m.value == "### Umbenannt im Test" for m in at.markdown)
            # Die Datei behaelt ihre Identitaet, nur der Name aendert sich.
            assert (PROJECTS_DIR / f"{projekt_id}.yaml").exists()
            assert "Umbenannt im Test" in [
                b.label for b in at.button
                if b.key and b.key.startswith("projektwahl_")
            ]
        finally:
            for datei in PROJECTS_DIR.glob("*.yaml"):
                datei.unlink()
            for datei in sicherung.glob("*.yaml"):
                shutil.copy(datei, PROJECTS_DIR / datei.name)

    def test_variante_wird_in_der_reiterreihe_umbenannt(self, at: AppTest, tmp_path):
        import shutil

        from app.config import PROJECTS_DIR
        from engine.io_yaml import load_project_yaml

        sicherung = tmp_path / "projects"
        shutil.copytree(PROJECTS_DIR, sicherung)
        try:
            keys = [b.key for b in at.button
                    if b.key and b.key.startswith("open_")]
            at = _klick(at, keys[0])
            projekt_id = keys[0].removeprefix("open_")

            feld = [t for t in at.get("text_input")
                    if t.key == f"variante_name_{projekt_id}"][0]
            feld.set_value("Netz hoch")
            at.run()
            _klick(at, f"variante_name_speichern_{projekt_id}")
            assert not at.exception

            gespeichert = load_project_yaml(PROJECTS_DIR / f"{projekt_id}.yaml")
            assert gespeichert.variante == "Netz hoch"
        finally:
            for datei in PROJECTS_DIR.glob("*.yaml"):
                datei.unlink()
            for datei in sicherung.glob("*.yaml"):
                shutil.copy(datei, PROJECTS_DIR / datei.name)


class TestKachelraster:
    """Gemeldet: Die Projektkacheln fluchteten nicht.

    Ursache war ein einziger Spaltensatz mit Modulo-Verteilung: Streamlit
    stapelt die Karten dann SPALTENWEISE, und eine hohe Karte verschiebt
    alles darunter in ihrer Spalte. Jetzt ein Spaltensatz je Reihe, dazu
    eine feste Kartenhoehe.
    """

    def test_je_reihe_ein_eigener_spaltensatz(self):
        quelle = (ROOT / "app" / "views" / "overview.py").read_text(
            encoding="utf-8"
        )
        block = quelle[quelle.index("# --- Projektkarten"):]
        assert "for reihe in range(0, len(gruppen), _KARTEN_JE_REIHE)" in block
        # Der alte Modulo-Griff darf nicht zurueckkehren.
        assert "i % len(cols)" not in block

    def test_karten_haben_eine_feste_hoehe(self):
        css = (ROOT / "app" / "theme.py").read_text(encoding="utf-8")
        block = css[css.index(".project-card {{"):]
        block = block[: block.index("}}")]
        assert "height:" in block, "ohne feste Hoehe fluchten die Knoepfe nicht"

    def test_lange_projektnamen_brechen_die_karte_nicht(self):
        css = (ROOT / "app" / "theme.py").read_text(encoding="utf-8")
        block = css[css.index(".project-card .card-title {{"):]
        block = block[: block.index("}}")]
        assert "text-overflow: ellipsis" in block
        assert "white-space: nowrap" in block
