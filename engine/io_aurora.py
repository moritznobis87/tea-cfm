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

from .models import MONATE, MarktpreisSzenario


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
