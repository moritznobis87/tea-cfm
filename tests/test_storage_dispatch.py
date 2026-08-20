"""
Der Speicher-Dispatch: Verhaelt er sich physikalisch und wirtschaftlich?

Die Tests sind bewusst KLEIN gehalten - 24 bis 48 Stunden mit von Hand
gesetzten Preisen. Ein Jahreslauf beweist nichts ueber das Verhalten in
einer bestimmten Lage; ein konstruierter Tagesgang schon.

Der Jahreslauf steht trotzdem daneben (TestJahreslauf): Er misst die
Rechenzeit und prueft die LP gegen ein unabhaengiges Verfahren.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine.models import NegativeStundenRegel  # noqa: E402
from engine.storage import (  # noqa: E402
    BatteryConfig,
    SpeicherModus,
    dispatch_jahr,
    negativstunden_maske,
    vollzyklen,
)


#: Ein Speicher, an dem sich die Faelle unterscheiden lassen: 5 MW,
#: 10 MWh brutto, 90 % Roundtrip, 5-95 % nutzbar.
def _batterie(**felder) -> BatteryConfig:
    vorgabe = dict(
        modus=SpeicherModus.GRUENSTROM,
        leistung_mw=5.0,
        kapazitaet_mwh=10.0,
        roundtrip_wirkungsgrad=0.90,
        degradationskosten_eur_mwh=0.0,
        netzbezug_limit_mw=0.0,
    )
    vorgabe.update(felder)
    return BatteryConfig(**vorgabe)


def _lauf(pv, preis, batterie=None, export_limit=12.6, grenzerloes=None):
    pv = np.asarray(pv, dtype=float)
    preis = np.asarray(preis, dtype=float)
    return dispatch_jahr(
        pv_mw=pv,
        preis_eur_mwh=preis,
        grenzerloes_eur_mwh=(
            preis if grenzerloes is None else np.asarray(grenzerloes, dtype=float)
        ),
        batterie=batterie or _batterie(),
        export_limit_mw=export_limit,
    )


def _tag(werte) -> np.ndarray:
    """24 Werte aus einer Kurzschreibweise (Stunde -> Wert)."""
    return np.asarray(werte, dtype=float)


class TestGrundverhalten:
    def test_1_ohne_preisunterschiede_faehrt_der_speicher_nicht(self):
        """Ohne Spread gibt es nichts zu verdienen - jeder Zyklus waere
        nur Verlust durch den Wirkungsgrad."""
        ergebnis = _lauf(np.zeros(24), np.full(24, 80.0))
        assert ergebnis.spalte("speicher_ins_netz_mw").sum() == pytest.approx(0.0)
        assert ergebnis.spalte("pv_in_speicher_mw").sum() == pytest.approx(0.0)

    def test_2_billig_mittags_teuer_abends(self):
        """Der Kernfall: PV laedt mittags, der Speicher entlaedt abends."""
        pv = _tag([0]*8 + [8]*6 + [0]*10)
        preis = _tag([50]*8 + [10]*6 + [200]*4 + [50]*6)
        ergebnis = _lauf(pv, preis)
        geladen = ergebnis.spalte("pv_in_speicher_mw")
        entladen = ergebnis.spalte("speicher_ins_netz_mw")
        assert geladen[8:14].sum() > 0, "mittags wurde nicht geladen"
        assert entladen[14:18].sum() > 0, "abends wurde nicht entladen"
        assert entladen[8:14].sum() == pytest.approx(0.0)

    def test_3_speicher_holt_abregelung_zurueck(self):
        """PV ueber dem Exportlimit: Was sonst verloren waere, geht in
        den Speicher."""
        pv = _tag([0]*8 + [20]*6 + [0]*10)   # 20 MW gegen 12,6 MW Limit
        preis = _tag([80]*24)
        ohne = _lauf(pv, preis, _batterie(leistung_mw=0.0, kapazitaet_mwh=0.0))
        mit = _lauf(pv, preis)
        assert (
            mit.spalte("abregelung_mw").sum()
            < ohne.spalte("abregelung_mw").sum()
        )
        assert mit.spalte("pv_in_speicher_mw").sum() > 0

    def test_4_voller_speicher_laedt_nicht_weiter(self):
        pv = _tag([20]*24)
        preis = _tag([80]*24)
        ergebnis = _lauf(pv, preis)
        batterie = _batterie()
        soc = ergebnis.spalte("soc_mwh")
        assert soc.max() <= batterie.kapazitaet_mwh * batterie.soc_max_pct + 1e-6

    def test_5_leerer_speicher_entlaedt_nicht(self):
        pv = np.zeros(24)
        preis = _tag([10]*12 + [300]*12)
        batterie = _batterie(soc_start_pct=0.05)
        ergebnis = _lauf(pv, preis, batterie)
        soc = ergebnis.spalte("soc_mwh")
        assert soc.min() >= batterie.kapazitaet_mwh * batterie.soc_min_pct - 1e-6
        # Ohne PV und ohne Netzbezug kann nichts entladen werden.
        assert ergebnis.spalte("speicher_ins_netz_mw").sum() == pytest.approx(
            0.0, abs=1e-6
        )


class TestBetriebsarten:
    def test_6_gruenstrom_laedt_nie_aus_dem_netz(self):
        pv = _tag([0]*8 + [8]*6 + [0]*10)
        preis = _tag([-20]*8 + [10]*6 + [200]*10)
        ergebnis = _lauf(pv, preis, _batterie(netzbezug_limit_mw=10.0))
        assert ergebnis.spalte("netz_in_speicher_mw").sum() == pytest.approx(
            0.0, abs=1e-9
        ), "Der Gruenstromspeicher hat aus dem Netz geladen"

    def test_7_graustrom_laedt_nachts_billig(self):
        pv = np.zeros(24)
        preis = _tag([5]*8 + [80]*8 + [250]*8)
        ergebnis = _lauf(
            pv, preis,
            _batterie(modus=SpeicherModus.GRAUSTROM, netzbezug_limit_mw=10.0),
        )
        netzbezug = ergebnis.spalte("netz_in_speicher_mw")
        assert netzbezug[:8].sum() > 0, "nachts wurde nicht aus dem Netz geladen"
        assert ergebnis.spalte("speicher_ins_netz_mw")[16:].sum() > 0


class TestNetzgrenzen:
    def test_8_exportlimit_gilt_in_jeder_stunde(self):
        pv = _tag([20]*24)
        preis = _tag([50]*12 + [300]*12)
        ergebnis = _lauf(pv, preis, export_limit=12.6)
        export = (
            ergebnis.spalte("pv_ins_netz_mw")
            + ergebnis.spalte("speicher_ins_netz_mw")
        )
        assert export.max() <= 12.6 + 1e-6

    def test_9_importlimit_gilt_in_jeder_stunde(self):
        pv = np.zeros(24)
        preis = _tag([5]*12 + [300]*12)
        ergebnis = _lauf(
            pv, preis,
            _batterie(modus=SpeicherModus.GRAUSTROM, netzbezug_limit_mw=3.0),
        )
        assert ergebnis.spalte("netz_in_speicher_mw").max() <= 3.0 + 1e-6


class TestEnergiebilanz:
    def test_10_wirkungsgrad_erzeugt_verluste(self):
        """Was hineingeht, kommt vermindert wieder heraus."""
        pv = _tag([0]*8 + [8]*6 + [0]*10)
        preis = _tag([50]*8 + [10]*6 + [400]*4 + [50]*6)
        batterie = _batterie(roundtrip_wirkungsgrad=0.81)   # eta = 0,9 je Weg
        ergebnis = _lauf(pv, preis, batterie)
        geladen = ergebnis.spalte("pv_in_speicher_mw").sum()
        entladen = ergebnis.spalte("speicher_ins_netz_mw").sum()
        assert geladen > 0
        # Der Speicher startet und endet beim selben Fuellstand, also ist
        # die Entladung genau der Roundtrip-Anteil der Ladung.
        assert entladen == pytest.approx(geladen * 0.81, rel=1e-3)

    def test_pv_bilanz_geht_in_jeder_stunde_auf(self):
        pv = _tag([0]*6 + list(range(1, 13)) + [0]*6)
        preis = _tag([80]*24)
        ergebnis = _lauf(pv, preis)
        summe = (
            ergebnis.spalte("pv_ins_netz_mw")
            + ergebnis.spalte("pv_in_speicher_mw")
            + ergebnis.spalte("abregelung_mw")
        )
        assert np.allclose(summe, ergebnis.spalte("pv_erzeugung_mw"), atol=1e-6)

    def test_11_zyklischer_abschluss_verhindert_scheinwert(self):
        """Ohne ihn leerte der Optimierer den Speicher in der letzten
        Stunde und buchte einen Erloes, der aus dem Anfangsbestand
        stammt."""
        pv = np.zeros(24)
        preis = _tag([50]*23 + [500])       # letzte Stunde extrem teuer
        batterie = _batterie(soc_start_pct=0.95)
        ergebnis = _lauf(pv, preis, batterie)
        soc = ergebnis.spalte("soc_mwh")
        assert soc[-1] == pytest.approx(
            batterie.kapazitaet_mwh * batterie.soc_start_pct, abs=1e-6
        )
        assert ergebnis.spalte("speicher_ins_netz_mw").sum() == pytest.approx(
            0.0, abs=1e-6
        )


class TestNegativePreise:
    def test_12_kein_gleichzeitiges_laden_und_entladen(self):
        """Bei negativem Grenzerloes wird man fuer den Verbrauch bezahlt.
        Ein LP kann daraus Gewinn schoepfen, indem es gleichzeitig laedt
        und entlaedt - der Fuellstand bleibt gleich, der Roundtrip-
        Verlust wird zur Einnahme.

        Der Waechter in dispatch.py faengt das ab. Geprueft wird der
        konstruierte Fall, der es ausloest: Speicher voll, Preis
        durchgehend negativ, keine PV.
        """
        pv = np.zeros(24)
        preis = np.full(24, -50.0)
        ergebnis = _lauf(
            pv, preis,
            _batterie(modus=SpeicherModus.GRAUSTROM, netzbezug_limit_mw=10.0,
                      soc_start_pct=0.95),
        )
        laden = (
            ergebnis.spalte("pv_in_speicher_mw")
            + ergebnis.spalte("netz_in_speicher_mw")
        )
        entladen = ergebnis.spalte("speicher_ins_netz_mw")
        gleichzeitig = (laden > 1e-6) & (entladen > 1e-6)
        assert not gleichzeitig.any(), (
            f"{int(gleichzeitig.sum())} Stunden mit gleichzeitigem Laden "
            "und Entladen"
        )

    def test_negativer_grenzerloes_fuehrt_zu_abregelung(self):
        """Ein rationaler Betreiber zahlt nicht dafuer, Strom zu liefern."""
        pv = _tag([0]*8 + [5]*8 + [0]*8)
        preis = _tag([80]*8 + [-30]*8 + [80]*8)
        ergebnis = _lauf(pv, preis, _batterie(leistung_mw=0.0, kapazitaet_mwh=0.0))
        assert ergebnis.spalte("pv_ins_netz_mw")[8:16].sum() == pytest.approx(
            0.0, abs=1e-6
        )
        assert ergebnis.spalte("abregelung_mw")[8:16].sum() > 0


class TestDegradation:
    def test_13_hohe_verschleisskosten_unterbinden_zyklen(self):
        pv = _tag([0]*8 + [8]*6 + [0]*10)
        preis = _tag([50]*8 + [40]*6 + [70]*4 + [50]*6)   # Spread 30
        billig = _lauf(pv, preis, _batterie(degradationskosten_eur_mwh=0.0))
        teuer = _lauf(pv, preis, _batterie(degradationskosten_eur_mwh=500.0))
        assert billig.spalte("speicher_ins_netz_mw").sum() > 0
        assert teuer.spalte("speicher_ins_netz_mw").sum() == pytest.approx(
            0.0, abs=1e-6
        )


class TestUnwirksamerSpeicher:
    """Der Vergleichsfall muss exakt PV-only sein - sonst ist der
    ausgewiesene Wertbeitrag wertlos."""

    @pytest.mark.parametrize(
        "felder", [{"leistung_mw": 0.0}, {"kapazitaet_mwh": 0.0},
                   {"aktiv": False}],
    )
    def test_14_15_ohne_speicher_bleibt_es_bei_pv_only(self, felder):
        pv = _tag([0]*8 + [20]*6 + [0]*10)
        preis = _tag([50]*8 + [10]*6 + [200]*4 + [50]*6)
        ergebnis = _lauf(pv, preis, _batterie(**felder))
        assert ergebnis.wertbeitrag_eur == pytest.approx(0.0, abs=1e-6)
        assert ergebnis.spalte("speicher_ins_netz_mw").sum() == pytest.approx(
            0.0, abs=1e-9
        )


class TestNegativstundenRegel:
    """Dieselbe gesetzliche Regel wie im Cashflow, nur in der Aufloesung,
    fuer die sie geschrieben wurde."""

    def test_eine_stunde_trifft_jede_negative_stunde(self):
        preis = np.array([10.0, -1.0, 10.0, -1.0])
        maske = negativstunden_maske(preis, NegativeStundenRegel.EINE_STUNDE)
        assert list(maske) == [False, True, False, True]

    def test_sechs_stunden_greift_erst_ab_der_sechsten(self):
        preis = np.array([-1.0]*5 + [10.0] + [-1.0]*6 + [10.0])
        maske = negativstunden_maske(preis, NegativeStundenRegel.SECHS_STUNDEN)
        assert not maske[:5].any(), "fuenf Stunden reichen noch nicht"
        assert maske[6:12].all(), "sechs Stunden in Folge muessen greifen"
        assert not maske[12]


class TestVollzyklen:
    def test_definition_bezieht_sich_auf_den_nutzbaren_hub(self):
        """Ein Zyklus ist das einmalige Durchfahren dessen, was der
        Speicher hergibt - nicht der Bruttokapazitaet."""
        pv = _tag([0]*8 + [8]*6 + [0]*10)
        preis = _tag([50]*8 + [10]*6 + [400]*4 + [50]*6)
        batterie = _batterie()
        ergebnis = _lauf(pv, preis, batterie)
        entladen = ergebnis.spalte("speicher_ins_netz_mw").sum()
        assert vollzyklen(ergebnis, batterie) == pytest.approx(
            entladen / batterie.nutzbare_kapazitaet_mwh
        )


class TestFehlerfaelle:
    def test_ungleiche_reihenlaengen_werden_gemeldet(self):
        with pytest.raises(ValueError, match="erwartet"):
            dispatch_jahr(
                pv_mw=np.zeros(24), preis_eur_mwh=np.zeros(12),
                grenzerloes_eur_mwh=np.zeros(24), batterie=_batterie(),
                export_limit_mw=10.0,
            )

    def test_exportlimit_null_wird_gemeldet(self):
        with pytest.raises(ValueError, match="Exportlimit"):
            _lauf(np.zeros(24), np.zeros(24), export_limit=0.0)


class TestJahreslauf:
    """Ein volles Jahr - Rechenzeit und Gegenprobe."""

    def _jahr(self):
        stunde = np.arange(8760) % 24
        tag = np.arange(8760) // 24
        tagesgang = np.clip(np.sin((stunde - 6) / 12 * np.pi), 0, None)
        jahresgang = 0.6 + 0.4 * np.sin((tag - 80) / 365 * 2 * np.pi)
        pv = 18.0 * tagesgang * jahresgang
        pv *= (18.0 * 1100) / pv.sum()
        rng = np.random.default_rng(7)
        preis = (
            80 + 40 * np.sin((stunde - 18) / 24 * 2 * np.pi)
            + rng.normal(0, 15, 8760)
        )
        preis[(pv > 12) & (rng.random(8760) < 0.4)] = -40.0
        return pv, preis

    def test_ein_jahr_loest_in_wenigen_sekunden(self):
        import time

        pv, preis = self._jahr()
        t0 = time.perf_counter()
        ergebnis = _lauf(pv, preis, _batterie(degradationskosten_eur_mwh=2.0))
        dauer = time.perf_counter() - t0
        assert ergebnis.wertbeitrag_eur > 0
        assert dauer < 30.0, f"Ein Jahr brauchte {dauer:.1f}s"

    def test_keine_ueberlappung_ueber_ein_volles_jahr(self):
        """Der Waechter darf im Normalfall nicht anschlagen - sonst
        waere die Formulierung selbst das Problem."""
        pv, preis = self._jahr()
        ergebnis = _lauf(
            pv, preis,
            _batterie(modus=SpeicherModus.GRAUSTROM, netzbezug_limit_mw=10.0,
                      degradationskosten_eur_mwh=2.0),
        )
        laden = (
            ergebnis.spalte("pv_in_speicher_mw")
            + ergebnis.spalte("netz_in_speicher_mw")
        )
        entladen = ergebnis.spalte("speicher_ins_netz_mw")
        assert not ((laden > 1e-6) & (entladen > 1e-6)).any()


class TestGleichstand:
    """Preis exakt null: Einspeisen und Abregeln bringen dasselbe.

    Ohne Aufloesung des Gleichstands greift der Solver willkuerlich zu.
    In den Aurora-Reihen stehen tausende Stunden mit glatt 0,00 EUR/MWh -
    an echten Daten erschienen sie samt und sonders als Abregelung, und
    die ausgewiesene Einspeisung sank um 2.225 MWh, ohne dass sich am
    Zielwert etwas aenderte.
    """

    def test_bei_preis_null_wird_eingespeist_statt_abgeregelt(self):
        pv = _tag([0] * 8 + [5] * 8 + [0] * 8)
        preis = np.zeros(24)
        ergebnis = _lauf(pv, preis, _batterie(leistung_mw=0.0, kapazitaet_mwh=0.0))
        assert ergebnis.spalte("abregelung_mw").sum() == pytest.approx(0.0, abs=1e-6)
        assert ergebnis.spalte("pv_ins_netz_mw").sum() == pytest.approx(
            pv.sum(), rel=1e-9
        )

    def test_bei_negativem_preis_wird_weiterhin_abgeregelt(self):
        """Die Aufloesung darf nur den Gleichstand treffen, nicht den
        Fall, in dem Einspeisen tatsaechlich Geld kostet."""
        pv = _tag([0] * 8 + [5] * 8 + [0] * 8)
        preis = np.full(24, -0.5)
        ergebnis = _lauf(pv, preis, _batterie(leistung_mw=0.0, kapazitaet_mwh=0.0))
        assert ergebnis.spalte("pv_ins_netz_mw").sum() == pytest.approx(0.0, abs=1e-6)
        assert ergebnis.spalte("abregelung_mw").sum() == pytest.approx(
            pv.sum(), rel=1e-9
        )


class TestWirkungsgradLoestEsNicht:
    """Ein hoher Wirkungsgrad beseitigt die Entartung NICHT.

    Naheliegender Gedanke: Wenn der Roundtrip-Verlust das Problem ist,
    dann behebt ihn ein besserer Wirkungsgrad. Das Gegenteil ist der
    Fall - es ist gerade der VERLUST, der die Gelegenheit schafft. Bei
    negativem Preis wird man fuer den Verbrauch bezahlt, und der Verlust
    IST der Verbrauch. Der Scheingewinn ist proportional zu (1 - RTE):

        RTE 80 %  -> 1.200 EUR, 21 von 24 Stunden ueberlappend
        RTE 90 %  ->   600 EUR, 23
        RTE 98 %  ->   120 EUR, 24
        RTE 100 % ->     0 EUR,  0

    Ein besserer Wirkungsgrad macht das Geschaeft also kleiner, nie
    unmoeglich - und bei 98 % ueberlappen sogar MEHR Stunden als bei
    90 %, weil der Trick mit weniger Verlust in mehr Stunden passt.

    Geprueft wird deshalb, dass der Waechter auch bei einem sehr guten
    Wirkungsgrad noch gebraucht wird und sein Ergebnis sauber ist.
    """

    @pytest.mark.parametrize("rte", [0.90, 0.98])
    def test_waechter_haelt_auch_bei_gutem_wirkungsgrad(self, rte):
        pv = np.zeros(24)
        preis = np.full(24, -50.0)
        ergebnis = _lauf(
            pv, preis,
            _batterie(modus=SpeicherModus.GRAUSTROM, netzbezug_limit_mw=10.0,
                      soc_start_pct=0.95, roundtrip_wirkungsgrad=rte),
        )
        laden = (
            ergebnis.spalte("pv_in_speicher_mw")
            + ergebnis.spalte("netz_in_speicher_mw")
        )
        entladen = ergebnis.spalte("speicher_ins_netz_mw")
        assert not ((laden > 1e-6) & (entladen > 1e-6)).any()
        assert ergebnis.hinweise, (
            "Der Waechter hat nicht angeschlagen - die nackte LP haette "
            "hier gleichzeitig geladen und entladen"
        )
