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


class TestVierAnsichten:
    def test_segmentwahl_bietet_genau_vier_sichten(self, at: AppTest):
        keys = [b.key for b in at.button if b.key and b.key.startswith("open_")]
        at = _klick(at, keys[0])
        wahl = at.get("button_group")[0]
        assert wahl.options == ["Ergebnis", "Finanzierung", "Risiko", "Annahmen"]
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
