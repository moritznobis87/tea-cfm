"""
Gemeinsame Fixtures fuer die Engine-Tests.

Die Fixtures bilden ein kleines, vollstaendig deterministisches
Beispielprojekt ab, dessen Erwartungswerte sich von Hand nachrechnen
lassen - keine Abhaengigkeit von den (aenderbaren) YAML-Beispieldaten.

Ausserdem wird hier das Datenverzeichnis umgelenkt - siehe unten.

Der Schalter --langsam
----------------------
Ein Teil der Tests loest echte lineare Programme oder faehrt die
Oberflaeche durch einen vollstaendigen Rasterlauf. Sie sind nicht
langsam, weil sie schlecht geschrieben waeren, sondern weil sie genau
das pruefen, was Minuten kostet - und ohne sie waere die
Auslegungssuche ungeprueft.

Sie laufen deshalb NICHT bei jedem Aufruf mit, sondern nur mit
`pytest --langsam`. Uebersprungen werden sie als SKIP und nicht durch
Deselektion: Ein Test, der stillschweigend verschwindet, ist schlimmer
als einer, der lange braucht - man sieht ihm nicht an, dass er fehlt.
Am Ende jedes Laufs ohne den Schalter steht deshalb, wie viele Tests
gerade nicht geprueft wurden.

Vor jedem Merge gehoert ein Lauf MIT `--langsam` dazu.
"""

from __future__ import annotations

import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

_WURZEL = Path(__file__).resolve().parent.parent

# Repository-Wurzel in den Importpfad aufnehmen, damit `import engine`
# auch ohne editierbare Installation funktioniert (z.B. `pytest` direkt
# im frisch geklonten Repo).
sys.path.insert(0, str(_WURZEL))


def _daten_umlenken() -> Path:
    """Die Tests auf eine Kopie von data/ zeigen lassen.

    Ein Teil der Suite fuehrt die echten Schreibwege vor: den
    Aurora-Import, den Speichern-Knopf der globalen Annahmen, das Anlegen
    von Varianten. Diese Tests SOLLEN schreiben - nur eben nicht in die
    ausgelieferten Daten.

    Bisher sicherten Fixtures die Datei vorher und schrieben sie im
    finally zurueck. Das haelt, solange der Lauf ordentlich endet. Wird er
    hart abgebrochen - Zeitueberschreitung, Strg-C, ein zweiter Prozess
    daneben -, laeuft kein finally, und der Testzustand bleibt im
    Arbeitsverzeichnis stehen. Beim naechsten Commit wandert er mit.
    Genau so haben synthetische Preise (8,0/9,0/10,0 ct/kWh) einmal die
    echte Aurora-Baseloadreihe des meistgenutzten Szenarios ersetzt.

    Die Kopie kann das nicht: Es gibt keinen Zustand, aus dem heraus ein
    Test die echte Datei anfassen koennte. Sie entsteht VOR dem Import
    der Testmodule - `app.config` liest die Variable beim Import, und
    `app.services` bindet die Pfade dann als Modulkonstanten.

    Eine von aussen gesetzte Variable gewinnt: Wer bewusst gegen ein
    anderes Verzeichnis testen will, soll das koennen.

    Der Name der Variablen steht hier woertlich und nicht als Import aus
    app.config: Ein Import von app.config wuerde dessen Modulcode
    ausfuehren, und der liest die Variable - bevor sie gesetzt waere.
    Gegen ein Auseinanderdriften der beiden Stellen sichert die
    Gegenprobe unten, die beim Einsammeln der Tests laut scheitert.
    """
    name = "VALYZE_DATA_DIR"
    if os.environ.get(name):
        return Path(os.environ[name])

    ziel = Path(tempfile.mkdtemp(prefix="valyze-daten-"))
    shutil.copytree(_WURZEL / "data", ziel, dirs_exist_ok=True)
    os.environ[name] = str(ziel)
    atexit.register(shutil.rmtree, ziel, True)
    return ziel


#: Das Datenverzeichnis DIESES Laufs. Testmodule, die Pfade brauchen,
#: nehmen sie von hier oder aus app.config - niemals selbst gebaut.
DATEN_DIR = _daten_umlenken()

from app.config import (  # noqa: E402
    DATA_DIR as _KONFIGURIERTES_DATENVERZEICHNIS,
)
from app.config import (
    DATA_DIR_ENV as _DATA_DIR_ENV,
)

# Gegenprobe: Die Umlenkung muss angekommen sein. Schlaegt sie fehl,
# zeigen die Tests auf die ausgelieferten Daten und wuerden sie
# beschreiben - dann soll die Suite gar nicht erst anlaufen.
assert _DATA_DIR_ENV == "VALYZE_DATA_DIR", (
    "app.config.DATA_DIR_ENV heisst anders als in conftest gesetzt"
)
assert _KONFIGURIERTES_DATENVERZEICHNIS == DATEN_DIR, (
    f"app.config zeigt auf {_KONFIGURIERTES_DATENVERZEICHNIS}, "
    f"erwartet war {DATEN_DIR} - wurde app.config zu frueh importiert?"
)

from engine import (  # noqa: E402
    AnlagenTyp,
    CapexBreakdown,
    GlobalAssumptions,
    MarktpreisSzenario,
    NegativeStundenModus,
    OpexItem,
    PVProject,
    TaxModus,
    TilgungsArt,
)


