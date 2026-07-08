"""
Fachliche Datenmodelle für die PV-Cashflow-Engine.

Bewusste MVP-Vereinfachung gegenüber der vollen Zielarchitektur:
- Kein separates GlobalAssumptions/Scenario-Layering in Phase 1.
  PVProject enthaelt alle Annahmen direkt. `resolve_assumptions()` in
  pipeline.py ist bereits als eigener Funktionsaufruf vorhanden (Pass-Through),
  damit das spaetere Einziehen von Global/Scenario keine Schnittstellenaenderung
  fuer die Engine-Module noetig macht.
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class TariffType(str, Enum):
    """Ersetzt den Excel-Freitext in C19 (Ursache eines dort gefundenen
    stillen Fehlers: nicht zuordenbarer Freitext lieferte 0 Erloes) durch
    ein geschlossenes, validiertes Set."""

    EEG_FIXED = "eeg_fixed"
    PPA = "ppa"
    MARKET_BEST_GUESS = "market_best_guess"  # folgt erst in Phase 2


class ProbabilisticValue(BaseModel):
    """Ein Wert mit P50 als Pflichtangabe und optionaler P15/P85-Bandbreite.
    Im MVP wird nur p50 tatsaechlich gerechnet; P15/P85 sind fuer die
    spaetere Sensitivitaet/Monte-Carlo-Erweiterung bereits vorgesehen."""

    p50: float
    p15: float | None = None
    p85: float | None = None


class TechnicalAssumptions(BaseModel):
    nennleistung_kwp: float = Field(gt=0)
    spezifischer_ertrag_kwh_kwp: ProbabilisticValue
    degradation_pct_pa: float = 0.0
    sicherheitsabschlag_pct: float = 0.0
    inbetriebnahme_datum: date


class RevenueAssumptions(BaseModel):
    tariff_type: TariffType
    eeg_satz_ct_kwh: float | None = None
    ppa_satz_ct_kwh: float | None = None
    direktvermarktung_abschlag_ct_kwh: float = 0.0
    vertragslaufzeit_jahre: int = Field(gt=0)

    @model_validator(mode="after")
    def check_tariff_consistency(self) -> "RevenueAssumptions":
        if self.tariff_type == TariffType.EEG_FIXED and self.eeg_satz_ct_kwh is None:
            raise ValueError("eeg_satz_ct_kwh erforderlich bei tariff_type=eeg_fixed")
        if self.tariff_type == TariffType.PPA and self.ppa_satz_ct_kwh is None:
            raise ValueError("ppa_satz_ct_kwh erforderlich bei tariff_type=ppa")
        if self.tariff_type == TariffType.MARKET_BEST_GUESS:
            raise NotImplementedError(
                "tariff_type=market_best_guess ist erst ab Phase 2 "
                "(zentrale Marktpreiskurve) implementiert."
            )
        return self


class OpexItem(BaseModel):
    """Eine Betriebskostenposition. Ersetzt Excels starre 9-Zeilen-Tabelle
    durch eine offene Liste beliebiger Laenge."""

    name: str
    basiswert_eur_kwp: float = 0.0
    start_betriebsjahr: int = 1
    index_pct_pa: float = 0.0
    end_betriebsjahr: int | None = None


class FinancingAssumptions(BaseModel):
    eigenkapitalquote_pct: float = Field(ge=0, le=1)
    fremdkapitalzins_pct: float = Field(ge=0)
    kreditlaufzeit_jahre: int = Field(gt=0)


class TaxAssumptions(BaseModel):
    steuersatz_pauschal_pct: float = Field(ge=0, le=1)
    # Bewusst keine AfA-/Verlustvortragsfelder im MVP - siehe Architekturnotiz
    # aus der Design-Phase (Phase-2-Erweiterung).


class PVProject(BaseModel):
    """Ein PV-Projekt mit allen fuer die Cashflow-Rechnung noetigen Annahmen.
    Fachliches Objekt, keine 1:1-Nachbildung von Excel-Zellen."""

    id: str
    name: str
    capex_total_eur: float = Field(gt=0)
    technical: TechnicalAssumptions
    revenue: RevenueAssumptions
    opex_items: list[OpexItem] = Field(default_factory=list)
    financing: FinancingAssumptions
    tax: TaxAssumptions


class EffectiveAssumptions(BaseModel):
    """Ergebnis von resolve_assumptions(). In Phase 1 identisch zu den
    Projektannahmen (kein Global/Scenario-Merge), aber als eigenes Objekt
    gefuehrt, damit die Engine-Module bereits gegen die Zielschnittstelle
    entwickelt werden."""

    capex_total_eur: float
    technical: TechnicalAssumptions
    revenue: RevenueAssumptions
    opex_items: list[OpexItem]
    financing: FinancingAssumptions
    tax: TaxAssumptions
    source_project_id: str


class KPIs(BaseModel):
    equity_irr: float | None
    npv_eur: float
    payback_jahre: float | None
    capex_total_eur: float
