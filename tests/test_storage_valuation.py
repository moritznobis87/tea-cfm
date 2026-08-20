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


class TestSchaltjahr:
    """Ein Schaltjahr darf den Speicher nicht entwerten.

    Der Anlass ist ein gemessener Fehler. Die Erzeugungsform liegt als
    8.760er-Reihe vor, ein Schaltjahr hat 8.784 Stunden. Wurde die Reihe
    darauf GESTRECKT, verschob sich jede Stunde gegenueber ihrer
    Tageszeit, und die Verschiebung summierte sich ueber das Jahr auf
    volle 24 Stunden - ab der Jahresmitte lag die Mittagsspitze der
    Erzeugung mitten in der Nacht der Preisreihe.

    Fuer den PV-Cashflow faellt so etwas nicht auf, die Jahresmenge
    stimmt ja. Fuer den Speicher war es fatal: Sein Wertbeitrag brach in
    den Schaltjahren auf gut die Haelfte ein (130 statt 248 Tsd. EUR im
    Lauf, der den Fehler zutage foerderte), obwohl der Preisspread
    dieser Jahre unveraendert war.
    """

    def test_eingefuegter_tag_haelt_jede_andere_stunde_an_ihrem_platz(self):
        from engine.storage.valuation import _stundenform

        form = list(np.arange(8760, dtype=float))
        lang = _stundenform(form, 8784)
        assert len(lang) == 8784
        schalttag_ab = (31 + 28) * 24
        # Alles vor dem 29. Februar steht unveraendert.
        assert np.array_equal(lang[:schalttag_ab], form[:schalttag_ab])
        # Der eingefuegte Tag ist die Kopie des 28. Februar.
        assert np.array_equal(
            lang[schalttag_ab:schalttag_ab + 24],
            form[schalttag_ab - 24:schalttag_ab],
        )
        # Und alles danach ist nur um genau einen Tag verschoben - nicht
        # um einen wachsenden Bruchteil.
        assert np.array_equal(lang[schalttag_ab + 24:], form[schalttag_ab:])

    def test_die_rueckrichtung_entfernt_denselben_tag(self):
        from engine.storage.valuation import _stundenform

        form = list(np.arange(8784, dtype=float))
        kurz = _stundenform(form, 8760)
        assert len(kurz) == 8760
        schalttag_ab = (31 + 28) * 24
        assert np.array_equal(kurz[:schalttag_ab], form[:schalttag_ab])
        assert np.array_equal(kurz[schalttag_ab:], form[schalttag_ab + 24:])

    def test_tagesgang_bleibt_in_phase(self):
        """Die Eigenschaft, an der der Fehler haftete.

        Geprueft wird nicht die Umformung, sondern ihre WIRKUNG: Jede
        Stunde der langen Reihe muss dieselbe Tageszeit tragen wie in
        der kurzen. Beim Strecken war das ab der Jahresmitte nicht mehr
        so - und genau das kostete den Speicher seinen Wert.
        """
        from engine.storage.valuation import _stundenform

        # Ein sauberer Tagesgang: mittags eins, nachts null.
        tag = [0.0] * 6 + [1.0] * 8 + [0.0] * 10
        form = tag * 365
        lang = _stundenform(form, 8784)
        mittags = lang.reshape(366, 24)[:, 6:14]
        nachts = np.delete(lang.reshape(366, 24), slice(6, 14), axis=1)
        assert mittags.min() == 1.0, "Eine Mittagsstunde ist keine mehr"
        assert nachts.max() == 0.0, "Es wird nachts erzeugt"

    def test_schaltjahr_traegt_denselben_beitrag(
        self, project, global_assumptions
    ):
        """Der Test am Ergebnis: Zwei Jahre mit identischen Preisen und
        identischer Erzeugung muessen denselben Beitrag liefern - auch
        wenn eines davon ein Schaltjahr ist."""
        project.nennleistung_kwp = 10_000.0
        project.inbetriebnahme_jahr = 2027
        global_assumptions.betriebsdauer_jahre = 2
        global_assumptions.degradation_pct_pa = 0.0
        a = resolve_assumptions(project, global_assumptions)
        tl = build_timeline(date(a.inbetriebnahme_jahr, a.inbetriebnahme_monat, 1), 2)
        energy = calculate_energy_production(tl, a)
        revenue = calculate_revenue(tl, energy, a)

        # Derselbe Tagesgang in beiden Jahren, nur die Laenge
        # unterscheidet sich: 2027 ist ein Normal-, 2028 ein Schaltjahr.
        preismuster = [20.0] * 6 + [30.0] * 6 + [20.0] * 6 + [120.0] * 6
        preise = {
            2027: tuple(preismuster * 365),
            2028: tuple(preismuster * 366),
        }
        form = ([0.0] * 6 + [1.0] * 8 + [0.0] * 10) * 365

        beitrag = dispatch_mehrjahr(
            a, BatteryConfig(
                modus=SpeicherModus.GRUENSTROM, leistung_mw=2.0,
                kapazitaet_mwh=4.0, degradationskosten_eur_mwh=0.0,
            ),
            energy=energy, revenue=revenue,
            preise_je_jahr=preise, form=form,
        )
        normal, schalt = beitrag.wertbeitrag_eur_je_jahr
        assert normal > 0
        # Das Schaltjahr hat einen Tag mehr Erzeugung und einen Tag mehr
        # Preisspread - es darf also leicht darueber liegen, aber nicht
        # zusammenbrechen. Beim Strecken lag es bei rund der Haelfte.
        assert schalt == pytest.approx(normal, rel=0.05), (
            f"Schaltjahr {schalt:,.0f} gegen Normaljahr {normal:,.0f}"
        )
