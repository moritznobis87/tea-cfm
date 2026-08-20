"""
Stuendliche Day-Ahead-Preise je Marktpreisszenario.

Warum es diese Datei gibt
-------------------------
Ein Marktpreisszenario fuehrt bisher Jahres- und Monatswerte des
Marktwerts Solar. Fuer die Cashflow-Rechnung reicht das: Der Erloes einer
PV-Anlage ist die Menge mal ihrem Capture Price.

Fuer einen Speicher reicht es NICHT. Sein ganzer Wert entsteht aus der
Reihenfolge der Stunden - aus dem Abstand zwischen der billigsten und
der teuersten Stunde eines Tages. Ein Monatsmittel enthaelt diese
Information nicht; aus ihm laesst sich kein Dispatch ableiten, und ein
aus der Form geschaetzter waere eine Aussage ueber die Schaetzung, nicht
ueber das Projekt.

Die Reihen kommen aus demselben Aurora-Export, aus dem auch die
Jahreskurven stammen ("Wholesale market price" in EUR/MWh, stuendlich).

Ablage
------
Nicht in der Annahmendatei: 34 Jahre mal 8.760 Werte sind knapp 300.000
Zahlen je Szenario - das YAML waere danach unlesbar und jede Aenderung
an einer beliebigen Annahme schriebe es komplett neu. Stattdessen je
Szenario eine gezippte CSV unter data/preise/, referenziert ueber den
Dateinamen (dieselbe Bauweise wie die Stundenreihen der Erzeugung in
data/lastgang/, siehe io_lastgang.py).

Format: zwei Spalten, `jahr` und `preis_eur_mwh`, chronologisch
innerhalb des Jahres. Nur VOLLSTAENDIGE Jahre (8.760 bzw. 8.784 Werte)
werden gespeichert - ein angebrochenes Jahr laesst sich nicht
optimieren, und ein stillschweigend aufgefuelltes waere eine Erfindung.
"""

from __future__ import annotations

import gzip
import io
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .io_lastgang import STUNDEN_NORMALJAHR, STUNDEN_SCHALTJAHR, LastgangFehler

#: Ablage der Preisreihen, je Szenario eine Datei.
PREIS_VERZEICHNIS = Path(__file__).resolve().parent.parent / "data" / "preise"

#: Spaltennamen des Aurora-Exports, in denen die Preise stehen koennen.
_PREISSPALTEN = (
    "Wholesale market price",
    "Baseload price",
    "Day-ahead price",
    "Price",
)
#: Spalten mit dem Zeitstempel - die lokale Zeit hat Vorrang, weil die
#: Stundenzuordnung eines Tages daran haengt.
_ZEITSPALTEN = ("Time (Local)", "Time (UTC)", "Datetime", "Time")


class PreisreiheFehler(LastgangFehler):
    """Die Datei laesst sich nicht als stuendliche Preisreihe lesen.

    Erbt von LastgangFehler, damit die Oberflaeche beide Importwege
    gleich behandeln kann.
    """


@dataclass(frozen=True)
class Preisauswertung:
    """Ergebnis eines Imports - die Reihen und ihre Gegenproben."""

    #: Kalenderjahr -> Stundenwerte in EUR/MWh.
    je_jahr: dict[int, tuple[float, ...]]
    #: Jahre, die verworfen wurden, weil sie unvollstaendig sind.
    unvollstaendig: dict[int, int]
    hinweise: list[str]

    @property
    def jahre(self) -> tuple[int, int]:
        schluessel = sorted(self.je_jahr)
        return (schluessel[0], schluessel[-1]) if schluessel else (0, 0)

    @property
    def mittelwert_eur_mwh(self) -> float:
        werte = [w for reihe in self.je_jahr.values() for w in reihe]
        return sum(werte) / len(werte) if werte else 0.0

    @property
    def negative_stunden_pct(self) -> float:
        werte = [w for reihe in self.je_jahr.values() for w in reihe]
        if not werte:
            return 0.0
        return sum(1 for w in werte if w < 0) / len(werte) * 100


def _spalte_finden(spalten, kandidaten, was: str) -> str:
    for name in kandidaten:
        if name in spalten:
            return name
    # Aurora benennt Spalten gelegentlich um; als Rueckfall die erste
    # Spalte, die den Kandidatennamen enthaelt.
    for name in spalten:
        if any(k.lower() in str(name).lower() for k in kandidaten):
            return name
    raise PreisreiheFehler(
        f"Keine Spalte mit {was} gefunden. Erwartet wurde eine der "
        f"Spalten {', '.join(kandidaten)}; gefunden wurden: "
        f"{', '.join(str(s) for s in spalten)}."
    )


