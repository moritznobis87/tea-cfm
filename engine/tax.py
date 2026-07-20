"""
Berechnet die Steuerlast - Pauschalsatz auf EBT oder AfA-basierte
Koerperschaftsteuer mit Freibetrag und Verlustvortrag (siehe TaxModus in
models.py).

Verlustvortrag (§8 Abs. 4 Z 2 KStG): Verluste sind in Oesterreich zeitlich
UNBEGRENZT vortragbar, aber in einem Gewinnjahr duerfen maximal
verlustvortrag_verrechnungsgrenze_pct (gesetzlich 75%) des steuerlichen
Ergebnisses durch vorgetragene Verluste verrechnet werden - der Rest muss
in jedem Fall versteuert werden. Deshalb ist diese Berechnung bewusst
SEQUENZIELL (Jahr fuer Jahr, nicht vektorisiert): der Verlustvortrag-
Bestand haengt vom Vorjahr ab.

Fuer volle Nachvollziehbarkeit werden AfA, Verlustvortrag-Bestand
(Anfang/Ende) und das tatsaechlich versteuerte Ergebnis als eigene
Spalten zurueckgegeben, nicht nur der Steuerbetrag - die UI zeigt diese
Zeitreihe explizit an (siehe Detailtabelle im Cashflow-Tab).
"""

from __future__ import annotations

import pandas as pd

from .models import TaxModus

TAX_COLUMNS = [
    "jahr",
    "afa_eur",
    "verlustvortrag_bop_eur",
    "steuerliches_ergebnis_vor_verlustvortrag_eur",
    "verlustvortrag_genutzt_eur",
    "verlustvortrag_bestand_eur",
    "steuerliches_ergebnis_eur",
    "steuer_eur",
]


def calculate_tax(
    revenue: pd.DataFrame,
    opex: pd.DataFrame,
    financing: pd.DataFrame,
    capex_total_eur: float,
    tax_modus: TaxModus,
    steuersatz_pct: float,
    afa_nutzungsdauer_jahre: int | None,
    freibetrag_eur: float,
    verlustvortrag_verrechnungsgrenze_pct: float,
) -> pd.DataFrame:
    ebt_vor_afa = (
        revenue["erloes_eur"].to_numpy()
        - opex["opex_gesamt_eur"].to_numpy()
        - financing["zinsen_eur"].to_numpy()
    )

    if tax_modus == TaxModus.PAUSCHAL_AUF_EBT:
        afa_eur_je_jahr = 0.0
        freibetrag_wirksam = 0.0
    else:
        afa_eur_je_jahr = capex_total_eur / afa_nutzungsdauer_jahre
        freibetrag_wirksam = freibetrag_eur

    rows = []
    verlustvortrag_bop = 0.0
    for jahr, ebt_ohne_afa in zip(revenue["jahr"], ebt_vor_afa, strict=True):
        # AfA nur innerhalb der Nutzungsdauer - danach ist das Wirtschaftsgut
        # steuerlich voll abgeschrieben, eine weitere Abschreibung waere
        # unzulaessig.
        afa = (
            afa_eur_je_jahr
            if tax_modus == TaxModus.AFA_KOERPERSCHAFTSTEUER
            and jahr <= afa_nutzungsdauer_jahre
            else 0.0
        )
        ergebnis_vor_verlustvortrag = ebt_ohne_afa - afa - freibetrag_wirksam

        if ergebnis_vor_verlustvortrag > 0:
            max_verrechenbar = (
                ergebnis_vor_verlustvortrag * verlustvortrag_verrechnungsgrenze_pct
            )
            verlustvortrag_genutzt = min(verlustvortrag_bop, max_verrechenbar)
        else:
            verlustvortrag_genutzt = 0.0

        steuerliches_ergebnis = max(
            ergebnis_vor_verlustvortrag - verlustvortrag_genutzt, 0.0
        )
        steuer = steuerliches_ergebnis * steuersatz_pct

        neuer_verlust_dieses_jahr = max(-ergebnis_vor_verlustvortrag, 0.0)
        verlustvortrag_eop = (
            verlustvortrag_bop - verlustvortrag_genutzt + neuer_verlust_dieses_jahr
        )

        rows.append(
            {
                "jahr": jahr,
                "afa_eur": afa,
                "verlustvortrag_bop_eur": verlustvortrag_bop,
                "steuerliches_ergebnis_vor_verlustvortrag_eur": ergebnis_vor_verlustvortrag,
                "verlustvortrag_genutzt_eur": verlustvortrag_genutzt,
                "verlustvortrag_bestand_eur": verlustvortrag_eop,
                "steuerliches_ergebnis_eur": steuerliches_ergebnis,
                "steuer_eur": steuer,
            }
        )
        verlustvortrag_bop = verlustvortrag_eop

    return pd.DataFrame(rows, columns=TAX_COLUMNS)
