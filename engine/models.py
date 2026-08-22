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

import math
from datetime import datetime
from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class AnlagenTyp(str, Enum):
    AGRI_PV = "agri_pv"
    KONVENTIONELL = "konventionell"


# Geschaeftsregel: Konventionelle Anlagen erhalten einen Abschlag auf den
# EAG-Zuschlagswert gegenueber Agri-PV. Bewusst als benannte Konstante
# (nicht als Nutzereingabe) - das ist eine Geschaeftsregel, kein Parameter.
KONVENTIONELL_ZUSCHLAG_ABSCHLAG_PCT = 0.25


class MarktSystem(str, Enum):
    """Marktsystematik der Bewertung - bestimmt als globaler Schalter,
    welche laenderspezifischen Regeln als Paket gelten.

    OESTERREICH: EAG-Marktpraemienmodell - 6h-Regel fuer den
                 Praemienentfall, Koerperschaftsteuer mit AfA,
                 Zinsmethode act/365, empirisches Ausschreibungsmodell
                 (OeMAG-Historie, Kurven-Fitting, Prognose).
    DEUTSCHLAND: EEG-Marktpraemienmodell - 1h-Regel, deutsche
                 Gewerbesteuer, Zinsmethode 30/360; statt des
                 empirischen Ausschreibungsmodells wird der erwartete
                 Marktpraemienzuschlag (anzulegender Wert) manuell
                 vorgegeben (de_marktpraemie_erwartet_ct_kwh).
    """

    OESTERREICH = "oesterreich"
    DEUTSCHLAND = "deutschland"


class TilgungsArt(str, Enum):
    ANNUITAET = "annuitaet"
    LINEAR = "linear"


class ZinsMethode(str, Enum):
    """Zinsberechnungsmethode fuer das (moeglicherweise unterjaehrige)
    erste Betriebsjahr - fuer volle Kalenderjahre liefern beide
    Methoden dieselbe Zinslast (Faktor 1,0), der Unterschied wirkt sich
    nur aus, wenn die Inbetriebnahme nicht am 1. Januar erfolgt.

    OESTERREICH: taggenau, act/365 (Anzahl Kalendertage seit
    Inbetriebnahme bis Jahresende / 365) - deckt sich mit der ohnehin
    bereits fuer die Produktion verwendeten Zeitachse (siehe
    engine.timeline.build_timeline). Nach staendiger oesterreichischer
    Rechtsprechung (OGH) fuer Unternehmen ohne abweichende Vereinbarung
    ueblich.

    DEUTSCH: kaufmaennische Methode 30/360 - jeder Monat zaehlt
    pauschal mit 30 Tagen, das Jahr mit 360 Tagen; Bruch = Restmonate
    im Anlaufjahr (inkl. Inbetriebnahmemonat) / 12. Historischer
    deutscher Bankenstandard.
    """

    OESTERREICH = "oesterreich_act_365"
    DEUTSCH = "deutsch_30_360"


class PachtModus(str, Enum):
    """Bemessung der Pacht.

    FIX: fester Betrag je installierter kWp/Jahr (Projektfeld
    pacht_eur_kwp_jahr) - unveraendert das bisherige Verhalten.

    UMSATZBETEILIGUNG: der Verpaechter erhaelt einen Anteil am
    Jahresumsatz (pacht_umsatzbeteiligung_pct, ueblich 5,5 %),
    mindestens aber eine fixe Mindestpacht je Hektar
    (pacht_mindestpacht_eur_ha_jahr x projektflaeche_ha, mit der
    allgemeinen Kosteninflation indexiert). Gerade in spaeteren
    Betriebsjahren kann die stetig steigende Mindestpacht die
    Umsatzbeteiligung uebersteigen (EAG-Foerderende, Degradation).
    """

    FIX = "fix"
    UMSATZBETEILIGUNG = "umsatzbeteiligung"


class DirektvermarktungsModus(str, Enum):
    """Bemessung der Direktvermarktungskosten (Bilanzkreis, Prognose,
    Marktzugang).

    ABSOLUT:              fester Betrag je erzeugter MWh (Projektfeld
                          direktvermarktungskosten_eur_mwh), z.B. 1 EUR/MWh.
    RELATIV_GROSSHANDEL:  Anteil am nominalen Grosshandelspreis (Baseload)
                          des Szenarios, marktueblich rund 10 %. Der
                          Dienstleister rechnet gegen den Spotmarkt ab,
                          nicht gegen den technologiespezifischen
                          Marktwert - deshalb ist das der uebliche Bezug.
                          Fehlt dem Szenario eine Baseload-Kurve (aeltere
                          Bestaende), gilt ersatzweise der Marktwert.
    RELATIV_MARKTWERT:    Anteil am nominalen Marktwert Solar. Bezieht die
                          Kosten auf den tatsaechlich erzielten Preis der
                          Anlage; fuer PV faellt das niedriger aus als der
                          Baseload-Bezug.
    """

    ABSOLUT = "absolut"
    RELATIV_GROSSHANDEL = "relativ_grosshandel"
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


class Zeitaufloesung(str, Enum):
    """Auf welcher Ebene Erzeugung und Marktwerte zusammengefuehrt werden.

    JAHR:  Eine Jahresmenge trifft auf einen Jahresmarktwert - die
           bisherige Rechnung. Sie unterstellt, dass jede Kilowattstunde
           denselben Preis erloest.
    MONAT: Die Jahresmenge wird ueber die Einspeisekurve auf zwoelf
           Monate verteilt und trifft dort auf Monatsmarktwerte. Das ist
           der Regelfall der Realitaet: PV erzeugt im Sommer viel und
           erloest dann wenig - eine Jahresrechnung ueberschaetzt den
           Erloes deshalb systematisch (Kannibalisierung).

    Der Cashflow bleibt in beiden Faellen jaehrlich; die Monatsebene ist
    eine Unterebene der Erloesrechnung. Finanzierung, Steuer und DSCR
    arbeiten weiterhin auf Jahresscheiben.
    """

    JAHR = "jahr"
    MONAT = "monat"


class PraemienModell(str, Enum):
    """Vertragsform der Foerderung - siehe engine/revenue.py.

    EINSEITIG_CFD: Verguetung = MAX(Marktwert, anzulegender Wert). Liegt
        der Markt darunter, wird aufgezahlt; liegt er darueber, behaelt
        der Betreiber den hoeheren Marktwert. Bisheriges Verhalten und
        die Grundform der EAG-Marktpraemie.
    ZWEISEITIG_CFD: Verguetung = anzulegender Wert. Ueberschreitungen
        gehen vollstaendig zurueck an die Foerderstelle - der Betreiber
        hat keine Preischance nach oben, dafuer kein Preisrisiko nach
        unten (Differenzvertrag im engeren Sinn, Richtung EEG 2027).
    EAG_TOLERANZBAND: Einseitiger CfD mit Rueckzahlung erst oberhalb
        eines Toleranzbandes - die oesterreichische Regelung nach
        § 10 EAG: Uebersteigt der Referenzmarktwert den anzulegenden
        Wert um mehr als 40 %, sind 66 % des uebersteigenden Teils
        zurueckzuzahlen; fuer Photovoltaik gilt das ab 5 MW
        Engpassleistung. Alle drei Groessen sind einstellbar, weil sie
        Gegenstand laufender Novellen sind.
    """

    EINSEITIG_CFD = "einseitig_cfd"
    ZWEISEITIG_CFD = "zweiseitig_cfd"
    EAG_TOLERANZBAND = "eag_toleranzband"


class TaxModus(str, Enum):
    PAUSCHAL_AUF_EBT = "pauschal_auf_ebt"
    #: Oesterreichische Koerperschaftsteuer: AfA, Freibetrag,
    #: Verlustvortrag mit 75%-Verrechnungsgrenze (§8 Abs. 4 Z 2 KStG).
    AFA_KOERPERSCHAFTSTEUER = "afa_koerperschaftsteuer"
    #: Deutsche Gewerbesteuer: AfA, gesetzlicher Freibetrag (24.500 EUR
    #: bei Personengesellschaften), Satz = 3,5% x Hebesatz, OHNE
    #: Verlustvortrag - siehe engine.tax fuer Details/Einschraenkungen.
    GEWERBESTEUER_DE = "gewerbesteuer_de"


# ---------------------------------------------------------------------------
# Projektmaske (Layer 2) - das sieht der Projektentwickler beim Anlegen
# ---------------------------------------------------------------------------


