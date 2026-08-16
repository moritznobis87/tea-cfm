"""
Erloes-Zeitreihe: Vermarktung (Merchant und/oder PPA) plus Foerderung.

Drei Fragen beantwortet dieses Modul, und sie sind bewusst getrennt:

1. WANN erzeugt die Anlage? - Jahres- oder Monatsscheiben (siehe
   engine/energy.py und GlobalAssumptions.zeitaufloesung). In der
   Monatsrechnung trifft die Sommermenge auf den Sommerpreis; die
   Jahresrechnung mittelt beides und ueberschaetzt den Erloes deshalb
   systematisch, weil PV genau dann erzeugt, wenn der Preis niedrig ist.

2. AN WEN wird verkauft? - Merchant zum Marktwert, PPA zum
   Vertragspreis, oder ein Teil von beidem (hybrid, siehe PVProject.ppa_*).

3. WAS zahlt die Foerderstelle? - je nach PraemienModell ein einseitiger
   CfD (bisheriges Verhalten), ein zweiseitiger CfD oder der
   oesterreichische Weg mit Toleranzband (§ 10 EAG).

Die drei Fragen sind unabhaengig voneinander: Die gleitende Marktpraemie
bemisst sich am REFERENZmarktwert, nicht am tatsaechlich erzielten Preis.
Ein PPA verschiebt deshalb die Erloesverteilung, nicht den
Foerderanspruch - wer unter dem Referenzwert verkauft, traegt die
Differenz selbst, wer darueber verkauft, behaelt sie.

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
fix (keine Indexierung). Der Vergleich Marktwert/anzulegender Wert
erfolgt daher konsistent zwischen dem bereits inflationierten (nominalen)
Marktwert und dem nominal fixen Zuschlagswert.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .energy import calculate_energy_production_monatlich
from .models import (
    EffectiveAssumptions,
    NegativeStundenModus,
    PraemienModell,
    Zeitaufloesung,
)

REVENUE_COLUMNS = [
    "jahr", "kalenderjahr", "marktwert_real_ct_kwh", "marktwert_nominal_ct_kwh",
    "verguetungssatz_ct_kwh", "erloes_eur", "erloes_markt_eur",
    "erloes_praemie_eur",
    # Aufgliederung der Vermarktung und die Gegenrichtung der Foerderung.
    # Ohne PPA ist erloes_ppa_eur = 0 und erloes_merchant_eur =
    # erloes_markt_eur; ohne Rueckzahlungspflicht ist rueckzahlung_eur = 0.
    "erloes_ppa_eur", "erloes_merchant_eur", "rueckzahlung_eur",
]


def _kurve_nachschlagen(kalenderjahr: pd.Series, kurve: dict[int, float]) -> pd.Series:
    if not kurve:
        return pd.Series(0.0, index=kalenderjahr.index)
    jahre_verfuegbar = sorted(kurve)
    geklemmt = kalenderjahr.clip(lower=jahre_verfuegbar[0], upper=jahre_verfuegbar[-1])
    return geklemmt.astype(int).map(kurve)


def _monatskurve_nachschlagen(
    kalenderjahr: pd.Series, monat: pd.Series, kurve: dict[int, list[float]]
) -> pd.Series:
    """Wie _kurve_nachschlagen, nur mit Monatsspalte - dieselbe
    Randwert-Klemmung ueber die Jahre."""
    if not kurve:
        return pd.Series(0.0, index=kalenderjahr.index)
    jahre_verfuegbar = sorted(kurve)
    geklemmt = kalenderjahr.clip(
        lower=jahre_verfuegbar[0], upper=jahre_verfuegbar[-1]
    ).astype(int)
    werte = [
        kurve[jahr][int(m) - 1] for jahr, m in zip(geklemmt, monat, strict=True)
    ]
    return pd.Series(werte, index=kalenderjahr.index, dtype=float)


def _ppa_preis_ct_kwh(
    jahr: pd.Series, assumptions: EffectiveAssumptions
) -> pd.Series:
    """PPA-Preis je Betriebsjahr in ct/kWh - ausserhalb der Vertragszeit 0.

    Indexiert wird ab dem ersten PPA-Jahr; ein Vertrag, der erst in
    Betriebsjahr 3 beginnt, startet also mit seinem vereinbarten Preis
    und nicht mit einem bereits zweimal indexierten.
    """
    start = assumptions.ppa_start_jahr
    ende = start + assumptions.ppa_laufzeit_jahre - 1
    innerhalb = (jahr >= start) & (jahr <= ende)
    index = (1 + assumptions.ppa_indexierung_pct_pa) ** (jahr - start).clip(lower=0)
    return innerhalb.astype(float) * assumptions.ppa_preis_eur_mwh / 10.0 * index


def _praemie_je_kwh(
    marktwert_ct_kwh: np.ndarray, assumptions: EffectiveAssumptions
) -> tuple[np.ndarray, np.ndarray]:
    """Praemie und Rueckzahlung je kWh (beide >= 0) vor der Foerderdauer-
    Pruefung.

    Getrennt gefuehrt, weil es zwei Zahlungsrichtungen sind: Die Praemie
    kommt von der Foerderstelle, die Rueckzahlung geht an sie zurueck.
    Zusammengefasst waere in der Auswertung nicht mehr zu sehen, welcher
    Teil des Ergebnisses aus einer Abschoepfung stammt.
    """
    anzulegender_wert = assumptions.eag_zuschlagswert_effektiv_ct_kwh
    praemie = np.maximum(anzulegender_wert - marktwert_ct_kwh, 0.0)
    ueberschuss = np.maximum(marktwert_ct_kwh - anzulegender_wert, 0.0)

    modell = assumptions.praemien_modell
    if modell == PraemienModell.ZWEISEITIG_CFD:
        # Voller Ausgleich in beide Richtungen: Der Betreiber erhaelt
        # immer genau den anzulegenden Wert.
        return praemie, ueberschuss

    if modell == PraemienModell.EAG_TOLERANZBAND:
        leistung_mw = assumptions.nennleistung_kwp / 1000.0
        if leistung_mw < assumptions.eag_rueckzahlung_ab_mw:
            # Unterhalb der Schwelle bleibt es beim einseitigen CfD -
            # kleine Anlagen behalten ihren Uebergewinn vollstaendig.
            return praemie, np.zeros_like(praemie)
        schwelle = anzulegender_wert * (
            1 + assumptions.eag_rueckzahlung_toleranzband_pct
        )
        ueber_band = np.maximum(marktwert_ct_kwh - schwelle, 0.0)
        return praemie, ueber_band * assumptions.eag_rueckzahlung_anteil_pct

    # EINSEITIG_CFD (Standard): keine Rueckzahlung.
    return praemie, np.zeros_like(praemie)


def _scheiben(
    timeline: pd.DataFrame, energy: pd.DataFrame, assumptions: EffectiveAssumptions
) -> pd.DataFrame:
    """Rechenscheiben mit Menge, Marktwert und Negativanteil.

    Eine Zeile je Jahr oder je Jahr und Monat - alles Weitere rechnet auf
    genau diesen Spalten und muss die Aufloesung nicht mehr kennen.
    """
    monatlich = assumptions.zeitaufloesung == Zeitaufloesung.MONAT
    if monatlich:
        df = calculate_energy_production_monatlich(timeline, assumptions)[
            ["jahr", "monat", "kalenderjahr", "produktion_kwh"]
        ].copy()
        marktwert_real = _monatskurve_nachschlagen(
            df["kalenderjahr"], df["monat"],
            assumptions.marktwert_solar_ct_kwh_je_monat,
        )
        negativ = _monatskurve_nachschlagen(
            df["kalenderjahr"], df["monat"],
            assumptions.anteil_negativer_stunden_pct_je_monat,
        )
    else:
        df = timeline[["jahr"]].copy()
        df["monat"] = 0
        df["kalenderjahr"] = assumptions.inbetriebnahme_jahr + (df["jahr"] - 1)
        df["produktion_kwh"] = energy["produktion_kwh"].to_numpy()
        marktwert_real = _kurve_nachschlagen(
            df["kalenderjahr"], assumptions.marktwert_solar_ct_kwh_je_kalenderjahr
        )
        negativ = _kurve_nachschlagen(
            df["kalenderjahr"],
            assumptions.anteil_negativer_stunden_pct_je_kalenderjahr,
        )

    # Inflationsfaktor bewusst auf Basis des TATSAECHLICHEN Kalenderjahres
    # (nicht des ggf. am Kurvenrand geklemmten Nachschlagejahres) - auch
    # wenn ueber das letzte Kurvenjahr hinaus mit dem letzten bekannten
    # Realpreis weitergerechnet wird, laeuft die allgemeine Geldentwertung
    # unabhaengig davon weiter.
    inflationsfaktor = (1 + assumptions.marktpreis_inflation_pct_pa) ** (
        df["kalenderjahr"] - assumptions.marktpreis_inflation_basisjahr
    )
    df["marktwert_real_ct_kwh"] = marktwert_real
    df["marktwert_nominal_ct_kwh"] = marktwert_real * inflationsfaktor
    # Gewichtung 0% = Effekt komplett ausgeblendet (volle Verguetung auch
    # in Stunden negativer Preise), 100% = volle gesetzliche Wirkung.
    df["anteil_negativ"] = negativ * assumptions.negative_stunden_gewichtung_pct
    return df


def calculate_revenue(
    timeline: pd.DataFrame, energy: pd.DataFrame, assumptions: EffectiveAssumptions
) -> pd.DataFrame:
    """Erloese je Betriebsjahr - unabhaengig von der Zeitaufloesung.

    Die Monatsrechnung ist eine Unterebene: Sie wird hier auf Jahre
    verdichtet, damit Kosten-, Finanzierungs- und Steuerrechnung
    unveraendert auf Jahresscheiben arbeiten koennen.
    """
    df = _scheiben(timeline, energy, assumptions)

    produktion = df["produktion_kwh"].to_numpy()
    mw = df["marktwert_nominal_ct_kwh"].to_numpy()
    neg = df["anteil_negativ"].to_numpy()
    innerhalb_foerderdauer = (
        df["jahr"].to_numpy() <= assumptions.eag_foerderdauer_jahre
    ).astype(float)

    praemie_je_kwh, rueckzahlung_je_kwh = _praemie_je_kwh(mw, assumptions)
    praemie_je_kwh = praemie_je_kwh * innerhalb_foerderdauer
    rueckzahlung_je_kwh = rueckzahlung_je_kwh * innerhalb_foerderdauer

    # Menge, die tatsaechlich vermarktet wird. Im Modus ABREGELUNG steht
    # die Anlage in Stunden negativer Preise still, im Modus MARKTWERT
    # speist sie weiter ein und erhaelt (nur) den Marktwert.
    if assumptions.negative_stunden_modus == NegativeStundenModus.MARKTWERT:
        menge_vermarktet = produktion
    else:
        menge_vermarktet = produktion * (1 - neg)
    # Gefoerderte Menge: In BEIDEN Modi entfaellt die Foerderung fuer den
    # Anteil negativer Stunden - das ist die gesetzliche Regelung.
    menge_gefoerdert = produktion * (1 - neg)

    # Vermarktungswege: Der PPA-Anteil bezieht sich auf die vermarktete
    # Menge, nicht auf die Nennleistung - ein Vertrag ueber 50 % der
    # Erzeugung liefert in einem schwachen Jahr eben weniger.
    ppa_preis = _ppa_preis_ct_kwh(df["jahr"], assumptions).to_numpy()
    ppa_anteil = assumptions.ppa_anteil_pct * (ppa_preis > 0)
    menge_ppa = menge_vermarktet * ppa_anteil
    menge_merchant = menge_vermarktet - menge_ppa

    df["erloes_ppa_eur"] = menge_ppa * ppa_preis / 100.0
    df["erloes_merchant_eur"] = menge_merchant * mw / 100.0
    df["erloes_markt_eur"] = df["erloes_ppa_eur"] + df["erloes_merchant_eur"]
    df["erloes_praemie_eur"] = menge_gefoerdert * praemie_je_kwh / 100.0
    df["rueckzahlung_eur"] = menge_gefoerdert * rueckzahlung_je_kwh / 100.0
    df["erloes_eur"] = (
        df["erloes_markt_eur"] + df["erloes_praemie_eur"] - df["rueckzahlung_eur"]
    )

    # Rechnerischer Verguetungssatz je kWh: Marktwert plus Foerderung
    # minus Rueckzahlung - der Satz, den die Foerderung ergibt, ohne den
    # Mengeneffekt der negativen Stunden und ohne PPA. Er beantwortet die
    # Frage "was ist eine Kilowattstunde wert?" und wird in Diagramm und
    # Bericht gegen den Marktwert gestellt.
    df["verguetungssatz_ct_kwh"] = mw + praemie_je_kwh - rueckzahlung_je_kwh

    if assumptions.zeitaufloesung != Zeitaufloesung.MONAT:
        return df[REVENUE_COLUMNS]

    return _verdichte_auf_jahre(df)


def _verdichte_auf_jahre(df: pd.DataFrame) -> pd.DataFrame:
    """Monatsscheiben zu Jahreszeilen.

    Betraege werden summiert, Preise mengengewichtet gemittelt: Der
    Jahresmarktwert einer PV-Anlage ist der Wert, den IHRE Kilowatt-
    stunden erloesen - ein ungewichteter Mittelwert ueber zwoelf Monate
    waere ein anderer (und fuer PV stets zu hoher) Preis.
    """
    menge_je_jahr = df["produktion_kwh"].groupby(df["jahr"]).sum()

    def _gewichtet(spalte: str) -> pd.Series:
        summe = (df[spalte] * df["produktion_kwh"]).groupby(df["jahr"]).sum()
        # Ein Jahr ganz ohne Erzeugung (theoretisch: Kurve komplett 0)
        # haette kein Gewicht - dann der einfache Mittelwert, damit die
        # Spalte keine Luecke bekommt.
        return (summe / menge_je_jahr).where(
            menge_je_jahr > 0, df[spalte].groupby(df["jahr"]).mean()
        )

    jahre = df.groupby("jahr", as_index=False).agg(
        kalenderjahr=("kalenderjahr", "first"),
        erloes_eur=("erloes_eur", "sum"),
        erloes_markt_eur=("erloes_markt_eur", "sum"),
        erloes_praemie_eur=("erloes_praemie_eur", "sum"),
        erloes_ppa_eur=("erloes_ppa_eur", "sum"),
        erloes_merchant_eur=("erloes_merchant_eur", "sum"),
        rueckzahlung_eur=("rueckzahlung_eur", "sum"),
    )
    for spalte in ("marktwert_real_ct_kwh", "marktwert_nominal_ct_kwh",
                   "verguetungssatz_ct_kwh"):
        jahre[spalte] = _gewichtet(spalte).to_numpy()
    return jahre[REVENUE_COLUMNS]
