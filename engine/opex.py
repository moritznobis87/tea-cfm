"""
Berechnet die Betriebskosten-Zeitreihe - sowohl die Gesamtsumme als auch
JEDE Kostenposition als eigene Spalte (Name der Position = Spaltenname),
damit die UI eine vollstaendige, aufgeschluesselte Aufstellung anzeigen
kann (z.B. als gestapeltes Balkendiagramm mit einer Position pro Legenden-
eintrag).

Quellen: globale Standard-OPEX-Positionen (EUR/kWp/Jahr-basiert), die
Pacht (eigene, produktionsUNabhaengige aber ggf. umsatzabhaengige
Position, siehe PachtModus) sowie zwei produktionsbasierte Positionen
(EUR/kWh, deshalb keine OpexItems, sondern separate Parameter):
Gemeindeabgabe und Direktvermarktungskosten.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .models import DirektvermarktungsModus, OpexItem, PachtModus

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
    pacht_modus: PachtModus = PachtModus.FIX,
    pacht_eur_kwp_jahr: float = 0.0,
    pacht_umsatzbeteiligung_pct: float = 0.0,
    pacht_mindestpacht_eur_ha_jahr: float = 0.0,
    projektflaeche_ha: float | None = None,
    erloes_eur: np.ndarray | None = None,
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
    # sowie Pacht (EUR/kWh- bzw. EUR/kWp- oder EUR/ha-Saetze, Preisstand
    # Inbetriebnahme = Betriebsjahr 1).
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

    # Pacht: eigene, benannte Position (wie ein OpexItem im gestapelten
    # Diagramm), aber je nach PachtModus unterschiedlich berechnet - kann
    # deshalb nicht ueber die generische opex_items-Schleife oben laufen.
    if pacht_modus == PachtModus.UMSATZBETEILIGUNG and erloes_eur is not None:
        umsatzbeteiligung = erloes_eur * pacht_umsatzbeteiligung_pct
        mindestpacht = (
            pacht_mindestpacht_eur_ha_jahr
            * (projektflaeche_ha or 0.0)
            * inflation_faktor
        )
        pacht_betrag = np.maximum(umsatzbeteiligung, mindestpacht)
    else:
        pacht_basis_eur = pacht_eur_kwp_jahr * nennleistung_kwp
        pacht_betrag = pacht_basis_eur * inflation_faktor
    # Additiv wie die generische Schleife oben: falls eine Standard-OPEX-
    # Position zufaellig ebenfalls "Pacht" heisst, wird addiert statt
    # einer doppelten Spalte (die spaetere Spaltenauswahl wuerde sonst
    # zwei gleichnamige Spalten liefern).
    if "Pacht" in df.columns:
        df["Pacht"] = df["Pacht"] + pacht_betrag
    else:
        df["Pacht"] = pacht_betrag
        posten_spalten.append("Pacht")
    # Nur den HIER berechneten Anteil addieren, nicht die (im Kollisions-
    # fall bereits um den generischen Loop-Beitrag ergaenzte) Spalte -
    # sonst wuerde der generische Anteil doppelt gezaehlt.
    df["opex_gesamt_eur"] += pacht_betrag

    return df[BASISSPALTEN + posten_spalten]
