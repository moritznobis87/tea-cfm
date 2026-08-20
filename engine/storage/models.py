"""
Datenmodell der Co-Location-Speicherbewertung.

Drei Objekte, streng getrennt nach ihrer Rolle:

    BatteryConfig          - was der Nutzer einstellt (Teil des Projekts)
    StorageDispatchResult  - was der Optimierer je Jahr herausrechnet
    StorageJahreswert      - was davon in den Cashflow geht

Die Trennung ist beabsichtigt: Der Cashflow braucht acht Zahlen je Jahr,
nicht 8.760 Stunden. Die Stundenbahn bleibt beim Ergebnisobjekt, damit
sie gezeichnet werden kann, wandert aber nicht durch die Bewertung.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

import numpy as np
from pydantic import BaseModel, Field, model_validator


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

    Leistung und Kapazitaet stehen GETRENNT, und die Kosten ebenso
    (`capex_energie_eur_kwh` / `capex_leistung_eur_kw`): Ein Speicher
    mit 5 MW / 10 MWh und einer mit 5 MW / 20 MWh unterscheiden sich nur
    in der Energie, und die Kostenrechnung muss das abbilden koennen.
    """

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
    degradationskosten_eur_mwh: float = Field(ge=0, default=2.0)

    #: Hoechster Netzbezug in MW. Beim Gruenstromspeicher wirkungslos -
    #: dort ist der Netzbezug ohnehin null (siehe dispatch.py).
    netzbezug_limit_mw: float = Field(ge=0, default=0.0)

    #: Investitionskosten, getrennt nach Energie und Leistung.
    capex_energie_eur_kwh: float = Field(ge=0, default=0.0)
    capex_leistung_eur_kw: float = Field(ge=0, default=0.0)
    #: Feste Betriebskosten je kW und Jahr.
    opex_eur_kw_jahr: float = Field(ge=0, default=0.0)

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

    @property
    def capex_gesamt_eur(self) -> float:
        return (
            self.kapazitaet_mwh * 1000 * self.capex_energie_eur_kwh
            + self.leistung_mw * 1000 * self.capex_leistung_eur_kw
        )

    @property
    def opex_jahr_eur(self) -> float:
        return self.leistung_mw * 1000 * self.opex_eur_kw_jahr


# --- Ergebnis ---------------------------------------------------------------


@dataclass(frozen=True)
class StorageJahreswert:
    """Was ein Betriebsjahr an den Cashflow weitergibt.

    Bewusst DELTAS gegen den PV-only-Fall und keine Absolutwerte: Das
    bestehende Cashflow-Modell rechnet den PV-Erloes aus Capture Prices
    (Marktwert Solar), der Dispatch dagegen stundenscharf. Beide Wege
    ergeben nicht denselben Absolutbetrag. Nur die DIFFERENZ ist eine
    saubere Aussage ueber den Speicher - sie entsteht aus zwei Laeufen
    mit identischen Preisen, Foerderregeln und Netzgrenzen.
    """

    jahr: int
    kalenderjahr: int
    #: Zusaetzlicher Markterloes gegenueber PV-only (kann negativ sein,
    #: wenn Verluste den Zeitverschiebungsgewinn uebersteigen).
    mehrerloes_eur: float
    #: Kosten des Netzbezugs (nur Graustrom).
    netzbezugskosten_eur: float
    #: Verschleisskosten des Durchsatzes.
    degradationskosten_eur: float
    #: Zusaetzlich eingespeiste Menge - Grundlage der mengenabhaengigen
    #: Abgaben und der Foerderung.
    mehrmenge_kwh: float
    #: Zurueckgewonnene Abregelung (Energie, die ohne Speicher der
    #: Einspeisegrenze zum Opfer gefallen waere).
    rueckgewonnene_kappung_kwh: float
    speicher_ladung_mwh: float
    speicher_entladung_mwh: float
    vollzyklen: float

    @property
    def deckungsbeitrag_eur(self) -> float:
        """Der Betrag, der dem Projektjahr zufliesst."""
        return (
            self.mehrerloes_eur
            - self.netzbezugskosten_eur
            - self.degradationskosten_eur
        )


#: Spalten der Stundenbahn. Als DataFrame-Container zulaessig (siehe
#: Modulkopf), aber mit festem Vertrag.
BAHN_SPALTEN = (
    "pv_erzeugung_mw",
    "pv_ins_netz_mw",
    "pv_in_speicher_mw",
    "netz_in_speicher_mw",
    "speicher_ins_netz_mw",
    "abregelung_mw",
    "soc_mwh",
    "preis_eur_mwh",
    "grenzerloes_eur_mwh",
)


@dataclass(frozen=True)
class StorageDispatchResult:
    """Ergebnis EINES optimierten Betriebsjahres.

    `bahn` ist ein Array der Form (stunden, len(BAHN_SPALTEN)) - roh und
    ohne pandas, damit die Engine unabhaengig bleibt. Die Oberflaeche
    macht daraus einen DataFrame.
    """

    jahr: int
    kalenderjahr: int
    bahn: np.ndarray
    #: Wert der Zielfunktion des optimierten Laufs (Erloes minus
    #: Netzbezug minus Degradation).
    zielwert_eur: float
    #: Derselbe Wert fuer den Vergleichslauf ohne Speicher.
    zielwert_pv_only_eur: float
    #: Diskretisierungsabstand zur stetigen Schranke, sofern gerechnet -
    #: siehe dispatch.schranke_lp. None heisst: nicht geprueft.
    abstand_zur_schranke_pct: float | None = None
    hinweise: list[str] = field(default_factory=list)

    @property
    def wertbeitrag_eur(self) -> float:
        return self.zielwert_eur - self.zielwert_pv_only_eur

    def spalte(self, name: str) -> np.ndarray:
        return self.bahn[:, BAHN_SPALTEN.index(name)]


class SolverFehler(RuntimeError):
    """Der Dispatch liess sich nicht rechnen.

    Eigene Klasse, damit die Oberflaeche einen Solverfehler von einem
    Programmierfehler unterscheiden und verstaendlich melden kann,
    statt abzustuerzen.
    """