#: Spaltennamen der Cashflow-Zeitreihe, die eine frei benannte
#: Kostenposition NICHT tragen darf - sie wuerde die gleichnamige
#: Ergebnisspalte ueberschreiben (siehe engine/cashflow.py).
RESERVIERTE_POSITIONSNAMEN = frozenset(
    {
        "jahr", "datum", "produktion_kwh", "marktwert_real_ct_kwh",
        "marktwert_nominal_ct_kwh", "verguetungssatz_ct_kwh", "erloes_eur",
        "erloes_markt_eur", "erloes_praemie_eur", "erloes_ppa_eur",
        "erloes_merchant_eur", "rueckzahlung_eur",
        "baseload_nominal_ct_kwh", "opex_gesamt_eur",
        "gemeindeabgabe_eur", "direktvermarktungskosten_eur", "zinsen_eur",
        "tilgung_eur", "afa_eur",
        "steuerliches_ergebnis_vor_verlustvortrag_eur",
        "verlustvortrag_genutzt_eur", "verlustvortrag_bestand_eur",
        "steuerliches_ergebnis_eur", "steuer_eur", "cf_operativ_eur",
        "cf_invest_eur", "cf_finanzierung_eur", "cf_gesamt_eur",
        "cf_kumuliert_eur", "dscr",
    }
)


def pruefe_positionsname(name: str) -> str:
    """Validiert den frei vergebenen Namen einer Kostenposition.

    Jede Betriebskostenposition wird zu einer eigenen Spalte der
    Cashflow-Zeitreihe (siehe engine/opex.py). Ein Name, der auf eine
    Ergebnisspalte faellt, wuerde diese ueberschreiben - deshalb wird er
    hier abgelehnt statt still Schaden anzurichten.
    """
    bereinigt = name.strip()
    if not bereinigt:
        raise ValueError("Der Name einer Kostenposition darf nicht leer sein.")
    if bereinigt.lower() in RESERVIERTE_POSITIONSNAMEN:
        raise ValueError(
            f"'{bereinigt}' ist ein reservierter Spaltenname der "
            "Cashflow-Zeitreihe und als Positionsname nicht zulaessig."
        )
    return bereinigt


class OpexItem(BaseModel):
    """Eine Betriebskostenposition (EUR je kWp und Jahr).

    Der Name wird zum Spaltennamen der Cashflow-Zeitreihe und damit zum
    Legendeneintrag im gestapelten Kostendiagramm - er wird deshalb gegen
    die reservierten Ergebnisspalten geprueft."""

    name: str
    basiswert_eur_kwp: float = 0.0
    start_betriebsjahr: int = 1
    index_pct_pa: float = 0.0
    indexierung_ab_jahr: int = 1

    @model_validator(mode="after")
    def _name_pruefen(self) -> OpexItem:
        self.name = pruefe_positionsname(self.name)
        return self


class CapexPosition(BaseModel):
    """Frei benannte, zusaetzliche Investitionskostenposition.

    CAPEX geht ausschliesslich als SUMME in die Rechnung ein (siehe
    pipeline.resolve_assumptions); zusaetzliche Positionen veraendern
    daher keine Formel, sondern nur die Aufgliederung in Maske, Diagramm
    und Bericht.
    """

    name: str
    betrag_eur: float = 0.0

    @model_validator(mode="after")
    def _name_pruefen(self) -> CapexPosition:
        self.name = pruefe_positionsname(self.name)
        return self


