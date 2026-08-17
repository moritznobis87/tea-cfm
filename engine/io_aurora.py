"""
Import von Aurora-Marktdaten zu einem Marktpreisszenario.

Aurora liefert je Szenario vier Dateien: eine Systemdatei (Preisniveau,
Nachfrage, Emissionen, Waehrungen, Inflationsindex) und eine
Technologiedatei (je Technologie Kapazitaet, Erzeugung, Capture Price,
Abregelungsquoten), beide jeweils in Jahres- und in Monatsaufloesung.

Was dieses Modul daraus macht:

- **Marktwert Solar** aus dem Capture Price der gewaehlten Technologie
  (EUR/MWh -> ct/kWh). Das ist der erzeugungsgewichtete Preis, den genau
  diese Technologie erloest - fuer eine PV-Bewertung die richtige
  Groesse, nicht der Baseload-Preis der Systemdatei.
- **Erzeugungsmenge in Stunden negativer Preise** aus den beiden
  Abregelungsquoten (6h- und 1h-Regel). Sie fuellen die beiden
  Zeitreihen, zwischen denen die Globalen Annahmen umschalten.
- **Einspeisekurve** aus der monatlichen Erzeugung derselben
  Technologie - der Ertragsverlauf steckt bereits in den Daten und muss
  nicht geschaetzt werden.
- **Inflation der Marktpreiskurven** aus dem Index der Systemdatei
  ("EUR Inflation, Index relative to ...").

MONATSDATEN SIND PFLICHT. Die Vertragsformen der Foerderung (zweiseitiger
CfD, Toleranzband nach § 10 EAG) sind abgeschnittene Funktionen des
Marktwerts: Ob eine Rueckzahlung entsteht, entscheidet sich in einzelnen
Monaten und ist aus einem Jahresmittel nicht rekonstruierbar - ein Jahr
mit 4 ct Mittelwert kann Monate ueber der Abschoepfungsschwelle
enthalten. Ein Import ohne Monatsaufloesung wuerde diese Rechnung
stillschweigend entwerten; deshalb bricht er hier ab (siehe
AuroraImportFehler).

Die Spaltenerkennung ist bewusst tolerant (Gross-/Kleinschreibung,
Mehrfach-Leerzeichen, Zusaetze in der Kopfzeile): Aurora-Exporte
unterscheiden sich zwischen Marktgebieten und Ausgabejahren in
Kleinigkeiten, und ein Import, der an einem zusaetzlichen Leerzeichen
scheitert, ist keiner.
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import pandas as pd

from .models import EINSPEISEKURVE_STANDARD_PCT, MONATE, MarktpreisSzenario


class AuroraImportFehler(ValueError):
    """Der Import kann nicht ausgefuehrt werden.

    Traegt eine Meldung, die dem Nutzer gezeigt wird - sie benennt die
    Datei und die fehlende Groesse, nicht die Codestelle.
    """


#: Kandidaten fuer die Monatsspalte, wenn Jahr und Monat getrennt stehen.
_MONATSNAMEN = {
    "jan": 1, "feb": 2, "mar": 3, "mär": 3, "apr": 4, "may": 5, "mai": 5,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "okt": 10,
    "nov": 11, "dec": 12, "dez": 12,
}

#: Ab diesem Wert wird eine Quote als Prozentangabe gelesen. Aurora
#: liefert Abregelungsquoten als Anteil (0-1); manche Exporte rechnen sie
#: in Prozent aus. Ueber 1,5 kann kein Anteil mehr gemeint sein.
_QUOTE_PROZENT_SCHWELLE = 1.5


def _normalisiere(spalte: str) -> str:
    return re.sub(r"\s+", " ", str(spalte)).strip().lower()


def _finde_spalte(df: pd.DataFrame, *begriffe: str, ohne: str = "") -> str | None:
    """Erste Spalte, deren Name alle Begriffe enthaelt.

    Kein exakter Vergleich: Aurora haengt je nach Export Einheiten oder
    Marktgebiete an die Kopfzeile an.
    """
    for spalte in df.columns:
        name = _normalisiere(spalte)
        if all(b in name for b in begriffe) and not (ohne and ohne in name):
            return spalte
    return None


def _pflichtspalte(df: pd.DataFrame, datei: str, *begriffe: str,
                   ohne: str = "") -> str:
    spalte = _finde_spalte(df, *begriffe, ohne=ohne)
    if spalte is None:
        raise AuroraImportFehler(
            f"In der Datei „{datei}“ fehlt eine Spalte mit "
            f"„{' '.join(begriffe)}“. Gefunden wurden: "
            + ", ".join(str(s) for s in df.columns[:12])
            + ("…" if len(df.columns) > 12 else "")
        )
    return spalte


def _monat(wert) -> int | None:
    """Monatsnummer aus Zahl, Monatsname oder Datum."""
    if wert is None or (isinstance(wert, float) and pd.isna(wert)):
        return None
    if isinstance(wert, (int, float)) and not isinstance(wert, bool):
        nummer = int(wert)
        return nummer if 1 <= nummer <= MONATE else None
    if isinstance(wert, pd.Timestamp):
        return int(wert.month)
    text = str(wert).strip().lower()
    if text.isdigit():
        nummer = int(text)
        return nummer if 1 <= nummer <= MONATE else None
    for kuerzel, nummer in _MONATSNAMEN.items():
        if text.startswith(kuerzel):
            return nummer
    # Letzter Versuch: ein Datum in irgendeiner Schreibweise.
    zeitpunkt = pd.to_datetime(text, errors="coerce", dayfirst=True)
    return None if pd.isna(zeitpunkt) else int(zeitpunkt.month)


def lies_tabelle(inhalt: bytes, dateiname: str) -> pd.DataFrame:
    """Liest CSV oder Excel - Aurora liefert beides.

    Bei CSV wird das Trennzeichen erraten (Komma oder Semikolon); ein
    deutsches Excel schreibt Semikolon.
    """
    name = dateiname.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(inhalt))
    try:
        return pd.read_csv(io.BytesIO(inhalt), sep=None, engine="python")
    except Exception as fehler:  # pragma: no cover - Formatfehler des Nutzers
        raise AuroraImportFehler(
            f"Die Datei „{dateiname}“ ließ sich nicht lesen: {fehler}"
        ) from fehler


def _jahr_und_monat(df: pd.DataFrame, datei: str, monatlich: bool) -> pd.DataFrame:
    """Ergaenzt die Spalten `_jahr` und (bei Monatsdaten) `_monat`."""
    jahr_spalte = _pflichtspalte(df, datei, "year")
    ergebnis = df.copy()
    ergebnis["_jahr"] = pd.to_numeric(ergebnis[jahr_spalte], errors="coerce")
    ergebnis = ergebnis[ergebnis["_jahr"].notna()]
    ergebnis["_jahr"] = ergebnis["_jahr"].astype(int)

    if not monatlich:
        return ergebnis

    monat_spalte = _finde_spalte(df, "month") or _finde_spalte(df, "monat")
    if monat_spalte is not None:
        ergebnis["_monat"] = [_monat(w) for w in ergebnis[monat_spalte]]
    else:
        # Kein eigenes Monatsfeld: Vielleicht steht die Periode als Datum
        # in der Jahresspalte selbst (z.B. "2030-07").
        ergebnis["_monat"] = [_monat(w) for w in df.loc[ergebnis.index, jahr_spalte]]
    if ergebnis["_monat"].isna().all():
        raise AuroraImportFehler(
            f"Die Datei „{datei}“ enthält keine Monatsspalte. Für das "
            "Monatsmodell (zweiseitiger CfD, Abschöpfung) wird die "
            "monatliche Auflösung benötigt – bitte die Monatsdatei laden."
        )
    ergebnis = ergebnis[ergebnis["_monat"].notna()]
    ergebnis["_monat"] = ergebnis["_monat"].astype(int)
    return ergebnis


def technologien(inhalt: bytes, dateiname: str) -> list[str]:
    """Auswahlliste „Gruppe · Untergruppe“ aus einer Technologiedatei.

    Die Bewertung braucht genau eine Technologie; welche das ist, kann
    nur der Nutzer entscheiden - „Solar“ steht je nach Marktgebiet als
    eigene Gruppe oder als Untergruppe von „Renewables“.
    """
    df = lies_tabelle(inhalt, dateiname)
    gruppe = _finde_spalte(df, "group", ohne="sub")
    untergruppe = _finde_spalte(df, "subgroup") or _finde_spalte(df, "sub group")
    if gruppe is None and untergruppe is None:
        return []
    paare = []
    for _, zeile in df.iterrows():
        g = str(zeile[gruppe]).strip() if gruppe is not None else ""
        u = str(zeile[untergruppe]).strip() if untergruppe is not None else ""
        if g.lower() in ("nan", "") and u.lower() in ("nan", ""):
            continue
        paare.append(technologie_label(g, u))
    return sorted(dict.fromkeys(paare))


def technologie_label(gruppe: str, untergruppe: str) -> str:
    gruppe = "" if gruppe.lower() in ("nan", "none") else gruppe
    untergruppe = "" if untergruppe.lower() in ("nan", "none") else untergruppe
    if gruppe and untergruppe:
        return f"{gruppe} · {untergruppe}"
    return gruppe or untergruppe


def vorschlag_solar(auswahl: list[str]) -> str | None:
    """Die naheliegende Technologie fuer eine PV-Bewertung.

    Nur ein Vorschlag - bestaetigt wird er im Formular. Bevorzugt wird
    ein Eintrag mit „solar“, unter mehreren der kuerzeste (also der
    allgemeinste, z.B. „Solar“ vor „Solar rooftop residential“).
    """
    treffer = [t for t in auswahl if "solar" in t.lower() or "pv" in t.lower()]
    return min(treffer, key=len) if treffer else None


@dataclass
class AuroraImport:
    """Ergebnis eines Imports - vor der Uebernahme in die Annahmen."""

    szenario: MarktpreisSzenario
    technologie: str
    jahre: tuple[int, int]
    monatsjahre: int
    #: Aus der monatlichen Erzeugung abgeleitet; leer, wenn die
    #: Erzeugungsspalte fehlt.
    einspeisekurve_pct_je_monat: list[float] = field(default_factory=list)
    inflation_basisjahr: int | None = None
    inflation_pct_pa: float | None = None
    #: Auffaelligkeiten, die den Import nicht verhindern - sie gehoeren
    #: dem Nutzer gezeigt, bevor er uebernimmt.
    hinweise: list[str] = field(default_factory=list)


def _quote(werte: pd.Series, hinweise: list[str], bezeichnung: str) -> pd.Series:
    """Abregelungsquote als Anteil 0-1, tolerant gegen Prozentangaben."""
    zahlen = pd.to_numeric(werte, errors="coerce")
    if zahlen.max(skipna=True) is not None and zahlen.max(skipna=True) > _QUOTE_PROZENT_SCHWELLE:
        hinweise.append(
            f"{bezeichnung}: Werte über 1,5 gefunden – als Prozentangabe "
            "gelesen und durch 100 geteilt."
        )
        zahlen = zahlen / 100.0
    return zahlen.clip(lower=0.0, upper=1.0)


def _technologiezeilen(
    df: pd.DataFrame, technologie: str, datei: str
) -> pd.DataFrame:
    gruppe = _finde_spalte(df, "group", ohne="sub")
    untergruppe = _finde_spalte(df, "subgroup") or _finde_spalte(df, "sub group")
    label = pd.Series(
        [
            technologie_label(
                str(z[gruppe]) if gruppe is not None else "",
                str(z[untergruppe]) if untergruppe is not None else "",
            )
            for _, z in df.iterrows()
        ],
        index=df.index,
    )
    zeilen = df[label == technologie]
    if zeilen.empty:
        raise AuroraImportFehler(
            f"In der Datei „{datei}“ gibt es keine Zeilen für die "
            f"Technologie „{technologie}“."
        )
    return zeilen


def _inflation(
    system_df: pd.DataFrame, hinweise: list[str]
) -> tuple[int | None, float | None]:
    """Basisjahr und mittlere Rate aus dem Inflationsindex der Systemdatei.

    Der Index ist auf ein Basisjahr normiert (dort 1,0); die Engine
    rechnet mit einer konstanten Rate ab genau diesem Jahr. Uebernommen
    wird deshalb das Basisjahr und die geometrisch mittlere Steigerung -
    eine Naeherung, die der Index selbst offenlegt.
    """
    spalte = _finde_spalte(system_df, "inflation")
    if spalte is None:
        hinweise.append(
            "Keine Inflationsspalte in der Systemdatei gefunden – "
            "Basisjahr und Rate bleiben unverändert."
        )
        return None, None
    werte = pd.to_numeric(system_df[spalte], errors="coerce")
    reihe = pd.DataFrame({"jahr": system_df["_jahr"], "index": werte}).dropna()
    reihe = reihe.groupby("jahr", as_index=False)["index"].mean().sort_values("jahr")
    if len(reihe) < 2:
        return None, None
    # Basisjahr = das Jahr, dessen Index am naechsten bei 1,0 liegt.
    basisjahr = int(reihe.loc[(reihe["index"] - 1.0).abs().idxmin(), "jahr"])
    erstes, letztes = reihe.iloc[0], reihe.iloc[-1]
    jahre = int(letztes["jahr"]) - int(erstes["jahr"])
    if jahre <= 0 or erstes["index"] <= 0:
        return basisjahr, None
    rate = (letztes["index"] / erstes["index"]) ** (1 / jahre) - 1
    return basisjahr, float(rate)


def importiere_aurora(
    name: str,
    technologie_monat: tuple[bytes, str],
    technologie_jahr: tuple[bytes, str] | None = None,
    system_jahr: tuple[bytes, str] | None = None,
    system_monat: tuple[bytes, str] | None = None,
    technologie: str | None = None,
    uncurtailed: bool = True,
) -> AuroraImport:
    """Baut ein Marktpreisszenario aus den Aurora-Dateien.

    technologie_*/system_*: (Dateiinhalt, Dateiname). Pflicht ist allein
    die Technologiedatei in MONATSaufloesung - ohne sie ist das
    Monatsmodell nicht rechenbar (siehe Modulkopf). Die uebrigen drei
    Dateien praezisieren: die Systemdatei liefert die Inflation, die
    Jahresdateien dienen der Gegenprobe.

    uncurtailed: Welcher Capture Price gilt? Voreingestellt der
    UNGEKUERZTE - die Wirkung negativer Preise bringt das Modell selbst
    ueber die Abregelungsquote ein (siehe engine/revenue.py). Mit dem
    bereits gekuerzten Preis wuerde sie doppelt zaehlen.
    """
    if not name.strip():
        raise AuroraImportFehler("Bitte einen Namen für das Szenario angeben.")

    hinweise: list[str] = []
    inhalt, datei = technologie_monat
    roh = lies_tabelle(inhalt, datei)
    tech = _jahr_und_monat(roh, datei, monatlich=True)

    if technologie is None:
        technologie = vorschlag_solar(technologien(inhalt, datei)) or ""
    zeilen = _technologiezeilen(tech, technologie, datei)

    preis_spalte = (
        _finde_spalte(zeilen, "uncurtailed", "capture price") if uncurtailed else None
    )
    if preis_spalte is None:
        preis_spalte = _pflichtspalte(zeilen, datei, "capture price", ohne="uncurtailed")
        if uncurtailed:
            hinweise.append(
                "Kein ungekürzter Capture Price gefunden – es gilt der "
                "um negative Stunden gekürzte. Die Abregelung wirkt dann "
                "doppelt; die Gewichtung negativer Stunden kann das in den "
                "Globalen Annahmen ausgleichen."
            )
    neg6_spalte = _pflichtspalte(zeilen, datei, "curtailment rate", "6 hour")
    neg1_spalte = _pflichtspalte(zeilen, datei, "curtailment rate", "1 hour")
    erzeugung_spalte = _finde_spalte(zeilen, "generation")

    tabelle = pd.DataFrame(
        {
            "jahr": zeilen["_jahr"].to_numpy(),
            "monat": zeilen["_monat"].to_numpy(),
            # EUR/MWh -> ct/kWh
            "preis": pd.to_numeric(zeilen[preis_spalte], errors="coerce").to_numpy()
            / 10.0,
            "neg6": _quote(zeilen[neg6_spalte], hinweise, "Abregelung 6h").to_numpy(),
            "neg1": _quote(zeilen[neg1_spalte], hinweise, "Abregelung 1h").to_numpy(),
            "erzeugung": (
                pd.to_numeric(zeilen[erzeugung_spalte], errors="coerce").to_numpy()
                if erzeugung_spalte is not None
                else 1.0
            ),
        }
    ).dropna(subset=["jahr", "monat", "preis"])

    if tabelle.empty:
        raise AuroraImportFehler(
            f"In der Datei „{datei}“ stehen für „{technologie}“ keine "
            "auswertbaren Monatswerte."
        )

    # Ein Jahr zaehlt nur mit, wenn alle zwoelf Monate da sind - eine
    # halbe Monatsreihe waere eine stillschweigend verschobene Reihe.
    vollstaendig = tabelle.groupby("jahr")["monat"].nunique() == MONATE
    unvollstaendig = sorted(vollstaendig[~vollstaendig].index.tolist())
    if unvollstaendig:
        hinweise.append(
            "Unvollständige Monatsreihen übergangen: "
            + ", ".join(str(j) for j in unvollstaendig[:8])
            + ("…" if len(unvollstaendig) > 8 else "")
        )
    tabelle = tabelle[tabelle["jahr"].isin(vollstaendig[vollstaendig].index)]
    if tabelle.empty:
        raise AuroraImportFehler(
            "Kein Kalenderjahr der Datei trägt alle zwölf Monate. Für "
            "das Monatsmodell (zweiseitiger CfD, Abschöpfung) werden "
            "vollständige Monatsreihen benötigt."
        )

    monatswerte: dict[int, list[float]] = {}
    neg6_monate: dict[int, list[float]] = {}
    neg1_monate: dict[int, list[float]] = {}
    jahreswerte: dict[int, float] = {}
    neg6_jahr: dict[int, float] = {}
    neg1_jahr: dict[int, float] = {}

    for jahr, gruppe in tabelle.groupby("jahr"):
        geordnet = gruppe.sort_values("monat")
        monatswerte[int(jahr)] = [float(w) for w in geordnet["preis"]]
        neg6_monate[int(jahr)] = [float(w) for w in geordnet["neg6"]]
        neg1_monate[int(jahr)] = [float(w) for w in geordnet["neg1"]]
        # Der Jahreswert ist das ERZEUGUNGSGEWICHTETE Mittel der
        # Monatswerte - genau die Groesse, die die Engine beim Verdichten
        # bildet. Ein einfacher Mittelwert waere fuer PV zu hoch.
        gewicht = geordnet["erzeugung"].fillna(0.0)
        if float(gewicht.sum()) <= 0:
            gewicht = pd.Series(1.0, index=geordnet.index)
        jahreswerte[int(jahr)] = float(
            (geordnet["preis"] * gewicht).sum() / gewicht.sum()
        )
        neg6_jahr[int(jahr)] = float((geordnet["neg6"] * gewicht).sum() / gewicht.sum())
        neg1_jahr[int(jahr)] = float((geordnet["neg1"] * gewicht).sum() / gewicht.sum())

    einspeisekurve: list[float] = []
    if erzeugung_spalte is not None:
        # Mittlerer Monatsanteil ueber alle vollstaendigen Jahre: Der
        # Ertragsverlauf steckt bereits in den Daten und muss nicht
        # geschaetzt werden.
        anteile = []
        for _, gruppe in tabelle.groupby("jahr"):
            geordnet = gruppe.sort_values("monat")
            summe = float(geordnet["erzeugung"].sum())
            if summe > 0:
                anteile.append([float(w) / summe for w in geordnet["erzeugung"]])
        if anteile:
            einspeisekurve = [
                sum(jahr[m] for jahr in anteile) / len(anteile) for m in range(MONATE)
            ]
    else:
        hinweise.append(
            "Keine Erzeugungsspalte gefunden – die Einspeisekurve bleibt "
            "unverändert, und die Jahreswerte sind ungewichtete Mittel "
            "der Monatswerte."
        )

    basisjahr = rate = None
    for datei_paar in (system_jahr, system_monat):
        if datei_paar is None:
            continue
        # Die Systemdatei ist Beiwerk: Sie liefert die Inflation, nicht
        # die Kurven. Ein Fehler in ihr darf den Import deshalb nicht
        # abbrechen - er wird gemeldet, und die Inflation bleibt stehen.
        # Gelesen wird sie ohne Monatsanspruch; die Monatsvariante wird
        # dabei einfach je Jahr gemittelt.
        try:
            system_roh = lies_tabelle(*datei_paar)
            system_df = _jahr_und_monat(system_roh, datei_paar[1], monatlich=False)
            basisjahr, rate = _inflation(system_df, hinweise)
        except AuroraImportFehler as fehler:
            hinweise.append(f"Systemdatei „{datei_paar[1]}“ übersprungen: {fehler}")
            continue
        if basisjahr is not None:
            break
    if system_jahr is None and system_monat is None:
        hinweise.append(
            "Ohne Systemdatei bleiben Inflationsrate und Basisjahr der "
            "Marktpreiskurven unverändert."
        )

    # Gegenprobe gegen die Jahresdatei: Sie ist keine zweite Quelle,
    # sondern ein Pruefstein - weicht der gewichtete Monatsschnitt stark
    # vom ausgewiesenen Jahreswert ab, stimmt etwas an der Zuordnung
    # nicht (falsche Technologie, falscher Capture Price).
    if technologie_jahr is not None:
        _gegenprobe(technologie_jahr, technologie, jahreswerte, uncurtailed, hinweise)

    szenario = MarktpreisSzenario(
        name=name.strip(),
        marktwert_solar_ct_kwh_je_kalenderjahr=jahreswerte,
        erzeugungsmenge_negativ_6h_pct_je_kalenderjahr=neg6_jahr,
        erzeugungsmenge_negativ_1h_pct_je_kalenderjahr=neg1_jahr,
        marktwert_solar_ct_kwh_je_monat=monatswerte,
        erzeugungsmenge_negativ_6h_pct_je_monat=neg6_monate,
        erzeugungsmenge_negativ_1h_pct_je_monat=neg1_monate,
    )
    jahre = (min(jahreswerte), max(jahreswerte))
    return AuroraImport(
        szenario=szenario,
        technologie=technologie,
        jahre=jahre,
        monatsjahre=len(monatswerte),
        einspeisekurve_pct_je_monat=einspeisekurve,
        inflation_basisjahr=basisjahr,
        inflation_pct_pa=rate,
        hinweise=hinweise,
    )


#: Relative Abweichung zwischen Jahresdatei und gewichtetem Monatsmittel,
#: ab der die Gegenprobe warnt. 2 % decken Rundung und eine leicht
#: abweichende Gewichtung ab, ohne einen Zuordnungsfehler zu verschlucken.
_GEGENPROBE_SCHRANKE = 0.02


def _gegenprobe(
    datei_paar: tuple[bytes, str],
    technologie: str,
    jahreswerte: dict[int, float],
    uncurtailed: bool,
    hinweise: list[str],
) -> None:
    inhalt, datei = datei_paar
    try:
        roh = lies_tabelle(inhalt, datei)
        jahr_df = _jahr_und_monat(roh, datei, monatlich=False)
        zeilen = _technologiezeilen(jahr_df, technologie, datei)
        spalte = (
            _finde_spalte(zeilen, "uncurtailed", "capture price") if uncurtailed else None
        ) or _finde_spalte(zeilen, "capture price", ohne="uncurtailed")
        if spalte is None:
            return
    except AuroraImportFehler as fehler:
        hinweise.append(f"Gegenprobe übersprungen: {fehler}")
        return

    abweichungen = []
    for _, zeile in zeilen.iterrows():
        jahr = int(zeile["_jahr"])
        aus_datei = pd.to_numeric(zeile[spalte], errors="coerce")
        if jahr not in jahreswerte or pd.isna(aus_datei):
            continue
        aus_datei = float(aus_datei) / 10.0
        if aus_datei == 0:
            continue
        if abs(jahreswerte[jahr] - aus_datei) / abs(aus_datei) > _GEGENPROBE_SCHRANKE:
            abweichungen.append(jahr)
    if abweichungen:
        hinweise.append(
            "Gegenprobe zur Jahresdatei: In "
            f"{len(abweichungen)} Jahr(en) weicht das erzeugungsgewichtete "
            "Monatsmittel um mehr als 2 % vom ausgewiesenen Jahreswert ab "
            f"(z. B. {abweichungen[0]}). Gerechnet wird mit den Monatswerten."
        )


# ---------------------------------------------------------------------------
# Aurora-Arbeitsmappe (Market Forecast Data, .xlsx/.xlsm)
# ---------------------------------------------------------------------------
#
# Der zweite Weg in dieses Modul: Statt vier CSV-Exporten eine einzige
# Arbeitsmappe. Sie enthaelt je Szenario ein Jahresblatt (Central, Low,
# High, teils Net Zero) und ein gemeinsames Blatt "Monthly prices" mit
# allen Szenarien.
#
# Zwischen den Jahrgaengen aendert Aurora Kleinigkeiten - Blattnamen
# ("Monthly prices"/"Monthly Prices"), Kopfzeilen um eine Zeile
# verschoben, zweisprachige Zusatzspalten, "Baseload"/"Baseload price"/
# "Baseload prices", "curtailment-below-zero"/"curtailment % - 1 hour
# rule". Deshalb wird NICHTS ueber feste Zeilen- oder Spaltennummern
# gefunden: Die Kopfzeile ist die Zeile, in der "Calendar year" und
# "Month" stehen; die Datenspalten sind die, unter denen beides eine
# Zahl ist; die Szenariospalte ist die, in der die Szenarionamen stehen.
# Gesucht wird dann im zusammengesetzten Text aller Beschriftungsspalten
# einer Zeile - das erfasst auch die deutschen Zweitspalten.

#: Aurora-Bezeichnung der Solartechnologien -> Anzeige im Tool.
#: "Fixed" ist die suedausgerichtete Pultanlage, "Tracking" die
#: einachsig nachgefuehrte. Ihr Marktwert unterscheidet sich sichtbar:
#: Der Tracker erzeugt breiter ueber den Tag verteilt und trifft damit
#: weniger stark die Mittagsstunden mit den niedrigsten Preisen.
SOLAR_TECHNOLOGIEN: dict[str, str] = {
    "fixed solar pv": "Pult",
    "tracking solar pv": "Tracker",
}
#: Voreinstellung - die weit ueberwiegende Bauform im Bestand.
TECHNOLOGIE_STANDARD = "Pult"

#: Preisszenario, das seine Familie vertritt, wo nicht alle Kurven
#: nebeneinander passen (Uebersichtsdiagramme).
PREISSZENARIO_STANDARD = "Central"


def ist_leitszenario(
    name: str,
    bauform: str = TECHNOLOGIE_STANDARD,
    preisszenario: str = PREISSZENARIO_STANDARD,
) -> bool:
    """Vertritt dieses Szenario seine Familie in der Uebersicht?

    Aus einer Arbeitsmappe entstehen bis zu sechs Szenarien je Jahrgang
    ("Stamm · Bauform · Preisszenario"). Nebeneinander gezeichnet sind
    das zwanzig Linien, von denen die meisten dasselbe sagen: Low und
    High sind die Spanne um Central, und der Tracker laeuft dicht neben
    dem Pult. Fuer den Ueberblick zaehlt je Familie eine Kurve - die
    uebrigen bleiben in den Reitern und in der Projektauswahl
    vollstaendig verfuegbar.

    Traegt ein Name keine der beiden Angaben (aeltere, von Hand
    gepflegte Szenarien), gilt er immer als Leitszenario: Sonst
    verschwaende ein Bestand aus der Uebersicht, nur weil er dem
    Namensschema nicht folgt.
    """
    teile = [t.strip() for t in name.split("·")]
    bauformen = {b.casefold() for b in SOLAR_TECHNOLOGIEN.values()}
    gefundene_bauform = next(
        (t for t in teile if t.casefold() in bauformen), ""
    )
    gefundenes_szenario = next(
        (t for t in teile if t.casefold() in _SZENARIO_NAMEN), ""
    )
    return (
        gefundene_bauform.casefold() in ("", bauform.casefold())
        and gefundenes_szenario.casefold() in ("", preisszenario.casefold())
    )

#: Szenarionamen, an denen die Szenariospalte erkannt wird.
_SZENARIO_NAMEN = ("central", "low", "high", "net zero")

#: Regeln der Abregelungsquote, die ein Jahresblatt fuehren kann - in
#: der Reihenfolge, in der sie im Blatt stehen.
_REGELN = {
    "1h": ("1 hour",),
    "4h": ("4 hour",),
    "6h": ("6 hour",),
    "15min": ("15 minute",),
}


def _text_normal(wert) -> str:
    """Vergleichsform einer Beschriftung: klein, ohne Bindestriche,
    ohne Mehrfach-Leerzeichen. "curtailed-below-zero" und "curtailed
    below zero" sind dieselbe Groesse."""
    if wert is None or (isinstance(wert, float) and pd.isna(wert)):
        return ""
    text = str(wert).replace("–", "-").replace("—", "-")
    text = text.replace("-", " ").replace("/", " ")
    return re.sub(r"\s+", " ", text).strip().lower()


