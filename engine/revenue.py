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
"""

from __future__ import annotations

import pandas as pd

from .models import EffectiveAssumptions

REVENUE_COLUMNS = ["jahr", "kalenderjahr", "verguetungssatz_ct_kwh", "erloes_eur"]


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

    marktwert = _kurve_nachschlagen(
        df["kalenderjahr"], assumptions.marktwert_solar_ct_kwh_je_kalenderjahr
    )

    innerhalb_foerderdauer = df["jahr"] <= assumptions.eag_foerderdauer_jahre
    praemie = (assumptions.eag_zuschlagswert_effektiv_ct_kwh - marktwert).clip(
        lower=0
    )
    satz_ct_kwh = marktwert + innerhalb_foerderdauer.astype(float) * praemie

    df["verguetungssatz_ct_kwh"] = satz_ct_kwh

    anteil_negativ = _kurve_nachschlagen(
        df["kalenderjahr"], assumptions.anteil_negativer_stunden_pct_je_kalenderjahr
    )
    verguetete_produktion_kwh = energy["produktion_kwh"].to_numpy() * (
        1 - anteil_negativ.to_numpy()
    )

    df["erloes_eur"] = verguetete_produktion_kwh * satz_ct_kwh.to_numpy() / 100.0

    return df[REVENUE_COLUMNS]