def lies_aurora_preise(inhalt: bytes | str, dateiname: str = "") -> Preisauswertung:
    """Liest einen Aurora-Stundenpreis-Export.

    Der Export traegt zwei Kopfzeilen: Spaltennamen und Einheiten. Die
    zweite wird uebersprungen - sonst laese pandas die Einheiten als
    ersten Datensatz und die ganze Spalte als Text.
    """
    if isinstance(inhalt, str):
        inhalt = inhalt.encode("utf-8")
    endung = Path(dateiname).suffix.lower()

    try:
        if endung in (".xlsx", ".xlsm"):
            tabelle = pd.read_excel(io.BytesIO(inhalt))
        else:
            roh = gzip.decompress(inhalt) if endung == ".gz" else inhalt
            tabelle = pd.read_csv(io.BytesIO(roh))
    except Exception as fehler:  # noqa: BLE001 - Ursache wird weitergereicht
        raise PreisreiheFehler(
            f"Die Datei liess sich nicht lesen: {fehler}"
        ) from fehler

    # Kompaktformat aus data/preise/ - bereits aufbereitet.
    if {"jahr", "preis_eur_mwh"} <= set(tabelle.columns):
        return _aus_kompaktformat(tabelle)

    # Einheitenzeile: Sie steht direkt unter dem Kopf und traegt keinen
    # Zeitstempel, den pandas parsen koennte.
    zeitspalte = _spalte_finden(tabelle.columns, _ZEITSPALTEN, "Zeitstempel")
    preisspalte = _spalte_finden(tabelle.columns, _PREISSPALTEN, "Preisen")
    zeiten = pd.to_datetime(tabelle[zeitspalte], errors="coerce")
    if zeiten.isna().iloc[0]:
        tabelle = tabelle.iloc[1:]
        zeiten = pd.to_datetime(tabelle[zeitspalte], errors="coerce")

    preise = pd.to_numeric(tabelle[preisspalte], errors="coerce")
    gueltig = zeiten.notna() & preise.notna()
    if not gueltig.any():
        raise PreisreiheFehler(
            "Die Datei enthaelt keine lesbaren Zeitstempel-Preis-Paare."
        )
    return _aus_zeitreihe(zeiten[gueltig], preise[gueltig])


def _aus_kompaktformat(tabelle: pd.DataFrame) -> Preisauswertung:
    je_jahr: dict[int, tuple[float, ...]] = {}
    for jahr, gruppe in tabelle.groupby("jahr"):
        je_jahr[int(jahr)] = tuple(
            float(w) for w in gruppe["preis_eur_mwh"].to_numpy()
        )
    return Preisauswertung(je_jahr=je_jahr, unvollstaendig={}, hinweise=[])


def _aus_zeitreihe(zeiten: pd.Series, preise: pd.Series) -> Preisauswertung:
    """Ordnet die Werte den Kalenderjahren zu und verwirft Bruchstuecke."""
    df = pd.DataFrame({"t": zeiten, "preis": preise}).sort_values("t")
    je_jahr: dict[int, tuple[float, ...]] = {}
    unvollstaendig: dict[int, int] = {}
    for jahr, gruppe in df.groupby(df["t"].dt.year):
        werte = tuple(float(w) for w in gruppe["preis"].to_numpy())
        if len(werte) in (STUNDEN_NORMALJAHR, STUNDEN_SCHALTJAHR):
            je_jahr[int(jahr)] = werte
        else:
            unvollstaendig[int(jahr)] = len(werte)

    if not je_jahr:
        raise PreisreiheFehler(
            "Kein vollstaendiges Kalenderjahr gefunden. Erwartet werden "
            f"{STUNDEN_NORMALJAHR} bzw. {STUNDEN_SCHALTJAHR} Stundenwerte "
            "je Jahr; gefunden wurden "
            + ", ".join(f"{j}: {n}" for j, n in sorted(unvollstaendig.items()))
            + "."
        )

    hinweise = []
    if unvollstaendig:
        hinweise.append(
            "Unvollstaendige Kalenderjahre wurden uebergangen: "
            + ", ".join(
                f"{j} ({n} von {STUNDEN_NORMALJAHR} Stunden)"
                for j, n in sorted(unvollstaendig.items())
            )
            + ". Ein angebrochenes Jahr laesst sich nicht optimieren."
        )
    return Preisauswertung(je_jahr, unvollstaendig, hinweise)


