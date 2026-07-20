"""
Berechnet die Erloes-Zeitreihe nach dem oesterreichischen EAG-
Marktpraemien-Mechanismus (gleitende Marktpraemie):

- Solange die EAG-Foerderdauer laeuft: Verguetung = MAX(Marktwert Solar,
  EAG-Zuschlagswert). Liegt der Marktwert unter dem Zuschlagswert, wird die
  Differenz als Praemie zugeschossen; liegt er darueber, erhaelt der
  Betreiber den (hoeheren) Marktwert.
- Nach Ablauf der Foerderdauer: reiner Marktpreisverkauf zum Marktwert
  Solar (keine Praemie mehr).
- In Stunden mit negativen Strompreisen entfaellt die Foerderung
  vollstaendig (anteil_negativer_stunden reduziert die verguetete
  Produktionsmenge) - das ist eine gesetzliche Regelung, keine
  Vereinfachung.

WICHTIG: Die Marktpreiskurven sind nach echtem KALENDERJAHR indiziert
(z.B. 2025-2060), nicht nach Betriebsjahr. Deshalb wird hier zuerst aus
dem Betriebsjahr (1, 2, 3, ...) unter Beruecksichtigung des projekt-
spezifischen Inbetriebnahmejahrs das tatsaechliche Kalenderjahr gebildet,
bevor in die Kurve nachgeschlagen wird. Liegt das Kalenderjahr ausserhalb
der in der Kurve definierten Jahre (z.B. Projekt startet vor 2025 oder
laeuft ueber 2060 hinaus), wird auf den jeweils naechstliegenden Rand-
wert der Kurve zurueckgegriffen (Clamping), statt zu extrapolieren.

INFLATIONIERUNG: Die Marktwert-Solar-Kurven aus Marktpreisstudien sind
REALE Werte auf Preisbasis des Studien-Erscheinungsjahrs (typischerweise,
z.B. "reale 2025-Preise"), keine bereits inflationierten Nominalwerte.
Fuer eine nominale Cashflow-Rechnung wird deshalb ein Inflationsaufschlag
angewendet: nominal(kalenderjahr) = real(kalenderjahr) *
(1+inflation)^(kalenderjahr - basisjahr). Der EAG-Zuschlagswert bleibt
davon UNBERUEHRT - er ist waehrend der Foerderdauer gesetzlich nominal
fix (keine Indexierung). Der MAX(Marktwert, EAG)-Vergleich erfolgt daher
konsistent zwischen dem bereits inflationierten (nominalen) Marktwert und
dem nominal fixen EAG-Zuschlagswert.
"""

from __future__ import annotations

import pandas as pd

from .models import EffectiveAssumptions, NegativeStundenModus

REVENUE_COLUMNS = [
    "jahr", "kalenderjahr", "marktwert_real_ct_kwh", "marktwert_nominal_ct_kwh",
    "verguetungssatz_ct_kwh", "erloes_eur", "erloes_markt_eur", "erloes_praemie_eur",
]


def _kurve_nachschlagen(kalenderjahr: pd.Series, kurve: dict[int, float]) -> pd.Series:
    if not kurve:
        return pd.Series(0.0, index=kalenderjahr.index)
    jahre_verfuegbar = sorted(kurve)
    geklemmt = kalenderjahr.clip(lower=jahre_verfuegbar[0], upper=jahre_verfuegbar[-1])
    return geklemmt.astype(int).map(kurve)


def calculate_revenue(
    timeline: pd.DataFrame, energy: pd.DataFrame, assumptions: EffectiveAssumptions
) -> pd.DataFrame:
    df = timeline[["jahr"]].copy()
    df["kalenderjahr"] = assumptions.inbetriebnahme_jahr + (df["jahr"] - 1)

    marktwert_real = _kurve_nachschlagen(
        df["kalenderjahr"], assumptions.marktwert_solar_ct_kwh_je_kalenderjahr
    )
    # Inflationsfaktor bewusst auf Basis des TATSAECHLICHEN Kalenderjahres
    # (nicht des ggf. am Kurvenrand geklemmten Nachschlagejahres) - auch
    # wenn ueber das letzte Kurvenjahr hinaus mit dem letzten bekannten
    # Realpreis weitergerechnet wird, laeuft die allgemeine Geldentwertung
    # unabhaengig davon weiter.
    inflationsfaktor = (1 + assumptions.marktpreis_inflation_pct_pa) ** (
        df["kalenderjahr"] - assumptions.marktpreis_inflation_basisjahr
    )
    marktwert_nominal = marktwert_real * inflationsfaktor

    df["marktwert_real_ct_kwh"] = marktwert_real
    df["marktwert_nominal_ct_kwh"] = marktwert_nominal

    innerhalb_foerderdauer = df["jahr"] <= assumptions.eag_foerderdauer_jahre
    praemie = (assumptions.eag_zuschlagswert_effektiv_ct_kwh - marktwert_nominal).clip(
        lower=0
    )
    satz_ct_kwh = marktwert_nominal + innerhalb_foerderdauer.astype(float) * praemie

    df["verguetungssatz_ct_kwh"] = satz_ct_kwh

    anteil_negativ_ungewichtet = _kurve_nachschlagen(
        df["kalenderjahr"], assumptions.anteil_negativer_stunden_pct_je_kalenderjahr
    )
    # Gewichtung 0% = Effekt komplett ausgeblendet (volle Verguetung auch
    # in Stunden negativer Preise), 100% = volle gesetzliche Wirkung.
    anteil_negativ = anteil_negativ_ungewichtet * assumptions.negative_stunden_gewichtung_pct

    produktion_kwh = energy["produktion_kwh"].to_numpy()
    satz = satz_ct_kwh.to_numpy()

    # Aufteilung des Erloeses in Markterloes (Verkauf zum nominalen
    # Marktwert) und Marktpraemie (Differenz Verguetungssatz - Marktwert,
    # nur waehrend der Foerderdauer > 0). Die Praemie entfaellt in Stunden
    # negativer Preise in BEIDEN Modi - die Modi unterscheiden sich nur
    # darin, ob der Markterloes fuer diesen Anteil erhalten bleibt.
    mw = marktwert_nominal.to_numpy()
    neg = anteil_negativ.to_numpy()
    praemie_je_kwh = satz - mw  # >= 0, nach Foerderdauer exakt 0

    if assumptions.negative_stunden_modus == NegativeStundenModus.MARKTWERT:
        # Anlage wird NICHT abgeregelt: Fuer den Anteil negativer Stunden
        # entfaellt nur die Marktpraemie, der (nominale) Jahresmarktwert
        # wird weiterhin verguetet. Nach der Foerderdauer ist der Satz
        # ohnehin der Marktwert - dieser Modus hat dann keine Wirkung mehr.
        df["erloes_markt_eur"] = produktion_kwh * mw / 100.0
        df["erloes_praemie_eur"] = produktion_kwh * (1 - neg) * praemie_je_kwh / 100.0
    else:
        # ABREGELUNG (Standard): Fuer den Anteil negativer Stunden
        # entfallen die Erloese vollstaendig - die Menge wird nicht
        # eingespeist.
        df["erloes_markt_eur"] = produktion_kwh * (1 - neg) * mw / 100.0
        df["erloes_praemie_eur"] = produktion_kwh * (1 - neg) * praemie_je_kwh / 100.0

    df["erloes_eur"] = df["erloes_markt_eur"] + df["erloes_praemie_eur"]

    return df[REVENUE_COLUMNS]
