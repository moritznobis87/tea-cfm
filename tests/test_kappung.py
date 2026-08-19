"""
Einspeisebegrenzung: die 70-%-Regel und ihre Wirkung auf die Rechnung.

Geprueft wird in drei Schichten:

1. Die Rechenregel selbst (engine/clipping.py) - dass sich die
   Nennleistung heraushebt, dass Monats- und Jahressicht zueinander
   passen, und dass eine bereits gekappte Reihe erkannt wird.
2. Die Wirkung auf die Mengenrechnung (engine/energy.py) - vor allem,
   dass die Kappung MIT DER DEGRADATION SCHRUMPFT. Wer den Verlust des
   ersten Jahres fortschreibt, verdreifacht ihn.
3. Der Durchgriff bis zu den Kennzahlen.

Die Testreihe ist synthetisch und hat eine scharfe Mittagsspitze -
damit ist von Hand nachvollziehbar, welche Stunden gekappt werden.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from engine.clipping import (
    kappungsverlust,
    limit_ohne_verlust,
    plateauverdacht,
)
from engine.models import (
    AnlagenTyp,
    CapexBreakdown,
    GlobalAssumptions,
    Projektannahmen,
    PVProject,
)

_ROOT = Path(__file__).resolve().parent.parent
STUNDEN = 8760


def _sonnenreihe(stunden: int = STUNDEN) -> list[float]:
    """Tagesgang mal Jahresgang, nachts null - eine PV-aehnliche Reihe."""
    werte = []
    for i in range(stunden):
        tages = max(0.0, math.sin(math.pi * ((i % 24) - 6) / 12))
        jahres = 0.55 + 0.45 * math.cos(2 * math.pi * ((i // 24) - 172) / 365)
        werte.append(tages * jahres)
    return werte


def _projekt(**kw) -> PVProject:
    felder = dict(
        id="p", name="P", anlagentyp=AnlagenTyp.KONVENTIONELL,
        capex=CapexBreakdown(epc_eur=5_000_000.0),
        nennleistung_kwp=10_000.0, vollbenutzungsstunden_kwh_kwp=1200.0,
        pacht_eur_kwp_jahr=4.0, fremdkapitalzins_pct=0.042,
        eigenkapitalquote_pct=0.2, eag_zuschlagswert_ct_kwh=6.5,
    )
    felder.update(kw)
    return PVProject(**felder)


class TestRechenregel:
    def test_die_nennleistung_kuerzt_sich_heraus(self):
        """Der Kern der Herleitung: Zwei Anlagen mit gleicher Profilform
        und gleichen Vollbenutzungsstunden verlieren denselben
        Prozentsatz - unabhaengig von ihrer Groesse. Nur deshalb laesst
        sich ein Befund von einem Projekt auf ein anderes uebertragen."""
        reihe = _sonnenreihe()
        anteil = kappungsverlust(reihe, 0.70, 1200.0).verlust_pct

        for kwp in (500.0, 10_000.0, 250_000.0):
            jahresmenge = kwp * 1200.0
            faktor = jahresmenge / sum(reihe)
            direkt = sum(
                max(0.0, w * faktor - 0.70 * kwp) for w in reihe
            ) / jahresmenge
            assert direkt == pytest.approx(anteil, abs=1e-12)

    def test_hohes_limit_kostet_nichts(self):
        k = kappungsverlust(_sonnenreihe(), 1.0, 1200.0)
        assert k.verlust_pct == 0.0
        assert k.betroffene_stunden == 0
        assert k.greift is False

    def test_niedrigeres_limit_kostet_mehr(self):
        reihe = _sonnenreihe()
        verluste = [
            kappungsverlust(reihe, lim, 1200.0).verlust_pct
            for lim in (0.80, 0.70, 0.60, 0.50)
        ]
        assert verluste == sorted(verluste)
        assert verluste[0] < verluste[-1]

    def test_mehr_vollbenutzungsstunden_bedeuten_mehr_kappung(self):
        """Dieselbe Profilform, ertragreicherer Standort: Die Spitze
        steigt gegen ein festes Limit, also wird mehr abgeschnitten."""
        reihe = _sonnenreihe()
        wenig = kappungsverlust(reihe, 0.70, 900.0).verlust_pct
        viel = kappungsverlust(reihe, 0.70, 1400.0).verlust_pct
        assert viel > wenig

    def test_spitze_und_verlustfreies_limit_sind_dasselbe(self):
        """Ab der hoechsten Stundenleistung kostet die Grenze nichts -
        das ist die Zahl fuer eine Netzausbau-Diskussion."""
        reihe = _sonnenreihe()
        k = kappungsverlust(reihe, 0.70, 1200.0)
        grenze = limit_ohne_verlust(reihe, 1200.0)
        assert grenze == pytest.approx(k.spitze_pct_kwp)
        assert kappungsverlust(reihe, grenze, 1200.0).verlust_pct == pytest.approx(0.0)

    def test_kurve_nach_kappung_ist_normiert(self):
        k = kappungsverlust(_sonnenreihe(), 0.60, 1200.0)
        assert sum(k.kurve_nach_kappung_pct_je_monat) == pytest.approx(1.0)

    def test_kappung_trifft_den_sommer(self):
        """Gekappt wird nur, wo die Leistung an die Grenze stoesst -
        im Winter passiert nichts."""
        k = kappungsverlust(_sonnenreihe(), 0.70, 1200.0)
        je_monat = k.verlust_pct_je_monat
        assert max(je_monat[4:8]) > 0        # Mai bis August
        assert je_monat[11] == 0             # Dezember

    def test_monatsanteile_ergeben_den_jahreswert(self):
        """Die beiden Bezugsgroessen duerfen nicht auseinanderlaufen:
        verlust_pct_je_monat misst am Ertrag DIESES Monats, verlust_pct
        am Jahresertrag."""
        reihe = _sonnenreihe()
        k = kappungsverlust(reihe, 0.65, 1200.0)
        gesamt = sum(reihe)
        laengen = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
        start, aus_monaten = 0, 0.0
        for i, laenge in enumerate(laengen):
            anteil_monat = sum(reihe[start:start + laenge]) / gesamt
            aus_monaten += anteil_monat * k.verlust_pct_je_monat[i]
            start += laenge
        assert aus_monaten == pytest.approx(k.verlust_pct, abs=1e-12)

    @pytest.mark.parametrize("limit", [0.0, -0.5])
    def test_unsinniges_limit_wird_abgewiesen(self, limit):
        with pytest.raises(ValueError):
            kappungsverlust(_sonnenreihe(), limit, 1200.0)

    def test_nullreihe_wird_abgewiesen(self):
        with pytest.raises(ValueError, match="null"):
            kappungsverlust([0.0] * STUNDEN, 0.70, 1200.0)


class TestPlateauerkennung:
    """Eine bereits gekappte Reihe ein zweites Mal zu kappen, zoege den
    Verlust doppelt ab - und niemand saehe es."""

    def test_freie_reihe_gilt_nicht_als_gekappt(self):
        assert plateauverdacht(_sonnenreihe()) is False

    @pytest.mark.parametrize("grenze", [0.9, 0.8, 0.6])
    def test_gekappte_reihe_wird_erkannt(self, grenze):
        reihe = _sonnenreihe()
        limit = max(reihe) * grenze
        assert plateauverdacht([min(w, limit) for w in reihe]) is True

    def test_hinterlegte_reihen_sind_ungekappt(self):
        """Die beiden Bauform-Reihen im Repository - waeren sie schon
        gekappt, waere jede Kappungsrechnung darauf falsch."""
        from engine.io_lastgang import stundenprofil, verfuegbare_bauformen

        for bauform in verfuegbare_bauformen():
            assert plateauverdacht(list(stundenprofil(bauform))) is False

    def test_gerundete_reihe_taeuscht_nicht(self):
        """Die hinterlegten Reihen sind auf 0,1 kW gerundet - bei 16,2 kW
        Spitze gibt es nur rund 160 moegliche Werte, da haeuft sich jeder.
        Die Erkennung darf darauf nicht hereinfallen."""
        reihe = [round(w * 16.2, 1) for w in _sonnenreihe()]
        assert plateauverdacht(reihe) is False

    def test_gekappte_reihe_meldet_sich_im_ergebnis(self):
        reihe = _sonnenreihe()
        limit = max(reihe) * 0.8
        k = kappungsverlust([min(w, limit) for w in reihe], 0.70, 1200.0)
        assert any("Plateau" in h for h in k.hinweise)


class TestWirkungAufDieMenge:
    @pytest.fixture
    def reihe_abgelegt(self, tmp_path, monkeypatch):
        """Legt eine Testreihe ab - im tmp-Verzeichnis, damit der
        Datenbestand des Repositorys unberuehrt bleibt."""
        from engine import io_lastgang

        ziel = tmp_path / "projekte"
        ziel.mkdir()
        monkeypatch.setattr(io_lastgang, "PROJEKT_VERZEICHNIS", ziel)
        io_lastgang.projektreihe.cache_clear()
        name = io_lastgang.speichere_projektreihe("p", _sonnenreihe())
        yield name
        io_lastgang.projektreihe.cache_clear()

    def _ga(self, **kw) -> GlobalAssumptions:
        felder = dict(afa_nutzungsdauer_jahre=20, betriebsdauer_jahre=30)
        felder.update(kw)
        return GlobalAssumptions(**felder)

    def test_ohne_reihe_wird_nicht_gekappt(self):
        """Eine Grenze allein reicht nicht - aus einer Jahresmenge laesst
        sich nicht ablesen, welche Stunden sie gerissen haben."""
        from engine.pipeline import run_valuation

        r = run_valuation(_projekt(), self._ga(einspeiselimit_pct=0.70))
        assert float(r.cashflow.data["kappung_kwh"].sum()) == 0.0

    def test_mit_reihe_wird_gekappt(self, reihe_abgelegt):
        from engine.pipeline import run_valuation

        r = run_valuation(
            _projekt(lastgang_datei=reihe_abgelegt),
            self._ga(einspeiselimit_pct=0.70),
        )
        assert float(r.cashflow.data["kappung_kwh"].sum()) > 0

    def test_ohne_limit_wird_nicht_gekappt(self, reihe_abgelegt):
        from engine.pipeline import run_valuation

        r = run_valuation(
            _projekt(lastgang_datei=reihe_abgelegt),
            self._ga(einspeiselimit_pct=None),
        )
        assert float(r.cashflow.data["kappung_kwh"].sum()) == 0.0

    def test_kappung_schrumpft_mit_der_degradation(self, reihe_abgelegt):
        """Der Befund, der eine feste Prozentzahl unbrauchbar macht: Die
        Grenze steht fest, die Anlage degradiert - ihre Spitze faellt
        Jahr fuer Jahr auf die Grenze zu und irgendwann darunter."""
        from engine.pipeline import run_valuation

        r = run_valuation(
            _projekt(lastgang_datei=reihe_abgelegt),
            self._ga(einspeiselimit_pct=0.70, degradation_pct_pa=0.005),
        )
        df = r.cashflow.data
        betrieb = df[df["jahr"] >= 1]
        anteil = (
            betrieb["kappung_kwh"]
            / (betrieb["kappung_kwh"] + betrieb["produktion_kwh"])
        ).tolist()
        assert anteil[0] > anteil[len(anteil) // 2] > anteil[-1]
        assert anteil[-1] < anteil[0] / 2

    def test_projekt_darf_die_vorgabe_ueberschreiben(self, reihe_abgelegt):
        """Ein einzelner Netzanschluss kann anders bemessen sein."""
        from engine.pipeline import run_valuation

        ga = self._ga(einspeiselimit_pct=0.70)
        eng = run_valuation(_projekt(lastgang_datei=reihe_abgelegt), ga)
        weit = run_valuation(
            _projekt(
                lastgang_datei=reihe_abgelegt,
                annahmen=Projektannahmen(einspeiselimit_pct=0.95),
            ),
            ga,
        )
        assert float(weit.cashflow.data["kappung_kwh"].sum()) < float(
            eng.cashflow.data["kappung_kwh"].sum()
        )

    def test_monats_und_jahresaufloesung_kappen_gleich(self, reihe_abgelegt):
        """Beide Wege muessen dieselbe Menge abziehen - sonst haengt die
        Wirkung der Einspeisegrenze an einer Einstellung, die mit ihr
        nichts zu tun hat."""
        from engine.models import Zeitaufloesung
        from engine.pipeline import run_valuation

        projekt = _projekt(lastgang_datei=reihe_abgelegt)
        jaehrlich = run_valuation(
            projekt, self._ga(einspeiselimit_pct=0.70,
                              zeitaufloesung=Zeitaufloesung.JAHR)
        )
        monatlich = run_valuation(
            projekt, self._ga(einspeiselimit_pct=0.70,
                              zeitaufloesung=Zeitaufloesung.MONAT)
        )
        assert float(jaehrlich.cashflow.data["kappung_kwh"].sum()) == pytest.approx(
            float(monatlich.cashflow.data["kappung_kwh"].sum()), rel=1e-9
        )

    def test_kennzahlen_ziehen_nach(self, reihe_abgelegt):
        from engine.pipeline import run_valuation

        ga = self._ga(einspeiselimit_pct=0.70)
        ohne = run_valuation(_projekt(), ga)
        mit = run_valuation(_projekt(lastgang_datei=reihe_abgelegt), ga)
        assert mit.kpis.npv_eur < ohne.kpis.npv_eur
        # Die IRR bleibt bei diesem Testprojekt undefiniert (der
        # Eigenkapital-Cashflow wechselt das Vorzeichen nicht sauber);
        # geprueft wird sie nur, wenn es sie gibt.
        if ohne.kpis.equity_irr is not None and mit.kpis.equity_irr is not None:
            assert mit.kpis.equity_irr < ohne.kpis.equity_irr

    def test_fehlende_datei_bricht_nicht_ab(self):
        """Eine Reihe ist eine Verfeinerung, keine Voraussetzung - fehlt
        die Datei, rechnet das Projekt wie zuvor."""
        from engine.pipeline import run_valuation

        r = run_valuation(
            _projekt(lastgang_datei="gibtesnicht.csv"),
            self._ga(einspeiselimit_pct=0.70),
        )
        assert float(r.cashflow.data["kappung_kwh"].sum()) == 0.0
        assert r.kpis.npv_eur is not None


class TestAblage:
    def test_dateiname_kann_nicht_ausbrechen(self, tmp_path, monkeypatch):
        """Der Dateiname steht in einer Projektdatei und ist damit
        Eingabe, nicht Programmtext."""
        from engine import io_lastgang

        monkeypatch.setattr(io_lastgang, "PROJEKT_VERZEICHNIS", tmp_path)
        pfad = io_lastgang.projektreihe_pfad("../../etc/passwd")
        assert pfad.parent == tmp_path

    def test_reihe_ueberlebt_den_rundlauf(self, tmp_path, monkeypatch):
        from engine import io_lastgang

        monkeypatch.setattr(io_lastgang, "PROJEKT_VERZEICHNIS", tmp_path)
        io_lastgang.projektreihe.cache_clear()
        werte = _sonnenreihe()
        name = io_lastgang.speichere_projektreihe("projekt-x", werte)
        gelesen = io_lastgang.projektreihe(name)
        assert gelesen is not None
        assert len(gelesen) == STUNDEN
        assert list(gelesen) == pytest.approx(werte, abs=1e-4)
        io_lastgang.projektreihe.cache_clear()

    def test_falsche_laenge_wird_abgewiesen(self, tmp_path, monkeypatch):
        from engine import io_lastgang
        from engine.io_lastgang import LastgangFehler

        monkeypatch.setattr(io_lastgang, "PROJEKT_VERZEICHNIS", tmp_path)
        with pytest.raises(LastgangFehler):
            io_lastgang.speichere_projektreihe("p", [1.0] * 100)

    def test_loeschen_entfernt_die_datei(self, tmp_path, monkeypatch):
        from engine import io_lastgang

        monkeypatch.setattr(io_lastgang, "PROJEKT_VERZEICHNIS", tmp_path)
        io_lastgang.projektreihe.cache_clear()
        name = io_lastgang.speichere_projektreihe("p", _sonnenreihe())
        io_lastgang.loesche_projektreihe(name)
        assert io_lastgang.projektreihe(name) is None

    def test_ohne_dateiname_keine_reihe(self):
        from engine.io_lastgang import projektreihe

        assert projektreihe(None) is None
        assert projektreihe("") is None