def _ist_jahr(wert) -> bool:
    return isinstance(wert, (int, float)) and not isinstance(wert, bool) and (
        1990 <= float(wert) <= 2100 and float(wert) == int(wert)
    )


def _abschnitte(df: pd.DataFrame) -> pd.Series:
    """Laufende Nummer des Abschnitts je Zeile.

    Abschnitte beginnen mit einer Ueberschrift in der ersten Spalte
    ("Results - solar"). Sie begrenzen das Fortschreiben der
    Beschriftungen: Ein Blocktitel darf nicht in den naechsten Block
    hineinlaufen.
    """
    ueberschrift = df.iloc[:, 0].apply(lambda w: bool(_text_normal(w)))
    return ueberschrift.cumsum()


def _beschriftungstext(df: pd.DataFrame, meta_spalten: list[int]) -> pd.Series:
    """Ein Suchtext je Zeile aus allen Beschriftungsspalten.

    Die Beschriftung steht in Aurora-Mappen mal in einer, mal in zwei
    Spalten (englisch/deutsch), und sie wird oft nur in der ersten Zeile
    eines Blocks gesetzt. Deshalb: je Spalte innerhalb des Abschnitts
    fortschreiben, danach alles zusammenfuegen.
    """
    abschnitt = _abschnitte(df)
    teile = []
    for spalte in meta_spalten:
        werte = df.iloc[:, spalte].apply(_text_normal).replace("", pd.NA)
        gefuellt = werte.groupby(abschnitt).ffill().fillna("")
        teile.append(gefuellt)
    return teile[0].str.cat(teile[1:], sep=" | ") if teile else pd.Series("", index=df.index)


