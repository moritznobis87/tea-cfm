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
from .covenants import KovenantAnalyse, analysiere_kovenanten
from .energy import calculate_energy_production
from .financing import calculate_financing
from .io_aurora import szenario_fuer
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
from .timeline import build_timeline, erstjahr_zins_pro_rata


def _opex_items(
    project: PVProject, global_assumptions: GlobalAssumptions
) -> list[OpexItem]:
    """Standardpositionen mit den Werten dieses Projekts, dann die
    projektspezifischen Zusatzpositionen.

    Die Reihenfolge bestimmt auch die Stapelreihenfolge im
    Kostendiagramm. Ein abweichender Basiswert ersetzt nur die Zahl -
    Name, Indexierung und Bezugsgroesse bleiben die der globalen
    Position, sonst waere es eine andere Kostenart.
    """
    abweichend = project.annahmen.opex_standard_eur_kwp
    standard = [
        item.model_copy(update={"basiswert_eur_kwp": abweichend[item.name]})
        if item.name in abweichend else item
        for item in global_assumptions.opex_standard
    ]
    return standard + list(project.zusatz_opex)


def _einspeisekurve(
    project: PVProject, global_assumptions: GlobalAssumptions
) -> list[float]:
    """Die Monatskurve der Bauform dieses Projekts.

    Die Bauform verteilt die Jahresmenge anders ueber das Jahr - der
    Tracker sommerlastiger als das Pult. Sie ist eine Eigenschaft der
    Anlage, also entscheidet das Projekt.

    Ausnahme ist die von Hand bearbeitete Kurve: Steht in den globalen
    Annahmen keine Bauform mehr (einspeisekurve_bauform == ""), wurde
    die aktive Kurve dort ausdruecklich abgewandelt. Sie zugunsten
    einer hinterlegten Kurve zu uebergehen, verwuerfe eine Eingabe
    stillschweigend.
    """
    if not global_assumptions.einspeisekurve_bauform:
        return list(global_assumptions.einspeisekurve_pct_je_monat)
    return list(
        global_assumptions.einspeisekurven_je_bauform.get(
            project.bauform, global_assumptions.einspeisekurve_pct_je_monat
        )
    )


