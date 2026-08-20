"""
Der Speicher im Cashflow.

Geprueft wird nicht der Dispatch (das tut test_storage_dispatch.py),
sondern die NAHTSTELLE: Was passiert mit Pacht, AfA, Steuer und
Eigenkapital, wenn ein Speicher dazukommt - und was passiert, wenn
keiner da ist.

Die wichtigste Zusicherung steht ganz oben: Ohne Speicher rechnet die
Bewertung Zeile fuer Zeile wie vorher. Ein Umbau der Pipeline, der
bestehende Projekte veraendert, waere ein stiller Fehler in jeder
gespeicherten Auswertung.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import BatteryConfig, SpeicherModus  # noqa: E402
from engine.energy import calculate_energy_production  # noqa: E402
from engine.pipeline import (  # noqa: E402
    resolve_assumptions,
    run_valuation_from_assumptions,
)
from engine.revenue import calculate_revenue  # noqa: E402
from engine.storage import SpeicherBeitrag, dispatch_mehrjahr  # noqa: E402
from engine.timeline import build_timeline  # noqa: E402


def _beitrag(jahre: int, wert_je_jahr: float, capex: float = 0.0,
             opex: float = 0.0) -> SpeicherBeitrag:
    """Ein kuenstlicher Beitrag - die Naht laesst sich ohne Solver pruefen."""
    return SpeicherBeitrag(
        wertbeitrag_eur_je_jahr=tuple([wert_je_jahr] * jahre),
        capex_eur=capex,
        opex_eur_je_jahr=tuple([opex] * jahre),
        jahreswerte=(),
        hinweise=(),
    )


@pytest.fixture
def aufgeloest(project, global_assumptions):
    return resolve_assumptions(project, global_assumptions)


class TestOhneSpeicher:
    def test_ergebnis_ist_unveraendert(self, aufgeloest):
        """Der Regressionsschutz des ganzen Umbaus."""
        ohne = run_valuation_from_assumptions(aufgeloest, "p")
        neutral = run_valuation_from_assumptions(aufgeloest, "p", speicher=None)
        assert neutral.kpis.equity_irr == ohne.kpis.equity_irr
        assert neutral.kpis.npv_eur == ohne.kpis.npv_eur
        assert neutral.kpis.capex_total_eur == ohne.kpis.capex_total_eur

    def test_spalte_existiert_und_ist_null(self, aufgeloest):
        """Die Spalte steht immer - so muss die Oberflaeche nicht
        unterscheiden, ob ein Speicher da ist."""
        ergebnis = run_valuation_from_assumptions(aufgeloest, "p")
        spalte = ergebnis.cashflow.data["erloes_speicher_eur"]
        assert spalte.abs().sum() == 0.0


class TestMitSpeicher:
    def test_erloes_landet_im_cashflow(self, aufgeloest):
        beitrag = _beitrag(aufgeloest.betriebsdauer_jahre, 100_000.0)
        ohne = run_valuation_from_assumptions(aufgeloest, "p")
        mit = run_valuation_from_assumptions(aufgeloest, "p", speicher=beitrag)
        d_o, d_m = ohne.cashflow.data, mit.cashflow.data
        betrieb = d_m["jahr"] >= 1
        assert d_m.loc[betrieb, "erloes_speicher_eur"].iloc[0] == pytest.approx(100_000.0)
        # Der Beitrag steckt zugleich im Gesamterloes.
        assert d_m.loc[betrieb, "erloes_eur"].iloc[0] == pytest.approx(
            d_o.loc[betrieb, "erloes_eur"].iloc[0] + 100_000.0
        )

    def test_umsatzpacht_bleibt_unberuehrt(self, project, global_assumptions):
        """Die fachlich wichtigste Zusicherung der Naht.

        Ob eine Umsatzbeteiligung auch die Arbitrageerloese eines
        mitgebauten Speichers erfasst, steht im Pachtvertrag. Der
        Prozentsatz wurde fuer die PV-Anlage verhandelt; ihn
        stillschweigend auszudehnen, aenderte einen Vertrag per
        Rechenannahme.
        """
        from engine import PachtModus

        project.pacht_modus = PachtModus.UMSATZBETEILIGUNG
        project.pacht_umsatzbeteiligung_pct = 0.05
        project.projektflaeche_ha = 10.0
        a = resolve_assumptions(project, global_assumptions)

        ohne = run_valuation_from_assumptions(a, "p")
        mit = run_valuation_from_assumptions(
            a, "p", speicher=_beitrag(a.betriebsdauer_jahre, 500_000.0)
        )
        pacht_o = ohne.cashflow.data["Pacht"].to_numpy()
        pacht_m = mit.cashflow.data["Pacht"].to_numpy()
        assert np.allclose(pacht_o, pacht_m), (
            "Der Speichererloes hat die Umsatzpacht erhoeht"
        )

    def test_capex_erhoeht_afa_und_eigenkapital(self, aufgeloest):
        beitrag = _beitrag(aufgeloest.betriebsdauer_jahre, 0.0, capex=2_000_000.0)
        ohne = run_valuation_from_assumptions(aufgeloest, "p")
        mit = run_valuation_from_assumptions(aufgeloest, "p", speicher=beitrag)
        assert mit.kpis.capex_total_eur == pytest.approx(
            ohne.kpis.capex_total_eur + 2_000_000.0
        )
        assert mit.kpis.eigenkapital_eur > ohne.kpis.eigenkapital_eur
        # Mehr Anlagevermoegen heisst mehr Abschreibung.
        assert (
            mit.cashflow.data["afa_eur"].sum()
            > ohne.cashflow.data["afa_eur"].sum()
        )

    def test_opex_erscheint_als_eigener_posten(self, aufgeloest):
        beitrag = _beitrag(aufgeloest.betriebsdauer_jahre, 0.0, opex=50_000.0)
        mit = run_valuation_from_assumptions(aufgeloest, "p", speicher=beitrag)
        daten = mit.cashflow.data
        assert "Speicher" in daten.columns
        betrieb = daten["jahr"] >= 1
        assert daten.loc[betrieb, "Speicher"].iloc[0] == pytest.approx(50_000.0)

    def test_reiner_kostenspeicher_senkt_die_rendite(self, aufgeloest):
        """CAPEX ohne Ertrag muss die Rendite druecken - sonst stimmt an
        der Naht etwas nicht."""
        beitrag = _beitrag(aufgeloest.betriebsdauer_jahre, 0.0, capex=2_000_000.0)
        ohne = run_valuation_from_assumptions(aufgeloest, "p")
        mit = run_valuation_from_assumptions(aufgeloest, "p", speicher=beitrag)
        assert mit.kpis.equity_irr < ohne.kpis.equity_irr

    def test_kuerzere_reihe_wird_mit_null_aufgefuellt(self, aufgeloest):
        """Fehlen fuer spaete Jahre die Stundenpreise, bleibt der Beitrag
        dort null - er darf nicht das letzte Jahr wiederholen."""
        beitrag = _beitrag(3, 100_000.0)
        mit = run_valuation_from_assumptions(aufgeloest, "p", speicher=beitrag)
        werte = mit.cashflow.data["erloes_speicher_eur"].to_numpy()
        assert werte[-1] == 0.0
        assert werte.sum() == pytest.approx(300_000.0)


class TestMehrjahreslauf:
    """Der Weg vom Dispatch zum Beitrag - mit Solver, aber winzig."""

    def _preise(self, jahre: range, muster: list[float]) -> dict[int, tuple]:
        return {j: tuple(muster * (8760 // len(muster))) for j in jahre}

    def test_beitrag_je_jahr_und_degradation(self, project, global_assumptions):
        project.nennleistung_kwp = 10_000.0
        # Die Betriebsdauer ist eine globale Annahme, kein Projektfeld.
        global_assumptions.betriebsdauer_jahre = 3
        a = resolve_assumptions(project, global_assumptions)
        tl = build_timeline(
            date(a.inbetriebnahme_jahr, a.inbetriebnahme_monat, 1), 3
        )
        energy = calculate_energy_production(tl, a)
        revenue = calculate_revenue(tl, energy, a)
        # Tag/Nacht-Muster: nachts billig, abends teuer.
        muster = [20.0] * 6 + [30.0] * 6 + [20.0] * 6 + [120.0] * 6
        preise = self._preise(
            range(a.inbetriebnahme_jahr, a.inbetriebnahme_jahr + 4), muster
        )
        form = ([0.0] * 6 + [1.0] * 8 + [0.0] * 10) * (8760 // 24)

        batterie = BatteryConfig(
            modus=SpeicherModus.GRUENSTROM, leistung_mw=2.0,
            kapazitaet_mwh=4.0, degradationskosten_eur_mwh=0.0,
        )
        beitrag = dispatch_mehrjahr(
            a, batterie, energy=energy, revenue=revenue,
            preise_je_jahr=preise, form=form,
        )
        assert len(beitrag.wertbeitrag_eur_je_jahr) == len(energy)
        assert all(w >= 0 for w in beitrag.wertbeitrag_eur_je_jahr)
        assert beitrag.wertbeitrag_gesamt_eur > 0
        assert beitrag.vollzyklen_mittel > 0

    def test_ohne_preisreihe_bleibt_das_jahr_leer(self, project, global_assumptions):
        a = resolve_assumptions(project, global_assumptions)
        tl = build_timeline(
            date(a.inbetriebnahme_jahr, a.inbetriebnahme_monat, 1), 2
        )
        energy = calculate_energy_production(tl, a).head(2)
        revenue = calculate_revenue(tl, energy, a).head(2)
        batterie = BatteryConfig(leistung_mw=1.0, kapazitaet_mwh=2.0)
        beitrag = dispatch_mehrjahr(
            a, batterie, energy=energy, revenue=revenue,
            preise_je_jahr={}, form=[1.0] * 8760,
        )
        assert beitrag.wertbeitrag_gesamt_eur == 0.0
        assert beitrag.hinweise, "Das fehlende Jahr muss gemeldet werden"


class TestVariantenvergleich:
    """Der Speicher gehoert in die Unterschiedstabelle.

    Zwei Varianten desselben Standorts koennen sich allein im Speicher
    unterscheiden - dann ist er der EINZIGE Unterschied, und die
    Tabelle muss ihn zeigen. Ein neu ergaenztes Projektfeld faellt sonst
    still aus dem Vergleich (siehe varianten.geprueft_alle_felder).
    """

    def test_speicher_erscheint_als_unterschied(self, project):
        from app.components.varianten import unterschiede

        ohne = project.model_copy(deep=True)
        ohne.id, ohne.variante = "a", "ohne"
        mit = project.model_copy(deep=True)
        mit.id, mit.variante = "b", "mit"
        mit.battery = BatteryConfig(
            modus=SpeicherModus.GRAUSTROM, leistung_mw=5.0, kapazitaet_mwh=10.0
        )

        gefunden = unterschiede([ohne, mit], ohne)
        speicher = [u for u in gefunden if u.feld == "battery"]
        assert speicher, "Der Speicher fehlt in der Unterschiedstabelle"
        assert speicher[0].werte[0] == "—"
        assert "5,0 MW" in speicher[0].werte[1]
        assert "Graustrom" in speicher[0].werte[1]

    def test_gleicher_speicher_ist_kein_unterschied(self, project):
        from app.components.varianten import unterschiede

        a = project.model_copy(deep=True)
        a.id, a.variante = "a", "eins"
        b = project.model_copy(deep=True)
        b.id, b.variante = "b", "zwei"
        for p in (a, b):
            p.battery = BatteryConfig(leistung_mw=5.0, kapazitaet_mwh=10.0)
        assert not [u for u in unterschiede([a, b], a) if u.feld == "battery"]

    def test_abgeschalteter_speicher_zaehlt_wie_keiner(self, project):
        """`aktiv=False` ist kein Speicher - die Tabelle darf keine
        Auslegung zeigen, die nicht rechnet."""
        from app.components.varianten import _speicher

        aus = BatteryConfig(aktiv=False, leistung_mw=5.0, kapazitaet_mwh=10.0)
        assert _speicher(aus) == "—"