def _baue_szenario_flach() -> MarktpreisSzenario:
    """Konstante 4 ct/kWh, keine negativen Stunden - macht Erloese trivial
    nachrechenbar."""
    jahre = range(2025, 2061)
    return MarktpreisSzenario(
        name="Testszenario",
        marktwert_solar_ct_kwh_je_kalenderjahr={j: 4.0 for j in jahre},
        anteil_negativer_stunden_pct_je_kalenderjahr={j: 0.0 for j in jahre},
    )


def _baue_global_assumptions() -> GlobalAssumptions:
    return GlobalAssumptions(
        gueltig_ab="test",
        # Bewusst 0: die Fixtures sollen trivial nachrechenbar bleiben;
        # die Kosteninflation wird in eigenen Tests geprueft.
        kosten_inflation_pct_pa=0.0,
        marktpreisszenarien=[_baue_szenario_flach()],
        marktpreis_inflation_pct_pa=0.0,  # Inflation aus -> nominal == real
        marktpreis_inflation_basisjahr=2025,
        opex_standard=[
            OpexItem(name="Betriebsführung", basiswert_eur_kwp=3.0),
        ],
        gemeindeabgabe_eur_kwh=0.002,
        direktvermarktungskosten_eur_kwh=0.001,
        negative_stunden_gewichtung_pct=1.0,
        # Explizit Abregelung: Die Einheitstests rechnen mit dem
        # vollstaendigen Verguetungsausfall (haerteste Annahme);
        # der App-Default ist seit 2.2 MARKTWERT.
        negative_stunden_modus=NegativeStundenModus.ABREGELUNG,
        degradation_pct_pa=0.0,
        sicherheitsabschlag_pct=0.0,
        eag_foerderdauer_jahre=20,
        betriebsdauer_jahre=25,
        kreditlaufzeit_jahre=20,
        tilgungsart=TilgungsArt.ANNUITAET,
        tax_modus=TaxModus.AFA_KOERPERSCHAFTSTEUER,
        steuersatz_pct=0.23,
        afa_nutzungsdauer_jahre=20,
        freibetrag_eur=0.0,
        verlustvortrag_verrechnungsgrenze_pct=0.75,
    )


def _baue_projekt() -> PVProject:
    return PVProject(
        id="testprojekt",
        name="Testprojekt",
        inbetriebnahme_jahr=2027,
        inbetriebnahme_monat=1,
        anlagentyp=AnlagenTyp.AGRI_PV,
        nennleistung_kwp=1000.0,
        vollbenutzungsstunden_kwh_kwp=1000.0,
        pacht_eur_kwp_jahr=5.0,
        fremdkapitalzins_pct=0.04,
        eigenkapitalquote_pct=0.2,
        eag_zuschlagswert_ct_kwh=7.0,
        gemeindeabgabe_eur_mwh=2.0,
        direktvermarktungskosten_eur_mwh=1.0,
        marktpreisszenario="Testszenario",
        capex=CapexBreakdown(epc_eur=500_000.0, netzanschluss_eur=50_000.0),
    )


@pytest.fixture
def szenario_flach() -> MarktpreisSzenario:
    return _baue_szenario_flach()


@pytest.fixture
def global_assumptions() -> GlobalAssumptions:
    return _baue_global_assumptions()


@pytest.fixture
def project() -> PVProject:
    return _baue_projekt()


# ---------------------------------------------------------------------------
# Der Schalter fuer die langsamen Tests
# ---------------------------------------------------------------------------


#: Name des Markers und des Schalters - an einer Stelle, damit beide
#: nicht auseinanderlaufen koennen.
LANGSAM = "langsam"


def pytest_addoption(parser) -> None:
    parser.addoption(
        f"--{LANGSAM}", action="store_true", default=False,
        help=(
            "Auch die Tests mitlaufen lassen, die echte lineare Programme "
            "loesen oder die Oberflaeche durch einen Rasterlauf fahren. "
            "Ohne diesen Schalter werden sie uebersprungen."
        ),
    )


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        f"{LANGSAM}: loest echte lineare Programme oder faehrt die "
        f"Oberflaeche durch einen Rasterlauf. Nur mit --{LANGSAM}.",
    )


def pytest_collection_modifyitems(config, items) -> None:
    if config.getoption(f"--{LANGSAM}"):
        return
    ueberspringen = pytest.mark.skip(
        reason=f"langsam - mit --{LANGSAM} mitlaufen lassen"
    )
    for eintrag in items:
        if LANGSAM in eintrag.keywords:
            eintrag.add_marker(ueberspringen)


def pytest_terminal_summary(terminalreporter, exitstatus, config) -> None:
    """Sagt am Ende, wie viele Tests gerade NICHT geprueft wurden.

    Ohne diese Zeile wuerde ein gruener Lauf so aussehen wie ein
    vollstaendiger, und genau das darf er nicht: Er hat die teuersten
    Zusagen der Anwendung nicht angefasst.
    """
    if config.getoption(f"--{LANGSAM}"):
        return
    offen = sum(
        1 for eintrag in terminalreporter.stats.get("skipped", [])
        if f"--{LANGSAM}" in str(getattr(eintrag, "longrepr", ""))
    )
    if offen:
        terminalreporter.write_line(
            f"{offen} langsame Tests uebersprungen - vor dem Merge einmal "
            f"mit --{LANGSAM} laufen lassen.",
            yellow=True,
        )
