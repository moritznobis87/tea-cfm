"""
Haelt das durchgerechnete Beispiel in Kapitel 13 der Rechenweg-
Dokumentation mit der Engine synchron.

Der Test liest die Zahlen direkt aus `docs/rechenmodell/rechenmodell.md`
(es gibt also keine zweite Quelle, die auseinanderlaufen koennte) und
vergleicht sie mit einer frisch gerechneten Bewertung des mitgelieferten
Beispielprojekts.

Schlaegt er fehl, ist entweder eine Rechenvorschrift geaendert oder das
Beispielprojekt bearbeitet worden. In beiden Faellen ist das Kapitel neu
zu erzeugen:

    python docs/rechenmodell/beispiel.py

Bewusst der einzige Test, der an den aenderbaren Beispieldaten unter
`data/` haengt - genau das ist seine Aufgabe.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

WURZEL = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(WURZEL))

from app.config import GLOBAL_ASSUMPTIONS_PATH, PROJECTS_DIR  # noqa: E402
from engine import run_valuation  # noqa: E402
from engine.io_yaml import (  # noqa: E402
    load_global_assumptions_yaml,
    load_project_yaml,
)

DOKUMENT = WURZEL / "docs" / "rechenmodell" / "rechenmodell.md"
PROJEKT = PROJECTS_DIR / "template-agri.yaml"
ANNAHMEN = GLOBAL_ASSUMPTIONS_PATH

HINWEIS = (
    "Kapitel 13 der Rechenweg-Dokumentation passt nicht mehr zum "
    "Rechenergebnis. Neu erzeugen mit: python docs/rechenmodell/beispiel.py"
)


def _zahl(text: str) -> float:
    """Deutsche Schreibweise ('5.320.000', '4,300', '13,80 %', 'Jahr 8')
    in eine Zahl."""
    treffer = re.search(r"-?[\d.]+(?:,\d+)?", text)
    assert treffer is not None, f"keine Zahl in {text!r}"
    return float(treffer.group().replace(".", "").replace(",", "."))


def _tabelle_nach(ueberschrift: str) -> list[list[str]]:
    """Zeilen der ersten Markdown-Tabelle unterhalb einer Ueberschrift."""
    text = DOKUMENT.read_text(encoding="utf-8")
    start = text.index(ueberschrift)
    zeilen = text[start:].split("\n")
    tabelle: list[list[str]] = []
    for zeile in zeilen:
        if zeile.startswith("|"):
            tabelle.append([z.strip() for z in zeile.strip().strip("|").split("|")])
        elif tabelle:
            break
    assert tabelle, f"keine Tabelle unter {ueberschrift!r}"
    return tabelle[2:]                       # Kopf und Trennzeile ueberspringen


@pytest.fixture(scope="module")
def ergebnis():
    return run_valuation(
        load_project_yaml(PROJEKT), load_global_assumptions_yaml(ANNAHMEN)
    )


#: Spalte der Dokumentationstabelle -> (Spalte der Cashflow-Zeitreihe,
#: erlaubte Abweichung). Die Toleranz entspricht der Rundung im Dokument.
ZEITREIHE_SPALTEN = [
    (1, "produktion_kwh", 1.0),
    (2, "marktwert_nominal_ct_kwh", 0.001),
    (3, "verguetungssatz_ct_kwh", 0.001),
    (4, "erloes_eur", 1.0),
    (5, "opex_gesamt_eur", 1.0),
    (6, "zinsen_eur", 1.0),
    (7, "tilgung_eur", 1.0),
    (8, "steuer_eur", 1.0),
    (9, "cf_gesamt_eur", 1.0),
]


def test_zeitreihe_stimmt_mit_der_engine_ueberein(ergebnis):
    df = ergebnis.cashflow.data
    zeilen = _tabelle_nach("## 13.3 Ergebniszeitreihe")
    assert len(zeilen) >= 5

    for zeile in zeilen:
        jahr = int(_zahl(zeile[0]))
        gerechnet = df[df["jahr"] == jahr]
        assert not gerechnet.empty, f"{HINWEIS} (Jahr {jahr} fehlt)"
        for spalte, name, toleranz in ZEITREIHE_SPALTEN:
            dokumentiert = _zahl(zeile[spalte])
            assert dokumentiert == pytest.approx(
                float(gerechnet.iloc[0][name]), abs=toleranz
            ), f"{HINWEIS} (Jahr {jahr}, {name})"


def test_kennzahlen_stimmen_mit_der_engine_ueberein(ergebnis):
    kpis = ergebnis.kpis
    werte = {
        zeile[0].split("$")[0].strip(): _zahl(zeile[1])
        for zeile in _tabelle_nach("## 13.4 Kennzahlen")
    }

    erwartet = {
        "Investitionsvolumen": (kpis.capex_total_eur, 1.0),
        "Eigenkapitaleinsatz": (kpis.eigenkapital_eur, 1.0),
        "EK-Rendite (XIRR)": ((kpis.equity_irr or 0) * 100, 0.01),
        "NPV bei 8 %": (kpis.npv_eur, 1.0),
        "Minimaler DSCR": (kpis.dscr_min, 0.01),
        "Payback (kumulierter Equity-CF": (kpis.payback_jahre, 0.0),
    }
    for name, (gerechnet, toleranz) in erwartet.items():
        assert name in werte, f"{HINWEIS} (Zeile {name!r} fehlt)"
        assert werte[name] == pytest.approx(gerechnet, abs=toleranz), (
            f"{HINWEIS} ({name})"
        )


def test_eingangsgroessen_beschreiben_das_beispielprojekt():
    projekt = load_project_yaml(PROJEKT)
    werte = {
        zeile[0].split("$")[0].strip(): zeile[1]
        for zeile in _tabelle_nach("## 13.1 Eingangsgrößen")
    }
    assert _zahl(werte["Nennleistung"]) == pytest.approx(projekt.nennleistung_kwp)
    assert _zahl(werte["Spezifischer Ertrag"]) == pytest.approx(
        projekt.vollbenutzungsstunden_kwh_kwp
    )
    assert _zahl(werte["Investitionsvolumen"]) == pytest.approx(
        projekt.capex.summe_eur, abs=1.0
    )
