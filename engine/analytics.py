"""
Erweiterte Analytik auf Basis der Bewertungs-Pipeline:

- Tornado-Analyse: Einzelvariation der wichtigsten Werttreiber und deren
  Wirkung auf die EK-Rendite (klassisches Projektfinanzierungs-Chart).
- IRR-Heatmap: EK-Rendite ueber ein 2D-Raster zweier Treiber.
- Monte-Carlo-Simulation: gleichzeitige, zufaellige Variation mehrerer
  Treiber -> Verteilung von IRR/NPV und Bandbreite des kumulierten
  Equity-Cashflows (P10/P50/P90).
- Gebotsassistent: minimaler EAG-Zuschlagswert (anzulegender Wert), der
  eine Ziel-EK-Rendite gerade noch erreicht - Untergrenze fuer ein Gebot
  in der EAG-Auktion.
- LCOE: Stromgestehungskosten (diskontierte Vollkosten je diskontierter
  kWh).
- Szenarienvergleich: identisches Projekt ueber alle hinterlegten
  Marktpreisszenarien.

Alle Funktionen arbeiten ueber run_valuation_from_assumptions() auf
Kopien des aufgeloesten Parametersatzes (EffectiveAssumptions) - sie
kennen die internen Berechnungsmodule nicht und bleiben bei Aenderungen
an der Cashflow-Engine automatisch konsistent.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .kpis import _xnpv
from .models import EffectiveAssumptions, GlobalAssumptions, PVProject
from .pipeline import (
    resolve_assumptions,
    run_valuation_from_assumptions,
)

# ---------------------------------------------------------------------------
# Gemeinsame Treiber-Mutationen
# ---------------------------------------------------------------------------


def _skaliere_kurve(kurve: dict[int, float], faktor: float) -> dict[int, float]:
    return {jahr: wert * faktor for jahr, wert in kurve.items()}


def _mutiere(ea: EffectiveAssumptions, treiber: str, faktor: float) -> EffectiveAssumptions:
    """Wendet einen multiplikativen Faktor auf einen benannten Werttreiber
    an und liefert eine neue EffectiveAssumptions-Kopie."""
    if treiber == "eag_zuschlag":
        return ea.model_copy(
            update={
                "eag_zuschlagswert_effektiv_ct_kwh": ea.eag_zuschlagswert_effektiv_ct_kwh
                * faktor
            }
        )
    if treiber == "marktwert":
        return ea.model_copy(
            update={
                "marktwert_solar_ct_kwh_je_kalenderjahr": _skaliere_kurve(
                    ea.marktwert_solar_ct_kwh_je_kalenderjahr, faktor
                )
            }
        )
    if treiber == "produktion":
        return ea.model_copy(
            update={
                "vollbenutzungsstunden_kwh_kwp": ea.vollbenutzungsstunden_kwh_kwp
                * faktor
            }
        )
    if treiber == "capex":
        return ea.model_copy(update={"capex_total_eur": ea.capex_total_eur * faktor})
    if treiber == "opex":
        return ea.model_copy(
            update={
                "opex_items": [
                    item.model_copy(
                        update={"basiswert_eur_kwp": item.basiswert_eur_kwp * faktor}
                    )
                    for item in ea.opex_items
                ]
            }
        )
    if treiber == "fk_zins":
        return ea.model_copy(
            update={"fremdkapitalzins_pct": ea.fremdkapitalzins_pct * faktor}
        )
    if treiber == "negative_stunden":
        return ea.model_copy(
            update={
                "anteil_negativer_stunden_pct_je_kalenderjahr": _skaliere_kurve(
                    ea.anteil_negativer_stunden_pct_je_kalenderjahr, faktor
                )
            }
        )
    raise ValueError(f"Unbekannter Treiber: {treiber}")


def _irr_fuer(ea: EffectiveAssumptions) -> float | None:
    result = run_valuation_from_assumptions(ea, ea.source_project_id, compute_npv_curve=False)
    return result.kpis.equity_irr


# ---------------------------------------------------------------------------
# Tornado-Analyse
# ---------------------------------------------------------------------------

#: (Treiber-Schluessel, Anzeigename). Reihenfolge ist unerheblich - das
#: Chart sortiert nach Wirkungsspanne.
TORNADO_TREIBER: list[tuple[str, str]] = [
    ("produktion", "Spezifischer Ertrag"),
    ("marktwert", "Marktwert-Niveau"),
    ("eag_zuschlag", "EAG-Zuschlagswert"),
    ("capex", "Investitionskosten"),
    ("opex", "Betriebskosten"),
    ("fk_zins", "Fremdkapitalzins"),
    ("negative_stunden", "Erzeugungsmenge neg. Stunden"),
]


def run_tornado(
    project: PVProject,
    global_assumptions: GlobalAssumptions,
    delta_pct: float = 0.10,
) -> pd.DataFrame:
    """Einzelvariation jedes Treibers um ±delta_pct; Ergebnis je Treiber:
    IRR bei -delta, Basis-IRR, IRR bei +delta sowie die Gesamtspanne."""
    ea = resolve_assumptions(project, global_assumptions)
    irr_basis = _irr_fuer(ea)

    rows = []
    for schluessel, name in TORNADO_TREIBER:
        irr_runter = _irr_fuer(_mutiere(ea, schluessel, 1 - delta_pct))
        irr_rauf = _irr_fuer(_mutiere(ea, schluessel, 1 + delta_pct))
        spanne = (
            abs((irr_rauf or 0) - (irr_runter or 0))
            if irr_rauf is not None or irr_runter is not None
            else 0.0
        )
        rows.append(
            {
                "treiber": schluessel,
                "name": name,
                "irr_runter": irr_runter,
                "irr_basis": irr_basis,
                "irr_rauf": irr_rauf,
                "spanne": spanne,
            }
        )

    df = pd.DataFrame(rows).sort_values("spanne", ascending=True)
    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# IRR-Heatmap (2D-Raster)
# ---------------------------------------------------------------------------

#: Fuer die Heatmap waehlbare Achsen: Schluessel -> (Anzeigename, ±Spanne).
HEATMAP_ACHSEN: dict[str, tuple[str, float]] = {
    "eag_zuschlag": ("EAG-Zuschlagswert", 0.20),
    "capex": ("Investitionskosten", 0.20),
    "produktion": ("Spezifischer Ertrag", 0.10),
    "marktwert": ("Marktwert-Niveau", 0.25),
    "opex": ("Betriebskosten", 0.25),
    "fk_zins": ("Fremdkapitalzins", 0.30),
}


def run_irr_heatmap(
    project: PVProject,
    global_assumptions: GlobalAssumptions,
    achse_x: str = "eag_zuschlag",
    achse_y: str = "capex",
    stufen: int = 7,
) -> pd.DataFrame:
    """EK-Rendite ueber ein stufen×stufen-Raster zweier Treiber (jeweils
    ±Spanne aus HEATMAP_ACHSEN, multiplikativ um die Basis). Rueckgabe im
    Langformat: faktor_x, faktor_y, equity_irr."""
    if achse_x == achse_y:
        raise ValueError("Heatmap-Achsen muessen verschieden sein")
    ea = resolve_assumptions(project, global_assumptions)
    _, spanne_x = HEATMAP_ACHSEN[achse_x]
    _, spanne_y = HEATMAP_ACHSEN[achse_y]

    faktoren_x = np.linspace(1 - spanne_x, 1 + spanne_x, stufen)
    faktoren_y = np.linspace(1 - spanne_y, 1 + spanne_y, stufen)

    rows = []
    for fy in faktoren_y:
        ea_y = _mutiere(ea, achse_y, float(fy))
        for fx in faktoren_x:
            irr = _irr_fuer(_mutiere(ea_y, achse_x, float(fx)))
            rows.append(
                {"faktor_x": float(fx), "faktor_y": float(fy), "equity_irr": irr}
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Monte-Carlo-Simulation
# ---------------------------------------------------------------------------


@dataclass
class MonteCarloResult:
    n_laeufe: int
    irr: np.ndarray          # EK-Rendite je Lauf (NaN = nicht berechenbar)
    npv: np.ndarray          # NPV je Lauf (zum MC-Diskontsatz)
    diskontsatz_pct: float
    jahre: np.ndarray        # Jahresachse (0..N) der Bandbreiten
    kum_p10: np.ndarray      # kumulierter Equity-Cashflow, 10%-Quantil
    kum_p25: np.ndarray
    kum_p50: np.ndarray
    kum_p75: np.ndarray
    kum_p90: np.ndarray

    @property
    def irr_gueltig(self) -> np.ndarray:
        return self.irr[~np.isnan(self.irr)]

    def wahrscheinlichkeit_irr_ueber(self, ziel: float) -> float:
        """Anteil der Laeufe mit IRR >= ziel. Laeufe ohne berechenbare IRR
        (kein Vorzeichenwechsel, i.d.R. durchgehend negativ) zaehlen
        konservativ als 'unter Ziel'."""
        if len(self.irr) == 0:
            return 0.0
        return float(np.sum(self.irr_gueltig >= ziel) / len(self.irr))


#: Standard-Unsicherheiten (Standardabweichung, multiplikativ) je Treiber.
MC_STANDARD_SIGMAS: dict[str, float] = {
    "produktion": 0.05,
    "marktwert": 0.10,
    "capex": 0.05,
    "opex": 0.05,
}


def run_monte_carlo(
    project: PVProject,
    global_assumptions: GlobalAssumptions,
    n_laeufe: int = 400,
    sigmas: dict[str, float] | None = None,
    diskontsatz_pct: float = 0.08,
    seed: int = 42,
    gebot_ziehungen: np.ndarray | None = None,
) -> MonteCarloResult:
    """Zieht je Lauf multiplikative Faktoren ~ Normal(1, sigma) fuer die
    Treiber aus `sigmas` (Default: MC_STANDARD_SIGMAS), rechnet die volle
    Bewertung und sammelt IRR, NPV und den kumulierten Equity-Cashflow.

    Fester Seed -> reproduzierbare Ergebnisse (wichtig fuer Caching und
    Nachvollziehbarkeit in Gremienunterlagen).

    gebot_ziehungen: optionale Stichprobe ERFOLGREICHER Gebote der
    naechsten EAG-Ausschreibung (engine.auktion.GebotsPrognose
    .gebots_ziehungen). Ist sie gesetzt, wird der EAG-Zuschlagswert je
    Lauf daraus gezogen (statt des fixen Projektwerts); der
    Konventionell-Abschlag des Projekts bleibt dabei erhalten. Damit
    fliesst die Auktionsunsicherheit als weitere Zufallsquelle in die
    IRR-Verteilung ein.
    """
    if sigmas is None:
        sigmas = MC_STANDARD_SIGMAS
    aktive = {k: s for k, s in sigmas.items() if s > 0}

    ea = resolve_assumptions(project, global_assumptions)
    rng = np.random.default_rng(seed)
    # Verhaeltnis effektiver/gebotener Wert (25%-Abschlag Konventionell).
    effektiv_faktor = (
        project.eag_zuschlagswert_effektiv_ct_kwh / project.eag_zuschlagswert_ct_kwh
        if project.eag_zuschlagswert_ct_kwh > 0
        else 1.0
    )

    irr_werte: list[float] = []
    npv_werte: list[float] = []
    kum_pfade: list[np.ndarray] = []
    jahre: np.ndarray | None = None

    for lauf in range(n_laeufe):
        ea_lauf = ea
        if gebot_ziehungen is not None and len(gebot_ziehungen) > 0:
            gebot = float(gebot_ziehungen[lauf % len(gebot_ziehungen)])
            ea_lauf = ea_lauf.model_copy(
                update={"eag_zuschlagswert_effektiv_ct_kwh": gebot * effektiv_faktor}
            )
        for treiber, sigma in aktive.items():
            # Untergrenze 0,4: schuetzt vor unphysikalischen Ausreissern
            # (negativer Ertrag/CAPEX) bei grossen Sigmas.
            faktor = max(float(rng.normal(1.0, sigma)), 0.4)
            ea_lauf = _mutiere(ea_lauf, treiber, faktor)

        result = run_valuation_from_assumptions(
            ea_lauf, ea.source_project_id, compute_npv_curve=False
        )
        df = result.cashflow.data
        cashflows = df["cf_gesamt_eur"].tolist()
        daten = df["datum"].tolist()

        irr = result.kpis.equity_irr
        irr_werte.append(np.nan if irr is None else irr)
        npv_werte.append(_xnpv(diskontsatz_pct, cashflows, daten))
        kum_pfade.append(df["cf_kumuliert_eur"].to_numpy())
        if jahre is None:
            jahre = df["jahr"].to_numpy()

    pfade = np.vstack(kum_pfade)
    return MonteCarloResult(
        n_laeufe=n_laeufe,
        irr=np.array(irr_werte),
        npv=np.array(npv_werte),
        diskontsatz_pct=diskontsatz_pct,
        jahre=jahre if jahre is not None else np.array([]),
        kum_p10=np.percentile(pfade, 10, axis=0),
        kum_p25=np.percentile(pfade, 25, axis=0),
        kum_p50=np.percentile(pfade, 50, axis=0),
        kum_p75=np.percentile(pfade, 75, axis=0),
        kum_p90=np.percentile(pfade, 90, axis=0),
    )


# ---------------------------------------------------------------------------
# Gebotsassistent: Break-even-EAG-Zuschlag fuer eine Ziel-IRR
# ---------------------------------------------------------------------------


def break_even_zuschlag(
    project: PVProject,
    global_assumptions: GlobalAssumptions,
    ziel_irr: float,
    min_ct_kwh: float = 0.5,
    max_ct_kwh: float = 15.0,
) -> float | None:
    """Minimaler EAG-Zuschlagswert (anzulegender Wert, ct/kWh), bei dem die
    EK-Rendite die Ziel-IRR gerade erreicht - die wirtschaftliche
    Untergrenze fuer ein Auktionsgebot.

    None, wenn das Ziel im Suchbereich nicht erreichbar ist (Ziel zu hoch)
    oder bereits ohne wirksame Praemie uebertroffen wird (Marktwert traegt
    das Projekt allein - dann ist jedes Gebot ab min_ct_kwh 'ausreichend').
    Rueckgabe in ct/kWh VOR dem Konventionell-Abschlag - also der Wert, der
    tatsaechlich geboten wuerde.
    """
    from scipy.optimize import brentq

    ea = resolve_assumptions(project, global_assumptions)
    # Verhaeltnis effektiv/geboten (Konventionell-Abschlag) beibehalten.
    if project.eag_zuschlagswert_ct_kwh <= 0:
        return None
    effektiv_faktor = (
        project.eag_zuschlagswert_effektiv_ct_kwh / project.eag_zuschlagswert_ct_kwh
    )

    def irr_bei(gebot_ct: float) -> float | None:
        ea_var = ea.model_copy(
            update={"eag_zuschlagswert_effektiv_ct_kwh": gebot_ct * effektiv_faktor}
        )
        return _irr_fuer(ea_var)

    def f(gebot_ct: float) -> float:
        irr = irr_bei(gebot_ct)
        # Nicht berechenbare IRR (kein Vorzeichenwechsel im Cashflow, i.d.R.
        # durchgehend negativ) konservativ als "weit unter Ziel" behandeln.
        return (irr if irr is not None else -1.0) - ziel_irr

    f_min, f_max = f(min_ct_kwh), f(max_ct_kwh)
    if f_min >= 0:
        # Ziel schon am unteren Rand erreicht -> Marktwert/Minimalpraemie
        # traegt das Projekt; kein echter Break-even im Suchbereich.
        return min_ct_kwh
    if f_max < 0:
        return None
    return float(brentq(f, min_ct_kwh, max_ct_kwh, xtol=0.001))


# ---------------------------------------------------------------------------
# LCOE (Stromgestehungskosten)
# ---------------------------------------------------------------------------


def calculate_lcoe(cashflow_df: pd.DataFrame, diskontsatz_pct: float) -> float | None:
    """LCOE = diskontierte Vollkosten (CAPEX + OPEX) / diskontierte
    Stromerzeugung, in ct/kWh. Diskontierung Act/365 analog XNPV."""
    daten = cashflow_df["datum"].tolist()
    d0 = daten[0]
    faktoren = np.array(
        [(1 + diskontsatz_pct) ** (-(d - d0).days / 365.0) for d in daten]
    )
    kosten = (-cashflow_df["cf_invest_eur"] + cashflow_df["opex_gesamt_eur"]).to_numpy()
    produktion = cashflow_df["produktion_kwh"].to_numpy()

    energie_diskontiert = float((produktion * faktoren).sum())
    if energie_diskontiert <= 0:
        return None
    return float((kosten * faktoren).sum() / energie_diskontiert * 100.0)


# ---------------------------------------------------------------------------
# Szenarienvergleich
# ---------------------------------------------------------------------------


@dataclass
class SzenarioVergleich:
    kennzahlen: pd.DataFrame          # szenario, equity_irr, npv_eur, erloes_gesamt_eur
    kum_cashflows: pd.DataFrame       # jahr + eine Spalte je Szenario (kum. Equity-CF)


def run_scenario_comparison(
    project: PVProject,
    global_assumptions: GlobalAssumptions,
    diskontsatz_pct: float = 0.08,
) -> SzenarioVergleich:
    """Rechnet das identische Projekt ueber alle hinterlegten
    Marktpreisszenarien und stellt IRR/NPV sowie die kumulierten
    Equity-Cashflows gegenueber."""
    ea = resolve_assumptions(project, global_assumptions)

    rows = []
    kum: dict[str, np.ndarray] = {}
    jahre: np.ndarray | None = None
    for szenario in global_assumptions.marktpreisszenarien:
        ea_var = ea.model_copy(
            update={
                "marktpreisszenario_name": szenario.name,
                "marktwert_solar_ct_kwh_je_kalenderjahr": szenario.marktwert_solar_ct_kwh_je_kalenderjahr,
                "anteil_negativer_stunden_pct_je_kalenderjahr": szenario.erzeugungsmenge_negativ(
                    global_assumptions.negative_stunden_regel
                ),
            }
        )
        result = run_valuation_from_assumptions(
            ea_var, ea.source_project_id, compute_npv_curve=False
        )
        df = result.cashflow.data
        rows.append(
            {
                "szenario": szenario.name,
                "equity_irr": result.kpis.equity_irr,
                "npv_eur": _xnpv(
                    diskontsatz_pct,
                    df["cf_gesamt_eur"].tolist(),
                    df["datum"].tolist(),
                ),
                "erloes_gesamt_eur": float(df["erloes_eur"].sum()),
            }
        )
        kum[szenario.name] = df["cf_kumuliert_eur"].to_numpy()
        if jahre is None:
            jahre = df["jahr"].to_numpy()

    kum_df = pd.DataFrame({"jahr": jahre if jahre is not None else [], **kum})
    return SzenarioVergleich(kennzahlen=pd.DataFrame(rows), kum_cashflows=kum_df)