def _szenario_je_zeile(df: pd.DataFrame, meta_spalten: list[int]) -> pd.Series:
    """Die Spalte, in der die Szenarionamen stehen - dynamisch gesucht."""
    beste, treffer_beste = None, 0
    for spalte in meta_spalten:
        werte = df.iloc[:, spalte].apply(_text_normal)
        treffer = int(werte.isin(_SZENARIO_NAMEN).sum())
        if treffer > treffer_beste:
            beste, treffer_beste = spalte, treffer
    if beste is None:
        return pd.Series("", index=df.index)
    return df.iloc[:, beste].apply(_text_normal)


@dataclass
class AuroraArbeitsmappe:
    """Eine gelesene Aurora-Arbeitsmappe.

    Traegt die Rohblaetter und das, was die Oberflaeche fuer die Auswahl
    braucht: welche Szenarien und welche Solartechnologien darin
    vorkommen.
    """

    titel: str
    geografie: str
    quartal: str
    preisbasisjahr: int | None
    szenarien: list[str]
    technologien: list[str]
    #: Monatsblatt: Rohzellen, Datenspalten (Spalte, Jahr, Monat),
    #: Suchtext und Szenario je Zeile.
    monat_df: pd.DataFrame = field(repr=False, default_factory=pd.DataFrame)
    monat_spalten: list[tuple[int, int, int]] = field(default_factory=list)
    monat_text: pd.Series = field(repr=False, default_factory=pd.Series)
    monat_szenario: pd.Series = field(repr=False, default_factory=pd.Series)
    #: Jahresblaetter je Szenario (Kleinschreibung) mit denselben Angaben.
    jahr_blaetter: dict[str, tuple[pd.DataFrame, list[tuple[int, int]], pd.Series]] = (
        field(repr=False, default_factory=dict)
    )


