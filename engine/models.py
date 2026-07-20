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


class DirektvermarktungsModus(str, Enum):
    """Bemessung der Direktvermarktungskosten (Bilanzkreis, Prognose,
    Marktzugang).

    ABSOLUT:           fester Betrag je erzeugter MWh (Projektfeld
                       direktvermarktungskosten_eur_mwh), z.B. 1 EUR/MWh.
    RELATIV_MARKTWERT: Anteil am nominalen Jahresmarktwert je erzeugter
                       kWh (globaler Prozentsatz), z.B. 10 % vom Marktwert -
                       die Kosten atmen dann mit dem Preisniveau.
    """

    ABSOLUT = "absolut"
    RELATIV_MARKTWERT = "relativ_marktwert"


class NegativeStundenRegel(str, Enum):
    """Regel, ab welcher Dauer zusammenhaengend negativer Preise die
    Marktpraemie entfaellt - bestimmt, welche der beiden Negativmengen-
    Zeitreihen eines Szenarios angewendet wird.

    SECHS_STUNDEN: Praemie entfaellt erst, wenn mindestens 6 Stunden am
                   Stueck negative Preise auftreten (Standard Oesterreich,
                   EAG).
    EINE_STUNDE:   Praemie entfaellt bereits ab 1 Stunde am Stueck
                   negativer Preise (Regelung Deutschland) - die
                   betroffene Erzeugungsmenge ist entsprechend groesser.
    """

    SECHS_STUNDEN = "6h"
    EINE_STUNDE = "1h"


class NegativeStundenModus(str, Enum):
    """Verhalten der Anlage in Stunden negativer Strompreise (in denen die
    Marktpraemie gesetzlich entfaellt).

    ABREGELUNG: Die Anlage wird abgeregelt - fuer den Anteil negativer
    Stunden entfallen die Erloese vollstaendig.
    MARKTWERT:  Die Anlage speist weiter ein - fuer den Anteil negativer
    Stunden entfaellt nur die Marktpraemie, der Jahresmarktwert wird
    weiterhin verguetet.
    """

    MARKTWERT = "marktwert"
    ABREGELUNG = "abregelung"


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
    widmung_eur: float = 0.0
    genehmigung_eur: float = 0.0
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
            + self.widmung_eur
            + self.genehmigung_eur
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
    # Inaktive Projekte bleiben erhalten, werden aber aus der Portfolio-
    # Analytik ausgeblendet und koennen aus den kumulierten KPIs
    # herausgerechnet werden - Pipeline-Bereinigung ohne Loeschen.
    aktiv: bool = True
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
    # Kosten der Direktvermarktung (Bilanzkreis, Prognose, Marktzugang),
    # ueblicherweise ca. 0,1 ct/kWh = 1 EUR/MWh.
    direktvermarktungskosten_eur_mwh: float = Field(ge=0, default=1.0)

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
    # Erzeugungsmenge in Stunden negativer Preise, als Anteil (0-1) der
    # PV-Jahreserzeugung - je Regel eine eigene Zeitreihe. Die 1h-Regel
    # erfasst mehr Stunden und damit groessere Mengen als die 6h-Regel.
    erzeugungsmenge_negativ_6h_pct_je_kalenderjahr: dict[int, float] = Field(
        default_factory=dict
    )
    erzeugungsmenge_negativ_1h_pct_je_kalenderjahr: dict[int, float] = Field(
        default_factory=dict
    )

    @model_validator(mode="before")
    @classmethod
    def _migriere_legacy_negativkurve(cls, data):
        """Aeltere Datenstaende (YAML/Direktkonstruktion) kennen nur EINE
        Negativkurve unter 'anteil_negativer_stunden_pct_je_kalenderjahr'.
        Sie wird in beide Regel-Zeitreihen uebernommen (fachlich: gleiche
        Annahme fuer 6h und 1h, solange keine getrennten Daten vorliegen).
        """
        if isinstance(data, dict):
            legacy = data.pop("anteil_negativer_stunden_pct_je_kalenderjahr", None)
            if legacy is not None:
                data.setdefault(
                    "erzeugungsmenge_negativ_6h_pct_je_kalenderjahr", legacy
                )
                data.setdefault(
                    "erzeugungsmenge_negativ_1h_pct_je_kalenderjahr", dict(legacy)
                )
        return data

    def erzeugungsmenge_negativ(
        self, regel: NegativeStundenRegel
    ) -> dict[int, float]:
        """Die zur Regel gehoerende Negativmengen-Zeitreihe."""
        if regel == NegativeStundenRegel.EINE_STUNDE:
            return self.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr
        return self.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr


