"""
Gebotsmodell fuer die oesterreichischen EAG-Marktpraemienausschreibungen
Photovoltaik (Price-Taker-Sicht).

Fachlicher Rahmen (Webrecherche, Stand 07/2026):
- Pay-as-Bid mit Gebotspreisreihung: Gebote werden aufsteigend gereiht und
  bis zur ausgeschriebenen Menge bezuschlagt; jeder Gewinner erhaelt seinen
  eigenen Gebotswert als anzulegenden Wert (EAG §§ 18 ff., OeMAG/
  EAG-Abwicklungsstelle, pvaustria.at). Hoechstpreis per Verordnung
  (2026/2027: 7,77 ct/kWh), Gebote darueber sind ungueltig.
- Die Auktionsliteratur (Haufe/Ehrhart 2018; Kreiss et al. 2017; Welisch/
  Kreiss 2019) beschreibt fuer Pay-as-Bid genau das in den Daten sichtbare
  Muster: Bieter "shaden" ihre Gebote knapp unter den erwarteten
  Grenzzuschlag; bei schwachem Wettbewerb liegen die Gebote nahe der
  Preisobergrenze, mit steigendem Wettbewerb sinken und verdichten sie sich.

Datenlage (data/ausschreibungen.yaml, 15 Runden 2022-2026):
- Je Runde nur AGGREGATE der bezuschlagten Gebote (min / mengengewichteter
  Mittelwert / max) plus Mengen. Einzelgebote werden nicht veroeffentlicht,
  daher scheiden KDE/GMM auf Rohgeboten aus - es bleibt die Anpassung
  parametrischer, auf [0, Preisobergrenze] BESCHRAENKTER Familien ueber
  Momenten-/Quantilbedingungen.
- "nicht bezuschlagte Leistung" ist unerfuellte ausgeschriebene Menge:
  Runden mit Hoechstzuschlag = Obergrenze und grosser Restmenge waren
  UNTERZEICHNET (alle gueltigen Gebote bezuschlagt -> die Aggregate
  beschreiben die volle Gebotsverteilung). Ab 07/2025 ist der
  Hoechstzuschlag < Obergrenze und die Restmenge ~0: UEBERZEICHNET; das
  eingereichte Gebotsvolumen wird von der OeMAG nicht veroeffentlicht,
  der Ueberzeichnungsgrad ist daher LATENT und wird aus dem Abstand
  Grenzzuschlag/Obergrenze rueckgeschaetzt.

Modellkern:
1. Je Runde wird eine beschraenkte Verteilungsfamilie ueber zwei robuste
   Bedingungen angepasst: (a) mengengewichteter Mittelwert der
   bezuschlagten Gebote, (b) beobachtetes Minimum als niedriges Quantil
   (EPS_MIN, dokumentierte Annahme). Fuer ueberzeichnete Runden ist (a)
   der trunkierte Erwartungswert unterhalb des Grenzzuschlags.
2. Familienvergleich (Beta, Kumaraswamy, trunkierte Normalverteilung)
   ueber die Rekonstruktion nicht gefitteter Groessen und Leave-one-out.
3. Wettbewerbs-Link: Lage (mittleres Gebot relativ zur Obergrenze, Logit)
   und Konzentration (log) werden linear auf ln(Wettbewerbsquote r =
   Gebotsmenge/ausgeschriebene Menge) regressiert - datengetrieben aus
   allen 15 Runden; Residuen liefern die Prognoseunsicherheit.
4. Prognose der naechsten Runde: Ziehungen von r (Lognormal um die
   Nutzererwartung) und Regressionsresiduen ergeben die praedik­tive
   Verteilung des GRENZZUSCHLAGSWERTS p_m. Als Price-Taker gilt:
   Zuschlagswahrscheinlichkeit(Gebot b) = P(p_m > b); das empfohlene
   Gebot fuer Zielwahrscheinlichkeit z ist das (1-z)-Quantil von p_m.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy import optimize, stats

# Annahme (dokumentiert): Das veroeffentlichte Minimum der Zuschlagswerte
# entspricht etwa dem 2%-Quantil aller Gebote (Groessenordnung 40-80
# Gebote je Runde; das guenstigste Gebot gewinnt immer). Die Ergebnisse
# reagieren nur schwach auf diese Annahme (Quantil im linken Auslaeufer).
EPS_MIN = 0.02

#: Toleranz (ct/kWh), innerhalb derer der Hoechstzuschlag als "an der
#: Obergrenze" gilt.
_CAP_TOLERANZ_CT = 0.02


# ---------------------------------------------------------------------------
# Datenmodell + Laden
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Ausschreibung:
    datum: date
    ausgeschrieben_mw: float
    bezuschlagt_mw: float
    zuschlag_min_ct: float
    zuschlag_mittel_ct: float
    zuschlag_max_ct: float
    preisobergrenze_ct: float

    @property
    def rest_mw(self) -> float:
        return self.ausgeschrieben_mw - self.bezuschlagt_mw

    @property
    def unterzeichnet(self) -> bool:
        """Unterzeichnet/gerade geraeumt: Der Hoechstzuschlag liegt (bis
        auf Rundung) an der Obergrenze - das Gebotsvolumen hat also nicht
        ausgereicht, um die Grenze zu druecken; alle gueltigen Gebote bis
        zur Obergrenze wurden bezuschlagt und die veroeffentlichten
        Aggregate beschreiben die VOLLE Gebotsverteilung. Der Grenzfall
        04/2025 (Hoechstzuschlag 8,97 bei Obergrenze 8,98, Rest 1,5 MW)
        faellt bewusst in dieses Regime: r = bezuschlagt/ausgeschrieben
        ~ 0,99 liefert einen Datenpunkt exakt an der Regimegrenze."""
        return self.zuschlag_max_ct >= self.preisobergrenze_ct - _CAP_TOLERANZ_CT

    @property
    def wettbewerbsquote_beobachtet(self) -> float | None:
        """r = Gebotsmenge / ausgeschriebene Menge. Nur fuer unterzeichnete
        Runden beobachtbar (dort Gebotsmenge = bezuschlagte Menge)."""
        if self.unterzeichnet:
            return self.bezuschlagt_mw / self.ausgeschrieben_mw
        return None


def load_ausschreibungen(path: str | Path) -> list[Ausschreibung]:
    daten = yaml.safe_load(Path(path).read_text())
    return [
        Ausschreibung(
            datum=date.fromisoformat(str(z["datum"])),
            ausgeschrieben_mw=float(z["ausgeschrieben_mw"]),
            bezuschlagt_mw=float(z["bezuschlagt_mw"]),
            zuschlag_min_ct=float(z["zuschlag_min_ct"]),
            zuschlag_mittel_ct=float(z["zuschlag_mittel_ct"]),
            zuschlag_max_ct=float(z["zuschlag_max_ct"]),
            preisobergrenze_ct=float(z["preisobergrenze_ct"]),
        )
        for z in daten["ausschreibungen"]
    ]


def ausschreibungen_dataframe(runden: list[Ausschreibung]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "datum": [r.datum for r in runden],
            "ausgeschrieben_mw": [r.ausgeschrieben_mw for r in runden],
            "bezuschlagt_mw": [r.bezuschlagt_mw for r in runden],
            "zuschlag_min_ct": [r.zuschlag_min_ct for r in runden],
            "zuschlag_mittel_ct": [r.zuschlag_mittel_ct for r in runden],
            "zuschlag_max_ct": [r.zuschlag_max_ct for r in runden],
            "preisobergrenze_ct": [r.preisobergrenze_ct for r in runden],
            "unterzeichnet": [r.unterzeichnet for r in runden],
        }
    )


# ---------------------------------------------------------------------------
# Verteilungsfamilien auf [0, Obergrenze]
# ---------------------------------------------------------------------------
# Einheitliche Parametrisierung ueber (mu_rel, kappa):
#   mu_rel  = Erwartungswert / Obergrenze  in (0, 1)   -> Lage
#   kappa   = Konzentration > 0                        -> Streuung (invers)
# Damit sind Familien direkt vergleichbar und der Wettbewerbs-Link ist
# familienunabhaengig formulierbar.


class _Familie:
    name: str = ""

    def dist(self, mu_rel: float, kappa: float, cap: float):
        raise NotImplementedError

    def mean(self, mu_rel: float, kappa: float, cap: float) -> float:
        return float(self.dist(mu_rel, kappa, cap).mean())

    def trunc_mean(self, mu_rel, kappa, cap, oben: float) -> float:
        """E[b | b <= oben] via numerischer Integration der Quantilfunktion
        (stabil fuer alle Familien)."""
        d = self.dist(mu_rel, kappa, cap)
        q_oben = float(d.cdf(oben))
        if q_oben <= 1e-9:
            return 0.0
        u = np.linspace(1e-6, q_oben - 1e-9, 400)
        return float(np.mean(d.ppf(u)))

    def ppf(self, mu_rel, kappa, cap, q: float) -> float:
        return float(self.dist(mu_rel, kappa, cap).ppf(q))

    def cdf(self, mu_rel, kappa, cap, x: float) -> float:
        return float(self.dist(mu_rel, kappa, cap).cdf(x))

    def pdf(self, mu_rel, kappa, cap, x: np.ndarray) -> np.ndarray:
        return self.dist(mu_rel, kappa, cap).pdf(x)


class FamilieBeta(_Familie):
    """Skalierte Beta auf [0, cap]: a = mu_rel*kappa, b = (1-mu_rel)*kappa.
    Natuerlich beschraenkt, beliebig schief; fuer mu_rel -> 1 und kappa
    moderat entsteht genau das erwartete Bild (Masse nahe der Obergrenze,
    langer linker Auslaeufer); Dichte an der Obergrenze -> 0 sobald
    (1-mu_rel)*kappa > 1."""

    name = "Beta"

    def dist(self, mu_rel, kappa, cap):
        return stats.beta(mu_rel * kappa, (1 - mu_rel) * kappa, loc=0, scale=cap)


class FamilieKumaraswamy(_Familie):
    """Kumaraswamy auf [0, cap] (F(x) = 1-(1-(x/cap)^a)^b): der Beta sehr
    aehnlich, mit analytischer Quantilfunktion. Interne Umrechnung von
    (mu_rel, kappa) auf (a, b) numerisch ueber die Momentbedingung."""

    name = "Kumaraswamy"

    @staticmethod
    def _mean_ab(a: float, b: float) -> float:
        from scipy.special import gammaln

        return float(b * np.exp(gammaln(1 + 1 / a) + gammaln(b) - gammaln(1 + 1 / a + b)))

    def _ab(self, mu_rel: float, kappa: float) -> tuple[float, float]:
        # kappa steuert a (Konzentration links), b wird auf den Mittelwert
        # kalibriert. mu_rel wird von Randwerten ferngehalten, damit die
        # Nullstellensuche stets ein Vorzeichenwechsel-Intervall hat.
        mu_rel = float(np.clip(mu_rel, 1e-4, 1 - 1e-4))
        a = max(kappa * mu_rel, 0.05)

        def f(log_b):
            return self._mean_ab(a, float(np.exp(log_b))) - mu_rel

        lo, hi = -8.0, 10.0
        if f(lo) <= 0:            # Mittelwert selbst bei b->0 unter Ziel
            return a, float(np.exp(lo))
        if f(hi) >= 0:
            return a, float(np.exp(hi))
        log_b = optimize.brentq(f, lo, hi)
        return a, float(np.exp(log_b))

    class _Dist:
        def __init__(self, a, b, cap):
            self.a, self.b, self.cap = a, b, cap

        def cdf(self, x):
            z = np.clip(np.asarray(x, dtype=float) / self.cap, 0, 1)
            return 1 - (1 - z**self.a) ** self.b

        def ppf(self, q):
            q = np.asarray(q, dtype=float)
            return self.cap * (1 - (1 - q) ** (1 / self.b)) ** (1 / self.a)

        def pdf(self, x):
            z = np.clip(np.asarray(x, dtype=float) / self.cap, 1e-12, 1 - 1e-12)
            return (
                self.a * self.b * z ** (self.a - 1)
                * (1 - z**self.a) ** (self.b - 1) / self.cap
            )

        def mean(self):
            u = np.linspace(1e-6, 1 - 1e-6, 800)
            return float(np.mean(self.ppf(u)))

    def dist(self, mu_rel, kappa, cap):
        a, b = self._ab(mu_rel, kappa)
        return self._Dist(a, b, cap)


class FamilieTruncNormal(_Familie):
    """Auf [0, cap] trunkierte Normalverteilung - bewusst als (symmetrische)
    Vergleichsbasis: sie kann die harte Obergrenze abbilden, aber keinen
    langen linken Auslaeufer bei gleichzeitig hoher Konzentration rechts."""

    name = "Trunkierte Normalverteilung"

    def dist(self, mu_rel, kappa, cap):
        mu = mu_rel * cap
        sigma = cap / max(kappa, 1e-6)
        a, b = (0 - mu) / sigma, (cap - mu) / sigma
        return stats.truncnorm(a, b, loc=mu, scale=sigma)


class FamilieInvGammaGespiegelt(_Familie):
    """An der Y-Achse gespiegelte und an die Preisobergrenze verschobene
    Inverse-Gamma-Verteilung: Gebot b = Obergrenze - Y mit
    Y ~ InvGamma(a, scale). Die Dichte faellt rechts zur Obergrenze sehr
    steil auf null (alle Ableitungen verschwinden dort) und laeuft nach
    links langsam aus (schwerer linker Auslaeufer) - exakt das fuer
    Pay-as-Bid unter Wettbewerb erwartete Bild: hoechste Dichte knapp
    unter dem erwarteten Grenzzuschlag. Parametrisierung: kappa =
    Formparameter a (Konzentration), Lage ueber E[b] = mu_rel * cap.
    Einschraenkung: Masse DIREKT an der Obergrenze (Gebote am Cap, wie in
    unterzeichneten Runden beobachtet) kann diese Familie prinzipbedingt
    nicht abbilden."""

    name = "Gespiegelte Inverse Gamma"

    class _Dist:
        def __init__(self, a, scale, cap):
            self.ig = stats.invgamma(a, scale=scale)
            self.cap = cap

        def cdf(self, x):
            return self.ig.sf(self.cap - np.asarray(x, dtype=float))

        def ppf(self, q):
            # Gebote sind physikalisch >= 0: extrem schwere linke
            # Auslaeufer werden am Nullpunkt gekappt.
            return np.maximum(self.cap - self.ig.isf(np.asarray(q, dtype=float)), 0.0)

        def pdf(self, x):
            return self.ig.pdf(self.cap - np.asarray(x, dtype=float))

        def mean(self):
            return max(self.cap - float(self.ig.mean()), 0.0)

    def dist(self, mu_rel, kappa, cap):
        a = max(float(kappa), 1.1)          # Erwartungswert existiert fuer a > 1
        scale = cap * (1 - float(np.clip(mu_rel, 1e-4, 1 - 1e-4))) * (a - 1)
        return self._Dist(a, max(scale, 1e-9), cap)


FAMILIEN: dict[str, _Familie] = {
    f.name: f
    for f in (
        FamilieBeta(),
        FamilieKumaraswamy(),
        FamilieTruncNormal(),
        FamilieInvGammaGespiegelt(),
    )
}


# ---------------------------------------------------------------------------
# Fit je Ausschreibung
# ---------------------------------------------------------------------------


@dataclass
class RundenFit:
    ausschreibung: Ausschreibung
    familie: str
    mu_rel: float
    kappa: float
    wettbewerbsquote: float          # beobachtet (unterzeichnet) oder latent
    wettbewerbsquote_latent: bool
    fit_residuum: float              # Restfehler der beiden Bedingungen


def fit_runde(runde: Ausschreibung, familie: _Familie) -> RundenFit:
    """Passt (mu_rel, kappa) an zwei Bedingungen an:
    (a) mengengewichteter Mittelwert der bezuschlagten Gebote,
    (b) Minimum der Zuschlagswerte als EPS_MIN-Quantil ALLER Gebote
        (das guenstigste Gebot gewinnt immer).
    Ueberzeichnete Runden nutzen fuer (a) den unterhalb des Grenzzuschlags
    trunkierten Erwartungswert; die Wettbewerbsquote ergibt sich dort als
    latenter Wert r = 1 / F(Grenzzuschlag)."""
    cap = runde.preisobergrenze_ct

    def residuen(theta):
        mu_rel = 1 / (1 + np.exp(-theta[0]))          # Logit-Ruecktransform
        kappa = float(np.exp(theta[1]))
        if runde.unterzeichnet:
            mean_soll = familie.mean(mu_rel, kappa, cap)
        else:
            mean_soll = familie.trunc_mean(mu_rel, kappa, cap, runde.zuschlag_max_ct)
        r1 = mean_soll - runde.zuschlag_mittel_ct
        r2 = familie.ppf(mu_rel, kappa, cap, EPS_MIN) - runde.zuschlag_min_ct
        return [r1, r2]

    start = np.array([np.log(0.85 / 0.15), np.log(8.0)])
    loesung = optimize.least_squares(
        residuen, start, method="trf", max_nfev=400,
        bounds=([-8.0, np.log(1.05)], [8.0, np.log(800.0)]),
    )
    mu_rel = float(1 / (1 + np.exp(-loesung.x[0])))
    kappa = float(np.exp(loesung.x[1]))

    if runde.unterzeichnet:
        r = runde.bezuschlagt_mw / runde.ausgeschrieben_mw
        latent = False
    else:
        q_grenz = familie.cdf(mu_rel, kappa, cap, runde.zuschlag_max_ct)
        r = 1.0 / max(q_grenz, 1e-6)
        latent = True

    return RundenFit(
        ausschreibung=runde, familie=familie.name, mu_rel=mu_rel, kappa=kappa,
        wettbewerbsquote=float(r), wettbewerbsquote_latent=latent,
        fit_residuum=float(np.sqrt(np.mean(np.array(residuen(loesung.x)) ** 2))),
    )


# ---------------------------------------------------------------------------
# Wettbewerbs-Link + kalibriertes Modell
# ---------------------------------------------------------------------------


def _logit(p):
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


@dataclass
class AuktionsModell:
    """Kalibriertes Gesamtmodell: je Runde gefittete Verteilungen plus der
    datengetriebene Link von Lage/Konzentration auf die Wettbewerbsquote."""

    familie_name: str
    fits: list[RundenFit]
    koef_lage: tuple[float, float]        # logit(mu_rel) = a + b*ln(r)
    koef_konzentration: tuple[float, float]  # ln(kappa)   = c + d*ln(r)
    residuen_lage: np.ndarray
    residuen_konzentration: np.ndarray
    # Lokales Trendmodell fuer die Prognose (Verankerung an der letzten
    # Runde): mittlere Rundenaenderung der transformierten Parameter in
    # den Wettbewerbsrunden (Bieterlernen) und deren Streuung.
    drift_lage: float = 0.0
    drift_konzentration: float = 0.0
    sd_lage: float = 0.35
    sd_konzentration: float = 0.35

    @property
    def familie(self) -> _Familie:
        return FAMILIEN[self.familie_name]

    @property
    def letzte_runde(self) -> RundenFit:
        return max(self.fits, key=lambda f: f.ausschreibung.datum)

    def parameter_bei(self, r: float, res_lage: float = 0.0,
                      res_kappa: float = 0.0) -> tuple[float, float]:
        x = np.log(max(r, 1e-3))
        mu_rel = 1 / (1 + np.exp(-(self.koef_lage[0] + self.koef_lage[1] * x + res_lage)))
        kappa = float(np.exp(self.koef_konzentration[0]
                             + self.koef_konzentration[1] * x + res_kappa))
        return float(mu_rel), max(kappa, 1.05)


def kalibriere_modell(
    runden: list[Ausschreibung], familie_name: str = "Beta"
) -> AuktionsModell:
    familie = FAMILIEN[familie_name]
    fits = [fit_runde(r, familie) for r in runden]

    x = np.log([f.wettbewerbsquote for f in fits])
    y_lage = _logit([f.mu_rel for f in fits])
    y_kappa = np.log([f.kappa for f in fits])
    b_l, a_l = np.polyfit(x, y_lage, 1)
    b_k, a_k = np.polyfit(x, y_kappa, 1)

    # Drift/Streuung aus den aufeinanderfolgenden Wettbewerbsrunden
    # (relevantes Regime fuer die Prognose). Fallback bei zu wenigen
    # Runden: kein Drift, konservative Streuung.
    wett = sorted(
        (f for f in fits if not f.ausschreibung.unterzeichnet),
        key=lambda f: f.ausschreibung.datum,
    )
    d_lage = np.diff(_logit([f.mu_rel for f in wett])) if len(wett) >= 2 else np.array([])
    d_konz = np.diff(np.log([f.kappa for f in wett])) if len(wett) >= 2 else np.array([])

    def _drift_sd(deltas: np.ndarray) -> tuple[float, float]:
        """Sparsamste belastbare Annahme bei erst drei beobachteten
        Rundenaenderungen (davon ein Regime-Eintrittssprung 07->10/2025):
        RANDOM WALK - Drift 0, d.h. die zentrale Prognosewelt entspricht
        exakt der letzten Runde (nur um Wettbewerbsquote und Obergrenze
        angepasst). Die STREUUNG der beobachteten Rundenaenderungen geht
        als Prognoseunsicherheit ein; nach oben begrenzt, da die
        Rundenschwankung der Fit-Parameter auch Kalibrierrauschen
        enthaelt (die Konzentration kappa ist aus Aggregaten nur grob
        identifiziert)."""
        if len(deltas) == 0:
            return 0.0, 0.35
        sd = np.std(deltas, ddof=1) if len(deltas) > 1 else 0.35
        return 0.0, float(np.clip(sd, 0.15, 0.8))

    drift_l, sd_l = _drift_sd(d_lage)
    drift_k, sd_k = _drift_sd(d_konz)

    return AuktionsModell(
        familie_name=familie_name,
        fits=fits,
        koef_lage=(float(a_l), float(b_l)),
        koef_konzentration=(float(a_k), float(b_k)),
        residuen_lage=y_lage - (a_l + b_l * x),
        residuen_konzentration=y_kappa - (a_k + b_k * x),
        drift_lage=drift_l,
        drift_konzentration=drift_k,
        sd_lage=sd_l,
        sd_konzentration=sd_k,
    )


# ---------------------------------------------------------------------------
# Familienvergleich + Validierung (Leave-one-out)
# ---------------------------------------------------------------------------


def vergleiche_familien(runden: list[Ausschreibung]) -> pd.DataFrame:
    """Bewertet jede Familie über zwei Kriterien:
    1. rekonstruktion_max: Bei unterzeichneten Runden ist der hoechste
       Zuschlagswert = Obergrenze, d.h. die Familie muss dort rechts noch
       spuerbare Masse tragen (P(b > 0.99*cap) >= 1/50 Geboten). Gemessen
       wird der Anteil verletzter Runden.
    2. loo_rmse_pm: Leave-one-out ueber die ueberzeichneten Runden -
       Prognosefehler des Grenzzuschlagswerts bei gegebener Wettbewerbs-
       quote (RMSE in ct/kWh).
    Zusaetzlich: mittleres Fit-Residuum der beiden Kalibrierbedingungen."""
    zeilen = []
    ueberzeichnet = [r for r in runden if not r.unterzeichnet]
    for name in FAMILIEN:
        modell = kalibriere_modell(runden, name)
        fit_rmse = float(np.mean([f.fit_residuum for f in modell.fits]))

        verletzt = 0
        unterz = [f for f in modell.fits if f.ausschreibung.unterzeichnet]
        for f in unterz:
            cap = f.ausschreibung.preisobergrenze_ct
            masse_oben = 1 - FAMILIEN[name].cdf(f.mu_rel, f.kappa, cap, 0.99 * cap)
            if masse_oben < 1 / 50:
                verletzt += 1

        fehler = []
        for raus in ueberzeichnet:
            rest = [r for r in runden if r is not raus]
            m = kalibriere_modell(rest, name)
            r_latent = fit_runde(raus, FAMILIEN[name]).wettbewerbsquote
            mu_rel, kappa = m.parameter_bei(r_latent)
            pm_prognose = FAMILIEN[name].ppf(
                mu_rel, kappa, raus.preisobergrenze_ct, min(1.0, 1 / r_latent)
            )
            fehler.append(pm_prognose - raus.zuschlag_max_ct)
        zeilen.append(
            {
                "familie": name,
                "fit_rmse_ct": round(fit_rmse, 4),
                "cap_masse_verletzt": f"{verletzt}/{len(unterz)}",
                "loo_rmse_pm_ct": round(float(np.sqrt(np.mean(np.square(fehler)))), 3),
            }
        )
    return pd.DataFrame(zeilen)


def validiere_loo(runden: list[Ausschreibung], familie_name: str) -> pd.DataFrame:
    """Leave-one-out je ueberzeichneter Runde: Prognose von Grenzzuschlag,
    Mittelwert und Minimum aus den uebrigen Runden (bei gegebener
    Wettbewerbsquote) - plus naive Basislinie 'bisheriger Ansatz'
    (Fortschreibung des letzten beobachteten Hoechstzuschlags)."""
    familie = FAMILIEN[familie_name]
    zeilen = []
    ueberzeichnet = [r for r in runden if not r.unterzeichnet]
    sortiert = sorted(runden, key=lambda r: r.datum)
    for raus in ueberzeichnet:
        rest = [r for r in runden if r is not raus]
        modell = kalibriere_modell(rest, familie_name)
        r_latent = fit_runde(raus, familie).wettbewerbsquote
        mu_rel, kappa = modell.parameter_bei(r_latent)
        cap = raus.preisobergrenze_ct
        q = min(1.0, 1 / r_latent)
        vorher = [r for r in sortiert if r.datum < raus.datum]
        naiv = vorher[-1].zuschlag_max_ct if vorher else np.nan
        zeilen.append(
            {
                "datum": raus.datum,
                "grenzzuschlag_ist_ct": raus.zuschlag_max_ct,
                "grenzzuschlag_modell_ct": round(familie.ppf(mu_rel, kappa, cap, q), 2),
                "grenzzuschlag_naiv_ct": naiv,
                "mittel_ist_ct": raus.zuschlag_mittel_ct,
                "mittel_modell_ct": round(
                    familie.trunc_mean(mu_rel, kappa, cap,
                                       familie.ppf(mu_rel, kappa, cap, q)), 2),
                "min_ist_ct": raus.zuschlag_min_ct,
                "min_modell_ct": round(familie.ppf(mu_rel, kappa, cap, EPS_MIN), 2),
            }
        )
    return pd.DataFrame(zeilen)


def differenzen_extrapolation(
    werte: list[float],
    ordnung: int = 2,
    lambdas: tuple[float, ...] | None = None,
) -> float:
    """Allgemeine Mehrfach-Differenzenextrapolation: beruecksichtigt
    neben dem aktuellen Trend auch dessen zeitliche Veraenderung
    (Beschleunigung) und optional hoehere Differenzen.

    Rekursive Differenzen: Delta^(k)_t = Delta^(k-1)_t - Delta^(k-1)_{t-1}.
    Extrapolation:
      1. Hoechste Differenz bleibt konstant:  D^(m) = Delta^(m)_t
      2. Niedrigere rekursiv:  D^(k) = Delta^(k)_t + lambda_k * D^(k+1)
      3. Naechster Wert:       x_{t+1} = x_t + D^(1)

    lambda_k in [0, 1] daempft die hoeheren Ableitungen (Standard 1;
    lambda -> 0 naehert sich der linearen Fortschreibung der jeweils
    niedrigeren Ordnung). Die effektive Ordnung wird durch die
    verfuegbaren Stuetzstellen begrenzt (Ordnung m braucht m+1 Werte);
    mit nur einer Stuetzstelle bleibt der letzte Wert stehen (Random
    Walk)."""
    n = len(werte)
    if n < 2:
        return float(werte[-1])
    m = int(max(1, min(ordnung, n - 1)))
    if lambdas is None:
        lambdas = tuple(1.0 for _ in range(max(m - 1, 0)))

    x = np.asarray(werte, dtype=float)
    letzte_diff = {k: float(np.diff(x, n=k)[-1]) for k in range(1, m + 1)}

    d_hat = letzte_diff[m]                       # Schritt 1+2
    for k in range(m - 1, 0, -1):                # Schritt 3
        lam = float(np.clip(lambdas[k - 1] if k - 1 < len(lambdas) else 1.0,
                            0.0, 1.0))
        d_hat = letzte_diff[k] + lam * d_hat
    return float(x[-1] + d_hat)                  # Schritt 4+5


def _fit_an_max_und_mittel(familie: _Familie, cap: float, max_ct: float,
                           mittel_ct: float, min_ct: float
                           ) -> tuple[float, float]:
    """Baut die Verteilung aus den Punktprognosen - methodisch identisch
    zum Fit der historischen Runden: (a) E[b | b <= max] = mittel
    (Momentum-Prognose), (b) Minimum als EPS_MIN-Quantil (Random Walk
    vom letzten beobachteten Minimum; fuer das Minimum ist keine
    Momentum-Fortschreibung spezifiziert). Die Wettbewerbsquote ist
    dann IMPLIZIERT: r = 1 / F(max)."""

    def residuen(theta):
        mu_rel = 1 / (1 + np.exp(-theta[0]))
        kappa = float(np.exp(theta[1]))
        # Der prognostizierte Mittelwert ist die vom Verfahren
        # vorgegebene Groesse und wird stark gewichtet (faktisch exakt
        # getroffen); das Minimum ist nur weicher Anker fuer den linken
        # Auslaeufer. Impliziert die Prognose eine Verdichtung (Ø
        # naehert sich dem Grenzzuschlag), steigt das Minimum
        # konsistent mit.
        r1 = (familie.trunc_mean(mu_rel, kappa, cap, max_ct) - mittel_ct) * 8.0
        r2 = familie.ppf(mu_rel, kappa, cap, EPS_MIN) - min_ct
        return [r1, r2]

    start = np.array([np.log(0.85 / 0.15), np.log(8.0)])
    loesung = optimize.least_squares(
        residuen, start, method="trf", max_nfev=400,
        bounds=([-8.0, np.log(1.05)], [8.0, np.log(800.0)]),
    )
    mu_rel = float(1 / (1 + np.exp(-loesung.x[0])))
    kappa = float(np.exp(loesung.x[1]))
    return mu_rel, kappa


def validiere_einschritt(runden: list[Ausschreibung], familie_name: str,
                          ordnung: int = 2,
                          lambdas: tuple[float, ...] | None = None
                          ) -> pd.DataFrame:
    """Rollierender Ein-Schritt-Backtest der Differenzenextrapolation
    ueber die Wettbewerbsrunden, im Vergleich zur naiven Fortschreibung
    des letzten Hoechstzuschlags. Die effektive Ordnung je Runde
    (begrenzt durch die verfuegbaren Stuetzstellen) wird in der Spalte
    'methode' ausgewiesen."""
    sortiert = sorted(runden, key=lambda r: r.datum)
    zeilen = []
    for i, ziel in enumerate(sortiert):
        if ziel.unterzeichnet or i == 0:
            continue
        wett_vorher = [r for r in sortiert[:i] if not r.unterzeichnet]
        if not wett_vorher:
            continue
        maxes = [r.zuschlag_max_ct for r in wett_vorher]
        mittels = [r.zuschlag_mittel_ct for r in wett_vorher]
        eff_ordnung = max(1, min(ordnung, len(maxes) - 1)) if len(maxes) > 1 else 0
        zeilen.append({
            "datum": ziel.datum,
            "methode": (f"Differenzen (Ordnung {eff_ordnung})" if eff_ordnung >= 1
                        else "Random Walk (eine Stuetzstelle)"),
            "grenzzuschlag_ist_ct": ziel.zuschlag_max_ct,
            "grenzzuschlag_modell_ct": round(
                differenzen_extrapolation(maxes, ordnung, lambdas), 2),
            "grenzzuschlag_naiv_ct": wett_vorher[-1].zuschlag_max_ct,
            "mittel_ist_ct": ziel.zuschlag_mittel_ct,
            "mittel_modell_ct": round(
                differenzen_extrapolation(mittels, ordnung, lambdas), 2),
            "min_ist_ct": ziel.zuschlag_min_ct,
        })
    return pd.DataFrame(zeilen)


# ---------------------------------------------------------------------------
# Prognose (Price-Taker): zwei Modi
# ---------------------------------------------------------------------------


@dataclass
class GebotsPrognose:
    """Verteilung der Zuschlagswerte fuer die Gebotsentscheidung - in
    einem von zwei Modi:

    modus='letzte':   Die letzte Ausschreibung gilt als GESETZT. Die
                      gefittete Zuschlagswert-Verteilung der letzten
                      Runde wird unveraendert verwendet; die gewaehlte
                      Wahrscheinlichkeit z (Risikoneigung) liefert den
                      Wert am (1-z)-Quantil der Zuschlagswerte.
    modus='prognose': Differenzenextrapolation der naechsten Runde
                      (auf Grenzzuschlag und Mittelwert getrennt);
                      daraus wird die neue Verteilung
                      gebaut. z ist hier die Zuschlagswahrscheinlichkeit
                      P(Grenzzuschlag > Gebot) ueber die
                      p_m-Unsicherheit (Streuung der historischen
                      Rundenaenderungen, an der Obergrenze trunkiert).
    """

    modus: str
    familie_name: str
    preisobergrenze_ct: float
    wettbewerbsquote: float
    mu_rel: float
    kappa: float
    grenzzuschlag_zentral_ct: float     # p_m der zentralen Welt
    mittel_prognose_ct: float
    pm_sample: np.ndarray
    dichte_x: np.ndarray
    dichte_y: np.ndarray                # Dichte ALLER Gebote
    dichte_zuschlag_y: np.ndarray       # Dichte der ZUSCHLAGSWERTE
    gebot_mittel_ct: float
    gebot_median_ct: float
    gebot_quantile: dict[int, float] = field(default_factory=dict)

    @property
    def _q_c(self) -> float:
        return min(1.0, 1.0 / max(self.wettbewerbsquote, 1.0 + 1e-6))

    @property
    def _dist(self):
        return FAMILIEN[self.familie_name].dist(
            self.mu_rel, self.kappa, self.preisobergrenze_ct
        )

    def zuschlagswahrscheinlichkeit(self, gebot_ct: float) -> float:
        """modus='prognose': P(Grenzzuschlag > Gebot).
        modus='letzte': Anteil der Zuschlagswerte der letzten Runde
        oberhalb des Gebots (Quantilslage in der gesetzten Runde)."""
        if self.modus == "prognose":
            return float(np.mean(self.pm_sample > gebot_ct))
        f = float(self._dist.cdf(gebot_ct))
        return float(np.clip((self._q_c - f) / self._q_c, 0.0, 1.0))

    def empfohlenes_gebot(self, zielwahrscheinlichkeit: float) -> float:
        """Wert zur gewaehlten Wahrscheinlichkeit/Risikoneigung z:
        modus='prognose': (1-z)-Quantil des Grenzzuschlags.
        modus='letzte':   (1-z)-Quantil der Zuschlagswerte der Runde."""
        z = float(np.clip(zielwahrscheinlichkeit, 0.01, 0.999))
        if self.modus == "prognose":
            return float(np.quantile(self.pm_sample, 1 - z))
        return float(self._dist.ppf((1 - z) * self._q_c))

    def gebots_ziehungen(self, n: int, seed: int = 42) -> np.ndarray:
        """Zufaellige ZUSCHLAGSWERTE fuer die Monte-Carlo-Simulation:
        modus='letzte': Ziehung aus der gesetzten Verteilung der letzten
        Runde. modus='prognose': je Welt ein Grenzzuschlag aus
        pm_sample; die zentrale Verteilung wird parallel dorthin
        verschoben und darunter gezogen (Formerhalt)."""
        rng = np.random.default_rng(seed)
        d = self._dist
        u = rng.uniform(1e-6, self._q_c, size=n)
        basis = np.asarray(d.ppf(u), dtype=float)
        if self.modus == "letzte":
            return np.clip(basis, 0.0, None)
        idx = rng.integers(0, len(self.pm_sample), size=n)
        verschoben = basis + (self.pm_sample[idx] - self.grenzzuschlag_zentral_ct)
        return np.clip(verschoben, 0.0, self.preisobergrenze_ct)


def _baue_prognose(modus: str, familie_name: str, cap: float, r: float,
                   mu_rel: float, kappa: float, pm_zentral: float,
                   pm_sample: np.ndarray) -> GebotsPrognose:
    familie = FAMILIEN[familie_name]
    d = familie.dist(mu_rel, kappa, cap)
    q_c = min(1.0, 1.0 / max(r, 1.0 + 1e-6))
    x = np.linspace(0.01 * cap, cap * (1 - 1e-4), 500)
    dichte_alle = np.asarray(d.pdf(x), dtype=float)
    dichte_zuschlag = dichte_alle * (x <= pm_zentral) / max(q_c, 1e-6)
    quantile = {q: float(d.ppf(q / 100 * q_c)) for q in (5, 25, 50, 75, 95)}
    return GebotsPrognose(
        modus=modus,
        familie_name=familie_name,
        preisobergrenze_ct=cap,
        wettbewerbsquote=r,
        mu_rel=mu_rel,
        kappa=kappa,
        grenzzuschlag_zentral_ct=pm_zentral,
        mittel_prognose_ct=familie.trunc_mean(mu_rel, kappa, cap, pm_zentral),
        pm_sample=pm_sample,
        dichte_x=x,
        dichte_y=dichte_alle,
        dichte_zuschlag_y=dichte_zuschlag,
        gebot_mittel_ct=familie.trunc_mean(mu_rel, kappa, cap, pm_zentral),
        gebot_median_ct=quantile[50],
        gebot_quantile=quantile,
    )


def prognose_letzte_runde(modell: AuktionsModell) -> GebotsPrognose:
    """Modus 1: Die letzte Ausschreibung gilt als gesetzt - Verteilung,
    Grenzzuschlag und Wettbewerbsquote der letzten Runde unveraendert."""
    anker = modell.letzte_runde
    a = anker.ausschreibung
    return _baue_prognose(
        modus="letzte",
        familie_name=modell.familie_name,
        cap=a.preisobergrenze_ct,
        r=anker.wettbewerbsquote,
        mu_rel=anker.mu_rel,
        kappa=anker.kappa,
        pm_zentral=a.zuschlag_max_ct,
        pm_sample=np.array([a.zuschlag_max_ct]),
    )


def prognose_naechste_runde(
    modell: AuktionsModell,
    preisobergrenze_ct: float,
    sigma_pm_ct: float | None = None,
    ordnung: int = 2,
    lambdas: tuple[float, ...] | None = None,
    n_ziehungen: int = 4000,
    seed: int = 42,
) -> GebotsPrognose:
    """Modus 2: Momentum-Prognose der naechsten Runde.

    1. Punktprognosen fuer Grenzzuschlag und mengengewichteten
       Mittelwert per Differenzenextrapolation (differenzen_
       extrapolation) ueber die Wettbewerbsrunden - Ordnung und
       Daempfungsparameter lambda konfigurierbar. Das Minimum wird
       unveraendert fortgeschrieben (Random Walk; die Historie zeigt
       dafuer keine stabile Dynamik). Danach Projektion auf den
       zulaessigen Bereich: Minimum <= Mittel <= Grenzzuschlag <
       Preisobergrenze.
    2. Daraus wird die neue Zuschlagswert-Verteilung gebaut - identisch
       zur Kalibrierung der historischen Runden: E[b | b <= max] =
       mittel, Minimum (Random Walk) als EPS_MIN-Quantil; abgeschnitten
       wird am prognostizierten Grenzzuschlag. Die Wettbewerbsquote ist
       impliziert (r = 1 / F(max)) und wird ausgewiesen.
    3. Unsicherheit des Grenzzuschlags: Normalverteilung um die
       Punktprognose mit der Streuung der historischen
       Rundenaenderungen (sigma_pm_ct, ueberschreibbar), an der
       Obergrenze und bei 0,5 ct trunkiert - der Grenzzuschlag faellt
       nie mit der Obergrenze zusammen.
    """
    rng = np.random.default_rng(seed)
    cap = preisobergrenze_ct
    wett = sorted((f.ausschreibung for f in modell.fits
                   if not f.ausschreibung.unterzeichnet),
                  key=lambda a: a.datum)
    maxes = [a.zuschlag_max_ct for a in wett]
    mittels = [a.zuschlag_mittel_ct for a in wett]

    # Punktprognosen + Projektion auf Min <= Mittel <= Max < Obergrenze
    max_hat = float(np.clip(
        differenzen_extrapolation(maxes, ordnung, lambdas), 0.5, cap - 0.02
    ))
    mittel_hat = float(np.clip(
        differenzen_extrapolation(mittels, ordnung, lambdas),
        0.3, max_hat - 0.05,
    ))

    if sigma_pm_ct is None:
        deltas = np.diff(maxes)
        sigma_pm_ct = float(np.clip(
            np.std(deltas, ddof=1) if len(deltas) > 1 else 0.5, 0.15, 0.8
        ))

    familie = FAMILIEN[modell.familie_name]
    min_anker = float(wett[-1].zuschlag_min_ct) if wett else 0.5 * mittel_hat
    min_anker = min(min_anker, mittel_hat - 0.05)
    mu_rel, kappa = _fit_an_max_und_mittel(
        familie, cap, max_hat, mittel_hat, min_anker
    )
    r_impliziert = 1.0 / max(familie.cdf(mu_rel, kappa, cap, max_hat), 1e-6)

    lo = (0.5 - max_hat) / sigma_pm_ct
    hi = (cap - 1e-6 - max_hat) / sigma_pm_ct
    pm_sample = stats.truncnorm.rvs(lo, hi, loc=max_hat, scale=sigma_pm_ct,
                                    size=n_ziehungen, random_state=rng)

    return _baue_prognose(
        modus="prognose",
        familie_name=modell.familie_name,
        cap=cap,
        r=r_impliziert,
        mu_rel=mu_rel,
        kappa=kappa,
        pm_zentral=max_hat,
        pm_sample=pm_sample,
    )