def _kopfzeilen_monat(df: pd.DataFrame) -> list[tuple[int, int, int]]:
    """Datenspalten des Monatsblatts als (Spalte, Jahr, Monat).

    Gesucht werden die Zeilen mit "Calendar year" und "Month"; die
    Datenspalten sind die, unter denen in beiden eine Zahl steht.
    """
    jahr_zeile = monat_zeile = None
    for i in range(min(len(df), 20)):
        werte = [_text_normal(w) for w in df.iloc[i]]
        if jahr_zeile is None and any(w in ("calendar year", "kalenderjahr") for w in werte):
            jahr_zeile = i
        if monat_zeile is None and any(w in ("month", "monat") for w in werte):
            monat_zeile = i
    if jahr_zeile is None or monat_zeile is None:
        raise AuroraImportFehler(
            "Im Blatt der Monatswerte fehlen die Kopfzeilen „Calendar year“ "
            "und „Month“ – die Arbeitsmappe hat ein unbekanntes Format."
        )
    spalten = []
    for spalte in range(df.shape[1]):
        jahr, monat = df.iat[jahr_zeile, spalte], df.iat[monat_zeile, spalte]
        if _ist_jahr(jahr) and isinstance(monat, (int, float)) and not isinstance(monat, bool):
            if 1 <= int(monat) <= MONATE:
                spalten.append((spalte, int(jahr), int(monat)))
    if not spalten:
        raise AuroraImportFehler(
            "Im Blatt der Monatswerte konnten keine Monatsspalten erkannt "
            "werden – die Arbeitsmappe hat ein unbekanntes Format."
        )
    return spalten


