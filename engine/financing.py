"""
Berechnet Zinsen, Tilgung und Darlehensstand ueber ein Kredit mit
Annuitaeten- oder linearer Tilgung, optional mit tilgungsfreiem
Anlaufjahr.

Konventionen:
- Zinsen eines Jahres fallen auf den Jahresanfangsstand an, die Tilgung
  fliesst nachschuessig am Jahresende (Bankenkonvention).
- Tilgungsfreies Anlaufjahr: Im ersten Betriebsjahr werden nur Zinsen
  auf die volle Kreditsumme gezahlt; die Tilgung beginnt in Jahr 2.
  Die ANZAHL der Tilgungsraten bleibt `kreditlaufzeit_jahre` - der
  Schuldendienst verlaengert sich also insgesamt um ein Jahr. Weil das
  erste Jahr ungetilgt bleibt, faellt auch im zweiten Jahr der Zins noch
  auf die volle Kreditsumme an (Jahresanfangsstand).
- Unterjaehriges erstes Betriebsjahr (Inbetriebnahme nicht am 1.
  Januar): Der GESAMTE Schuldendienst des Rumpfjahres wird mit
  `erstjahr_zins_faktor` anteilig gerechnet (siehe engine.timeline.
  erstjahr_zins_pro_rata, ZinsMethode) - Zins und Tilgung gemeinsam.
  Wer das Darlehen im Dezember abruft, zahlt einen Dezember, nicht ein
  Jahr.

  Frueher wirkte der Faktor nur auf die Zinsen. Bei Annuitaet ist die
  Rate aber fix, und die Tilgung ergibt sich als Rest: Ein kleinerer
  Zins liess die Tilgung genau um denselben Betrag WACHSEN. Ein im
  Dezember angeschlossenes Projekt tilgte dadurch im Rumpfjahr fast
  eine volle Jahresrate, waehrend es rund 5 % einer Jahresmenge
  erzeugte.

  Weil im Rumpfjahr weniger getilgt wird, verschiebt sich der
  Ratenplan: Die Laufzeit zaehlt ab Abruf, das Darlehen endet also
  ebenfalls unterjaehrig ein Jahr spaeter. Die letzte Rate ist auf den
  Restsaldo begrenzt.
- Keine Zahlung ohne Schuld: Tilgung und Zins sind auf den offenen
  Saldo begrenzt. Ohne diese Grenze zahlte der Plan in bestimmten
  Konstellationen eine Rate mehr, als das Darlehen gross war.
"""

from __future__ import annotations

import numpy_financial as npf
import pandas as pd

from .models import TilgungsArt

FINANCING_COLUMNS = [
    "jahr",
    "zinsen_eur",
    "tilgung_eur",
    "schuldendienst_eur",
    "darlehensstand_bop_eur",
    "darlehensstand_eop_eur",
]


def calculate_financing(
    timeline: pd.DataFrame,
    investitionsvolumen_eur: float,
    eigenkapitalquote_pct: float,
    fremdkapitalzins_pct: float,
    kreditlaufzeit_jahre: int,
    tilgungsart: TilgungsArt,
    tilgungsfreies_anlaufjahr: bool = False,
    erstjahr_zins_faktor: float = 1.0,
) -> pd.DataFrame:
    fremdkapital_eur = investitionsvolumen_eur * (1 - eigenkapitalquote_pct)

    # Erstes und letztes Jahr mit Tilgungsrate. Die Annuitaet/lineare Rate
    # wird unveraendert ueber `kreditlaufzeit_jahre` Raten berechnet - das
    # Anlaufjahr verschiebt den Ratenplan nur um ein Jahr nach hinten.
    erstes_tilgungsjahr = 2 if tilgungsfreies_anlaufjahr else 1
    # Ein anteiliges Rumpfjahr tilgt weniger als eine volle Rate; der Rest
    # wandert ans Ende. Nur wenn im ersten Jahr ueberhaupt getilgt wird -
    # bei tilgungsfreiem Anlaufjahr ist der Ratenplan ohnehin schon
    # verschoben.
    rumpfjahr = erstjahr_zins_faktor < 1.0 and not tilgungsfreies_anlaufjahr
    letztes_schuldendienstjahr = (
        kreditlaufzeit_jahre
        + (1 if tilgungsfreies_anlaufjahr else 0)
        + (1 if rumpfjahr else 0)
    )

    if tilgungsart == TilgungsArt.ANNUITAET:
        annuitaet_eur = npf.pmt(
            fremdkapitalzins_pct, kreditlaufzeit_jahre, -fremdkapital_eur
        )
    else:
        tilgung_linear_eur = fremdkapital_eur / kreditlaufzeit_jahre

    rows = []
    balance = fremdkapital_eur
    for _, period in timeline.iterrows():
        jahr = int(period["jahr"])
        # Ohne offene Schuld gibt es nichts zu zahlen - auch dann nicht,
        # wenn der Ratenplan rechnerisch noch ein Jahr laufen wuerde.
        if jahr <= letztes_schuldendienstjahr and balance > 0:
            # Der Zeitanteil des Rumpfjahres gilt fuer den GANZEN
            # Schuldendienst, nicht nur fuer den Zins.
            anteil = erstjahr_zins_faktor if jahr == 1 else 1.0
            zinsen = balance * fremdkapitalzins_pct * anteil
            if jahr < erstes_tilgungsjahr:
                # Tilgungsfreies Anlaufjahr: nur Zinsen.
                tilgung = 0.0
            elif tilgungsart == TilgungsArt.ANNUITAET:
                # Anteilige Rate, davon der anteilige Zins - die Tilgung
                # des Rumpfjahres ist damit derselbe Bruchteil eines
                # vollen ersten Jahres wie die Zinslast.
                tilgung = annuitaet_eur * anteil - zinsen
            else:
                tilgung = tilgung_linear_eur * anteil
            # Die letzte Rate zahlt nur noch den Restsaldo.
            tilgung = min(max(tilgung, 0.0), balance)
            schuldendienst = tilgung + zinsen
        else:
            zinsen = 0.0
            schuldendienst = 0.0
            tilgung = 0.0

        balance_eop = max(balance - tilgung, 0.0)
        rows.append(
            {
                "jahr": jahr,
                "zinsen_eur": zinsen,
                "tilgung_eur": tilgung,
                "schuldendienst_eur": schuldendienst,
                "darlehensstand_bop_eur": balance,
                "darlehensstand_eop_eur": balance_eop,
            }
        )
        balance = balance_eop

    return pd.DataFrame(rows, columns=FINANCING_COLUMNS)