class GlobalAssumptions(BaseModel):
    gueltig_ab: str = ""

    # Mehrere benannte Marktpreisszenarien zur Auswahl je Projekt (siehe
    # PVProject.marktpreisszenario). Nach Kalenderjahr indiziert.
    marktpreisszenarien: list[MarktpreisSzenario] = Field(default_factory=list)

    # Die Marktwert-Solar-Kurven aus Marktpreisstudien (Aurora/Enervis) sind
    # typischerweise REALE Werte auf Preisbasis des Studien-Erscheinungsjahrs
    # (marktpreis_inflation_basisjahr), keine bereits inflationierten
    # Nominalwerte. Fuer eine nominale Cashflow-Rechnung wird deshalb ein
    # Inflationsaufschlag ab diesem Basisjahr angewendet: nominal(jahr) =
    # real(jahr) * (1+inflation)^(jahr - basisjahr). Der EAG-Zuschlagswert
    # ist davon bewusst NICHT betroffen - er ist waehrend der Foerderdauer
    # gesetzlich nominal fix, keine Indexierung.
    marktpreis_inflation_pct_pa: float = Field(ge=0, default=0.02)
    marktpreis_inflation_basisjahr: int = Field(default=2025)

    # Allgemeine Kosteninflation: wirkt auf ALLE Kostenpositionen ohne
    # eigene Preislogik - Pacht, Gemeindeabgabe und Direktvermarktungs-
    # kosten (absoluter Modus) eskalieren damit ab dem 2. Betriebsjahr
    # (Eingaben = Preisstand bei Inbetriebnahme). Die Standard-OPEX-
    # Positionen tragen ihre eigene, sichtbare Indexierung (Vorbelegung
    # ebenfalls 2 %/a ab Jahr 1); Direktvermarktung im Relativ-Modus
    # folgt bereits dem nominalen Marktwert.
    kosten_inflation_pct_pa: float = Field(ge=0, default=0.02)

    # Regel fuer den Praemienentfall bei negativen Preisen (6h = Standard
    # Oesterreich/EAG, 1h = Regelung Deutschland). Bestimmt, welche
    # Negativmengen-Zeitreihe der Szenarien angewendet wird.
    negative_stunden_regel: NegativeStundenRegel = NegativeStundenRegel.SECHS_STUNDEN

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
    # Direktvermarktungskosten-Vorschlagswert (analog Gemeindeabgabe): dient
    # nur als Vorbelegung im "Neues Projekt"-Formular, tatsaechlich
    # angewendet wird PVProject.direktvermarktungskosten_eur_mwh.
    direktvermarktungskosten_eur_kwh: float = Field(ge=0, default=0.001)
    # Bemessungsmodus der Direktvermarktungskosten (gilt fuer alle
    # Projekte). Im Modus RELATIV_MARKTWERT ersetzt der Prozentsatz die
    # projektspezifischen EUR/MWh-Werte.
    direktvermarktung_modus: DirektvermarktungsModus = DirektvermarktungsModus.ABSOLUT
    direktvermarktung_pct_marktwert: float = Field(ge=0, le=1, default=0.10)

    # Gewichtung des Anteils negativer Stunden (0% = wird komplett
    # ignoriert, d.h. volle Verguetung auch in Stunden negativer Preise;
    # 100% = volle gesetzliche Wirkung wie in den Preiskurven hinterlegt).
    # Dient zum "Einblenden" des Effekts, z.B. fuer Sensitivitaets- oder
    # Vergleichsrechnungen ohne diesen Abschlag.
    negative_stunden_gewichtung_pct: float = Field(ge=0, le=1, default=1.0)
    negative_stunden_modus: NegativeStundenModus = NegativeStundenModus.MARKTWERT

    # Technische Standardannahmen
    degradation_pct_pa: float = 0.0
    sicherheitsabschlag_pct: float = 0.0

    # Foerder- und Betrachtungsdauer
    eag_foerderdauer_jahre: int = Field(gt=0, default=20)
    betriebsdauer_jahre: int = Field(gt=0, default=25)

    # Finanzierung
    kreditlaufzeit_jahre: int = Field(gt=0, default=20)
    tilgungsart: TilgungsArt = TilgungsArt.ANNUITAET
    #: Jahr 1 nur Zinsen, Tilgung ab Jahr 2 (verlaengert den
    #: Schuldendienst um ein Jahr, Anzahl der Tilgungsraten bleibt gleich).
    tilgungsfreies_anlaufjahr: bool = False

    # Steuer
    tax_modus: TaxModus = TaxModus.AFA_KOERPERSCHAFTSTEUER
    steuersatz_pct: float = Field(ge=0, le=1, default=0.25)
    afa_nutzungsdauer_jahre: int | None = None
    freibetrag_eur: float = 0.0
    # Verlustvortrag (§8 Abs. 4 Z 2 KStG): zeitlich unbegrenzt vortragbar,
    # aber pro Gewinnjahr nur bis verlustvortrag_verrechnungsgrenze_pct des
    # steuerlichen Ergebnisses verrechenbar (siehe tax.py). Kein "Ein/Aus"-
    # Schalter, da Verlustvortrag gesetzlich vorgeschrieben ist - Kontrolle
    # erfolgt ausschliesslich ueber die Verrechnungsgrenze selbst.
    verlustvortrag_verrechnungsgrenze_pct: float = Field(ge=0, le=1, default=0.75)

    @model_validator(mode="after")
    def check_afa_fields(self) -> GlobalAssumptions:
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
    # Aufgeloeste Negativmengen-Kurve gemaess gewaehlter Regel (6h/1h).
    anteil_negativer_stunden_pct_je_kalenderjahr: dict[int, float]
    negative_stunden_regel: NegativeStundenRegel
    marktpreis_inflation_pct_pa: float
    marktpreis_inflation_basisjahr: int
    kosten_inflation_pct_pa: float

    opex_items: list[OpexItem]
    gemeindeabgabe_eur_kwh: float
    direktvermarktungskosten_eur_kwh: float
    direktvermarktung_modus: DirektvermarktungsModus
    direktvermarktung_pct_marktwert: float
    negative_stunden_gewichtung_pct: float
    negative_stunden_modus: NegativeStundenModus

    capex_total_eur: float
    eigenkapitalquote_pct: float
    fremdkapitalzins_pct: float
    kreditlaufzeit_jahre: int
    tilgungsart: TilgungsArt
    tilgungsfreies_anlaufjahr: bool

    tax_modus: TaxModus
    steuersatz_pct: float
    afa_nutzungsdauer_jahre: int | None
    freibetrag_eur: float
    verlustvortrag_verrechnungsgrenze_pct: float


class KPIs(BaseModel):
    """Kern-Kennzahlen eines Projekts aus Eigenkapitalsicht."""

    equity_irr: float | None
    npv_eur: float
    payback_jahre: float | None
    capex_total_eur: float
    #: Eigenkapitaleinsatz im Jahr 0 (CAPEX abzueglich Kreditaufnahme).
    eigenkapital_eur: float = 0.0
    dscr_min: float | None = None