def _kopfzeilen_jahr(df: pd.DataFrame) -> list[tuple[int, int]]:
    """Datenspalten eines Jahresblatts als (Spalte, Jahr)."""
    # Zwei Jahresspalten genuegen als Nachweis: Andere Zellen koennen
    # zwar zufaellig im Jahresbereich liegen, aber nicht zwei in einer
    # Zeile nebeneinander - und die erste solche Zeile ist die Kopfzeile.
    for i in range(min(len(df), 60)):
        kandidaten = [
            (spalte, int(df.iat[i, spalte]))
            for spalte in range(df.shape[1])
            if _ist_jahr(df.iat[i, spalte])
        ]
        if len(kandidaten) >= 2:
            return kandidaten
    return []


def _kopfangabe(df: pd.DataFrame, schluessel: str) -> str:
    """Wert aus dem Kopf der Mappe ("Title", "Geography", "Currency")."""
    for i in range(min(len(df), 10)):
        for spalte in range(min(df.shape[1], 8)):
            if _text_normal(df.iat[i, spalte]) == schluessel:
                for rechts in range(spalte + 1, min(spalte + 4, df.shape[1])):
                    wert = df.iat[i, rechts]
                    if wert is not None and str(wert).strip():
                        return str(wert).strip()
    return ""


