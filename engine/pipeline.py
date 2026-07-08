"""
Orchestriert den kompletten Ablauf von PVProject bis ValuationResult.

Dies ist die einzige Funktion, die UI (Streamlit) und spaeter das
Repository tatsaechlich aufrufen sollen - sie kapselt die interne
Modulstruktur der Engine vollstaendig.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .cashflow import CashflowTimeseries, calculate_cashflow
from .energy import calculate_energy_production
from .financing import calculate_financing
from .kpis import calculate_kpis
from .models import EffectiveAssumptions, KPIs, PVProject
from .opex import calculate_opex
from .revenue import calculate_revenue
from .tax import calculate_tax
from .timeline import build_timeline


def resolve_assumptions(project: PVProject) -> EffectiveAssumptions:
    """Loest Global/Projekt/Szenario-Ebenen zu einem einzigen Parametersatz
    auf.

    Phase-1-Vereinfachung: Es gibt noch kein GlobalAssumptions- oder
    Scenario-Objekt, PVProject enthaelt bereits alle Annahmen direkt. Diese
    Funktion ist deshalb aktuell ein reiner Pass-Through - sie existiert
    aber bewusst schon jetzt als eigener Aufruf, damit das spaetere
    Einziehen von Global Assumptions + Szenario-Deltas eine Erweiterung
    dieser einen Funktion ist, statt eine Aenderung an jedem Engine-Modul
    oder an der UI noetig zu machen.
    """
    return EffectiveAssumptions(
        capex_total_eur=project.capex_total_eur,
        technical=project.technical,
        revenue=project.revenue,
        opex_items=project.opex_items,
        financing=project.financing,
        tax=project.tax,
        source_project_id=project.id,
    )


@dataclass
class ValuationResult:
    project_id: str
    effective_assumptions: EffectiveAssumptions
    cashflow: CashflowTimeseries
    kpis: KPIs
    berechnet_am: datetime


def run_valuation(project: PVProject) -> ValuationResult:
    assumptions = resolve_assumptions(project)

    timeline = build_timeline(
        inbetriebnahme_datum=assumptions.technical.inbetriebnahme_datum,
        laufzeit_jahre=assumptions.revenue.vertragslaufzeit_jahre,
    )

    energy = calculate_energy_production(timeline, assumptions.technical)
    revenue = calculate_revenue(timeline, energy, assumptions.revenue)
    opex = calculate_opex(
        timeline, assumptions.opex_items, assumptions.technical.nennleistung_kwp
    )
    financing = calculate_financing(
        timeline, assumptions.capex_total_eur, assumptions.financing
    )
    tax = calculate_tax(revenue, opex, financing, assumptions.tax)

    cashflow = calculate_cashflow(
        timeline=timeline,
        revenue=revenue,
        opex=opex,
        financing=financing,
        tax=tax,
        capex_total_eur=assumptions.capex_total_eur,
        eigenkapitalquote_pct=assumptions.financing.eigenkapitalquote_pct,
        inbetriebnahme_datum=assumptions.technical.inbetriebnahme_datum,
        project_id=project.id,
    )

    kpis = calculate_kpis(cashflow)

    return ValuationResult(
        project_id=project.id,
        effective_assumptions=assumptions,
        cashflow=cashflow,
        kpis=kpis,
        berechnet_am=datetime.now(),
    )
