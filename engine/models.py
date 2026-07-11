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
    inbetriebnahme_monat: int = Field(ge=1, le=12, default=1)

    # Technische Anlagenparameter
    anlagentyp: AnlagenTyp
    nennleistung_kwp: float = Field(gt=0)
    vollbenutzungsstunden_kwh_kwp: float = Field(gt=0)

    # Wirtschaftliche Parameter
    pacht_eur_kwp_jahr: float = Field(ge=0)
    fremdkapitalzins_pct: float = Field(ge=0)
    eigenkapitalquote_pct: float = Field(ge=0, le=1)
    eag_zuschlagswert_ct_kwh: float = Field(gt=0)
    gemeindeabgabe_eur_mwh: float = Field(ge=0, default=2.0)

    # Investkosten
    capex: CapexBreakdown = Field(default_factory=CapexBreakdown)

    # Wahl des Marktpreisszenarios (siehe GlobalAssumptions.marktpreisszenarien).
    # "Aurora 10/25" ist das Standardszenario.
    marktpreisszenario: str = "Aurora 10/25"

    # Nur relevant, wenn Pacht zuletzt in €/ha/Jahr eingegeben wurde - dient
    # der Rueckumrechnung beim erneuten Oeffnen des €/ha-Eingabemodus.
    projektflaeche_ha: float | None = None

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


class MarktpreisSzenario(BaseModel):
    """Eine benannte Marktpreis-Prognose (z.B. 'Aurora 10/25'). Kurven sind
    nach echtem KALENDERJAHR indiziert (nicht nach Betriebsjahr) - beim
    Zuweisen zu einem Projekt wird ueber dessen Inbetriebnahmejahr auf die
    passende Stelle der Kurve gemappt (siehe pipeline.resolve_assumptions
    und revenue.calculate_revenue)."""

    name: str
    marktwert_solar_ct_kwh_je_kalenderjahr: dict[int, float] = Field(
        default_factory=dict
    )
    anteil_negativer_stunden_pct_je_kalenderjahr: dict[int, float] = Field(
        default_factory=dict
    )


class GlobalAssumptions(BaseModel):
    gueltig_ab: str = ""

    # Mehrere benannte Marktpreisszenarien zur Auswahl je Projekt (siehe
    # PVProject.marktpreisszenario). Nach Kalenderjahr indiziert.
    marktpreisszenarien: list[MarktpreisSzenario] = Field(default_factory=list)

    # Standardbetriebskosten (Pacht kommt separat aus dem Projekt)
    opex_standard: list[OpexItem] = Field(default_factory=list)

    # Gemeindeabgabe: pro erzeugter kWh an die Standortgemeinde, unabhaengig
    # von der Anlagengroesse. Deshalb kein OpexItem (das ist EUR/kWp/Jahr-
    # basiert), sondern ein eigener Produktions-basierter Satz.
    # Gemeindeabgabe-Vorschlagswert: dient nur als Vorbelegung im
    # "Neues Projekt"-Formular. Die tatsaechlich angewendete Abgabe ist
    # projektspezifisch (siehe PVProject.gemeindeabgabe_eur_mwh), da sie je
    # nach Standortgemeinde variieren kann.
    gemeindeabgabe_eur_kwh: float = Field(ge=0, default=0.002)

    # Technische Standardannahmen
    degradation_pct_pa: float = 0.0
    sicherheitsabschlag_pct: float = 0.0

    # Foerder- und Betrachtungsdauer
    eag_foerderdauer_jahre: int = Field(gt=0, default=20)
    betriebsdauer_jahre: int = Field(gt=0, default=25)

    # Finanzierung
    kreditlaufzeit_jahre: int = Field(gt=0, default=20)
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

    def get_szenario(self, name: str) -> MarktpreisSzenario | None:
        for szenario in self.marktpreisszenarien:
            if szenario.name == name:
                return szenario
        return None

    @property
    def szenario_namen(self) -> list[str]:
        return [s.name for s in self.marktpreisszenarien]


# ---------------------------------------------------------------------------
# Ergebnis von resolve_assumptions() - vollstaendig aufgeloester Parametersatz
# ---------------------------------------------------------------------------


class EffectiveAssumptions(BaseModel):
    source_project_id: str
    inbetriebnahme_jahr: int
    inbetriebnahme_monat: int
    nennleistung_kwp: float
    vollbenutzungsstunden_kwh_kwp: float
    degradation_pct_pa: float
    sicherheitsabschlag_pct: float

    eag_zuschlagswert_effektiv_ct_kwh: float
    eag_foerderdauer_jahre: int
    betriebsdauer_jahre: int
    marktpreisszenario_name: str
    marktwert_solar_ct_kwh_je_kalenderjahr: dict[int, float]
    anteil_negativer_stunden_pct_je_kalenderjahr: dict[int, float]

    opex_items: list[OpexItem]
    gemeindeabgabe_eur_kwh: float

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
    dscr_min: float | None = None