def lies_arbeitsmappe(inhalt: bytes, dateiname: str) -> AuroraArbeitsmappe:
    """Liest die Arbeitsmappe und sagt, was in ihr steckt."""
    try:
        blaetter = pd.read_excel(io.BytesIO(inhalt), sheet_name=None, header=None)
    except Exception as fehler:
        raise AuroraImportFehler(
            f"Die Arbeitsmappe „{dateiname}“ ließ sich nicht lesen: {fehler}"
        ) from fehler

    monatsblatt = next(
        (name for name in blaetter if _text_normal(name).startswith("monthly")), None
    )
    if monatsblatt is None:
        raise AuroraImportFehler(
            f"In „{dateiname}“ fehlt das Blatt „Monthly prices“. Für das "
            "Monatsmodell (zweiseitiger CfD, Abschöpfung) werden monatliche "
            "Daten benötigt – bitte die vollständige Aurora-Arbeitsmappe laden."
        )

    monat_df = blaetter[monatsblatt]
    monat_spalten = _kopfzeilen_monat(monat_df)
    erste_datenspalte = monat_spalten[0][0]
    meta = [s for s in range(1, erste_datenspalte)]
    monat_text = _beschriftungstext(monat_df, meta)
    monat_szenario = _szenario_je_zeile(monat_df, meta)

    szenarien: list[str] = []
    for name in blaetter:
        if _text_normal(name) in _SZENARIO_NAMEN:
            szenarien.append(str(name).strip())
    if not szenarien:
        # Ohne Jahresblaetter bleiben die Szenarien des Monatsblatts.
        szenarien = [w.title() for w in dict.fromkeys(monat_szenario) if w]

    technologien = [
        anzeige
        for aurora, anzeige in SOLAR_TECHNOLOGIEN.items()
        if monat_text.str.contains(aurora, regex=False).any()
    ]

    jahr_blaetter = {}
    for name in blaetter:
        if _text_normal(name) not in _SZENARIO_NAMEN:
            continue
        jahr_df = blaetter[name]
        spalten = _kopfzeilen_jahr(jahr_df)
        if not spalten:
            continue
        meta_jahr = [s for s in range(1, spalten[0][0])]
        jahr_blaetter[_text_normal(name)] = (
            jahr_df, spalten, _beschriftungstext(jahr_df, meta_jahr)
        )

    waehrung = _kopfangabe(monat_df, "currency")
    basisjahr = None
    treffer = re.search(r"real\s+(\d{4})", waehrung.lower())
    if treffer:
        basisjahr = int(treffer.group(1))

    return AuroraArbeitsmappe(
        titel=_kopfangabe(monat_df, "title"),
        geografie=_kopfangabe(monat_df, "geography"),
        quartal=_quartal_aus_name(dateiname),
        preisbasisjahr=basisjahr,
        szenarien=szenarien,
        technologien=technologien or [TECHNOLOGIE_STANDARD],
        monat_df=monat_df,
        monat_spalten=monat_spalten,
        monat_text=monat_text,
        monat_szenario=monat_szenario,
        jahr_blaetter=jahr_blaetter,
    )


def _quartal_aus_name(dateiname: str) -> str:
    """Ausgabestand aus dem Dateinamen ("Q3_26", "Oct25") - er macht den
    Szenarionamen im Tool unterscheidbar."""
    treffer = re.search(r"(Q[1-4][_ ]?\d{2})", dateiname, re.IGNORECASE)
    if treffer:
        return treffer.group(1).replace("_", "/").upper()
    treffer = re.search(
        r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[_ ]?(\d{2})",
        dateiname, re.IGNORECASE,
    )
    if treffer:
        return f"{treffer.group(1).title()} {treffer.group(2)}"
    return ""


def _monatsreihen(
    mappe: AuroraArbeitsmappe, szenario: str, *begriffe: str, ohne: str = ""
) -> dict[int, list[float]]:
    """Zwoelferreihen je Kalenderjahr fuer die erste passende Zeile.

    Nur vollstaendige Jahre: Eine Reihe mit zehn Monaten stuende in der
    Kurve stillschweigend verschoben.
    """
    passend = mappe.monat_text.str.contains(begriffe[0], regex=False)
    for begriff in begriffe[1:]:
        passend &= mappe.monat_text.str.contains(begriff, regex=False)
    if ohne:
        passend &= ~mappe.monat_text.str.contains(ohne, regex=False)
    passend &= mappe.monat_szenario == _text_normal(szenario)

    zeilen = list(mappe.monat_df.index[passend])
    if not zeilen:
        return {}
    zeile = zeilen[0]

    roh: dict[int, dict[int, float]] = {}
    for spalte, jahr, monat in mappe.monat_spalten:
        wert = pd.to_numeric(mappe.monat_df.iat[zeile, spalte], errors="coerce")
        if pd.notna(wert):
            roh.setdefault(jahr, {})[monat] = float(wert)
    return {
        jahr: [werte[m] for m in range(1, MONATE + 1)]
        for jahr, werte in roh.items()
        if len(werte) == MONATE
    }


