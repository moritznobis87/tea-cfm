"""
Bewertungs-Engine: reine Fachlogik ohne UI-Abhaengigkeiten.

Oeffentliche API dieses Pakets - die App (und Tests) importieren
ausschliesslich von hier, nicht aus den Untermodulen.
"""

from .analytics import (
    HEATMAP_ACHSEN,
    MC_STANDARD_SIGMAS,
    MonteCarloResult,
    SzenarioVergleich,
    break_even_zuschlag,
    calculate_lcoe,
    run_irr_heatmap,
    run_monte_carlo,
    run_scenario_comparison,
    run_tornado,
)
from .auktion import (
    AuktionsModell,
    Ausschreibung,
    GebotsPrognose,
    ausschreibungen_dataframe,
    differenzen_extrapolation,
    kalibriere_modell,
    load_ausschreibungen,
    prognose_letzte_runde,
    prognose_naechste_runde,
    validiere_einschritt,
    validiere_loo,
    vergleiche_familien,
)
from .cashflow import CashflowTimeseries
from .io_ergebnis_excel import pipeline_ergebnis_excel
from .models import (
    AnlagenTyp,
    CapexBreakdown,
    DirektvermarktungsModus,
    EffectiveAssumptions,
    GlobalAssumptions,
    KPIs,
    MarktpreisSzenario,
    NegativeStundenModus,
    NegativeStundenRegel,
    OpexItem,
    PVProject,
    TaxModus,
    TilgungsArt,
)
from .pipeline import (
    ValuationResult,
    resolve_assumptions,
    run_valuation,
    run_valuation_from_assumptions,
)
from .sensitivity import run_eag_sensitivity

__all__ = [
    "pipeline_ergebnis_excel",
    "Ausschreibung",
    "AuktionsModell",
    "GebotsPrognose",
    "ausschreibungen_dataframe",
    "kalibriere_modell",
    "load_ausschreibungen",
    "differenzen_extrapolation",
    "prognose_letzte_runde",
    "prognose_naechste_runde",
    "validiere_einschritt",
    "validiere_loo",
    "vergleiche_familien",
    "HEATMAP_ACHSEN",
    "MC_STANDARD_SIGMAS",
    "MonteCarloResult",
    "SzenarioVergleich",
    "break_even_zuschlag",
    "calculate_lcoe",
    "run_irr_heatmap",
    "run_monte_carlo",
    "run_scenario_comparison",
    "run_tornado",
    "run_valuation_from_assumptions",
    "AnlagenTyp",
    "CapexBreakdown",
    "DirektvermarktungsModus",
    "NegativeStundenRegel",
    "CashflowTimeseries",
    "EffectiveAssumptions",
    "GlobalAssumptions",
    "KPIs",
    "MarktpreisSzenario",
    "NegativeStundenModus",
    "OpexItem",
    "PVProject",
    "TaxModus",
    "TilgungsArt",
    "ValuationResult",
    "resolve_assumptions",
    "run_valuation",
    "run_eag_sensitivity",
]
