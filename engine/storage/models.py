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

from dataclasses import dataclass, field

import numpy as np

# Die Auslegung gehoert zum Projekt und steht deshalb in engine/models.py
# (siehe dort). Hier wird sie nur weitergereicht, damit
# `from engine.storage import BatteryConfig` weiterhin traegt.
from ..models import BatteryConfig, SpeicherModus

__all__ = [
    "BAHN_SPALTEN",
    "BatteryConfig",
    "SolverFehler",
    "SpeicherModus",
    "StorageDispatchResult",
    "StorageJahreswert",
]


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
    #: Abregelung des Vergleichslaufs in MWh - Bezugspunkt der
    #: Rueckgewinnung. Sie steht hier und nicht in der Bahn, weil sie zu
    #: einem ANDEREN Lauf gehoert; in einer Spalte neben den Stunden des
    #: optimierten Laufs waere sie irrefuehrend.
    abregelung_pv_only_mwh: float = 0.0
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