def _erste_zeile_text(
    mappe: AuroraArbeitsmappe, szenario: str, *begriffe: str
) -> str:
    """Der Suchtext der ersten passenden Monatszeile - aus ihm laesst
    sich ablesen, welche Regel Aurora dort meint."""
    passend = mappe.monat_szenario == _text_normal(szenario)
    for begriff in begriffe:
        passend &= mappe.monat_text.str.contains(begriff, regex=False)
    treffer = list(mappe.monat_text[passend])
    return treffer[0] if treffer else ""


def _jahresreihe(
    mappe: AuroraArbeitsmappe, szenario: str, *begriffe: str, ohne: str = ""
) -> dict[int, float]:
    """Jahreswerte aus dem Szenarioblatt fuer die erste passende Zeile."""
    blatt = mappe.jahr_blaetter.get(_text_normal(szenario))
    if blatt is None:
        return {}
    df, spalten, text = blatt
    passend = text.str.contains(begriffe[0], regex=False)
    for begriff in begriffe[1:]:
        passend &= text.str.contains(begriff, regex=False)
    if ohne:
        passend &= ~text.str.contains(ohne, regex=False)
    zeilen = list(df.index[passend])
    if not zeilen:
        return {}
    zeile = zeilen[0]
    werte = {}
    for spalte, jahr in spalten:
        wert = pd.to_numeric(df.iat[zeile, spalte], errors="coerce")
        if pd.notna(wert):
            werte[jahr] = float(wert)
    return werte


def _abregelung_jahr(
    mappe: AuroraArbeitsmappe, szenario: str, tech: str
) -> dict[str, dict[int, float]]:
    """Die Abregelungsquoten aller im Blatt gefuehrten Regeln (Anteil 0-1)."""
    ergebnis = {}
    for regel, begriffe in _REGELN.items():
        werte = _jahresreihe(
            mappe, szenario, "curtailment", *begriffe, tech, "germany"
        )
        if werte:
            ergebnis[regel] = {j: w / 100.0 for j, w in werte.items()}
    return ergebnis


def _regel_aus_text(text: str) -> str | None:
    """Die im Text genannte Abregelungsregel, falls eine genannt wird."""
    for regel, begriffe in _REGELN.items():
        if all(b in text for b in begriffe):
            return regel
    return None


def _regel_der_monatsreihe(
    mappe: AuroraArbeitsmappe,
    zeilentext: str,
    monat: dict[int, list[float]],
    jahr: dict[str, dict[int, float]],
) -> str | None:
    """Auf welche Regel bezieht sich die monatliche Abregelungsquote?

    Aurora benennt sie je nach Jahrgang unterschiedlich: „curtailment %
    - 1 hour rule“ sagt es direkt, „curtailment-below-zero“ nicht. Im
    zweiten Fall steht die Antwort in der Fussnote des Abschnitts
    („equivalent to the 15 minute rule“). Erst wenn auch die fehlt,
    wird geraten - und zwar mit einem erzeugungsgewichteten Vergleich,
    weil Aurora seine Jahreswerte gewichtet und ein ungewichtetes
    Monatsmittel fuer PV systematisch zu niedrig liegt.
    """
    # Genannte Regeln zaehlen nur, wenn das Jahresblatt sie auch fuehrt -
    # sonst gaebe es kein Niveau, auf das sich skalieren liesse.
    aus_beschriftung = _regel_aus_text(zeilentext)
    if aus_beschriftung in jahr:
        return aus_beschriftung

    fussnoten = mappe.monat_text[
        mappe.monat_text.str.contains("equivalent to", regex=False)
    ]
    for text in fussnoten:
        regel = _regel_aus_text(text)
        if regel in jahr:
            return regel

    if not monat or not jahr:
        return None
    gewicht = [w / sum(EINSPEISEKURVE_STANDARD_PCT) for w in EINSPEISEKURVE_STANDARD_PCT]
    mittel = {
        j: sum(w * g for w, g in zip(werte, gewicht, strict=True))
        for j, werte in monat.items()
    }
    beste, abstand_beste = None, None
    for regel, werte in jahr.items():
        gemeinsam = set(mittel) & set(werte)
        if not gemeinsam:
            continue
        abstand = sum(abs(mittel[j] - werte[j]) for j in gemeinsam) / len(gemeinsam)
        if abstand_beste is None or abstand < abstand_beste:
            beste, abstand_beste = regel, abstand
    return beste


def _skaliere_auf_regel(
    monat: dict[int, list[float]],
    referenz: dict[int, float],
    ziel: dict[int, float],
) -> dict[int, list[float]]:
    """Monatsprofil der einen Regel auf das Jahresniveau der anderen.

    Die Monatsreihe traegt die Form (Fruehjahr viel, Winter wenig), die
    Jahresreihe das Niveau der gesuchten Regel. Beides zusammen ergibt
    die Monatsreihe der gesuchten Regel - ohne sie waere die 6h-Regel
    entweder ohne Monatsprofil oder auf dem falschen Niveau.
    """
    ergebnis = {}
    for jahr, werte in monat.items():
        faktor = 1.0
        if jahr in referenz and jahr in ziel and referenz[jahr] > 0:
            faktor = ziel[jahr] / referenz[jahr]
        ergebnis[jahr] = [min(max(w * faktor, 0.0), 1.0) for w in werte]
    return ergebnis


def importiere_arbeitsmappe(
    mappe: AuroraArbeitsmappe,
    basisname: str,
    technologie: str = TECHNOLOGIE_STANDARD,
    szenarien: list[str] | None = None,
    uncurtailed: bool = True,
) -> list[AuroraImport]:
    """Ein Marktpreisszenario je Aurora-Szenario aus einer Arbeitsmappe.

    Die drei Preisszenarien (Central, Low, High) werden als drei
    getrennte Marktpreisszenarien angelegt - „<Basisname> · Pult ·
    Central“ und so fort. Damit sind sie im Projekt einzeln waehlbar
    (eine Variante je Szenario) und stehen zugleich gemeinsam im
    Szenarienvergleich der Risikosicht: Die Sensitivitaet gegenueber dem
    Preispfad ist dort ein Bild, kein Rechenlauf von Hand.

    technologie: „Pult“ oder „Tracker“ (siehe SOLAR_TECHNOLOGIEN). Beide
    Bauformen erloesen unterschiedlich, deshalb ist die Wahl Teil des
    Imports und keine Nebensache.
    """
    if not basisname.strip():
        raise AuroraImportFehler("Bitte einen Namen für die Szenarien angeben.")

    aurora_tech = next(
        (a for a, anzeige in SOLAR_TECHNOLOGIEN.items() if anzeige == technologie),
        None,
    )
    if aurora_tech is None:
        raise AuroraImportFehler(
            f"Unbekannte Technologie „{technologie}“ – erwartet werden "
            + " oder ".join(SOLAR_TECHNOLOGIEN.values())
            + "."
        )

    gewaehlt = szenarien or mappe.szenarien
    ergebnisse: list[AuroraImport] = []
    for szenario in gewaehlt:
        ergebnisse.append(
            _importiere_szenario(
                mappe, basisname.strip(), technologie, aurora_tech, szenario,
                uncurtailed,
            )
        )
    return ergebnisse