def resolve_assumptions(
    project: PVProject, global_assumptions: GlobalAssumptions
) -> EffectiveAssumptions:
    # Die Abweichungen dieses Projekts haben Vorrang vor der globalen
    # Vorgabe; `erbe` ist die einzige Stelle, an der beides
    # zusammenkommt (siehe engine/models.py::Projektannahmen).
    abw = project.annahmen

    def erbe(feld: str):
        """Der wirksame Wert eines Parameters: Abweichung oder Vorgabe.

        None im Projekt heisst "folgt der Vorgabe" - nicht "auf None
        gesetzt". Deshalb wird hier auf `is None` geprueft und nicht auf
        Wahrheitswert: Ein abweichendes 0 % oder False muss wirken.
        """
        eigen = getattr(abw, feld)
        return getattr(global_assumptions, feld) if eigen is None else eigen

    opex_items = _opex_items(project, global_assumptions)

    # Das Szenario ergibt sich aus zwei Angaben: dem im Projekt
    # hinterlegten Namen (ohne Bauform) und der Bauform der Anlage. Der
    # Tracker erzeugt breiter ueber den Tag verteilt und trifft die
    # preisschwachen Mittagsstunden weniger stark - seine Marktwertkurve
    # ist deshalb eine andere als die der Pultaufstaenderung.
    szenario = szenario_fuer(
        global_assumptions, project.marktpreisszenario, project.bauform
    )
    if szenario is None:
        if global_assumptions.marktpreisszenarien:
            # Fallback auf das erste verfuegbare Szenario, falls der im
            # Projekt hinterlegte Name nicht (mehr) existiert - so bricht
            # eine Berechnung nicht einfach ab, wenn z.B. ein Szenario in
            # den Globalen Annahmen umbenannt/geloescht wurde.
            szenario = global_assumptions.marktpreisszenarien[0]
        else:
            szenario = MarktpreisSzenario(name="(kein Szenario hinterlegt)")

    # Einmal aufgeloest, dreifach gebraucht: Sie waehlt die
    # Negativmengen-Zeitreihe des Szenarios (6h oder 1h) und geht
    # ausserdem als Regel in die Erloesrechnung ein.
    negativ_regel = erbe("negative_stunden_regel")

    return EffectiveAssumptions(
        source_project_id=project.id,
        inbetriebnahme_jahr=project.inbetriebnahme_jahr,
        inbetriebnahme_monat=project.inbetriebnahme_monat,
        nennleistung_kwp=project.nennleistung_kwp,
        vollbenutzungsstunden_kwh_kwp=project.vollbenutzungsstunden_kwh_kwp,
        degradation_pct_pa=erbe("degradation_pct_pa"),
        sicherheitsabschlag_pct=erbe("sicherheitsabschlag_pct"),
        eag_zuschlagswert_effektiv_ct_kwh=project.eag_zuschlagswert_effektiv_ct_kwh,
        eag_foerderdauer_jahre=erbe("eag_foerderdauer_jahre"),
        betriebsdauer_jahre=erbe("betriebsdauer_jahre"),
        marktpreisszenario_name=szenario.name,
        marktwert_solar_ct_kwh_je_kalenderjahr=szenario.marktwert_solar_ct_kwh_je_kalenderjahr,
        anteil_negativer_stunden_pct_je_kalenderjahr=szenario.erzeugungsmenge_negativ(
            negativ_regel
        ),
        negative_stunden_regel=negativ_regel,
        zeitaufloesung=global_assumptions.zeitaufloesung,
        einspeisekurve_pct_je_monat=_einspeisekurve(project, global_assumptions),
        marktwert_solar_ct_kwh_je_monat=szenario.marktwert_monatskurve(),
        baseload_ct_kwh_je_kalenderjahr=szenario.baseload_ct_kwh_je_kalenderjahr,
        baseload_ct_kwh_je_monat=szenario.baseload_monatskurve(),
        anteil_negativer_stunden_pct_je_monat=szenario.negativ_monatskurve(
            negativ_regel
        ),
        praemien_modell=erbe("praemien_modell"),
        eag_rueckzahlung_ab_mw=erbe("eag_rueckzahlung_ab_mw"),
        eag_rueckzahlung_toleranzband_pct=erbe("eag_rueckzahlung_toleranzband_pct"),
        eag_rueckzahlung_anteil_pct=erbe("eag_rueckzahlung_anteil_pct"),
        ppa_anteil_pct=project.ppa_anteil_pct,
        ppa_preis_eur_mwh=project.ppa_preis_eur_mwh,
        ppa_start_jahr=project.ppa_start_jahr,
        ppa_laufzeit_jahre=project.ppa_laufzeit_jahre,
        ppa_indexierung_pct_pa=project.ppa_indexierung_pct_pa,
        marktpreis_inflation_pct_pa=erbe("marktpreis_inflation_pct_pa"),
        marktpreis_inflation_basisjahr=erbe("marktpreis_inflation_basisjahr"),
        kosten_inflation_pct_pa=erbe("kosten_inflation_pct_pa"),
        opex_items=opex_items,
        pacht_modus=project.pacht_modus,
        pacht_eur_kwp_jahr=project.pacht_eur_kwp_jahr,
        pacht_umsatzbeteiligung_pct=project.pacht_umsatzbeteiligung_pct,
        pacht_mindestpacht_eur_ha_jahr=project.pacht_mindestpacht_eur_ha_jahr,
        projektflaeche_ha=project.projektflaeche_ha,
        gemeindeabgabe_eur_kwh=project.gemeindeabgabe_eur_mwh / 1000,
        direktvermarktungskosten_eur_kwh=project.direktvermarktungskosten_eur_mwh / 1000,
        direktvermarktung_modus=erbe("direktvermarktung_modus"),
        direktvermarktung_pct_marktwert=erbe("direktvermarktung_pct_marktwert"),
        negative_stunden_gewichtung_pct=erbe("negative_stunden_gewichtung_pct"),
        negative_stunden_modus=erbe("negative_stunden_modus"),
        capex_total_eur=project.capex.summe_eur,
        eigenkapitalquote_pct=project.eigenkapitalquote_pct,
        fremdkapitalzins_pct=project.fremdkapitalzins_pct,
        kreditlaufzeit_jahre=erbe("kreditlaufzeit_jahre"),
        tilgungsart=erbe("tilgungsart"),
        tilgungsfreies_anlaufjahr=erbe("tilgungsfreies_anlaufjahr"),
        zinsmethode=erbe("zinsmethode"),
        dscr_cash_trap=erbe("dscr_cash_trap"),
        dscr_event_of_default=erbe("dscr_event_of_default"),
        tax_modus=erbe("tax_modus"),
        steuersatz_pct=erbe("steuersatz_pct"),
        afa_nutzungsdauer_jahre=erbe("afa_nutzungsdauer_jahre"),
        freibetrag_eur=erbe("freibetrag_eur"),
        gewerbesteuer_hebesatz_pct=erbe("gewerbesteuer_hebesatz_pct"),
        gewerbesteuer_freibetrag_eur=erbe("gewerbesteuer_freibetrag_eur"),
        verlustvortrag_verrechnungsgrenze_pct=erbe("verlustvortrag_verrechnungsgrenze_pct"),
    )


