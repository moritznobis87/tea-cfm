"""
Fachliche Datenmodelle, Version 2 - ausgerichtet am Arbeitsablauf eines
Projektentwicklers, nicht mehr am Excel-Original.

Kernprinzip: PVProject enthaelt NUR das, was sich von Projekt zu Projekt
tatsaechlich unterscheidet (die "Projektmaske"). Alles, was selten
geaendert wird (Preiskurven, Standardbetriebskosten, Kreditlaufzeit,
Steuerlogik, Degradation ...), lebt in GlobalAssumptions und wird
automatisch uebernommen.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class AnlagenTyp(str, Enum):
    AGRI_PV = "agri_pv"
    KONVENTIONELL = "konventionell"


# Geschaeftsregel: Konventionelle Anlagen erhalten einen Abschlag auf den
# EAG-Zuschlagswert gegenueber Agri-PV. Bewusst als benannte Konstante
# (nicht als Nutzereingabe) - das ist eine Geschaeftsregel, kein Parameter.
KONVENTIONELL_ZUSCHLAG_ABSCHLAG_PCT = 0.25


class TilgungsArt(str, Enum):
    ANNUITAET = "annuitaet"
    LINEAR = "linear"


class TaxModus(str, Enum):
    PAUSCHAL_AUF_EBT = "pauschal_auf_ebt"
    AFA_KOERPERSCHAFTSTEUER = "afa_koerperschaftsteuer"


# ---------------------------------------------------------------------------
# Projektmaske (Layer 2) - das sieht der Projektentwickler beim Anlegen
# ---------------------------------------------------------------------------


class CapexBreakdown(BaseModel):
    """Investitionskosten nach Kategorie. Alle Werte in EUR (Gesamtbetrag,
    nicht spezifisch), damit die Eingabe unmittelbar einem Angebot/einer
    Kostenschaetzung entspricht."""

    epc_eur: float = 0.0
    netzanschluss_eur: float = 0.0
    trasse_eur: float = 0.0
    sonstige_extern_eur: float = 0.0
    agm_eur: float = 0.0
    m_and_a_eur: float = 0.0
    poenale_puffer_eur: float = 0.0

    @property
    def summe_eur(self) -> float:
        return (
            self.epc_eur
            + self.netzanschluss_eur
            + self.trasse_eur
            + self.sonstige_extern_eur
            + self.agm_eur
            + self.m_and_a_eur
            + self.poenale_puffer_eur
        )


class PVProject(BaseModel):
    """Die Projektmaske. Bewusst schlank gehalten - Ziel ist eine Anlage
    in unter zwei Minuten. Alles Uebrige kommt aus GlobalAssumptions."""

    id: str
    name: str
    inbetriebnahme_jahr: int = Field(default_factory=lambda: datetime.now().year + 1)

    # Technische Anlagenparameter
    anlagentyp: AnlagenTyp
    nennleistung_kwp: float = Field(gt=0)
    vollbenutzungsstunden_kwh_kwp: float = Field(gt=0)

    # Wirtschaftliche Parameter
    pacht_eur_kwp_jahr: float = Field(ge=0)
    fremdkapitalzins_pct: float = Field(ge=0)
    eigenkapitalquote_pct: float = Field(ge=0, le=1)
    eag_zuschlagswert_ct_kwh: float = Field(gt=0)

    # Investkosten
    capex: CapexBreakdown = Field(default_factory=CapexBreakdown)

    @property
    def eag_zuschlagswert_effektiv_ct_kwh(self) -> float:
        """Wendet die Geschaeftsregel an: Konventionell -> 25% Abschlag."""
        if self.anlagentyp == AnlagenTyp.KONVENTIONELL:
            return self.eag_zuschlagswert_ct_kwh * (
                1 - KONVENTIONELL_ZUSCHLAG_ABSCHLAG_PCT
            )
        return self.eag_zuschlagswert_ct_kwh


# ---------------------------------------------------------------------------
# Globale Annahmen (Layer 1) - selten geaendert, fuer alle Projekte gueltig
# ---------------------------------------------------------------------------


class OpexItem(BaseModel):
    name: str
    basiswert_eur_kwp: float = 0.0
    start_betriebsjahr: int = 1
    index_pct_pa: float = 0.0
    indexierung_ab_jahr: int = 1


class GlobalAssumptions(BaseModel):
    gueltig_ab: str = ""

    # Preiskurven (Jahr = Betriebsjahr ab Inbetriebnahme, 1-indiziert)
    marktwert_solar_ct_kwh_je_jahr: dict[int, float] = Field(default_factory=dict)
    anteil_negativer_stunden_pct_je_jahr: dict[int, float] = Field(
        default_factory=dict
    )

    # Standardbetriebskosten (Pacht kommt separat aus dem Projekt)
    opex_standard: list[OpexItem] = Field(default_factory=list)

    # Technische Standardannahmen
    degradation_pct_pa: float = 0.0
    sicherheitsabschlag_pct: float = 0.0

    # Foerder- und Betrachtungsdauer
    eag_foerderdauer_jahre: int = Field(gt=0, default=20)
    betriebsdauer_jahre: int = Field(gt=0, default=25)

    # Finanzierung
    kreditlaufzeit_jahre: int = Field(gt=0, default=15)
    tilgungsart: TilgungsArt = TilgungsArt.ANNUITAET

    # Steuer
    tax_modus: TaxModus = TaxModus.PAUSCHAL_AUF_EBT
    steuersatz_pct: float = Field(ge=0, le=1, default=0.25)
    afa_nutzungsdauer_jahre: int | None = None
    freibetrag_eur: float = 0.0

    @model_validator(mode="after")
    def check_afa_fields(self) -> "GlobalAssumptions":
        if (
            self.tax_modus == TaxModus.AFA_KOERPERSCHAFTSTEUER
            and self.afa_nutzungsdauer_jahre is None
        ):
            raise ValueError(
                "afa_nutzungsdauer_jahre erforderlich bei tax_modus=afa_koerperschaftsteuer"
            )
        return self


# ---------------------------------------------------------------------------
# Ergebnis von resolve_assumptions() - vollstaendig aufgeloester Parametersatz
# ---------------------------------------------------------------------------


class EffectiveAssumptions(BaseModel):
    source_project_id: str
    inbetriebnahme_jahr: int
    nennleistung_kwp: float
    vollbenutzungsstunden_kwh_kwp: float
    degradation_pct_pa: float
    sicherheitsabschlag_pct: float

    eag_zuschlagswert_effektiv_ct_kwh: float
    eag_foerderdauer_jahre: int
    betriebsdauer_jahre: int
    marktwert_solar_ct_kwh_je_jahr: dict[int, float]
    anteil_negativer_stunden_pct_je_jahr: dict[int, float]

    opex_items: list[OpexItem]

    capex_total_eur: float
    eigenkapitalquote_pct: float
    fremdkapitalzins_pct: float
    kreditlaufzeit_jahre: int
    tilgungsart: TilgungsArt

    tax_modus: TaxModus
    steuersatz_pct: float
    afa_nutzungsdauer_jahre: int | None
    freibetrag_eur: float


class KPIs(BaseModel):
    equity_irr: float | None
    npv_eur: float
    payback_jahre: float | None
    capex_total_eur: float