def _importiere_szenario(
    mappe: AuroraArbeitsmappe,
    basisname: str,
    technologie: str,
    aurora_tech: str,
    szenario: str,
    uncurtailed: bool,
) -> AuroraImport:
    hinweise: list[str] = []

    preis_begriffe = (
        (aurora_tech, "uncurtailed capture price") if uncurtailed
        else (aurora_tech, "capture price curtailed below zero")
    )
    marktwert_monat = _monatsreihen(mappe, szenario, *preis_begriffe)
    if not marktwert_monat and uncurtailed:
        marktwert_monat = _monatsreihen(
            mappe, szenario, aurora_tech, "capture price curtailed below zero"
        )
        if marktwert_monat:
            hinweise.append(
                "Kein ungekürzter Capture Price im Monatsblatt – es gilt der "
                "um negative Stunden gekürzte. Die Abregelung wirkt dann "
                "doppelt; die Gewichtung negativer Stunden kann das in den "
                "Globalen Annahmen ausgleichen."
            )
    if not marktwert_monat:
        raise AuroraImportFehler(
            f"Für „{technologie}“ und das Szenario „{szenario}“ stehen im "
            "Blatt der Monatswerte keine vollständigen Monatsreihen des "
            "Capture Price. Ohne sie sind zweiseitiger CfD und Abschöpfung "
            "nicht rechenbar."
        )

    # EUR/MWh -> ct/kWh
    marktwert_monat = {j: [w / 10.0 for w in werte] for j, werte in marktwert_monat.items()}

    baseload_monat = {
        j: [w / 10.0 for w in werte]
        for j, werte in _monatsreihen(
            mappe, szenario, "baseload", ohne="solar"
        ).items()
    }
    if not baseload_monat:
        hinweise.append(
            "Kein Baseload-Preis im Monatsblatt gefunden – die "
            "Direktvermarktungskosten im Modus „Anteil am Großhandelspreis“ "
            "greifen dann ersatzweise auf den Marktwert zurück."
        )

    # Abregelung: Monatsprofil aus dem Monatsblatt, Niveau je Regel aus
    # dem Jahresblatt.
    abregelung_monat = _monatsreihen(mappe, szenario, aurora_tech, "curtailment")
    abregelung_monat = {j: [w / 100.0 for w in werte] for j, werte in abregelung_monat.items()}
    jahresregeln = _abregelung_jahr(mappe, szenario, aurora_tech)
    zeilentext = _erste_zeile_text(mappe, szenario, aurora_tech, "curtailment")
    referenz_regel = _regel_der_monatsreihe(
        mappe, zeilentext, abregelung_monat, jahresregeln
    )

    def _reihe_fuer(regel: str) -> tuple[dict[int, list[float]], dict[int, float]]:
        jahr = jahresregeln.get(regel, {})
        if abregelung_monat and referenz_regel and jahr:
            monat = _skaliere_auf_regel(
                abregelung_monat, jahresregeln[referenz_regel], jahr
            )
        else:
            monat = abregelung_monat
            jahr = jahr or {
                j: sum(w) / MONATE for j, w in abregelung_monat.items()
            }
        return monat, jahr

    neg6_monat, neg6_jahr = _reihe_fuer("6h")
    neg1_monat, neg1_jahr = _reihe_fuer("1h")
    if not abregelung_monat and not jahresregeln:
        hinweise.append(
            "Keine Abregelungsquoten in der Arbeitsmappe gefunden – die "
            "Erzeugungsmenge in Stunden negativer Preise bleibt null. Bei "
            "älteren Ausgaben stehen sie auf eigenen Detailblättern; dann "
            "bitte von Hand nachtragen."
        )
    elif not abregelung_monat:
        hinweise.append(
            "Keine monatliche Abregelungsquote in der Arbeitsmappe – es "
            "gelten die Jahreswerte für alle zwölf Monate."
        )
    elif referenz_regel is None:
        hinweise.append(
            "Im Jahresblatt fehlen die Abregelungsquoten nach 1h- und "
            "6h-Regel – die monatliche Quote gilt für beide Regeln "
            "unverändert."
        )
    elif referenz_regel not in ("6h", "1h"):
        hinweise.append(
            f"Die monatliche Abregelungsquote entspricht der {referenz_regel}-"
            "Regel; sie wurde je Kalenderjahr auf das Niveau der 1h- und "
            "6h-Regel des Jahresblatts skaliert (Monatsprofil bleibt)."
        )

    # Jahreswerte: Aurora weist sie erzeugungsgewichtet aus - das ist
    # genauer als ein Mittel aus unseren Monatswerten, weil dort die
    # Stundenmengen eingehen. Fehlen sie, bleibt das Monatsmittel.
    marktwert_jahr = {
        j: w / 10.0
        for j, w in _jahresreihe(
            mappe, szenario, *preis_begriffe, "germany"
        ).items()
    }
    if not marktwert_jahr:
        marktwert_jahr = {j: sum(w) / MONATE for j, w in marktwert_monat.items()}
    baseload_jahr = {
        j: w / 10.0
        for j, w in _jahresreihe(
            mappe, szenario, "baseload", "germany", ohne="solar"
        ).items()
    }
    if not baseload_jahr and baseload_monat:
        baseload_jahr = {j: sum(w) / MONATE for j, w in baseload_monat.items()}

    name = " · ".join(
        teil for teil in (basisname, technologie, szenario.strip()) if teil
    )
    szenario_modell = MarktpreisSzenario(
        name=name,
        marktwert_solar_ct_kwh_je_kalenderjahr=marktwert_jahr,
        erzeugungsmenge_negativ_6h_pct_je_kalenderjahr=neg6_jahr,
        erzeugungsmenge_negativ_1h_pct_je_kalenderjahr=neg1_jahr,
        marktwert_solar_ct_kwh_je_monat=marktwert_monat,
        erzeugungsmenge_negativ_6h_pct_je_monat=neg6_monat,
        erzeugungsmenge_negativ_1h_pct_je_monat=neg1_monat,
        baseload_ct_kwh_je_kalenderjahr=baseload_jahr,
        baseload_ct_kwh_je_monat=baseload_monat,
    )
    jahre = (min(marktwert_jahr), max(marktwert_jahr)) if marktwert_jahr else (0, 0)
    if mappe.preisbasisjahr is None:
        hinweise.append(
            "Die Arbeitsmappe nennt keine Preisbasis – Basisjahr und "
            "Inflationsrate der Marktpreiskurven bleiben unverändert."
        )
    return AuroraImport(
        szenario=szenario_modell,
        technologie=technologie,
        jahre=jahre,
        monatsjahre=len(marktwert_monat),
        einspeisekurve_pct_je_monat=[],
        inflation_basisjahr=mappe.preisbasisjahr,
        inflation_pct_pa=None,
        hinweise=hinweise,
    )
