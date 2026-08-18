"""
Berechnet die Steuerlast - drei Modi (siehe TaxModus in models.py):
Pauschalsatz auf EBT, oesterreichische AfA-Koerperschaftsteuer mit
Freibetrag und Verlustvortrag, oder deutsche Gewerbesteuer.

Abschreibung im Anlaufjahr: Oesterreich kennt die Halbjahresregelung
(§ 7 Abs. 2 EStG) - mehr als sechs Monate Nutzung ergeben die volle
Jahres-AfA, sonst die halbe. Deutschland rechnet monatsgenau (§ 7 Abs. 1
Satz 4 EStG). Der im Anlaufjahr nicht genutzte Teil verfaellt nicht: Es
wird abgeschrieben, solange Restbuchwert vorhanden ist, die Abschreibung
reicht also entsprechend weiter.

Oesterreichischer Verlustvortrag (§8 Abs. 4 Z 2 KStG): Verluste sind
zeitlich UNBEGRENZT vortragbar, aber in einem Gewinnjahr duerfen
maximal verlustvortrag_verrechnungsgrenze_pct (gesetzlich 75%) des
steuerlichen Ergebnisses durch vorgetragene Verluste verrechnet
werden - der Rest muss in jedem Fall versteuert werden.

Deutsche Gewerbesteuer: Steuer = MAX(EBT - AfA - Freibetrag, 0) x
Steuermesszahl (gesetzlich 3,5%) x Hebesatz (gemeindeabhaengig,
haeufig 400-450%). Freibetrag gesetzlich 24.500 EUR/Jahr bei
Personengesellschaften (u.a. GmbH & Co. KG). Vereinfachend OHNE
Verlustvortrag modelliert (jedes Jahr unabhaengig betrachtet) - echte
Gewerbesteuer kennt zwar einen Verlustvortrag (§10a GewStG), dieser
wird hier bewusst nicht abgebildet, da das als Referenz validierte
Modell (Vergleich mit einer realen Projekt-Excel) ihn ebenfalls nicht
beruecksichtigt.

Freibetrag und Verlust sind zweierlei: Der Freibetrag mindert die
Bemessungsgrundlage bis auf null, erzeugt aber KEINEN vortragsfaehigen
Verlust. Wurde er (bis v5.18) vor der Verlustermittlung abgezogen, baute
schon ein Jahr mit kleinem Gewinn einen Verlustvortrag auf, den es nie
gegeben hat. Die Reihenfolge ist deshalb: steuerliches Ergebnis, dann
Verlustabzug, dann Freibetrag.

Fuer volle Nachvollziehbarkeit werden AfA, Verlustvortrag-Bestand
(Anfang/Ende) und das tatsaechlich versteuerte Ergebnis als eigene
Spalten zurueckgegeben, nicht nur der Steuerbetrag - die UI zeigt diese
Zeitreihe explizit an (siehe Detailtabelle im Cashflow-Tab). Deshalb ist
diese Berechnung bewusst SEQUENZIELL (Jahr fuer Jahr, nicht vektorisiert):
der Verlustvortrag-Bestand haengt vom Vorjahr ab.
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


def _anlaufjahr_afa_anteil(tax_modus: TaxModus, inbetriebnahme_monat: int) -> float:
    """Anteil der Jahres-AfA, der im Anlaufjahr angesetzt werden darf.

    OESTERREICH (Koerperschaftsteuer): Halbjahresregelung (§ 7 Abs. 2
    EStG) - wird das Wirtschaftsgut mehr als sechs Monate genutzt, steht
    die volle Jahres-AfA zu, sonst die halbe. Es gibt nichts dazwischen.

    DEUTSCHLAND (Gewerbesteuer): pro rata temporis (§ 7 Abs. 1 Satz 4
    EStG) - je angefangenem Nutzungsmonat ein Zwoelftel.

    Frueher stand hier in beiden Faellen die volle Jahres-AfA: Eine im
    Dezember angeschlossene Anlage schrieb ein ganzes Jahr ab, obwohl sie
    einen Monat lief.
    """
    monate_in_betrieb = 13 - inbetriebnahme_monat
    if tax_modus == TaxModus.GEWERBESTEUER_DE:
        return monate_in_betrieb / 12
    if tax_modus == TaxModus.AFA_KOERPERSCHAFTSTEUER:
        return 1.0 if monate_in_betrieb > 6 else 0.5
    # Ohne AfA (Pauschalmodus) ist der Anteil ohne Bedeutung.
    return 1.0


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
    gewerbesteuer_hebesatz_pct: float = 400.0,
    gewerbesteuer_freibetrag_eur: float = 24_500.0,
    inbetriebnahme_monat: int = 1,
) -> pd.DataFrame:
    ebt_vor_afa = (
        revenue["erloes_eur"].to_numpy()
        - opex["opex_gesamt_eur"].to_numpy()
        - financing["zinsen_eur"].to_numpy()
    )

    afa_aktiv = tax_modus in (
        TaxModus.AFA_KOERPERSCHAFTSTEUER, TaxModus.GEWERBESTEUER_DE,
    )
    if tax_modus == TaxModus.PAUSCHAL_AUF_EBT:
        afa_eur_je_jahr = 0.0
        freibetrag_wirksam = 0.0
        effektiver_satz = steuersatz_pct
        verrechnungsgrenze_wirksam = verlustvortrag_verrechnungsgrenze_pct
    elif tax_modus == TaxModus.GEWERBESTEUER_DE:
        afa_eur_je_jahr = capex_total_eur / afa_nutzungsdauer_jahre
        freibetrag_wirksam = gewerbesteuer_freibetrag_eur
        # Steuermesszahl (gesetzlich 3,5%) x Hebesatz (z.B. 400% -> 4,0).
        effektiver_satz = 0.035 * (gewerbesteuer_hebesatz_pct / 100)
        # Bewusst kein Verlustvortrag (siehe Modul-Docstring).
        verrechnungsgrenze_wirksam = 0.0
    else:
        afa_eur_je_jahr = capex_total_eur / afa_nutzungsdauer_jahre
        freibetrag_wirksam = freibetrag_eur
        effektiver_satz = steuersatz_pct
        verrechnungsgrenze_wirksam = verlustvortrag_verrechnungsgrenze_pct

    # Anteil der Jahres-AfA im Anlaufjahr. Eine im Dezember in Betrieb
    # genommene Anlage schreibt kein volles Jahr ab - und der nicht
    # genutzte Teil verfaellt nicht, er wandert ans Ende der
    # Nutzungsdauer (der Restbuchwert wird abgeschrieben, nicht gekuerzt).
    afa_anteil_anlaufjahr = _anlaufjahr_afa_anteil(tax_modus, inbetriebnahme_monat)

    rows = []
    verlustvortrag_bop = 0.0
    restbuchwert = capex_total_eur if afa_aktiv else 0.0
    for jahr, ebt_ohne_afa in zip(revenue["jahr"], ebt_vor_afa, strict=True):
        # Abgeschrieben wird, solange Restbuchwert da ist. Die Grenze
        # ersetzt die frueher feste Bedingung "jahr <= Nutzungsdauer":
        # Bei unterjaehrigem Beginn reicht die Abschreibung ein Jahr
        # weiter, die SUMME bleibt aber die Investition.
        anteil = afa_anteil_anlaufjahr if jahr == 1 else 1.0
        afa = min(afa_eur_je_jahr * anteil, restbuchwert) if afa_aktiv else 0.0
        restbuchwert -= afa
        # Der Freibetrag steht BEWUSST nicht in dieser Zeile: Er mindert die
        # Bemessungsgrundlage, ist aber kein Verlust. Zog man ihn hier ab,
        # baute ein Jahr mit kleinem Gewinn einen Verlustvortrag auf, den es
        # nie gegeben hat - und der spaeter echte Gewinne abschirmte.
        ergebnis_vor_verlustvortrag = ebt_ohne_afa - afa

        if ergebnis_vor_verlustvortrag > 0:
            max_verrechenbar = ergebnis_vor_verlustvortrag * verrechnungsgrenze_wirksam
            verlustvortrag_genutzt = min(verlustvortrag_bop, max_verrechenbar)
        else:
            verlustvortrag_genutzt = 0.0

        # Reihenfolge: erst Verlustabzug, dann Freibetrag (§ 11 GewStG fuer
        # die Gewerbesteuer; fuer die Koerperschaftsteuer ist der
        # Freibetrag mit dem ausgelieferten Standard 0 ohne Wirkung).
        steuerliches_ergebnis = max(
            ergebnis_vor_verlustvortrag - verlustvortrag_genutzt
            - freibetrag_wirksam,
            0.0,
        )
        steuer = steuerliches_ergebnis * effektiver_satz

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
