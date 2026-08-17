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

from pydantic import BaseModel, Field, field_validator, model_validator


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
    # Standardszenario ist der aktuelle Aurora-Jahrgang.
    marktpreisszenario: str = "Aurora Q3/26 · Pult · Central"

    # Bei Pachtmodus FIX nur relevant, wenn die Pacht zuletzt in
    # €/ha/Jahr eingegeben wurde (Rueckumrechnung beim erneuten Oeffnen
    # des €/ha-Eingabemodus). Bei Pachtmodus UMSATZBETEILIGUNG direkt
    # Berechnungsgrundlage der Mindestpacht (siehe
    # pacht_mindestpacht_eur_ha_jahr) - sollte dort gesetzt sein.
    projektflaeche_ha: float | None = None

    @field_validator("name", "variante", "standort", mode="before")
    @classmethod
    def _trimmen(cls, wert):
        """Fuehrende/nachlaufende Leerzeichen wuerden zwei Varianten
        desselben Standorts in getrennte Gruppen aufteilen, ohne dass man
        den Unterschied sieht."""
        return wert.strip() if isinstance(wert, str) else wert

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


#: Monatsertrag einer 1-kWp-Anlage in kWh, Januar bis Dezember - die
#: Quelle der Einspeisekurven. Ausgelesen aus PVGIS je Bauform,
#: derselbe Standort und dieselbe Konfiguration; die Jahressummen sind
#: 1.148 kWh/kWp (Pult) und 1.429 kWh/kWp (Tracker), also 24,5 %
#: Nachfuehrgewinn.
#:
#: Die Werte stehen hier in ihrer Rohform und nicht schon normiert, weil
#: sie damit nachpruefbar bleiben: Wer die PVGIS-Abfrage wiederholt,
#: vergleicht Zahl fuer Zahl. Fuer die Rechnung zaehlt nur ihr
#: Verhaeltnis - die Jahresmenge kommt aus Leistung und
#: Vollbenutzungsstunden des Projekts, nicht von hier.
PVGIS_MONATSERTRAG_KWH_KWP: dict[str, list[float]] = {
    "Pult": [
        69.69, 87.20, 112.98, 113.01, 111.01, 113.67,
        122.11, 110.76, 96.59, 88.06, 63.89, 59.50,
    ],
    "Tracker": [
        85.42, 108.20, 139.14, 141.25, 137.08, 144.45,
        157.08, 139.65, 118.34, 108.10, 78.07, 72.57,
    ],
}


def _normiert(werte: list[float]) -> list[float]:
    """Anteile mit Summe 1 - die Hoehe der Reihe ist gleichgueltig."""
    gesamt = sum(werte)
    return [w / gesamt for w in werte]


#: Einspeisekurven je Bauform: Anteil der Jahreserzeugung je Monat
#: (Januar bis Dezember), Summe 1. Normiert aus den PVGIS-Monatsertraegen
#: darueber.
#:
#: Der Tracker verschiebt Erzeugung in die langen Tage: Sein
#: Nachfuehrgewinn liegt im Juli bei 28,6 %, im Dezember nur bei 22,0 %.
#: Seine Kurve ist deshalb etwas sommerlastiger als die der
#: Pultaufstaenderung - fuer die Monatsrechnung wesentlich, weil die
#: Sommermonate die niedrigeren Marktwerte tragen.
EINSPEISEKURVEN_JE_BAUFORM: dict[str, list[float]] = {
    bauform: _normiert(werte)
    for bauform, werte in PVGIS_MONATSERTRAG_KWH_KWP.items()
}

#: Bauform der Standardkurve - Pult, wie auch beim Aurora-Import
#: (io_aurora.TECHNOLOGIE_STANDARD).
EINSPEISEKURVE_STANDARD_BAUFORM = "Pult"

#: Standard-Einspeisekurve: die Pult-Kurve.
EINSPEISEKURVE_STANDARD_PCT = list(
    EINSPEISEKURVEN_JE_BAUFORM[EINSPEISEKURVE_STANDARD_BAUFORM]
)

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

    eag_zuschlagswert_effektiv_ct_kwh: float
    eag_foerderdauer_jahre: int
    betriebsdauer_jahre: int
    marktpreisszenario_name: str
    marktwert_solar_ct_kwh_je_kalenderjahr: dict[int, float]
    # Aufgeloeste Negativmengen-Kurve gemaess gewaehlter Regel (6h/1h).
    anteil_negativer_stunden_pct_je_kalenderjahr: dict[int, float]
    negative_stunden_regel: NegativeStundenRegel

    # --- Monatsebene ----------------------------------------------------------
    # Nur wirksam bei zeitaufloesung = MONAT; sonst tragen sie dieselbe
    # Aussage wie die Jahreskurven und bleiben ungenutzt.
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
