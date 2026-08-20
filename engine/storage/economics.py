"""
Der Grenzerloes je Stunde - und was der Dispatch daraus wert ist.

Dieses Modul ist die Bruecke zwischen der bestehenden Foerderlogik und
dem Optimierer. Es baut KEINE zweite Foerderrechnung: Die Praemie kommt
aus `engine.revenue._praemie_je_kwh`, dieselbe Funktion, die auch der
Cashflow benutzt.

Warum der Zeitpunkt der Einspeisung den Foerderanspruch nicht beruehrt
---------------------------------------------------------------------
Die gleitende Marktpraemie bemisst sich am REFERENZmarktwert (Monats-
bzw. Jahreswert), nicht am tatsaechlich erzielten Preis - so steht es im
Kopf von engine/revenue.py, und daraus folgt der ganze Rest:

    Verschiebt der Speicher eine MWh von 12 auf 19 Uhr, aendert sich die
    Praemie NICHT. Der Grenzwert der Verschiebung ist die reine
    Preisdifferenz der beiden Stunden.

Was sich sehr wohl aendert, ist die MENGE: Zurueckgewonnene Abregelung
erhoeht die gefoerderte Menge, Roundtrip-Verluste senken sie. Beides
laeuft ueber die Praemie je kWh und ist damit im Grenzerloes enthalten.

Der Grenzerloes je Stunde ist deshalb

    v(t) = preis(t) + 10 * (praemie - rueckzahlung)      [EUR/MWh]

mit dem Faktor 10 fuer ct/kWh -> EUR/MWh, und praemie = 0 in den
Stunden, in denen die Foerderung wegen negativer Preise entfaellt.

Ausdrueckliche Vereinfachungen fuer V1
--------------------------------------
1. NUR DAY-AHEAD. Intraday, FCR, aFRR und mFRR sind nicht modelliert -
   es gibt keine Zeitreihen dafuer. Der ausgewiesene Wert ist damit eine
   UNTERGRENZE des realen Speicherwerts, nicht seine Obergrenze.
2. PERFEKTE VORAUSSCHAU. Der Optimierer kennt das ganze Jahr. Ein realer
   Betreiber handelt gegen eine Prognose und erreicht davon
   erfahrungsgemaess 80-95 %. Der Wert ist insofern eine OBERGRENZE des
   Day-Ahead-Werts. Beide Effekte wirken gegenlaeufig; sie werden NICHT
   gegeneinander aufgerechnet.
3. NETZENERGIE IST NICHT FOERDERFAEHIG. Was der Graustromspeicher aus
   dem Netz zieht und wieder einspeist, erhaelt keine Marktpraemie - es
   ist keine PV-Erzeugung. Umgesetzt ueber die Mengenbilanz (siehe
   `jahreswert`), nicht ueber einen zweiten SOC.
4. PPA ALS FINANZIELLER KONTRAKT. Ein PPA-Anteil veraendert den
   Dispatch-Anreiz nicht; der Speicher optimiert gegen den
   Day-Ahead-Preis. Fuer einen physischen Pay-as-produced-Vertrag waere
   das zu vereinfacht - dann gehoerte die vertraglich abgenommene Menge
   aus dem optimierbaren Volumen heraus.
5. ABREGELUNG BEI NEGATIVEM WERT. Faellt der Grenzerloes unter null,
   regelt der Optimierer ab, statt einzuspeisen - unabhaengig vom
   eingestellten Negativstunden-Modus. Ein rationaler Betreiber zahlt
   nicht dafuer, Strom zu liefern.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..models import EffectiveAssumptions, NegativeStundenRegel
from ..revenue import _praemie_je_kwh
from .models import BatteryConfig, StorageDispatchResult, StorageJahreswert

#: ct/kWh -> EUR/MWh
_CT_KWH_ZU_EUR_MWH = 10.0


def negativstunden_maske(
    preis_eur_mwh: np.ndarray, regel: NegativeStundenRegel
) -> np.ndarray:
    """Stunden, in denen die Foerderung entfaellt.

    Die 1-Stunden-Regel trifft jede Stunde mit negativem Preis. Die
    6-Stunden-Regel greift erst, wenn der Preis SECHS Stunden in Folge
    negativ war - und dann fuer diese Stunden.

    Das ist dieselbe gesetzliche Regel, die das Cashflow-Modell ueber
    einen Mengenanteil je Monat abbildet (`anteil_negativer_stunden_*`).
    Hier laesst sie sich exakt auswerten, weil die Stundenreihe vorliegt;
    es ist keine zweite Regel, sondern dieselbe in der Aufloesung, fuer
    die sie geschrieben wurde.
    """
    negativ = preis_eur_mwh < 0
    if regel == NegativeStundenRegel.EINE_STUNDE:
        return negativ

    # Laufende Laenge der negativen Serie je Stunde
    maske = np.zeros_like(negativ)
    lauf = 0
    for i, ist_negativ in enumerate(negativ):
        lauf = lauf + 1 if ist_negativ else 0
        if lauf >= 6:
            # Die ganze bisherige Serie faellt aus der Foerderung
            maske[i - lauf + 1: i + 1] = True
    return maske


def grenzerloes_je_stunde(
    preis_eur_mwh: np.ndarray,
    referenz_marktwert_ct_kwh: float,
    assumptions: EffectiveAssumptions,
    in_foerderdauer: bool = True,
) -> np.ndarray:
    """Was eine zusaetzlich eingespeiste MWh in dieser Stunde einbringt.

    `referenz_marktwert_ct_kwh` ist der Marktwert Solar des
    Bezugszeitraums - genau die Groesse, an der sich die Praemie bemisst.
    Er kommt aus dem Marktpreisszenario und nicht aus der Stundenreihe:
    Die Praemie haengt am Referenzwert, nicht am erzielten Preis.
    """
    praemie, rueckzahlung = _praemie_je_kwh(
        np.array([referenz_marktwert_ct_kwh]), assumptions
    )
    netto_ct_kwh = float(praemie[0] - rueckzahlung[0])
    if not in_foerderdauer:
        netto_ct_kwh = 0.0

    foerderung = np.full(len(preis_eur_mwh), netto_ct_kwh * _CT_KWH_ZU_EUR_MWH)
    ohne_foerderung = negativstunden_maske(
        preis_eur_mwh, assumptions.negative_stunden_regel
    )
    # Die Gewichtung blendet den Effekt stufenlos ein - dieselbe
    # Bedeutung wie in der Jahresrechnung (0 % = Regel ohne Wirkung).
    gewicht = assumptions.negative_stunden_gewichtung_pct
    foerderung[ohne_foerderung] *= 1.0 - gewicht
    return preis_eur_mwh + foerderung


# --- Auswertung -------------------------------------------------------------


@dataclass(frozen=True)
class Wertzerlegung:
    """Woher der Speicherwert kommt.

    Nur die NETZARBITRAGE ist eine exakte Differenz zweier
    Optimierungen: Sie ist der Mehrwert, den die Erlaubnis zum Netzbezug
    stiftet, und laesst sich durch einen zweiten Lauf ohne diese
    Erlaubnis sauber abgrenzen.

    Die Aufteilung des PV-Anteils in Abregelungsrueckgewinn und
    Zeitverschiebung ist dagegen NICHT eindeutig: Dieselbe gespeicherte
    Kilowattstunde kann beides zugleich sein - sie waere abgeregelt
    worden UND sie wird in eine teurere Stunde verschoben. Es gibt keine
    Reihenfolge der beiden Effekte, die sachlich zwingender waere als die
    andere.

    Deshalb wird hier NICHT gerechnet, als waere sie eindeutig: Der
    PV-Anteil steht als eine Zahl, daneben die zurueckgewonnene Menge in
    MWh als das, was sie ist - eine Menge, keine Wertzuordnung.
    """

    pv_speicherwert_eur: float
    netzarbitrage_eur: float
    rueckgewonnene_kappung_mwh: float
    verschobene_energie_mwh: float

    @property
    def gesamt_eur(self) -> float:
        return self.pv_speicherwert_eur + self.netzarbitrage_eur


def vollzyklen(ergebnis: StorageDispatchResult, batterie: BatteryConfig) -> float:
    """Aequivalente Vollzyklen des Jahres.

    Definition: entladene Energie geteilt durch die NUTZBARE Kapazitaet
    (Hub zwischen soc_min und soc_max), nicht durch die Bruttokapazitaet.
    Ein Zyklus ist damit das einmalige Durchfahren dessen, was der
    Speicher tatsaechlich hergibt.
    """
    if batterie.nutzbare_kapazitaet_mwh <= 0:
        return 0.0
    entladen = float(ergebnis.spalte("speicher_ins_netz_mw").sum())
    return entladen / batterie.nutzbare_kapazitaet_mwh


def jahreswert(
    ergebnis: StorageDispatchResult,
    batterie: BatteryConfig,
    abregelung_ohne_speicher_mwh: float,
) -> StorageJahreswert:
    """Aggregiert ein optimiertes Jahr zu dem, was der Cashflow braucht."""
    preis = ergebnis.spalte("preis_eur_mwh")
    pv_speicher = ergebnis.spalte("pv_in_speicher_mw")
    netz_speicher = ergebnis.spalte("netz_in_speicher_mw")
    entladung = ergebnis.spalte("speicher_ins_netz_mw")
    abregelung = ergebnis.spalte("abregelung_mw")

    laden = float((pv_speicher + netz_speicher).sum())
    entladen = float(entladung.sum())
    durchsatz = 0.5 * (laden + entladen)

    return StorageJahreswert(
        jahr=ergebnis.jahr,
        kalenderjahr=ergebnis.kalenderjahr,
        mehrerloes_eur=ergebnis.wertbeitrag_eur
        + float((netz_speicher * preis).sum())
        + batterie.degradationskosten_eur_mwh * durchsatz,
        netzbezugskosten_eur=float((netz_speicher * preis).sum()),
        degradationskosten_eur=batterie.degradationskosten_eur_mwh * durchsatz,
        mehrmenge_kwh=(
            abregelung_ohne_speicher_mwh - float(abregelung.sum())
            - (laden - entladen)
        ) * 1000.0,
        rueckgewonnene_kappung_kwh=(
            abregelung_ohne_speicher_mwh - float(abregelung.sum())
        ) * 1000.0,
        speicher_ladung_mwh=laden,
        speicher_entladung_mwh=entladen,
        vollzyklen=vollzyklen(ergebnis, batterie),
    )


def zerlegung(
    mit_speicher: StorageDispatchResult,
    nur_pv_abregelung_mwh: float,
    ohne_netzbezug: StorageDispatchResult | None = None,
) -> Wertzerlegung:
    """Der Wertbeitrag, so weit er sich sauber trennen laesst.

    `ohne_netzbezug` ist der Lauf desselben Speichers im
    Gruenstrom-Betrieb. Fehlt er (weil der Speicher ohnehin nur PV
    laedt), ist die Netzarbitrage null.
    """
    gesamt = mit_speicher.wertbeitrag_eur
    if ohne_netzbezug is None:
        pv_anteil, arbitrage = gesamt, 0.0
    else:
        pv_anteil = ohne_netzbezug.wertbeitrag_eur
        arbitrage = gesamt - pv_anteil

    abregelung_mit = float(mit_speicher.spalte("abregelung_mw").sum())
    return Wertzerlegung(
        pv_speicherwert_eur=pv_anteil,
        netzarbitrage_eur=arbitrage,
        rueckgewonnene_kappung_mwh=max(nur_pv_abregelung_mwh - abregelung_mit, 0.0),
        verschobene_energie_mwh=float(
            mit_speicher.spalte("pv_in_speicher_mw").sum()
        ),
    )
