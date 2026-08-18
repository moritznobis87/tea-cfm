"""
Erzeugt die gemeinsame Zeitachse, auf der alle anderen Engine-Module
aufsetzen (Energie, Erloese, OPEX, Finanzierung, Steuer).

Die Perioden sind KALENDERJAHRE - Erloes-, Kosten- und Steuerrechnung
folgen dem Geschaeftsjahr. Eine Betriebsdauer von N Jahren meint aber N
mal zwoelf Monate AB INBETRIEBNAHME, nicht N Kalenderjahre: Bei
unterjaehriger Inbetriebnahme laeuft die Achse deshalb ueber N+1
Kalenderjahre, von denen das erste und das letzte sich zu einem vollen
Jahr ergaenzen (Inbetriebnahme im Dezember: Jahr 1 hat einen Monat, Jahr
N+1 hat elf).

Frueher endete die Achse nach N Kalenderjahren. Ein im Dezember
angeschlossenes Projekt verlor dadurch fast ein volles Betriebsjahr
gegenueber einem im Januar angeschlossenen - der Rumpfmonat am Anfang
wurde am Ende nie ausgeglichen.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from .models import ZinsMethode

TIMELINE_COLUMNS = [
    "jahr",
    "datum_start",
    "datum_ende",
    "pro_rata_faktor",
    "ist_letztes_jahr",
]


def erstjahr_zins_pro_rata(inbetriebnahme_datum: date, methode: ZinsMethode) -> float:
    """Anteiliger Zinsfaktor des ersten (moeglicherweise unterjaehrigen)
    Betriebsjahres - 1.0 bei Inbetriebnahme am 1. Januar, sonst < 1.0.

    OESTERREICH (act/365): identische taggenaue Logik wie der
    Produktions-pro_rata_faktor in build_timeline() (siehe dort) - fuer
    volle Kalenderjahre ohnehin deckungsgleich, fuer das Anlaufjahr
    exakt dieselbe Zeitachse.

    DEUTSCH (30/360): jeder Restmonat des Anlaufjahres (inklusive
    Inbetriebnahmemonat) zaehlt pauschal mit 30 Tagen, das Jahr mit
    360 Tagen - unabhaengig vom tatsaechlichen Kalendertag der
    Inbetriebnahme (kaufmaennische Konvention).
    """
    if methode == ZinsMethode.DEUTSCH:
        restmonate = 13 - inbetriebnahme_datum.month
        return restmonate * 30 / 360
    jahresende = date(inbetriebnahme_datum.year, 12, 31)
    tage = (jahresende - inbetriebnahme_datum).days + 1
    return min(tage / 365.0, 1.0)


def anzahl_perioden(inbetriebnahme_datum: date, laufzeit_jahre: int) -> int:
    """Wie viele KALENDERJAHRE eine Laufzeit von `laufzeit_jahre` Jahren
    beruehrt.

    Bei Inbetriebnahme im Januar sind das genau `laufzeit_jahre`, sonst
    eines mehr: Das Anlaufjahr ist ein Rumpfjahr, und der fehlende Teil
    faellt am Ende an.
    """
    return laufzeit_jahre + (1 if inbetriebnahme_datum.month > 1 else 0)


def build_timeline(inbetriebnahme_datum: date, laufzeit_jahre: int) -> pd.DataFrame:
    """Baut die Jahres-Zeitachse fuer die Betriebsphase.

    Die Achse laeuft vom Inbetriebnahmetag bis zum Tag vor dem
    `laufzeit_jahre`-ten Jahrestag - also ueber exakt `laufzeit_jahre`
    mal zwoelf Monate, verteilt auf `anzahl_perioden()` Kalenderjahre.

    Der Investitionszeitpunkt (Jahr 0, CAPEX-Abfluss) ist bewusst NICHT
    Teil dieser Timeline, sondern wird erst in cashflow.py als separate
    Zeile ergaenzt - analog zur Trennung von Spalte H (Investition) und
    Spalten I..AM (Betriebsjahre) im Excel-Original.
    """
    if laufzeit_jahre <= 0:
        raise ValueError("laufzeit_jahre muss > 0 sein")

    perioden = anzahl_perioden(inbetriebnahme_datum, laufzeit_jahre)
    # Letzter Betriebstag: der Tag vor dem Jahrestag der Inbetriebnahme.
    letzter_tag = date(
        inbetriebnahme_datum.year + laufzeit_jahre,
        inbetriebnahme_datum.month,
        inbetriebnahme_datum.day,
    ) - timedelta(days=1)

    rows = []
    period_start = inbetriebnahme_datum
    for jahr in range(1, perioden + 1):
        period_end = min(
            date(inbetriebnahme_datum.year + jahr - 1, 12, 31), letzter_tag
        )
        tage = (period_end - period_start).days + 1
        pro_rata_faktor = min(tage / 365.0, 1.0)
        rows.append(
            {
                "jahr": jahr,
                "datum_start": period_start,
                "datum_ende": period_end,
                "pro_rata_faktor": pro_rata_faktor,
                "ist_letztes_jahr": jahr == perioden,
            }
        )
        period_start = date(period_end.year + 1, 1, 1)

    return pd.DataFrame(rows, columns=TIMELINE_COLUMNS)