@dataclass
class ValuationResult:
    project_id: str
    effective_assumptions: EffectiveAssumptions
    cashflow: CashflowTimeseries
    kpis: KPIs
    npv_curve: pd.DataFrame
    berechnet_am: datetime
    #: Auswertung der DSCR-Kovenanten (Cash Trap, Event of Default) auf
    #: der fertigen Cashflow-Zeitreihe - siehe engine/covenants.py. Die
    #: Cashflow-Rechnung selbst bleibt davon unberuehrt.
    kovenanten: KovenantAnalyse | None = None


def run_valuation(
    project: PVProject, global_assumptions: GlobalAssumptions
) -> ValuationResult:
    assumptions = resolve_assumptions(project, global_assumptions)
    return run_valuation_from_assumptions(assumptions, project.id)


def run_valuation_from_assumptions(
    assumptions: EffectiveAssumptions,
    project_id: str,
    compute_npv_curve: bool = True,
) -> ValuationResult:
    """Bewertung direkt aus einem (ggf. modifizierten) aufgeloesten
    Parametersatz - Grundlage fuer Sensitivitaeten, Heatmaps und
    Monte-Carlo-Simulationen, die viele Varianten rechnen und dabei den
    Merge-Schritt und (optional) die NPV-Kurve einsparen wollen."""
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
        assumptions.direktvermarktungskosten_eur_kwh,
        direktvermarktung_modus=assumptions.direktvermarktung_modus,
        direktvermarktung_pct_marktwert=assumptions.direktvermarktung_pct_marktwert,
        marktwert_nominal_ct_kwh=revenue["marktwert_nominal_ct_kwh"].to_numpy(),
        baseload_nominal_ct_kwh=revenue["baseload_nominal_ct_kwh"].to_numpy(),
        kosten_inflation_pct_pa=assumptions.kosten_inflation_pct_pa,
        pacht_modus=assumptions.pacht_modus,
        pacht_eur_kwp_jahr=assumptions.pacht_eur_kwp_jahr,
        pacht_umsatzbeteiligung_pct=assumptions.pacht_umsatzbeteiligung_pct,
        pacht_mindestpacht_eur_ha_jahr=assumptions.pacht_mindestpacht_eur_ha_jahr,
        projektflaeche_ha=assumptions.projektflaeche_ha,
        erloes_eur=revenue["erloes_eur"].to_numpy(),
    )
    financing = calculate_financing(
        timeline,
        assumptions.capex_total_eur,
        assumptions.eigenkapitalquote_pct,
        assumptions.fremdkapitalzins_pct,
        assumptions.kreditlaufzeit_jahre,
        assumptions.tilgungsart,
        assumptions.tilgungsfreies_anlaufjahr,
        erstjahr_zins_pro_rata(inbetriebnahme_datum, assumptions.zinsmethode),
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
        assumptions.verlustvortrag_verrechnungsgrenze_pct,
        gewerbesteuer_hebesatz_pct=assumptions.gewerbesteuer_hebesatz_pct,
        gewerbesteuer_freibetrag_eur=assumptions.gewerbesteuer_freibetrag_eur,
    )

    cashflow = calculate_cashflow(
        timeline=timeline,
        energy=energy,
        revenue=revenue,
        opex=opex,
        financing=financing,
        tax=tax,
        capex_total_eur=assumptions.capex_total_eur,
        eigenkapitalquote_pct=assumptions.eigenkapitalquote_pct,
        inbetriebnahme_datum=inbetriebnahme_datum,
        project_id=project_id,
    )

    kpis = calculate_kpis(cashflow)
    kovenanten = analysiere_kovenanten(
        cashflow.data,
        assumptions.dscr_cash_trap,
        assumptions.dscr_event_of_default,
    )
    npv_curve = (
        calculate_npv_curve(cashflow) if compute_npv_curve else pd.DataFrame()
    )

    return ValuationResult(
        project_id=project_id,
        effective_assumptions=assumptions,
        cashflow=cashflow,
        kpis=kpis,
        npv_curve=npv_curve,
        berechnet_am=datetime.now(),
        kovenanten=kovenanten,
    )