class CapexBreakdown(BaseModel):
    """Investitionskosten nach Kategorie. Alle Werte in EUR (Gesamtbetrag,
    nicht spezifisch), damit die Eingabe unmittelbar einem Angebot/einer
    Kostenschaetzung entspricht.

    Neben den festen Kategorien koennen beliebig viele frei benannte
    Positionen ergaenzt werden (siehe CapexPosition)."""

    epc_eur: float = 0.0
    netzanschluss_eur: float = 0.0
    trasse_eur: float = 0.0
    widmung_eur: float = 0.0
    genehmigung_eur: float = 0.0
    sonstige_extern_eur: float = 0.0
    agm_eur: float = 0.0
    m_and_a_eur: float = 0.0
    poenale_puffer_eur: float = 0.0
    #: Frei benannte Zusatzpositionen des Projekts.
    zusatzpositionen: list[CapexPosition] = Field(default_factory=list)

    @property
    def summe_eur(self) -> float:
        return sum(p.betrag_eur for p in self.zusatzpositionen) + (
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


#: Monatsertrag in kWh, Januar bis Dezember - die Quelle der
#: Einspeisekurven. Monatssummen der Stundenreihen unter data/lastgang/,
#: je Bauform eine: Auslegungssimulationen aus RatedPower fuer ein
#: eigenes Projekt, dieselbe Anlage einmal fest aufgestaendert und
#: einmal einachsig nachgefuehrt.
#:
#: ACHTUNG - die HOEHEN sind zwischen den beiden Reihen nicht
#: vergleichbar: Sie stammen aus verschieden grossen Auslegungen (58.845
#: gegen 32.399 kWh, Spitze 39,0 gegen 16,2 kW). Ein Nachfuehrgewinn
#: laesst sich daraus nicht ableiten. Fuer die Rechnung zaehlt ohnehin
#: nur die FORM: Die Jahresmenge kommt aus Leistung und
#: Vollbenutzungsstunden des Projekts.
#:
#: Warum nicht PVGIS: Bis v5.20 standen hier Werte aus einer
#: PVGIS-Abfrage. Sie wiesen dem Winter (Nov-Feb) 24,4 % der
#: Jahreserzeugung zu - die Simulation der realen Anlage sagt 13,5 %.
#: Die Gegenprobe entscheidet: Mit der PVGIS-Kurve ergeben Auroras
#: Monatsmarktwerte einen Jahresmarktwert, der Auroras eigenen
#: Jahreswert um 12 bis 22 % uebersteigt; mit dieser Kurve bleibt die
#: Abweichung zwischen -2 und +4 %. Die PVGIS-Abfrage duerfte eine sehr
#: steile Aufstaenderung getroffen haben (ihre Sommermonate liegen
#: auffaellig flach bei 111-122 kWh/kWp).
#:
#: Die Rohwerte stehen hier und nicht schon normiert, weil sie damit
#: nachpruefbar bleiben - tests/test_lastgang.py rechnet sie aus den
#: Stundenreihen nach.
MONATSERTRAG_KWH_JE_BAUFORM: dict[str, list[float]] = {
    "Pult": [
        1272.8, 2693.0, 4264.6, 8021.2, 7076.0, 7041.9,
        7384.2, 8187.8, 6041.5, 2898.2, 1675.0, 2289.0,
    ],
    "Tracker": [
        635.7, 1431.3, 2246.0, 4257.8, 4074.2, 4165.7,
        4243.7, 4466.7, 3201.8, 1620.7, 855.6, 1199.8,
    ],
}


def _normiert(werte: list[float]) -> list[float]:
    """Anteile mit Summe 1 - die Hoehe der Reihe ist gleichgueltig."""
    gesamt = sum(werte)
    return [w / gesamt for w in werte]


#: Einspeisekurven je Bauform: Anteil der Jahreserzeugung je Monat
#: (Januar bis Dezember), Summe 1. Normiert aus den Monatsertraegen
#: darueber.
#:
#: Der Tracker ist etwas sommerlastiger als das Pult - fuer die
#: Monatsrechnung wesentlich, weil die Sommermonate die niedrigeren
#: Marktwerte tragen. Der groessere Unterschied liegt aber im TAGESGANG,
#: den diese Kurve gar nicht abbildet: Aus denselben Stundenreihen
#: gerechnet hat das Pult einen scharfen Mittagspeak (13,4 % der
#: Jahreserzeugung um 11 und um 12 Uhr), der Tracker ein Plateau von
#: 9 bis 14 Uhr bei rund 10 % und deutlich mehr Ertrag frueh und spaet
#: (6 Uhr: 2,7 gegen 0,9 %; 17 Uhr: 4,9 gegen 2,3 %). Deshalb weist
#: Aurora dem Tracker einen hoeheren Marktwert zu - er trifft die
#: teureren Randstunden. In die Monatsrechnung geht das ueber die
#: Marktwertkurve des Szenarios ein, nicht ueber diese Anteile.
EINSPEISEKURVEN_JE_BAUFORM: dict[str, list[float]] = {
    bauform: _normiert(werte)
    for bauform, werte in MONATSERTRAG_KWH_JE_BAUFORM.items()
}

#: Bauform der Standardkurve - Pult, wie auch beim Aurora-Import
#: (io_aurora.TECHNOLOGIE_STANDARD).
EINSPEISEKURVE_STANDARD_BAUFORM = "Pult"

#: Standard-Einspeisekurve: die Pult-Kurve.
EINSPEISEKURVE_STANDARD_PCT = list(
    EINSPEISEKURVEN_JE_BAUFORM[EINSPEISEKURVE_STANDARD_BAUFORM]
)


class Projektannahmen(BaseModel):
    """Abweichungen dieses Projekts von den globalen Annahmen.

    Grundregel: **None heisst "folgt der Vorgabe"**. Ein Projekt
    speichert also NICHT den globalen Wert, sondern nur, dass es ihm
    folgt - sonst erreichte eine spaetere Aenderung der Vorgabe kein
    einziges Projekt mehr, und die globalen Annahmen waeren keine
    Vorgaben, sondern nur noch ein Anlagevorschlag.

    Zusammengefuehrt wird an genau einer Stelle:
    pipeline.resolve_assumptions(). Alles, was hier steht, hat dort
    Vorrang vor dem gleichnamigen Feld der GlobalAssumptions.

    Warum ein eigener Block und keine Felder direkt am PVProject: Die
    Regel "None = Vorgabe" gilt hier ausnahmslos, am PVProject dagegen
    nicht (dort ist z.B. projektflaeche_ha=None schlicht "keine
    Flaeche"). Ein eigener Block macht die Regel nachpruefbar und die
    YAML-Datei lesbar - gespeichert wird nur, was gesetzt ist.
    """

    model_config = ConfigDict(validate_assignment=True)

    # --- Kreditvertrag ------------------------------------------------------
    # Die Bank verhandelt je Projekt. Dass Eigenkapitalanteil und Zins
    # bisher am Projekt hingen, Laufzeit und Tilgungsart aber global
    # waren, hatte keinen fachlichen Grund - es ist derselbe Vertrag.
    kreditlaufzeit_jahre: int | None = Field(default=None, gt=0)
    tilgungsart: TilgungsArt | None = None
    tilgungsfreies_anlaufjahr: bool | None = None
    zinsmethode: ZinsMethode | None = None
    dscr_cash_trap: float | None = Field(default=None, ge=0)
    dscr_event_of_default: float | None = Field(default=None, ge=0)

    # --- Steuern ------------------------------------------------------------
    # Haengt an Sitz und Rechtsform der Projektgesellschaft, nicht am
    # Portfolio: Eine deutsche Gesellschaft rechnet Gewerbesteuer, auch
    # wenn die uebrigen Projekte oesterreichisch sind.
    tax_modus: TaxModus | None = None
    steuersatz_pct: float | None = Field(default=None, ge=0, le=1)
    afa_nutzungsdauer_jahre: int | None = Field(default=None, gt=0)
    freibetrag_eur: float | None = Field(default=None, ge=0)
    gewerbesteuer_hebesatz_pct: float | None = Field(default=None, ge=0)
    gewerbesteuer_freibetrag_eur: float | None = Field(default=None, ge=0)
    verlustvortrag_verrechnungsgrenze_pct: float | None = Field(
        default=None, ge=0, le=1
    )

    # --- Anlage und Ertrag --------------------------------------------------
    degradation_pct_pa: float | None = Field(default=None, ge=0)
    sicherheitsabschlag_pct: float | None = Field(default=None, ge=0, le=1)
    betriebsdauer_jahre: int | None = Field(default=None, gt=0)
    #: Einspeisegrenze dieses Netzanschlusses (Anteil der kWp). Die
    #: Vorgabe von 70 % ist der Regelfall; ein einzelner Anschluss kann
    #: anders bemessen sein.
    einspeiselimit_pct: float | None = Field(default=None, gt=0, le=1)

    # --- Speicherpreise -----------------------------------------------------
    # Die Auslegung eines Speichers (Leistung, Kapazitaet, Betriebsart)
    # gehoert zum Projekt und steht in PVProject.battery. Was er KOSTET,
    # gehoert nicht dorthin: Batteriepreise sind eine Marktannahme, keine
    # Projekteigenschaft, und sie fallen Jahr fuer Jahr spuerbar. Stuenden
    # sie an der Auslegung, muesste eine Preissenkung in jedem einzelnen
    # Projekt nachgetragen werden.
    #
    # Hier gilt deshalb wie ueberall in diesem Block: None heisst "folgt
    # der Vorgabe". Liegt fuer ein Projekt ein Angebot vor, weicht es ab -
    # alle uebrigen folgen dem zentral gepflegten Marktpreis.
    speicher_capex_eur_kw: float | None = Field(default=None, ge=0)
    speicher_opex_eur_kw_jahr: float | None = Field(default=None, ge=0)

    # --- Foerdermodell und Vermarktung --------------------------------------
    praemien_modell: PraemienModell | None = None
    eag_foerderdauer_jahre: int | None = Field(default=None, gt=0)
    eag_rueckzahlung_ab_mw: float | None = Field(default=None, ge=0)
    eag_rueckzahlung_toleranzband_pct: float | None = Field(default=None, ge=0)
    eag_rueckzahlung_anteil_pct: float | None = Field(default=None, ge=0, le=1)
    negative_stunden_regel: NegativeStundenRegel | None = None
    negative_stunden_modus: NegativeStundenModus | None = None
    negative_stunden_gewichtung_pct: float | None = Field(
        default=None, ge=0, le=1
    )
    direktvermarktung_modus: DirektvermarktungsModus | None = None
    direktvermarktung_pct_marktwert: float | None = Field(
        default=None, ge=0, le=1
    )

    # --- Preis- und Kostenpfad ----------------------------------------------
    marktpreis_inflation_pct_pa: float | None = Field(default=None, ge=0)
    marktpreis_inflation_basisjahr: int | None = None
    kosten_inflation_pct_pa: float | None = Field(default=None, ge=0)

    # --- Betriebskosten -----------------------------------------------------
    #: Abweichende Basiswerte der GLOBALEN Standardpositionen, je
    #: Positionsname in EUR/kWp/Jahr. Frueh im Projekt sind das
    #: Erfahrungswerte, mit zunehmender Reife werden daraus Angebote -
    #: und die unterscheiden sich von Standort zu Standort erheblich.
    #:
    #: Bewusst ein dict statt einer Kopie der ganzen Liste: Eine neu
    #: aufgenommene globale Position erscheint dadurch in allen
    #: Projekten, eine geloeschte verschwindet ueberall, und im Projekt
    #: steht nur, was tatsaechlich verhandelt wurde. Der Preis ist die
    #: Bindung an den Namen - wird eine globale Position umbenannt,
    #: faellt das Projekt auf ihren Standardwert zurueck.
    opex_standard_eur_kwp: dict[str, float] = Field(default_factory=dict)

    @field_validator("opex_standard_eur_kwp")
    @classmethod
    def _keine_negativen_kosten(cls, werte):
        for name, wert in werte.items():
            if wert < 0:
                raise ValueError(f"Betriebskosten {name!r}: {wert} < 0")
        return werte

    @property
    def gesetzte_felder(self) -> list[str]:
        """Die Namen der tatsaechlich abweichenden Felder.

        Grundlage der Zaehlzeile in der Oberflaeche ("2 Abweichungen") -
        ohne sie faellt in einem halben Jahr niemandem mehr auf, dass
        dieses Projekt der Vorgabe nicht mehr folgt.
        """
        gesetzt = [
            name for name, wert in self
            if name != "opex_standard_eur_kwp" and wert is not None
        ]
        if self.opex_standard_eur_kwp:
            gesetzt.append("opex_standard_eur_kwp")
        return gesetzt


# ---------------------------------------------------------------------------
# Batteriespeicher (Co-Location)
# ---------------------------------------------------------------------------
#
# Die Auslegung steht HIER und nicht im Rechenpaket engine/storage/: Sie
# ist Teil des Projekts und wird mit ihm gespeichert - wie CapexBreakdown
# oder OpexItem. Was engine/storage/ besitzt, sind die ERGEBNISSE der
# Optimierung, und die werden nie persistiert.
#
# Diese Richtung der Abhaengigkeit ist zwingend: engine/storage/economics.py
# braucht die Foerderlogik aus diesem Modul. Laege die Auslegung dort,
# importierten sich beide Module gegenseitig.


class SpeicherModus(str, Enum):
    """Woraus der Speicher geladen werden darf.

    Die Unterscheidung ist keine Feinheit, sondern der Kern der
    wirtschaftlichen Bewertung: Ein Gruenstromspeicher hebt PV-Energie
    aus billigen in teure Stunden und holt Abregelung zurueck. Ein
    Graustromspeicher kann zusaetzlich Arbitrage am Day-Ahead-Markt
    fahren - und traegt dafuer die Frage, ob die aus dem Netz bezogene
    und wieder eingespeiste Energie foerderfaehig ist (sie ist es
    nicht, siehe economics.py).
    """

    #: Laden ausschliesslich aus der PV-Anlage.
    GRUENSTROM = "gruenstrom"
    #: Laden aus PV und Netz.
    GRAUSTROM = "graustrom"


class BatteryConfig(BaseModel):
    """Speicherauslegung eines Projekts - optional, siehe PVProject.

    Bestandsprojekte fuehren kein `battery`-Feld; sie laden unveraendert
    und rechnen wie bisher. Ein Speicher entsteht erst, wenn er
    ausdruecklich angelegt wird.

    Was hier steht - und was nicht
    -----------------------------
    Hier steht, WIE der Speicher gebaut ist: Leistung, Kapazitaet,
    Betriebsart, Wirkungsgrad, Fuellstandsgrenzen, Verschleiss. Alles
    davon ist eine Eigenschaft dieser Anlage.

    Was er KOSTET, steht nicht hier, sondern in den Annahmen
    (Projektannahmen.speicher_capex_eur_kw als vorliegendes Angebot und
    die globale Vorgabe dahinter, die aus einem Leistungs- und einem
    Energieanteil besteht). Batteriepreise sind eine Marktannahme, und sie
    fallen Jahr fuer Jahr spuerbar; an der Auslegung festgemacht,
    muesste eine Preissenkung in jedem Projekt einzeln nachgetragen
    werden. Die Rechnung steht in engine/storage/kosten.py.

    Leistung und Kapazitaet stehen GETRENNT, und die Preise ebenso
    (je kWh und je kW): Ein Speicher mit 5 MW / 10 MWh und einer mit
    5 MW / 20 MWh unterscheiden sich nur in der Energie, und die
    Kostenrechnung muss das abbilden koennen.

    `extra="forbid"`: Eine aeltere Projektdatei, die noch
    `capex_energie_eur_kwh` unter `battery` fuehrt, soll beim Laden
    scheitern und nicht stillschweigend einen gesetzten Preis verlieren.
    """

    model_config = ConfigDict(extra="forbid")

    aktiv: bool = True
    modus: SpeicherModus = SpeicherModus.GRUENSTROM

    #: Dauerleistung in MW, symmetrisch fuer Laden und Entladen.
    leistung_mw: float = Field(ge=0, default=5.0)
    #: Nutzbare Bruttokapazitaet in MWh. Der tatsaechlich nutzbare Hub
    #: ergibt sich daraus mit soc_min/soc_max.
    kapazitaet_mwh: float = Field(ge=0, default=10.0)

    #: Roundtrip-Wirkungsgrad (AC-seitig, 0-1). Er wird symmetrisch auf
    #: Laden und Entladen aufgeteilt: eta_lade = eta_entlade = sqrt(RTE).
    #: Das ist die uebliche Konvention, wenn nur ein Gesamtwirkungsgrad
    #: bekannt ist - sie unterstellt, dass Verluste je zur Haelfte beim
    #: Laden und beim Entladen anfallen.
    roundtrip_wirkungsgrad: float = Field(gt=0, le=1, default=0.90)

    soc_min_pct: float = Field(ge=0, le=1, default=0.05)
    soc_max_pct: float = Field(ge=0, le=1, default=0.95)
    #: Fuellstand zu Jahresbeginn UND -ende (zyklischer Abschluss, siehe
    #: dispatch.py). Ohne ihn leerte der Optimierer den Speicher am
    #: Jahresende und buchte den Erloes als Zusatzwert, der in Wahrheit
    #: aus dem Anfangsbestand stammt.
    soc_start_pct: float = Field(ge=0, le=1, default=0.50)

    #: Verschleisskosten je MWh Durchsatz. Sie halten den Speicher davon
    #: ab, fuer minimale Preisspreads zu zyklieren. Durchsatz ist hier
    #: definiert als 0,5 x (Ladeenergie + Entladeenergie) - so zaehlt ein
    #: voller Zyklus (rein und wieder raus) einmal und nicht zweimal.
    #:
    #: None heisst: aus dem Zellpreis abgeleitet, naemlich
    #: Energieanteil der Investition geteilt durch die
    #: Zyklenlebensdauer (siehe kosten.verschleiss_eur_mwh). Das ist der
    #: Regelfall - ein Zyklus verbraucht einen Anteil der Zelle, und wie
    #: teuer dieser Anteil ist, steht in den Marktannahmen und nicht an
    #: der Auslegung.
    #:
    #: Ein eingetragener Wert gilt dagegen unveraendert. Er ist fuer den
    #: Fall gedacht, dass fuer diese Anlage eine Zellgarantie mit
    #: eigenen Zahlen vorliegt.
    degradationskosten_eur_mwh: float | None = Field(default=None, ge=0)

    #: Hoechster Netzbezug in MW. Beim Gruenstromspeicher wirkungslos -
    #: dort ist der Netzbezug ohnehin null (siehe dispatch.py).
    netzbezug_limit_mw: float = Field(ge=0, default=0.0)

    @model_validator(mode="after")
    def _grenzen_pruefen(self) -> BatteryConfig:
        if self.soc_min_pct >= self.soc_max_pct:
            raise ValueError(
                "soc_min_pct muss kleiner als soc_max_pct sein"
            )
        return self

    # --- abgeleitete Groessen ---------------------------------------

    @property
    def eta_lade(self) -> float:
        return math.sqrt(self.roundtrip_wirkungsgrad)

    @property
    def eta_entlade(self) -> float:
        return math.sqrt(self.roundtrip_wirkungsgrad)

    @property
    def nutzbare_kapazitaet_mwh(self) -> float:
        """Der Hub zwischen unterer und oberer Grenze.

        Bezugsgroesse der Vollzyklen: Ein Zyklus ist das einmalige
        Durchfahren des NUTZBAREN Hubs, nicht der Bruttokapazitaet.
        """
        return self.kapazitaet_mwh * (self.soc_max_pct - self.soc_min_pct)

    @property
    def dauer_h(self) -> float:
        """C-Rate als Dauer: Wie lange haelt der volle Hub bei Nennleistung?"""
        if self.leistung_mw <= 0:
            return 0.0
        return self.nutzbare_kapazitaet_mwh / self.leistung_mw

    @property
    def wirksam(self) -> bool:
        """Ein Speicher ohne Leistung oder ohne Kapazitaet ist keiner.

        Wichtig fuer den Vergleichsfall: Der PV-only-Lauf ist derselbe
        Optimierer mit einem unwirksamen Speicher - dieselben Preise,
        dieselben Foerderregeln, dasselbe Exportlimit (siehe
        dispatch.pv_only).
        """
        return (
            self.aktiv
            and self.leistung_mw > 0
            and self.nutzbare_kapazitaet_mwh > 0
        )

    # Investition und Betriebskosten sind KEINE Eigenschaften dieses
    # Objekts mehr - sie haengen an Preisen, die in den Annahmen stehen.
    # Die Rechnung dazu: engine/storage/kosten.py.


class PVProject(BaseModel):
    """Die Projektmaske. Bewusst schlank gehalten - Ziel ist eine Anlage
    in unter zwei Minuten. Alles Uebrige kommt aus GlobalAssumptions."""

    id: str
    #: Name des STANDORTS bzw. Projekts - ohne Sensitivitaets-Zusatz.
    #: Mehrere Varianten desselben Standorts tragen denselben Namen und
    #: werden ueber ihn gruppiert (Sidebar, Variantenreiter).
    name: str
    #: Name der Sensitivitaet/Variante innerhalb des Standorts, z.B.
    #: "Netzkosten +20 %". Leer = der unbenannte Grundfall; die
    #: Oberflaeche zeigt ihn als "Basis". Bewusst KEINE Ableitung aus dem
    #: Projektnamen: "Loedersdorf Agri" und "Loedersdorf konventionell"
    #: sind zwei Anlagentypen, keine Sensitivitaeten - das kann nur der
    #: Nutzer entscheiden.
    variante: str = ""
    #: Kurzbezeichnung des Ortes, z.B. "St. Georgen" zur Projektkennung
    #: "OÖ_St.Georgen_Spitzwieser". Sie ist die Beschriftung in
    #: Diagrammen: Die vollstaendige Kennung traegt Bundesland und
    #: Grundeigentuemer und ist dort zu lang - in einer Punktwolke mit
    #: dreissig Projekten ueberlagern sich die Namen sonst.
    #: Leer = die Kennung wird auch als Beschriftung verwendet.
    #: Teilen sich mehrere Projekte einen Standort, nummeriert die
    #: Anzeige durch ("St. Georgen I", "St. Georgen II") - siehe
    #: services.standort_labels.
    standort: str = ""
    #: Traegt diese Variante die Entscheidung fuer ihren Standort?
    #: Nur die Leitvariante geht in die Portfolio-Kennzahlen und in die
    #: Pipeline ein - ohne sie zaehlte ein Standort mit drei
    #: Sensitivitaeten dreifach (Leistung, Investitionsvolumen,
    #: Eigenkapital). Ist an einem Standort keine gesetzt, gilt die
    #: erste Variante (siehe services.leitvariante_von).
    leitvariante: bool = False
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
    #: Aufstaenderung: "Pult" (fest, nach Sueden geneigt) oder "Tracker"
    #: (einachsig nachgefuehrt). Sie entscheidet ueber ZWEI Groessen -
    #: die Einspeisekurve (siehe EINSPEISEKURVEN_JE_BAUFORM) und die
    #: Marktwertkurve des gewaehlten Preisszenarios: Der Tracker
    #: erzeugt breiter ueber den Tag verteilt und trifft die
    #: preisschwachen Mittagsstunden weniger stark.
    #:
    #: Die Bauform ist eine Eigenschaft der ANLAGE, nicht der
    #: Preisprognose. Frueher steckte sie im Szenarionamen ("Aurora
    #: Q3/26 · Pult · Central"), was sie zu einer Wahl zwischen
    #: Marktmeinungen machte - dabei ist sie eine Wahl zwischen
    #: Anlagen. Der Migrationsschritt unten holt sie aus Altbestaenden
    #: heraus.
    bauform: str = EINSPEISEKURVE_STANDARD_BAUFORM

    #: Dateiname der hinterlegten Stundenreihe unter
    #: data/lastgang/projekte/, oder None. Sobald ein Projekt konkret
    #: genug ist, liegt aus der Auslegungssimulation eine Reihe der
    #: EINSPEISUNG vor (8.760 Werte). Sie leistet zweierlei: Sie
    #: ersetzt die Einspeisekurve der Bauform durch die dieser Anlage,
    #: und sie ist die einzige Grundlage, auf der sich die Wirkung der
    #: Einspeisegrenze beziffern laesst (siehe engine/clipping.py).
    #:
    #: Nur der Dateiname, nicht die Reihe selbst: 8.760 Zahlen in jeder
    #: Projektdatei machten sie unlesbar und jeden Diff wertlos.
    lastgang_datei: str | None = None

    #: Batteriespeicher in Co-Location - None heisst: keiner.
    #:
    #: Bestandsprojekte fuehren das Feld nicht und laden unveraendert;
    #: eine Migration gibt es nicht. Ohne Speicher rechnet das Projekt
    #: exakt wie bisher - der Dispatch wird gar nicht erst aufgerufen.
    battery: BatteryConfig | None = None

    # Wirtschaftliche Parameter
    pacht_eur_kwp_jahr: float = Field(ge=0)
    #: Bemessung der Pacht - siehe PachtModus. FIX (Standard) nutzt
    #: unveraendert pacht_eur_kwp_jahr; UMSATZBETEILIGUNG nutzt die
    #: beiden Felder darunter statt pacht_eur_kwp_jahr.
    pacht_modus: PachtModus = PachtModus.FIX
    #: Anteil am Jahresumsatz bei UMSATZBETEILIGUNG (ueblich 5,5 %).
    pacht_umsatzbeteiligung_pct: float = Field(ge=0, le=1, default=0.055)
    #: Fixe Mindestpacht je Hektar/Jahr bei UMSATZBETEILIGUNG - wird mit
    #: der allgemeinen Kosteninflation indexiert. Benoetigt eine gesetzte
    #: projektflaeche_ha, sonst wirkt die Mindestpacht wie 0.
    pacht_mindestpacht_eur_ha_jahr: float = Field(ge=0, default=0.0)
    fremdkapitalzins_pct: float = Field(ge=0)
    eigenkapitalquote_pct: float = Field(ge=0, le=1)
    eag_zuschlagswert_ct_kwh: float = Field(gt=0)
    gemeindeabgabe_eur_mwh: float = Field(ge=0, default=2.0)
    # Kosten der Direktvermarktung (Bilanzkreis, Prognose, Marktzugang),
    # ueblicherweise ca. 0,1 ct/kWh = 1 EUR/MWh.
    direktvermarktungskosten_eur_mwh: float = Field(ge=0, default=1.0)

    # --- Hybride Vermarktung: PPA + Merchant --------------------------------
    # Ein Teil der Menge geht zu einem festen Preis an einen Abnehmer, der
    # Rest wird am Spotmarkt vermarktet. Voreingestellt ist 0 % - ohne
    # ausdrueckliche Eingabe rechnet ein Projekt wie bisher rein
    # merchant, und bestehende Bewertungen aendern sich nicht.
    #
    # Die Foerderung bleibt davon unberuehrt: Die gleitende Marktpraemie
    # bemisst sich am REFERENZmarktwert, nicht am tatsaechlich erzielten
    # Preis (siehe engine/revenue.py). Ein PPA verschiebt also die
    # Erloesverteilung, nicht den Foerderanspruch.
    #: Anteil der Erzeugung unter PPA (0-1). 0 = kein PPA.
    ppa_anteil_pct: float = Field(ge=0, le=1, default=0.0)
    #: Fester PPA-Preis in EUR/MWh (Preisstand im ersten PPA-Jahr).
    ppa_preis_eur_mwh: float = Field(ge=0, default=65.0)
    #: Erstes Betriebsjahr des PPA (1 = ab Inbetriebnahme).
    ppa_start_jahr: int = Field(ge=1, default=1)
    #: Laufzeit in Jahren ab ppa_start_jahr.
    ppa_laufzeit_jahre: int = Field(ge=0, default=10)
    #: Jaehrliche Indexierung des PPA-Preises (0 = nominal fix; bei
    #: langen Vertraegen sind 1-2 %/a marktueblich).
    ppa_indexierung_pct_pa: float = Field(ge=0, default=0.0)

    # Investkosten
    capex: CapexBreakdown = Field(default_factory=CapexBreakdown)

    #: Zusaetzliche, projektspezifische Betriebskosten - werden in
    #: pipeline.resolve_assumptions an die globale Standardliste
    #: angehaengt und danach genauso behandelt (eigene Spalte, eigener
    #: Legendeneintrag, eigene Indexierung).
    zusatz_opex: list[OpexItem] = Field(default_factory=list)

    # Wahl des Marktpreisszenarios (siehe GlobalAssumptions.marktpreisszenarien).
    # Standardszenario ist der aktuelle Aurora-Jahrgang. Der Name traegt
    # KEINE Bauform mehr - die steht im Feld `bauform`, und welche der
    # beiden Kurven eines Jahrgangs gerechnet wird, entscheidet sich
    # erst beim Aufloesen (io_aurora.szenario_fuer).
    marktpreisszenario: str = "Aurora Q3/26 · Central"

    # Bei Pachtmodus FIX nur relevant, wenn die Pacht zuletzt in
    # €/ha/Jahr eingegeben wurde (Rueckumrechnung beim erneuten Oeffnen
    # des €/ha-Eingabemodus). Bei Pachtmodus UMSATZBETEILIGUNG direkt
    # Berechnungsgrundlage der Mindestpacht (siehe
    # pacht_mindestpacht_eur_ha_jahr) - sollte dort gesetzt sein.
    projektflaeche_ha: float | None = None

    #: Abweichungen von den globalen Annahmen - siehe Projektannahmen.
    #: Leer bedeutet: Dieses Projekt folgt in allem der Vorgabe.
    annahmen: Projektannahmen = Field(default_factory=Projektannahmen)

    @field_validator("name", "variante", "standort", mode="before")
    @classmethod
    def _trimmen(cls, wert):
        """Fuehrende/nachlaufende Leerzeichen wuerden zwei Varianten
        desselben Standorts in getrennte Gruppen aufteilen, ohne dass man
        den Unterschied sieht."""
        return wert.strip() if isinstance(wert, str) else wert

    @field_validator("bauform")
    @classmethod
    def _bekannte_bauform(cls, wert):
        """Eine unbekannte Bauform faende weder eine Einspeise- noch eine
        Marktwertkurve und rechnete stillschweigend mit der Vorgabe."""
        if wert not in EINSPEISEKURVEN_JE_BAUFORM:
            bekannt = ", ".join(EINSPEISEKURVEN_JE_BAUFORM)
            raise ValueError(f"Unbekannte Bauform {wert!r} - bekannt: {bekannt}")
        return wert

    @model_validator(mode="before")
    @classmethod
    def _bauform_aus_szenarioname(cls, data):
        """Holt die Bauform aus einem Altbestand heraus.

        Bis v5.14 stand sie im Szenarionamen ("Aurora Q3/26 · Pult ·
        Central"). Gespeicherte Projekte, aeltere Excel-Importe und
        direkt konstruierte Objekte tragen sie dort weiterhin; hier
        wandert sie in das Feld `bauform`, und der Name verliert sie.
        Ein ausdruecklich gesetztes Feld hat Vorrang - nur der Name
        wird dann noch bereinigt.
        """
        if not isinstance(data, dict):
            return data
        name = data.get("marktpreisszenario")
        if not isinstance(name, str) or "·" not in name:
            return data
        # Lokal importiert: io_aurora liest models, ein Import auf
        # Modulebene waere ein Zirkel.
        from .io_aurora import ohne_bauform, zerlege_szenarioname

        bauform = zerlege_szenarioname(name)[1]
        if bauform:
            data.setdefault("bauform", bauform)
            data["marktpreisszenario"] = ohne_bauform(name)
        return data

    @property
    def anzeigename(self) -> str:
        """Name fuer Titel, Dateinamen und Tabellen.

        Ohne die Variante waeren zwei Sensitivitaeten desselben Standorts
        in Portfoliotabelle, PDF-Titel und Excel-Dateinamen nicht
        auseinanderzuhalten.
        """
        return f"{self.name} · {self.variante}" if self.variante else self.name

    @property
    def variantenlabel(self) -> str:
        """Beschriftung der Variante fuer Reiter und Listen - der
        unbenannte Grundfall heisst 'Basis'."""
        return self.variante or "Basis"

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


MONATE = 12


def _monatskurve(
    monatsreihen: dict[int, list[float]], jahreswerte: dict[int, float]
) -> dict[int, list[float]]:
    """Fuehrt Monats- und Jahresreihe zu einer vollstaendigen Monatskurve
    zusammen; die Monatsreihe hat Vorrang."""
    kurve = {jahr: [wert] * MONATE for jahr, wert in jahreswerte.items()}
    kurve.update({jahr: list(werte) for jahr, werte in monatsreihen.items()})
    return kurve


class MarktpreisSzenario(BaseModel):
    """Eine benannte Marktpreis-Prognose (z.B. 'Aurora Q3/26 · Pult ·
    Central'). Kurven sind
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

    # --- Monatsreihen (optional) --------------------------------------------
    # Je Kalenderjahr zwoelf Werte, Januar bis Dezember. Sie treten an die
    # Stelle des Jahreswerts, sobald in den Globalen Annahmen die
    # Monatsaufloesung gewaehlt ist; fehlt fuer ein Jahr eine Monatsreihe,
    # gilt sein Jahreswert fuer alle zwoelf Monate. Dadurch bleibt ein
    # Szenario auch dann rechenbar, wenn nur ein Teil der Jahre in
    # Monatsaufloesung vorliegt.
    marktwert_solar_ct_kwh_je_monat: dict[int, list[float]] = Field(
        default_factory=dict
    )
    erzeugungsmenge_negativ_6h_pct_je_monat: dict[int, list[float]] = Field(
        default_factory=dict
    )
    erzeugungsmenge_negativ_1h_pct_je_monat: dict[int, list[float]] = Field(
        default_factory=dict
    )

    # --- Grosshandelspreis (Baseload) ----------------------------------------
    # Rechnet NICHT mit: Der Erloes einer PV-Anlage bemisst sich am
    # Marktwert Solar, nicht am Baseload. Der Baseload ist die
    # Einordnung dazu - aus dem Abstand beider Kurven liest man den
    # Kannibalisierungseffekt ab, und er ist der uebliche Bezugspunkt
    # fuer PPA-Preise. Einheit wie beim Marktwert: ct/kWh.
    baseload_ct_kwh_je_kalenderjahr: dict[int, float] = Field(default_factory=dict)
    baseload_ct_kwh_je_monat: dict[int, list[float]] = Field(default_factory=dict)

    @field_validator(
        "marktwert_solar_ct_kwh_je_monat",
        "erzeugungsmenge_negativ_6h_pct_je_monat",
        "erzeugungsmenge_negativ_1h_pct_je_monat",
    )
    @classmethod
    def _zwoelf_monatswerte(cls, reihen):
        """Eine Monatsreihe mit elf Werten waere stillschweigend um einen
        Monat verschoben - hier faellt sie auf."""
        for jahr, werte in reihen.items():
            if len(werte) != 12:
                raise ValueError(
                    f"Monatsreihe {jahr}: {len(werte)} Werte statt 12"
                )
        return reihen

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

    def erzeugungsmenge_negativ_monate(
        self, regel: NegativeStundenRegel
    ) -> dict[int, list[float]]:
        """Monatsreihe der Negativmengen zur gewaehlten Regel."""
        if regel == NegativeStundenRegel.EINE_STUNDE:
            return self.erzeugungsmenge_negativ_1h_pct_je_monat
        return self.erzeugungsmenge_negativ_6h_pct_je_monat

    def marktwert_monatskurve(self) -> dict[int, list[float]]:
        """Marktwerte je Kalenderjahr als Zwoelferreihe.

        Jahre ohne Monatsreihe steuern ihren Jahreswert bei, auf alle
        zwoelf Monate gelegt - so ist die Kurve immer vollstaendig, auch
        wenn Monatsdaten nur fuer einen Teil der Jahre vorliegen.
        """
        return _monatskurve(
            self.marktwert_solar_ct_kwh_je_monat,
            self.marktwert_solar_ct_kwh_je_kalenderjahr,
        )

    def baseload_monatskurve(self) -> dict[int, list[float]]:
        """Grosshandelspreis je Kalenderjahr als Zwoelferreihe."""
        return _monatskurve(
            self.baseload_ct_kwh_je_monat, self.baseload_ct_kwh_je_kalenderjahr
        )

    def negativ_monatskurve(
        self, regel: NegativeStundenRegel
    ) -> dict[int, list[float]]:
        """Negativmengen je Kalenderjahr als Zwoelferreihe."""
        return _monatskurve(
            self.erzeugungsmenge_negativ_monate(regel),
            self.erzeugungsmenge_negativ(regel),
        )


class GlobalAssumptions(BaseModel):
    gueltig_ab: str = ""

    # Marktsystematik (Laenderschalter) - siehe MarktSystem. Der Wechsel
    # ueber die Flaggen-Buttons der Seite "Globale Annahmen" setzt die
    # abhaengigen Felder (negative_stunden_regel, tax_modus, zinsmethode)
    # als Paket um; sie bleiben danach einzeln aenderbar.
    markt_system: MarktSystem = MarktSystem.OESTERREICH

    # Erwarteter Marktpraemienzuschlag (anzulegender Wert) fuer das
    # deutsche EEG-Modell - wird auf der Seite "Marktpraemie" manuell
    # eingetragen, da das empirische Ausschreibungsmodell (OeMAG-
    # Historie) nur fuer Oesterreich gilt.
    de_marktpraemie_erwartet_ct_kwh: float = Field(ge=0, default=5.0)

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

    # --- Zeitaufloesung und Einspeisekurve -----------------------------------
    # Voreingestellt ist die Jahresrechnung: Sie ist das bisherige
    # Verhalten, und ohne gepflegte Monatsdaten waere die Monatsrechnung
    # nur eine aufwendigere Art, dasselbe Ergebnis zu erhalten.
    zeitaufloesung: Zeitaufloesung = Zeitaufloesung.JAHR
    #: Anteil der Jahreserzeugung je Monat (12 Werte, Januar bis
    #: Dezember). Die Summe wird beim Rechnen auf 1 normiert - eine Kurve
    #: aus gerundeten Prozentwerten (99,8 %) soll die Jahresmenge nicht
    #: still veraendern.
    einspeisekurve_pct_je_monat: list[float] = Field(
        default_factory=lambda: list(EINSPEISEKURVE_STANDARD_PCT)
    )
    #: Hinterlegte Kurven je Bauform ("Pult", "Tracker"), abgeleitet aus
    #: Stundenreihen (siehe EINSPEISEKURVEN_JE_BAUFORM). Sie stehen zur
    #: Auswahl, damit ein Wechsel der Bauform nicht bedeutet, zwoelf
    #: Zahlen von Hand einzutragen. Gerechnet wird immer mit
    #: einspeisekurve_pct_je_monat - der aktiven Kurve.
    einspeisekurven_je_bauform: dict[str, list[float]] = Field(
        default_factory=lambda: {k: list(v)
                                 for k, v in EINSPEISEKURVEN_JE_BAUFORM.items()}
    )
    #: Welche Bauform die aktive Kurve liefert. Leer = von Hand
    #: bearbeitete Kurve, die zu keiner der hinterlegten Bauformen mehr
    #: passt.
    einspeisekurve_bauform: str = EINSPEISEKURVE_STANDARD_BAUFORM

    # --- Marktpraemienmodell --------------------------------------------------
    # Welche Vertragsform zwischen Betreiber und Foerderstelle gilt -
    # siehe PraemienModell. Die Parameter darunter gelten nur fuer
    # EAG_TOLERANZBAND. Der Standard folgt dem Laenderschalter
    # (markt_system, Vorbelegung Oesterreich): das EAG kennt das
    # Toleranzband, das deutsche EEG den einseitigen CfD. Der Wechsel
    # der Marktsystematik stellt das Modell mit um
    # (app/views/assumptions.py::_wechsle_markt_system), danach bleibt
    # es frei waehlbar.
    praemien_modell: PraemienModell = PraemienModell.EAG_TOLERANZBAND
    #: Ab welcher Engpassleistung die Rueckzahlungspflicht greift
    #: (§ 10 EAG: Photovoltaik ab 5 MW).
    eag_rueckzahlung_ab_mw: float = Field(ge=0, default=5.0)
    #: Toleranzband: Erst oberhalb des um diesen Anteil erhoehten
    #: anzulegenden Werts entsteht eine Rueckzahlung (§ 10 EAG: 40 %).
    eag_rueckzahlung_toleranzband_pct: float = Field(ge=0, default=0.40)
    #: Anteil des uebersteigenden Betrags, der zurueckzuzahlen ist
    #: (§ 10 EAG: 66 %).
    eag_rueckzahlung_anteil_pct: float = Field(ge=0, le=1, default=0.66)

    # --- Vorschlagswerte fuer hybride PPA -------------------------------------
    # Nur Vorbelegung der Projektmaske; gerechnet wird immer mit den
    # Projektfeldern (siehe PVProject.ppa_*).
    ppa_anteil_pct_vorschlag: float = Field(ge=0, le=1, default=0.50)
    ppa_preis_eur_mwh_vorschlag: float = Field(ge=0, default=65.0)
    ppa_laufzeit_jahre_vorschlag: int = Field(ge=0, default=10)
    ppa_indexierung_pct_pa_vorschlag: float = Field(ge=0, default=0.01)

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
    # Vorschlagswert fuer den Umsatzbeteiligungs-Prozentsatz (analog
    # Gemeindeabgabe/Direktvermarktung): dient nur als Vorbelegung im
    # "Neues Projekt"-Formular bei Pachtmodus UMSATZBETEILIGUNG,
    # tatsaechlich angewendet wird PVProject.pacht_umsatzbeteiligung_pct.
    # Hausueblich sind 5,1 %.
    pacht_umsatzbeteiligung_pct_vorschlag: float = Field(ge=0, le=1, default=0.051)
    # Vorschlagswert fuer die Mindestpacht in EUR je Hektar und Jahr. Sie
    # ist der Boden unter der Umsatzbeteiligung: Faellt der Erloes aus,
    # bleibt dem Verpaechter dieser Betrag. Hausueblich sind 3.000 EUR/ha.
    pacht_mindestpacht_eur_ha_jahr_vorschlag: float = Field(ge=0, default=3000.0)
    # --- Vorbelegung der Projektmaske ----------------------------------------
    # Diese Groessen sind je Projekt verschieden und werden dort auch
    # gespeichert - eine Vererbung waere hier sinnlos. Ihre VORBELEGUNG im
    # Formular "Neues Projekt" stand aber bis v5.16 hart im Code; damit
    # war der Hausstandard nicht pflegbar, obwohl er genau das ist: eine
    # Vorgabe. Jetzt steht er hier.
    nennleistung_kwp_vorschlag: float = Field(gt=0, default=5000.0)
    vollbenutzungsstunden_kwh_kwp_vorschlag: float = Field(gt=0, default=1050.0)
    eigenkapitalquote_pct_vorschlag: float = Field(ge=0, le=1, default=0.20)
    fremdkapitalzins_pct_vorschlag: float = Field(ge=0, default=0.042)
    #: EPC-Vorbelegung je Anlagentyp in EUR/kWp. Agri-PV baut teurer als
    #: eine konventionelle Freiflaechenanlage - hoehere Aufstaenderung
    #: und groessere Reihenabstaende.
    epc_eur_kwp_vorschlag_je_anlagentyp: dict[str, float] = Field(
        default_factory=lambda: {"Agri-PV": 520.0, "Konventionell": 430.0}
    )
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

    #: Hoechste zulaessige Einspeisung am Netzverknuepfungspunkt, als
    #: Anteil der Modulspitzenleistung. In Oesterreich ueblich 70 %.
    #: None heisst: keine Begrenzung.
    #:
    #: Wirksam wird sie nur, wenn eine Stundenreihe vorliegt - aus einer
    #: Monats- oder Jahresmenge laesst sich nicht ablesen, in welchen
    #: Stunden die Leistung ueber der Grenze lag (siehe
    #: engine/clipping.py).
    einspeiselimit_pct: float | None = Field(default=0.70, gt=0, le=1)

    # --- Speicherpreise (Co-Location) ---------------------------------
    #
    # Zentral gepflegt, weil sie eine Marktannahme sind und keine
    # Projekteigenschaft. Ein Projekt mit vorliegendem Angebot weicht in
    # seinen Projektannahmen ab.
    #
    # ZWEI Parameter, und das ist der Kern:
    #
    #     CAPEX = a * Leistung[kW] + b * Kapazitaet[kWh]
    #
    # `a` traegt, was an der Anschlussleistung haengt (Umrichter/PCS,
    # Trafo, Schaltanlage, Netzanschluss, Baustelle), `b` was an der
    # Energie haengt (Zellen, Module, Racks, Thermomanagement).
    #
    # Die Vorgaenger-Fassung kannte nur `a`. Damit kostete ein 3-MW-
    # Speicher mit 12 MWh genau so viel wie einer mit 24 MWh - doppelt so
    # viele Zellen zum Nulltarif. Der groessere Teil der Speicherkosten
    # ist energiebezogen; ohne `b` fehlt genau der Teil, der mit der
    # Speicherdauer skaliert.
    speicher_capex_leistung_eur_kw: float = Field(ge=0, default=48.0)
    speicher_capex_energie_eur_kwh: float = Field(ge=0, default=82.0)
    speicher_opex_eur_kw_jahr: float = Field(ge=0, default=8.0)

    #: Wie viele Vollzyklen die Zelle haelt. Zusammen mit dem
    #: Energieanteil der Investition ergibt sich daraus, was ein Zyklus
    #: kostet: 82 EUR/kWh bei 6.000 Zyklen sind 13,7 EUR je MWh
    #: Durchsatz.
    #:
    #: Die frueher fest eingetragenen 2 EUR/MWh waren um das Siebenfache
    #: zu niedrig und liessen den Optimierer zyklieren, wo sich das nicht
    #: mehr rechnete - besonders bei kurzen Speichern, die am meisten
    #: zyklieren. 6.000 Vollzyklen sind fuer LFP der uebliche Ansatz;
    #: Datenblaetter nennen je nach Entladetiefe und Temperatur 4.000
    #: bis 10.000.
    speicher_zyklenlebensdauer: int = Field(gt=0, default=6000)
    #: Name der zuletzt gewaehlten Kalibrierung - reine Merkgroesse fuer
    #: die Oberflaeche. Gerechnet wird IMMER mit den beiden Zahlen
    #: darueber: Wer sie von Hand anpasst, soll seinen Wert behalten und
    #: nicht beim naechsten Aufbau von einer Voreinstellung ueberschrieben
    #: werden.
    speicher_kalibrierung: str = ""

    # Foerder- und Betrachtungsdauer
    eag_foerderdauer_jahre: int = Field(gt=0, default=20)
    betriebsdauer_jahre: int = Field(gt=0, default=25)

    # Finanzierung
    kreditlaufzeit_jahre: int = Field(gt=0, default=20)
    tilgungsart: TilgungsArt = TilgungsArt.ANNUITAET
    #: Jahr 1 nur Zinsen, Tilgung ab Jahr 2 (verlaengert den
    #: Schuldendienst um ein Jahr, Anzahl der Tilgungsraten bleibt gleich).
    tilgungsfreies_anlaufjahr: bool = False
    #: Zinsberechnung fuer das (moeglicherweise unterjaehrige) erste
    #: Betriebsjahr - siehe ZinsMethode. Wirkt sich nur aus, wenn die
    #: Inbetriebnahme nicht am 1. Januar erfolgt.
    zinsmethode: ZinsMethode = ZinsMethode.OESTERREICH

    # DSCR-Kovenanten des Kreditvertrags (siehe engine/covenants.py).
    # Sie veraendern die Cashflow-Rechnung nicht, sondern werden als
    # Kovenantenpruefung darauf ausgewertet.
    #: Cash Trap / Lock-up: Unterhalb dieses DSCR darf nicht mehr
    #: ausgeschuettet werden; der freie Cashflow bleibt als Reserve in
    #: der Gesellschaft. Marktueblich 1,10x.
    dscr_cash_trap: float = Field(ge=0, default=1.10)
    #: Event of Default: Unterhalb dieses DSCR liegt eine
    #: Vertragsverletzung vor, die ueblicherweise durch eine
    #: Eigenkapitaleinlage geheilt wird (Equity Cure). Marktueblich 1,05x.
    dscr_event_of_default: float = Field(ge=0, default=1.05)

    # Steuer
    tax_modus: TaxModus = TaxModus.AFA_KOERPERSCHAFTSTEUER
    steuersatz_pct: float = Field(ge=0, le=1, default=0.25)
    afa_nutzungsdauer_jahre: int | None = None
    freibetrag_eur: float = 0.0
    #: Hebesatz fuer TaxModus.GEWERBESTEUER_DE (gemeindeabhaengig,
    #: haeufig 400-450%; z.B. 400.0 fuer 400%, NICHT als Bruch 0-1 wie
    #: die uebrigen *_pct-Felder - der natuerliche Wertebereich (200-900)
    #: passt nicht in eine 0-1-Konvention). Effektiver Satz = 3,5% x
    #: (Hebesatz/100).
    gewerbesteuer_hebesatz_pct: float = Field(ge=0, default=400.0)
    #: Gesetzlicher Gewerbesteuer-Freibetrag bei Personengesellschaften
    #: (u.a. GmbH & Co. KG) - Stand 2026: 24.500 EUR/Jahr.
    gewerbesteuer_freibetrag_eur: float = Field(ge=0, default=24_500.0)

    # Verlustvortrag (§8 Abs. 4 Z 2 KStG): zeitlich unbegrenzt vortragbar,
    # aber pro Gewinnjahr nur bis verlustvortrag_verrechnungsgrenze_pct des
    # steuerlichen Ergebnisses verrechenbar (siehe tax.py). Kein "Ein/Aus"-
    # Schalter, da Verlustvortrag gesetzlich vorgeschrieben ist - Kontrolle
    # erfolgt ausschliesslich ueber die Verrechnungsgrenze selbst.
    verlustvortrag_verrechnungsgrenze_pct: float = Field(ge=0, le=1, default=0.75)

    @model_validator(mode="after")
    def _einspeisekurve_pruefen(self) -> GlobalAssumptions:
        """Zwoelf Werte, keiner negativ, Summe > 0.

        Eine leere Liste wird auf die Standardkurve zurueckgesetzt -
        aeltere Datenstaende kennen das Feld nicht, und eine Anlage ohne
        Erzeugungsverteilung waere in der Monatsrechnung eine Anlage ohne
        Erzeugung.
        """
        if not self.einspeisekurve_pct_je_monat:
            self.einspeisekurve_pct_je_monat = list(EINSPEISEKURVE_STANDARD_PCT)
            return self
        if len(self.einspeisekurve_pct_je_monat) != MONATE:
            raise ValueError(
                "einspeisekurve_pct_je_monat braucht 12 Werte "
                f"(Januar bis Dezember), hat {len(self.einspeisekurve_pct_je_monat)}"
            )
        if any(w < 0 for w in self.einspeisekurve_pct_je_monat):
            raise ValueError("einspeisekurve_pct_je_monat: kein Wert darf negativ sein")
        if sum(self.einspeisekurve_pct_je_monat) <= 0:
            raise ValueError("einspeisekurve_pct_je_monat: Summe muss groesser 0 sein")
        return self

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

    #: Einspeisegrenze als Anteil der kWp; None heisst unbegrenzt.
    einspeiselimit_pct: float | None = None
    #: Stundenreihe der Einspeisung, sofern eine hinterlegt ist. Als
    #: tuple, weil EffectiveAssumptions gecacht durch die Pipeline
    #: gereicht wird und eine Liste dort veraenderbar waere.
    lastgang_reihe: tuple[float, ...] | None = None

    # Aufgeloeste Speicherpreise. Sie stehen hier und nicht an
    # BatteryConfig, damit es genau EINE Stelle gibt, an der feststeht,
    # welcher Preis fuer dieses Projekt gilt - siehe
    # engine/storage/kosten.py.
    #: Das Angebot DIESES Projekts, oder None. Anders als sonst in
    #: EffectiveAssumptions bleibt hier die Unterscheidung "gesetzt oder
    #: nicht" erhalten und wird nicht auf einen Wert aufgeloest - der
    #: Rechenweg haengt daran: Ein Angebot gilt so, wie es ist; ohne
    #: Angebot rechnet das Zweiparametermodell (siehe
    #: engine/storage/kosten.py).
    speicher_capex_eur_kw: float | None = None
    #: Die zentrale Kalibrierung: Leistungs- und Energieanteil.
    speicher_capex_leistung_eur_kw: float = 0.0
    speicher_capex_energie_eur_kwh: float = 0.0
    speicher_opex_eur_kw_jahr: float = 0.0
    speicher_zyklenlebensdauer: int = 6000

    eag_zuschlagswert_effektiv_ct_kwh: float
    eag_foerderdauer_jahre: int
    betriebsdauer_jahre: int
    marktpreisszenario_name: str
    marktwert_solar_ct_kwh_je_kalenderjahr: dict[int, float]
    # Aufgeloeste Negativmengen-Kurve gemaess gewaehlter Regel (6h/1h).
    anteil_negativer_stunden_pct_je_kalenderjahr: dict[int, float]
    negative_stunden_regel: NegativeStundenRegel

    # --- Monatsebene ----------------------------------------------------------
    # Wirksam bei zeitaufloesung = MONAT - und seit der Rumpfjahr-Korrektur
    # ausserdem im Anlaufjahr, auch in der Jahresaufloesung (siehe
    # engine/revenue.py::_scheiben).
    #
    # Jahres- und Monatsreihe sind beide Capture Prices desselben
    # Szenarios; der Jahreswert traegt bereits ein Erzeugungsprofil, die
    # Monatsreihe wird erst hier mit der Einspeisekurve gewichtet.
    #
    # Nachgerechnet: Aus den Monatsreihen laesst sich der Jahreswert mit
    # EINEM Gewichtsvektor ueber alle 34 Jahre auf 0,004 ct genau
    # rekonstruieren. Beide beschreiben also dasselbe, und die
    # Gegenprobe ist damit ein Test der Kurve: Gewichtet man die
    # Monatswerte mit der hinterlegten Einspeisekurve, muss ungefaehr
    # der Jahreswert herauskommen. Mit den Kurven aus den
    # RatedPower-Stundenreihen trifft das zu (2030, Pult: 4,239 gegen
    # 4,195 ct/kWh, +1,1 %); mit der frueheren PVGIS-Kurve nicht
    # (4,860 ct/kWh, +15,8 %) - siehe MONATSERTRAG_KWH_JE_BAUFORM.
    #
    # Eine frueher hier notierte Erklaerung, der Jahreswert trage das
    # Profil des deutschen Anlagenparks (Juli zu Dezember rund 10:1),
    # war falsch: Der dafuer geschaetzte Gewichtsvektor war aus den
    # Daten nicht identifizierbar. Die Abweichung lag an der Kurve.
    zeitaufloesung: Zeitaufloesung = Zeitaufloesung.JAHR
    einspeisekurve_pct_je_monat: list[float] = Field(
        default_factory=lambda: list(EINSPEISEKURVE_STANDARD_PCT)
    )
    marktwert_solar_ct_kwh_je_monat: dict[int, list[float]] = Field(
        default_factory=dict
    )
    anteil_negativer_stunden_pct_je_monat: dict[int, list[float]] = Field(
        default_factory=dict
    )
    #: Grosshandelspreis (Baseload) des Szenarios - Bezugsgroesse der
    #: Direktvermarktungskosten im Modus RELATIV_GROSSHANDEL.
    baseload_ct_kwh_je_kalenderjahr: dict[int, float] = Field(default_factory=dict)
    baseload_ct_kwh_je_monat: dict[int, list[float]] = Field(default_factory=dict)

    # --- Foerdermodell und hybride Vermarktung --------------------------------
    praemien_modell: PraemienModell = PraemienModell.EINSEITIG_CFD
    eag_rueckzahlung_ab_mw: float = 5.0
    eag_rueckzahlung_toleranzband_pct: float = 0.40
    eag_rueckzahlung_anteil_pct: float = 0.66
    ppa_anteil_pct: float = 0.0
    ppa_preis_eur_mwh: float = 0.0
    ppa_start_jahr: int = 1
    ppa_laufzeit_jahre: int = 0
    ppa_indexierung_pct_pa: float = 0.0
    marktpreis_inflation_pct_pa: float
    marktpreis_inflation_basisjahr: int
    kosten_inflation_pct_pa: float

    opex_items: list[OpexItem]
    pacht_modus: PachtModus
    pacht_eur_kwp_jahr: float
    pacht_umsatzbeteiligung_pct: float
    pacht_mindestpacht_eur_ha_jahr: float
    projektflaeche_ha: float | None
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
    zinsmethode: ZinsMethode
    dscr_cash_trap: float
    dscr_event_of_default: float

    tax_modus: TaxModus
    steuersatz_pct: float
    afa_nutzungsdauer_jahre: int | None
    freibetrag_eur: float
    gewerbesteuer_hebesatz_pct: float
    gewerbesteuer_freibetrag_eur: float
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