# --- Ablage -----------------------------------------------------------------


def _dateiname(szenario: str) -> Path:
    kennung = (
        szenario.lower()
        .replace("ä", "ae").replace("ö", "oe").replace("ü", "ue").replace("ß", "ss")
    )
    kennung = "".join(c if c.isalnum() else "_" for c in kennung).strip("_")
    while "__" in kennung:
        kennung = kennung.replace("__", "_")
    return PREIS_VERZEICHNIS / f"{kennung}.csv.gz"


def speichere_preisreihe(szenario: str, auswertung: Preisauswertung) -> str:
    """Legt die Reihen als gezippte CSV ab; gibt den Dateinamen zurueck."""
    PREIS_VERZEICHNIS.mkdir(parents=True, exist_ok=True)
    pfad = _dateiname(szenario)
    zeilen = [
        {"jahr": jahr, "preis_eur_mwh": round(wert, 2)}
        for jahr in sorted(auswertung.je_jahr)
        for wert in auswertung.je_jahr[jahr]
    ]
    puffer = io.BytesIO()
    with gzip.open(puffer, "wt", encoding="utf-8", compresslevel=9) as f:
        pd.DataFrame(zeilen).to_csv(f, index=False)
    pfad.write_bytes(puffer.getvalue())
    preisreihe.cache_clear()
    return pfad.name


@lru_cache(maxsize=8)
def preisreihe(dateiname: str | None) -> dict[int, tuple[float, ...]] | None:
    """Die gespeicherten Reihen eines Szenarios - None, wenn keine da ist.

    Zwischengespeichert, weil die Datei knapp 300.000 Werte traegt und
    bei jedem Durchlauf neu zu lesen die Seite spuerbar bremste.
    """
    if not dateiname:
        return None
    pfad = PREIS_VERZEICHNIS / dateiname
    if not pfad.exists():
        return None
    return lies_aurora_preise(pfad.read_bytes(), pfad.name).je_jahr


def verfuegbare_preisreihen() -> list[str]:
    if not PREIS_VERZEICHNIS.exists():
        return []
    return sorted(p.name for p in PREIS_VERZEICHNIS.glob("*.csv.gz"))


def reihe_fuer_szenario(szenarioname: str) -> str | None:
    """Die Stundenpreisreihe eines Marktpreisszenarios - oder None.

    Verbunden wird ueber den NAMEN und nicht ueber ein Feld am Szenario.
    Der Grund ist derselbe, aus dem die Reihe ueberhaupt eine eigene
    Datei ist: Sie gehoert zu einem Aurora-Jahrgang, nicht zu einer
    einzelnen Kurve. `speichere_preisreihe` legt sie unter dem
    slugifizierten Namen ab, hier wird derselbe Name wieder gebildet.

    Die BAUFORM faellt dabei weg. Der Day-Ahead-Preis ist eine
    Eigenschaft des Marktes und nicht der Modulaufstaenderung - Pult und
    Tracker desselben Jahrgangs teilen sich eine Reihe, genau wie sie
    sich den Baseload teilen. Zwei getrennte Dateien mit identischem
    Inhalt waeren zwei Wahrheiten ueber denselben Markt.

    Gibt es keine Datei, ist das kein Fehler: Aeltere Jahrgaenge fuehren
    keine Stundenpreise. Dann laesst sich fuer dieses Szenario eben kein
    Speicher rechnen, und die Oberflaeche sagt das (siehe
    app/speicher.py).
    """
    if not szenarioname:
        return None
    from .io_aurora import ohne_bauform

    name = _dateiname(ohne_bauform(szenarioname)).name
    return name if (PREIS_VERZEICHNIS / name).is_file() else None


def stunden_fuer_jahr(
    dateiname: str | None, kalenderjahr: int
) -> tuple[float, ...] | None:
    """Die Reihe eines Kalenderjahres.

    Liegt das Jahr ausserhalb der Reihe, wird auf das naechstliegende
    vorhandene Jahr zurueckgegriffen - dieselbe Klammerregel, mit der
    auch die Jahreskurven ausserhalb ihres Bereichs gelesen werden
    (siehe engine/revenue.py). Ein fehlendes Jahr ist damit kein Fehler,
    aber die Aussage wird schwaecher, je weiter man sich entfernt.
    """
    reihen = preisreihe(dateiname)
    if not reihen:
        return None
    if kalenderjahr in reihen:
        return reihen[kalenderjahr]
    jahre = sorted(reihen)
    naechstes = min(jahre, key=lambda j: abs(j - kalenderjahr))
    return reihen[naechstes]
