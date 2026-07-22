"""
Erzeugt die gemeinsame Zeitachse, auf der alle anderen Engine-Module
aufsetzen (Energie, Erloese, OPEX, Finanzierung, Steuer).

Bekannte MVP-Vereinfachung: Es wird angenommen, dass jede Betriebsperiode
ein volles Kalenderjahr (Jan-Dez) ist. Excels Sonderfall "Inbetriebnahme
mitten im Jahr -> Vertragsende auf den Jahrestag statt Jahresende" (Zeilen
18/42, abhaengig vom Auktion-Flag) wird hier bewusst noch nicht abgebildet
und ist ein Kandidat fuer eine spaetere Erweiterung.
"""

from __future__ import annotations

from datetime import date

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


def build_timeline(inbetriebnahme_datum: date, laufzeit_jahre: int) -> pd.DataFrame:
    """Baut die Jahres-Zeitachse fuer die Betriebsphase (Jahr 1..N).

    Der Investitionszeitpunkt (Jahr 0, CAPEX-Abfluss) ist bewusst NICHT
    Teil dieser Timeline, sondern wird erst in cashflow.py als separate
    Zeile ergaenzt - analog zur Trennung von Spalte H (Investition) und
    Spalten I..AM (Betriebsjahre) im Excel-Original.
    """
    if laufzeit_jahre <= 0:
        raise ValueError("laufzeit_jahre muss > 0 sein")

    rows = []
    period_start = inbetriebnahme_datum
    for jahr in range(1, laufzeit_jahre + 1):
        period_end = date(inbetriebnahme_datum.year + jahr - 1, 12, 31)
        tage = (period_end - period_start).days + 1
        pro_rata_faktor = min(tage / 365.0, 1.0)
        rows.append(
            {
                "jahr": jahr,
                "datum_start": period_start,
                "datum_ende": period_end,
                "pro_rata_faktor": pro_rata_faktor,
                "ist_letztes_jahr": jahr == laufzeit_jahre,
            }
        )
        period_start = date(period_end.year + 1, 1, 1)

    return pd.DataFrame(rows, columns=TIMELINE_COLUMNS)
