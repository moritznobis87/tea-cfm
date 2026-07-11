"""
Orchestriert den kompletten Ablauf von PVProject + GlobalAssumptions bis
ValuationResult.

Anders als in Phase 1 ist resolve_assumptions() jetzt ein echter Merge:
Die Projektmaske (selten vorhandene Werte) wird mit den globalen
Standardannahmen zu einem vollstaendigen Parametersatz zusammengefuehrt.
Die Pacht aus dem Projekt wird dabei automatisch der globalen OPEX-Liste
hinzugefuegt; die Geschaeftsregel "Konventionell -> -25% EAG-Zuschlag"
wird ueber PVProject.eag_zuschlagswert_effektiv_ct_kwh angewendet.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

import pandas as pd

from .cashflow import CashflowTimeseries, calculate_cashflow
from .energy import calculate_energy_production
from .financing import calculate_financing
from .kpis import KPIs, calculate_kpis, calculate_npv_curve
from .models import (
    EffectiveAssumptions,
    GlobalAssumptions,
    MarktpreisSzenario,
    OpexItem,
    PVProject,
)
from .opex import calculate_opex
from .revenue import calculate_revenue
from .tax import calculate_tax
from .timeline import build_timeline


def resolve_assumptions(
    project: PVProject, global_assumptions: GlobalAssumptions
) -> EffectiveAssumptions:
    pacht_item = OpexItem(
        name="Pacht", basiswert_eur_kwp=project.pacht_eur_kwp_jahr
    )
    opex_items = [*global_assumptions.opex_standard, pacht_item]

    szenario = global_assumptions.get_szenario(project.marktpreisszenario)
    if szenario is None:
        if global_assumptions.marktpreisszenarien:
            # Fallback auf das erste verfuegbare Szenario, falls der im
            # Projekt hinterlegte Name nicht (mehr) existiert - so bricht
            # eine Berechnung nicht einfach ab, wenn z.B. ein Szenario in
            # den Globalen Annahmen umbenannt/geloescht wurde.
            szenario = global_assumptions.marktpreisszenarien[0]
        else:
            szenario = MarktpreisSzenario(name="(kein Szenario hinterlegt)")

    return EffectiveAssumptions(
        source_project_id=project.id,
        inbetriebnahme_jahr=project.inbetriebnahme_jahr,
        inbetriebnahme_monat=project.inbetriebnahme_monat,
        nennleistung_kwp=project.nennleistung_kwp,
        vollbenutzungsstunden_kwh_kwp=project.vollbenutzungsstunden_kwh_kwp,
        degradation_pct_pa=global_assumptions.degradation_pct_pa,
        sicherheitsabschlag_pct=global_assumptions.sicherheitsabschlag_pct,
        eag_zuschlagswert_effektiv_ct_kwh=project.eag_zuschlagswert_effektiv_ct_kwh,
        eag_foerderdauer_jahre=global_assumptions.eag_foerderdauer_jahre,
        betriebsdauer_jahre=global_assumptions.betriebsdauer_jahre,
        marktpreisszenario_name=szenario.name,
        marktwert_solar_ct_kwh_je_kalenderjahr=szenario.marktwert_solar_ct_kwh_je_kalenderjahr,
        anteil_negativer_stunden_pct_je_kalenderjahr=szenario.anteil_negativer_stunden_pct_je_kalenderjahr,
        opex_items=opex_items,
        gemeindeabgabe_eur_kwh=project.gemeindeabgabe_eur_mwh / 1000,
        capex_total_eur=project.capex.summe_eur,
        eigenkapitalquote_pct=project.eigenkapitalquote_pct,
        fremdkapitalzins_pct=project.fremdkapitalzins_pct,
        kreditlaufzeit_jahre=global_assumptions.kreditlaufzeit_jahre,
        tilgungsart=global_assumptions.tilgungsart,
        tax_modus=global_assumptions.tax_modus,
        steuersatz_pct=global_assumptions.steuersatz_pct,
        afa_nutzungsdauer_jahre=global_assumptions.afa_nutzungsdauer_jahre,
        freibetrag_eur=global_assumptions.freibetrag_eur,
    )


@dataclass
class ValuationResult:
    project_id: str
    effective_assumptions: EffectiveAssumptions
    cashflow: CashflowTimeseries
    kpis: KPIs
    npv_curve: pd.DataFrame
    berechnet_am: datetime


def run_valuation(
    project: PVProject, global_assumptions: GlobalAssumptions
) -> ValuationResult:
    assumptions = resolve_assumptions(project, global_assumptions)

    inbetriebnahme_datum = date(
        assumptions.inbetriebnahme_jahr, assumptions.inbetriebnahme_monat, 1
    )
    timeline = build_timeline(
        inbetriebnahme_datum=inbetriebnahme_datum,
        laufzeit_jahre=assumptions.betriebsdauer_jahre,
    )

    energy = calculate_energy_production(timeline, assumptions)
    revenue = calculate_revenue(timeline, energy, assumptions)
    opex = calculate_opex(
        timeline,
        assumptions.opex_items,
        assumptions.nennleistung_kwp,
        energy,
        assumptions.gemeindeabgabe_eur_kwh,
    )
    financing = calculate_financing(
        timeline,
        assumptions.capex_total_eur,
        assumptions.eigenkapitalquote_pct,
        assumptions.fremdkapitalzins_pct,
        assumptions.kreditlaufzeit_jahre,
        assumptions.tilgungsart,
    )
    tax = calculate_tax(
        revenue,
        opex,
        financing,
        assumptions.capex_total_eur,
        assumptions.tax_modus,
        assumptions.steuersatz_pct,
        assumptions.afa_nutzungsdauer_jahre,
        assumptions.freibetrag_eur,
    )

    cashflow = calculate_cashflow(
        timeline=timeline,
        revenue=revenue,
        opex=opex,
        financing=financing,
        tax=tax,
        capex_total_eur=assumptions.capex_total_eur,
        eigenkapitalquote_pct=assumptions.eigenkapitalquote_pct,
        inbetriebnahme_datum=inbetriebnahme_datum,
        project_id=project.id,
    )

    kpis = calculate_kpis(cashflow)
    npv_curve = calculate_npv_curve(cashflow)

    return ValuationResult(
        project_id=project.id,
        effective_assumptions=assumptions,
        cashflow=cashflow,
        kpis=kpis,
        npv_curve=npv_curve,
        berechnet_am=datetime.now(),
    )
