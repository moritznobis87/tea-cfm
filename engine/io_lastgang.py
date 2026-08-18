"""
Einspeisekurve aus einer Stundenreihe.

Die Einspeisekurve (zwoelf Monatsanteile) ist die Bruecke zwischen der
Jahresmenge und der Monatsrechnung. Sie laesst sich schaetzen - besser
ist, sie aus einer echten Erzeugungszeitreihe abzuleiten: Ein
Stundenlastgang eines Ertragsgutachtens (PVsyst, Meteonorm) oder einer
Bestandsanlage kennt den Verlauf genau, den eine Schaetzung nur
nachbildet.

Dieses Modul macht daraus die zwoelf Anteile:

1. 8.760 Werte (bzw. 8.784 im Schaltjahr) werden den Monaten zugeordnet,
2. je Monat summiert,
3. auf 1 normiert.

Die absolute Hoehe der Werte ist dabei gleichgueltig - kW, kWh, MW oder
Prozent einer Nennleistung ergeben dieselbe Kurve. Das ist der Grund,
warum die Reihe nicht kalibriert werden muss: Sie liefert die FORM, die
Menge kommt weiterhin aus Leistung und Vollbenutzungsstunden des
Projekts.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd

from .models import MONATE

#: Stunden je Monat im Normaljahr und im Schaltjahr.
_STUNDEN_JE_MONAT = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]
_STUNDEN_JE_MONAT_SCHALT = [744, 696, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]

STUNDEN_NORMALJAHR = sum(_STUNDEN_JE_MONAT)
STUNDEN_SCHALTJAHR = sum(_STUNDEN_JE_MONAT_SCHALT)


class LastgangFehler(ValueError):
    """Die Reihe laesst sich nicht als Jahres-Stundenreihe lesen."""


@dataclass(frozen=True)
class Einspeiseauswertung:
    """Ergebnis der Auswertung - die Kurve und ihre Gegenproben."""

    kurve_pct_je_monat: list[float]
    stunden: int
    schaltjahr: bool
    #: Summe der Eingabewerte (in der Einheit der Reihe) - Gegenprobe
    #: gegen das Ertragsgutachten.
    summe: float
    #: Groesster Einzelwert - bei einer Leistungsreihe die Spitze.
    spitze: float
    #: Rechnerische Vollbenutzungsstunden, wenn die Reihe eine Leistung
    #: in kW/MW ist: Summe / Spitze. Nur eine Einordnung, kein
    #: Rechenwert - die Menge kommt aus dem Projekt.
    vollbenutzungsstunden: float
    hinweise: list[str]


def lies_stundenreihe(inhalt: bytes | str, dateiname: str = "") -> list[float]:
    """Zahlen aus Text, CSV oder Excel - eine Reihe, viele Schreibweisen.

    Erlaubt sind: eine Zahl je Zeile, mehrere Werte je Zeile (CSV),
    deutsches Dezimalkomma, Tausenderpunkte und leere Zellen. Eine
    Kopfzeile wird uebergangen: Was sich nicht in eine Zahl verwandeln
    laesst, faellt heraus.
    """
    if isinstance(inhalt, bytes) and dateiname.lower().endswith(
        (".xlsx", ".xlsm", ".xls")
    ):
        df = pd.read_excel(io.BytesIO(inhalt), header=None)
        werte = [w for spalte in df.columns for w in df[spalte].tolist()]
        return [float(w) for w in werte if isinstance(w, (int, float))
                and not isinstance(w, bool) and pd.notna(w)]

    text = inhalt.decode("utf-8-sig", errors="replace") if isinstance(inhalt, bytes) else inhalt
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]

    # Ist das Komma Dezimalzeichen oder Feldtrenner? Beides kommt vor,
    # und "1,9" waere sonst still zu zwei Werten (1 und 9) zerfallen.
    # Entschieden wird an der Gestalt der Zeilen: Steht in fast jeder
    # Zeile genau eine Zahl, ist das Komma ein Dezimalzeichen. Ebenso,
    # wenn die Zeilen mit Semikolon oder Tabulator geteilt sind - dann
    # trennt eben das.
    _EINZELWERT = re.compile(r"^-?\d{1,3}(?:\.\d{3})*(?:,\d+)?$|^-?\d+(?:\.\d+)?$")
    zeilenweise = bool(zeilen) and sum(
        bool(_EINZELWERT.match(z)) for z in zeilen
    ) >= 0.9 * len(zeilen)
    getrennt = any(";" in z or "\t" in z for z in zeilen)
    trenner = r"[\s;]+" if (zeilenweise or getrennt) else r"[\s;,]+"

    zahlen: list[float] = []
    for stueck in re.split(trenner, text.strip()):
        if not stueck:
            continue
        # Deutsches Dezimalkomma, englischer Tausenderpunkt: Ein Komma
        # ist immer das Dezimaltrennzeichen, ein Punkt nur dann, wenn
        # kein Komma vorkommt.
        bereinigt = stueck.replace(" ", "")
        if "," in bereinigt:
            bereinigt = bereinigt.replace(".", "").replace(",", ".")
        try:
            zahlen.append(float(bereinigt))
        except ValueError:
            continue
    return zahlen


def einspeisekurve_aus_stundenreihe(werte: list[float]) -> Einspeiseauswertung:
    """Zwoelf Monatsanteile aus einer Jahres-Stundenreihe.

    Erwartet werden 8.760 Werte (Normaljahr) oder 8.784 (Schaltjahr),
    beginnend am 1. Januar, 00:00. Andere Laengen werden abgewiesen: Eine
    um Stunden verschobene Reihe ergaebe eine still verschobene Kurve -
    der Fehler faende sich erst in der Rendite wieder.
    """
    hinweise: list[str] = []
    anzahl = len(werte)
    if anzahl not in (STUNDEN_NORMALJAHR, STUNDEN_SCHALTJAHR):
        def _tausender(zahl: int) -> str:
            return f"{zahl:,.0f}".replace(",", ".")

        raise LastgangFehler(
            f"Die Reihe hat {_tausender(anzahl)} Werte. Erwartet werden "
            f"{_tausender(STUNDEN_NORMALJAHR)} Stunden (oder "
            f"{_tausender(STUNDEN_SCHALTJAHR)} im Schaltjahr), beginnend "
            "am 1. Januar, 00:00."
        )
    if any(w < 0 for w in werte):
        hinweise.append(
            "Die Reihe enthält negative Werte (Eigenverbrauch oder "
            "Bezug?). Sie gehen mit ihrem Vorzeichen in die Monatssumme "
            "ein."
        )

    schaltjahr = anzahl == STUNDEN_SCHALTJAHR
    laengen = _STUNDEN_JE_MONAT_SCHALT if schaltjahr else _STUNDEN_JE_MONAT

    summen: list[float] = []
    start = 0
    for laenge in laengen:
        summen.append(float(sum(werte[start:start + laenge])))
        start += laenge

    gesamt = sum(summen)
    if gesamt <= 0:
        raise LastgangFehler(
            "Die Reihe summiert sich auf null – daraus lässt sich keine "
            "Verteilung ableiten."
        )
    kurve = [s / gesamt for s in summen]
    if any(s <= 0 for s in summen):
        leere = [i + 1 for i, s in enumerate(summen) if s <= 0]
        hinweise.append(
            "Monate ohne Erzeugung: "
            + ", ".join(str(m) for m in leere)
            + ". Das ist für eine Jahresreihe ungewöhnlich – bitte "
            "prüfen, ob die Reihe wirklich am 1. Januar beginnt."
        )

    spitze = max(werte)
    return Einspeiseauswertung(
        kurve_pct_je_monat=kurve,
        stunden=anzahl,
        schaltjahr=schaltjahr,
        summe=gesamt,
        spitze=spitze,
        vollbenutzungsstunden=(gesamt / spitze if spitze > 0 else 0.0),
        hinweise=hinweise,
    )


def kurve_aus_datei(inhalt: bytes | str, dateiname: str = "") -> Einspeiseauswertung:
    """Bequemer Weg: lesen und auswerten in einem Schritt."""
    werte = lies_stundenreihe(inhalt, dateiname)
    if not werte:
        raise LastgangFehler(
            "In der Eingabe wurden keine Zahlen gefunden. Erwartet wird "
            "eine Stundenreihe – eine Zahl je Zeile oder als Spalte einer "
            "CSV-/Excel-Datei."
        )
    return einspeisekurve_aus_stundenreihe(werte)


def monatsnamen_kurz() -> list[str]:
    """Nur fuer Ausgaben in Berichten - die Oberflaeche hat ihre eigene,
    uebersetzte Liste (app/config.py)."""
    return ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
            "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"][:MONATE]
