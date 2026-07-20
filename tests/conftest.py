"""
Gemeinsame Fixtures fuer die Engine-Tests.

Die Fixtures bilden ein kleines, vollstaendig deterministisches
Beispielprojekt ab, dessen Erwartungswerte sich von Hand nachrechnen
lassen - keine Abhaengigkeit von den (aenderbaren) YAML-Beispieldaten.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Repository-Wurzel in den Importpfad aufnehmen, damit `import engine`
# auch ohne editierbare Installation funktioniert (z.B. `pytest` direkt
# im frisch geklonten Repo).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
