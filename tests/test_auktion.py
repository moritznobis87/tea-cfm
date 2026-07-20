"""
Tests des EAG-Gebotsmodells (engine/auktion.py): Datenladen und
Regime-Erkennung, Erfuellung der Kalibrierbedingungen, geforderte
Verteilungseigenschaften (harte Obergrenze, Asymmetrie, Dichte an der
Obergrenze je Regime), Richtung des Wettbewerbs-Links, Monotonie der
Prognose sowie die Integration in die Monte-Carlo-Simulation.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from engine.auktion import (
    EPS_MIN,
    FAMILIEN,
    differenzen_extrapolation,
    fit_runde,
    kalibriere_modell,
    load_ausschreibungen,
    prognose_letzte_runde,
    prognose_naechste_runde,
    validiere_einschritt,
    validiere_loo,
    vergleiche_familien,
)

DATEN = Path(__file__).parent.parent / "data" / "ausschreibungen.yaml"


@pytest.fixture(scope="module")
def runden():
    return load_ausschreibungen(DATEN)


@pytest.fixture(scope="module")
def modell(runden):
    return kalibriere_modell(runden, "Beta")


@pytest.fixture(scope="module")
def modell_ig(runden):
    return kalibriere_modell(runden, "Gespiegelte Inverse Gamma")


class TestDatenUndRegime:
    def test_alle_runden_geladen(self, runden):
        assert len(runden) == 15
        assert all(r.zuschlag_min_ct <= r.zuschlag_mittel_ct <= r.zuschlag_max_ct
                   <= r.preisobergrenze_ct + 1e-9 for r in runden)

    def test_regime_erkennung(self, runden):
        # Fruehe Runden unterzeichnet, Wettbewerbsrunden ab 07/2025.
        nach_datum = sorted(runden, key=lambda r: r.datum)
        assert nach_datum[0].unterzeichnet
        assert not nach_datum[-1].unterzeichnet
        assert sum(not r.unterzeichnet for r in runden) == 4


class TestRundenFit:
    def test_kalibrierbedingungen_erfuellt(self, runden):
        """Mittelwert- und Minimum-Bedingung werden je Runde (nahezu)
        exakt getroffen."""
        familie = FAMILIEN["Beta"]
        for runde in runden:
            fit = fit_runde(runde, familie)
            cap = runde.preisobergrenze_ct
            if runde.unterzeichnet:
                mean_modell = familie.mean(fit.mu_rel, fit.kappa, cap)
            else:
                mean_modell = familie.trunc_mean(
                    fit.mu_rel, fit.kappa, cap, runde.zuschlag_max_ct
                )
            assert mean_modell == pytest.approx(runde.zuschlag_mittel_ct, abs=0.5)
            min_modell = familie.ppf(fit.mu_rel, fit.kappa, cap, EPS_MIN)
            assert min_modell == pytest.approx(runde.zuschlag_min_ct, abs=0.7)

    def test_harte_obergrenze(self, modell):
        familie = FAMILIEN["Beta"]
        f = modell.letzte_runde
        cap = f.ausschreibung.preisobergrenze_ct
        assert familie.cdf(f.mu_rel, f.kappa, cap, cap) == pytest.approx(1.0)
        assert familie.ppf(f.mu_rel, f.kappa, cap, 0.999999) <= cap + 1e-9

    def test_dichte_an_obergrenze_je_regime(self, modell):
        """Geforderte Eigenschaft: In UEBERZEICHNETEN Runden ist die Dichte
        an der Obergrenze praktisch null (Beta-Parameter beta > 1) - das
        ergibt sich in allen vier Wettbewerbsrunden von selbst aus dem
        Fit. In unterzeichneten Runden traegt die Verteilung Masse an der
        Obergrenze (beta < 1, Gebote am Cap) - mit Ausnahme frueher
        Explorationsrunden (12/2022, 07/2023), in denen die Gebote laut
        Literatur breiter streuten."""
        for f in modell.fits:
            beta_param = (1 - f.mu_rel) * f.kappa
            if not f.ausschreibung.unterzeichnet:
                assert beta_param > 1.0
        unterz = [f for f in modell.fits if f.ausschreibung.unterzeichnet]
        am_cap = sum((1 - f.mu_rel) * f.kappa < 1.0 for f in unterz)
        assert am_cap >= len(unterz) - 2

    def test_asymmetrie_langer_linker_auslaeufer(self, modell):
        """Median > Mittelwert (linksschiefe Verteilung) in den
        Wettbewerbsrunden."""
        familie = FAMILIEN["Beta"]
        f = modell.letzte_runde
        cap = f.ausschreibung.preisobergrenze_ct
        median = familie.ppf(f.mu_rel, f.kappa, cap, 0.5)
        mean = familie.mean(f.mu_rel, f.kappa, cap)
        assert median > mean

    def test_latente_wettbewerbsquote_ueber_eins(self, modell):
        for f in modell.fits:
            if not f.ausschreibung.unterzeichnet:
                assert f.wettbewerbsquote_latent and f.wettbewerbsquote > 1.0
            else:
                assert not f.wettbewerbsquote_latent and f.wettbewerbsquote <= 1.0


class TestLinkUndPrognose:
    def test_link_richtungen(self, modell):
        """Datengetriebener Link: mehr Wettbewerb -> niedrigere Lage,
        hoehere Konzentration."""
        assert modell.koef_lage[1] < 0
        assert modell.koef_konzentration[1] > 0

    def test_wettbewerbsquote_impliziert(self, modell):
        """Die Wettbewerbsquote ist im Prognosemodus impliziert
        (r = 1/F(max)) und liegt im plausiblen Ueberzeichnungsbereich."""
        p = prognose_naechste_runde(modell, 7.77, n_ziehungen=500)
        assert 1.0 < p.wettbewerbsquote < 5.0

    def test_zuschlagskurve_monoton_und_kalibriert(self, modell):
        p = prognose_naechste_runde(modell, 7.77)
        gebote = np.linspace(4.0, 7.77, 30)
        probs = [p.zuschlagswahrscheinlichkeit(b) for b in gebote]
        assert all(a >= b - 1e-9 for a, b in zip(probs, probs[1:], strict=False))
        for ziel in (0.5, 0.8, 0.9):
            b = p.empfohlenes_gebot(ziel)
            assert b <= 7.77 + 1e-9
            assert p.zuschlagswahrscheinlichkeit(b) == pytest.approx(ziel, abs=0.03)

    def test_differenzen_extrapolation(self):
        """Rekursive Mehrfach-Differenzenextrapolation exakt nach
        Spezifikation - inkl. des motivierenden Beispiels: Halbiert sich
        der Rueckgang (-40 -> -20 -> -10), erwartet das Verfahren mit
        Daempfung lambda=0,5 den naechsten Schritt bei -5."""
        w = [100.0, 60.0, 40.0, 30.0]
        assert differenzen_extrapolation(w, 1) == pytest.approx(20.0)   # linear
        assert differenzen_extrapolation(w, 2) == pytest.approx(30.0)   # lambda=1
        assert differenzen_extrapolation(w, 2, (0.5,)) == pytest.approx(25.0)
        # Handrechnung reale Daten, Ordnung 2: 6,69 + (-0,11 + 0,38)
        assert differenzen_extrapolation([8.48, 7.29, 6.80, 6.69], 2) == (
            pytest.approx(6.96, abs=1e-9)
        )
        # lambda=0 entspricht der linearen Fortschreibung
        assert differenzen_extrapolation(w, 2, (0.0,)) == pytest.approx(20.0)
        # Effektive Ordnung durch Stuetzstellen begrenzt; Random Walk bei 1
        assert differenzen_extrapolation([7.29, 6.80], 4) == pytest.approx(6.31)
        assert differenzen_extrapolation([5.0], 3) == 5.0

    def test_gebots_ziehungen_erfolgreich_und_begrenzt(self, modell):
        p = prognose_naechste_runde(modell, 7.77, n_ziehungen=800)
        zieh = p.gebots_ziehungen(400, seed=1)
        assert len(zieh) == 400
        assert (zieh > 0).all() and (zieh <= 7.77 + 1e-9).all()
        # Erfolgreiche Gebote liegen im Mittel unter dem Grenzzuschlag.
        assert zieh.mean() < np.mean(p.pm_sample)

    def test_reproduzierbar(self, modell):
        p1 = prognose_naechste_runde(modell, 7.77, seed=7)
        p2 = prognose_naechste_runde(modell, 7.77, seed=7)
        assert np.allclose(p1.pm_sample, p2.pm_sample)

    def test_modus_letzte_runde_gesetzt(self, modell):
        """Modus 1: Verteilung der letzten Runde unveraendert; die
        Risikoneigung waehlt das Quantil der Zuschlagswerte."""
        p = prognose_letzte_runde(modell)
        ist = modell.letzte_runde.ausschreibung
        assert p.modus == "letzte"
        assert p.grenzzuschlag_zentral_ct == ist.zuschlag_max_ct
        # Monoton: hoehere Sicherheit -> niedrigerer Wert; nie ueber p_m
        w = [p.empfohlenes_gebot(z) for z in (0.5, 0.7, 0.9, 0.95)]
        assert all(a >= b for a, b in zip(w, w[1:], strict=False))
        assert max(w) <= ist.zuschlag_max_ct + 1e-9
        # Kalibriert: P(Wert) am gewaehlten Quantil == Zielwahrscheinlichkeit
        assert p.zuschlagswahrscheinlichkeit(
            p.empfohlenes_gebot(0.8)
        ) == pytest.approx(0.8, abs=0.02)
        # Ziehungen bleiben unter dem gesetzten Grenzzuschlag
        zieh = p.gebots_ziehungen(300, seed=2)
        assert (zieh <= ist.zuschlag_max_ct + 1e-9).all()


class TestValidierungUndVergleich:
    def test_familienvergleich_liefert_alle_kandidaten(self, runden):
        df = vergleiche_familien(runden)
        assert set(df["familie"]) == set(FAMILIEN)
        beta = df.set_index("familie").loc["Beta"]
        tn = df.set_index("familie").loc["Trunkierte Normalverteilung"]
        # Kernargument der Modellwahl: Beta beschreibt die beobachteten
        # Aggregate (Mittelwert + Minimum gemeinsam) deutlich besser.
        assert beta["fit_rmse_ct"] < tn["fit_rmse_ct"] / 2

    def test_loo_deckt_alle_wettbewerbsrunden_ab(self, runden):
        loo = validiere_loo(runden, "Beta")
        assert len(loo) == sum(not r.unterzeichnet for r in runden)
        assert loo["grenzzuschlag_modell_ct"].notna().all()


class TestMonteCarloIntegration:
    def test_gebotsziehung_veraendert_irr_verteilung(
        self, project, global_assumptions, modell
    ):
        from engine import run_monte_carlo

        p = prognose_naechste_runde(modell, 7.77, n_ziehungen=500)
        basis = run_monte_carlo(project, global_assumptions, n_laeufe=30,
                                sigmas={"produktion": 0.0})
        mit_gebot = run_monte_carlo(
            project, global_assumptions, n_laeufe=30,
            sigmas={"produktion": 0.0},
            gebot_ziehungen=p.gebots_ziehungen(30, seed=3),
        )
        # Ohne weitere Unsicherheiten ist die Basis konstant, mit
        # Gebotsziehung streut die IRR.
        assert np.nanstd(basis.irr) == pytest.approx(0.0, abs=1e-12)
        assert np.nanstd(mit_gebot.irr) > 0.001

    def test_konventionell_abschlag_bleibt_erhalten(
        self, project, global_assumptions, modell
    ):
        from engine import AnlagenTyp, run_monte_carlo

        p = prognose_naechste_runde(modell, 7.77, n_ziehungen=200)
        ziehung = np.array([6.0])  # ein festes "Gebot" fuer alle Laeufe
        agri = run_monte_carlo(project, global_assumptions, n_laeufe=3,
                               sigmas={}, gebot_ziehungen=ziehung)
        konv = project.model_copy(deep=True)
        konv.anlagentyp = AnlagenTyp.KONVENTIONELL
        konv_mc = run_monte_carlo(konv, global_assumptions, n_laeufe=3,
                                  sigmas={}, gebot_ziehungen=ziehung)
        # Konventionell (25 % Abschlag auf das Gebot) rentiert schlechter.
        assert np.nanmean(konv_mc.irr) < np.nanmean(agri.irr)
        assert p.preisobergrenze_ct == 7.77


class TestVerankertePrognoseUndFamilienwahl:
    """Kernanforderungen der ueberarbeiteten Prognose: Verankerung an der
    letzten Runde (Median-Grenzzuschlag nicht deutlich ueber dem letzten
    Ist-Wert), keine Masse an der Obergrenze bei Ueberzeichnung sowie die
    geforderte Dichteform der gespiegelten Inversen Gamma."""

    def test_punktprognosen_und_ordnungsprojektion(self, modell_ig):
        """Standard (Ordnung 2, lambda=1): Grenzzuschlag 6,69 +
        (-0,11 + 0,38) = 6,96; die Ordnung Min <= OE <= Max < Obergrenze
        wird eingehalten (OE-Rohprognose 7,09 wird auf max - 0,05
        projiziert)."""
        p = prognose_naechste_runde(modell_ig, 7.77)
        assert p.grenzzuschlag_zentral_ct == pytest.approx(6.96, abs=0.02)
        assert p.grenzzuschlag_zentral_ct < 7.77
        assert p.gebot_mittel_ct < p.grenzzuschlag_zentral_ct
        assert p.gebot_quantile[5] < p.gebot_mittel_ct

    def test_ordnung_und_daempfung_wirken(self, modell_ig):
        p1 = prognose_naechste_runde(modell_ig, 7.77, ordnung=1)
        p2 = prognose_naechste_runde(modell_ig, 7.77, ordnung=2)
        p2d = prognose_naechste_runde(modell_ig, 7.77, ordnung=2,
                                      lambdas=(0.0,))
        # Ordnung 1 = linearer Trend (6,58); lambda=0 faellt darauf zurueck
        assert p1.grenzzuschlag_zentral_ct == pytest.approx(6.58, abs=0.02)
        assert p2d.grenzzuschlag_zentral_ct == pytest.approx(
            p1.grenzzuschlag_zentral_ct, abs=0.01
        )
        assert p2.grenzzuschlag_zentral_ct > p1.grenzzuschlag_zentral_ct

    def test_keine_masse_an_obergrenze_bei_ueberzeichnung(self, modell_ig):
        p = prognose_naechste_runde(modell_ig, 7.77)
        assert float(np.mean(p.pm_sample >= 7.77 - 1e-9)) == 0.0

    def test_dichteform_steil_rechts_langsam_links(self, modell_ig):
        """Gespiegelte InvGamma, Zuschlagswerte: Modus knapp unter dem
        Grenzzuschlag; rechts vom Modus faellt die Dichte praktisch auf
        null, links laeuft sie langsam aus."""
        p = prognose_naechste_runde(modell_ig, 7.77)
        x, y = p.dichte_x, p.dichte_zuschlag_y
        modus = x[int(np.argmax(y))]
        assert p.gebot_mittel_ct < modus <= 7.77
        rechts = y[np.searchsorted(x, min(modus + 0.2, 7.7))]
        links = y[np.searchsorted(x, modus - 0.5)]
        assert rechts < 0.1 * y.max()          # steiler Abfall nach rechts
        assert links > 5 * max(rechts, 1e-12)  # links deutlich langsamer
        assert links > 0.02 * y.max()
        # Harte Obergrenze: am Cap ist die Dichte null.
        assert y[-1] < 1e-6 * max(y.max(), 1e-9)

    def test_einschritt_backtest_deckt_wettbewerbsrunden(self, runden):
        """Backtest der Momentum-Formel: eine Runde weniger als
        Wettbewerbsrunden (die erste hat keinen Wettbewerbs-Vorgaenger);
        die Formel greift erst ab drei Stuetzstellen (ausgewiesen)."""
        bt = validiere_einschritt(runden, "Gespiegelte Inverse Gamma")
        assert len(bt) == sum(not r.unterzeichnet for r in runden) - 1
        # Erste Runde hat nur eine Stuetzstelle (Random Walk), danach
        # steigt die effektive Ordnung mit den verfuegbaren Runden.
        assert bt["methode"].iloc[0].startswith("Random Walk")
        assert bt["methode"].iloc[1:].str.startswith("Differenzen").all()
        # 06/2026 aus [8.48, 7.29, 6.80], Ordnung 2: 6.80 + (-0.49 + 0.70)
        letzte_zeile = bt.iloc[-1]
        assert letzte_zeile["grenzzuschlag_modell_ct"] == pytest.approx(7.01, abs=0.02)
