"""
Berechnet die Betriebskosten-Zeitreihe - sowohl die Gesamtsumme als auch
JEDE Kostenposition als eigene Spalte (Name der Position = Spaltenname),
damit die UI eine vollstaendige, aufgeschluesselte Aufstellung anzeigen
kann (z.B. als gestapeltes Balkendiagramm mit einer Position pro Legenden-
eintrag).

Quellen: globale Standard-OPEX-Positionen (EUR/kWp/Jahr-basiert), die
projektspezifische Pacht (wird in pipeline.py bereits zu einer
gemeinsamen Liste zusammengefuehrt) sowie zwei produktionsbasierte
Positionen (EUR/kWh, deshalb keine OpexItems, sondern separate Parameter):
Gemeindeabgabe und Direktvermarktungskosten.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .models import DirektvermarktungsModus, OpexItem

BASISSPALTEN = [
    "jahr", "opex_gesamt_eur", "gemeindeabgabe_eur", "direktvermarktungskosten_eur",
]


def calculate_opex(
    timeline: pd.DataFrame,
    opex_items: list[OpexItem],
    nennleistung_kwp: float,
    energy: pd.DataFrame,
    gemeindeabgabe_eur_kwh: float = 0.0,
    direktvermarktungskosten_eur_kwh: float = 0.0,
    direktvermarktung_modus: DirektvermarktungsModus = DirektvermarktungsModus.ABSOLUT,
    direktvermarktung_pct_marktwert: float = 0.0,
    marktwert_nominal_ct_kwh: np.ndarray | None = None,
    kosten_inflation_pct_pa: float = 0.0,
) -> pd.DataFrame:
    df = timeline[["jahr"]].copy()
    df["opex_gesamt_eur"] = 0.0

    posten_spalten: list[str] = []
    for item in opex_items:
        basis_eur = item.basiswert_eur_kwp * nennleistung_kwp
        aktiv = df["jahr"] >= item.start_betriebsjahr

        jahre_seit_indexstart = (df["jahr"] - item.indexierung_ab_jahr).clip(lower=0)
        indexierter_betrag = basis_eur * (1 + item.index_pct_pa) ** jahre_seit_indexstart
        betrag = aktiv.astype(float) * indexierter_betrag

        # Bei zwei Positionen mit identischem Namen wird addiert statt
        # einer neuen Spalte - so bleibt jede Bezeichnung ein eindeutiger
        # Legendeneintrag.
        if item.name in df.columns:
            df[item.name] = df[item.name] + betrag
        else:
            df[item.name] = betrag
            posten_spalten.append(item.name)

        df["opex_gesamt_eur"] += betrag

    produktion_kwh = energy["produktion_kwh"].to_numpy()
    # Allgemeine Kosteninflation fuer die produktionsbasierten Positionen
    # (EUR/kWh-Saetze, Preisstand Inbetriebnahme = Betriebsjahr 1).
    inflation_faktor = (
        (1 + kosten_inflation_pct_pa)
        ** (df["jahr"] - 1).clip(lower=0).to_numpy()
    )
    df["gemeindeabgabe_eur"] = (
        produktion_kwh * gemeindeabgabe_eur_kwh * inflation_faktor
    )
    if (
        direktvermarktung_modus == DirektvermarktungsModus.RELATIV_MARKTWERT
        and marktwert_nominal_ct_kwh is not None
    ):
        # Anteil am nominalen Jahresmarktwert je erzeugter kWh - die
        # Kosten steigen und fallen mit dem Preisniveau.
        df["direktvermarktungskosten_eur"] = (
            produktion_kwh
            * marktwert_nominal_ct_kwh
            / 100.0
            * direktvermarktung_pct_marktwert
        )
    else:
        df["direktvermarktungskosten_eur"] = (
            produktion_kwh * direktvermarktungskosten_eur_kwh * inflation_faktor
        )
    df["opex_gesamt_eur"] += df["gemeindeabgabe_eur"] + df["direktvermarktungskosten_eur"]

    return df[BASISSPALTEN + posten_spalten]
