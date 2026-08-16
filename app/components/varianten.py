"""
Vergleich der Sensitivitaeten eines Standorts.

Zwei Fragen beantwortet dieses Modul, und beide beantwortet es aus den
vorhandenen Daten - es gibt nichts zusaetzlich zu pflegen:

1. Wie stehen die Varianten zueinander? (`kennzahlenzeilen`)
2. Was unterscheidet sie ueberhaupt? (`unterschiede`)

Die zweite ist die eigentlich schwer zu beantwortende: Wer drei Wochen
spaeter auf "Netz high" schaut, weiss nicht mehr, welche Felder er
damals angefasst hat. Der Vergleich der Projektmodelle weiss es.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.formatting import fmt_eur, fmt_number, fmt_pct
from engine import AnlagenTyp, PachtModus, PVProject

#: Relative Schranke fuer den Zahlenvergleich - dieselbe Ueberlegung wie
#: bei der Aenderungszaehlung der Parameterspalte: Das YAML-Speicherformat
#: und die spezifische Eingabe runden, und zwei Werte, die sich erst in
#: der zehnten Stelle unterscheiden, sind kein Unterschied.
_TOLERANZ = 1e-9


def _eur(wert) -> str:
    return fmt_eur(wert)


def _pct(wert) -> str:
    return fmt_pct(wert, 2)


def _zahl0(wert) -> str:
    return fmt_number(wert, 0)


def _zahl2(wert) -> str:
    return fmt_number(wert, 2)


def _ct(wert) -> str:
    return f"{fmt_number(wert, 2)} ct/kWh"


def _jahr(wert) -> str:
    """Jahreszahlen ohne Tausenderpunkt - "2.028" ist kein Jahr."""
    return str(int(wert))


def _text(wert) -> str:
    if isinstance(wert, AnlagenTyp):
        return "Agri-PV" if wert == AnlagenTyp.AGRI_PV else "Konventionell"
    if isinstance(wert, PachtModus):
        return "Fix" if wert == PachtModus.FIX else "Umsatzbeteiligung"
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if wert is None:
        return "—"
    return str(wert)


#: Felder, die im Unterschiedsvergleich auftauchen koennen - mit der
#: Beschriftung aus der Projektmaske und der passenden Darstellung.
#: Bewusst dieselben Bezeichnungen wie im Formular: Der Vergleich soll
#: auf ein Feld zeigen, das man wiederfindet.
_FELDER: dict[str, tuple[str, callable]] = {
    "anlagentyp": ("Anlagentyp", _text),
    "aktiv": ("Aktiv", _text),
    "inbetriebnahme_jahr": ("Inbetriebnahme – Jahr", _jahr),
    "inbetriebnahme_monat": ("Inbetriebnahme – Monat", _jahr),
    "nennleistung_kwp": ("Leistung (kWp)", _zahl0),
    "vollbenutzungsstunden_kwh_kwp": ("Vollbenutzungsstunden (kWh/kWp)", _zahl0),
    "pacht_eur_kwp_jahr": ("Pacht (€/kWp/Jahr)", _zahl2),
    "pacht_modus": ("Pachtmodus", _text),
    "pacht_umsatzbeteiligung_pct": ("Umsatzbeteiligung", _pct),
    "pacht_mindestpacht_eur_ha_jahr": ("Mindestpacht (€/ha/Jahr)", _zahl0),
    "projektflaeche_ha": ("Projektfläche (ha)", _zahl2),
    "fremdkapitalzins_pct": ("Fremdkapitalzins", _pct),
    "eigenkapitalquote_pct": ("Eigenkapitalquote", _pct),
    "eag_zuschlagswert_ct_kwh": ("EAG-Zuschlagswert", _ct),
    "gemeindeabgabe_eur_mwh": ("Gemeindeabgabe (€/MWh)", _zahl2),
    "direktvermarktungskosten_eur_mwh": ("DV-Kosten (€/MWh)", _zahl2),
    "marktpreisszenario": ("Marktpreisszenario", _text),
    "ppa_anteil_pct": ("PPA-Anteil", _pct),
    "ppa_preis_eur_mwh": ("PPA-Preis (€/MWh)", _zahl2),
    "ppa_start_jahr": ("PPA – erstes Betriebsjahr", _zahl0),
    "ppa_laufzeit_jahre": ("PPA-Laufzeit (Jahre)", _zahl0),
    "ppa_indexierung_pct_pa": ("PPA-Indexierung", _pct),
    "capex.epc_eur": ("EPC (€)", _eur),
    "capex.netzanschluss_eur": ("Netzanschluss (€)", _eur),
    "capex.trasse_eur": ("Trasse (€)", _eur),
    "capex.widmung_eur": ("Widmung (€)", _eur),
    "capex.genehmigung_eur": ("Genehmigung (€)", _eur),
    "capex.sonstige_extern_eur": ("Sonstige externe Kosten (€)", _eur),
    "capex.agm_eur": ("AGM (€)", _eur),
    "capex.m_and_a_eur": ("M&A (€)", _eur),
    "capex.poenale_puffer_eur": ("Pönale + Puffer (€)", _eur),
}

#: Diese Felder benennen die Variante, sie beschreiben sie nicht - ein
#: Unterschied darin ist keine Annahme, sondern die Identitaet.
_KEINE_ANNAHME = {"id", "name", "standort", "variante", "leitvariante"}


@dataclass(frozen=True)
class Unterschied:
    """Ein Feld, das zwischen den Varianten abweicht."""

    feld: str
    label: str
    #: Dargestellter Wert je Variante, in der Reihenfolge der Varianten.
    werte: list[str]
    #: Weicht der Wert der Variante von der Referenz ab?
    abweichend: list[bool]


def _wert(projekt: PVProject, pfad: str):
    ziel = projekt
    for teil in pfad.split("."):
        ziel = getattr(ziel, teil)
    return ziel


def _gleich(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) \
            and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) <= _TOLERANZ * max(abs(a), abs(b), 1.0)
    return a == b


def _positionssumme(positionen) -> float:
    """Summe frei benannter Positionen - ihre Zahl und Benennung ist
    projektspezifisch, ein Feld-fuer-Feld-Vergleich waere unlesbar."""
    return sum(getattr(p, "betrag_eur", getattr(p, "basiswert_eur_kwp", 0.0))
               for p in positionen)


def unterschiede(
    varianten: list[PVProject], referenz: PVProject
) -> list[Unterschied]:
    """Nur die Felder, in denen sich die Varianten tatsaechlich
    unterscheiden - in der Reihenfolge der Projektmaske.

    Alles Uebrige wegzulassen ist der Zweck: Eine Tabelle mit vierzig
    identischen Zeilen beantwortet die Frage nicht, welche drei davon
    den Unterschied ausmachen.
    """
    ergebnis: list[Unterschied] = []
    for pfad, (label, formatiere) in _FELDER.items():
        werte = [_wert(v, pfad) for v in varianten]
        if all(_gleich(w, werte[0]) for w in werte[1:]):
            continue
        ref = _wert(referenz, pfad)
        ergebnis.append(
            Unterschied(
                feld=pfad,
                label=label,
                werte=[formatiere(w) for w in werte],
                abweichend=[not _gleich(w, ref) for w in werte],
            )
        )

    # Frei benannte Positionen: als Summe, nicht Zeile fuer Zeile - ihre
    # Anzahl und Benennung ist je Projekt anders, ein Feldvergleich
    # ergaebe eine Tabelle ohne gemeinsame Zeilen.
    for pfad, label in [("capex.zusatzpositionen", "Weitere Investkosten (€)"),
                        ("zusatz_opex", "Weitere Betriebskosten (€/kWp/Jahr)")]:
        summen = [_positionssumme(_wert(v, pfad)) for v in varianten]
        if all(_gleich(s, summen[0]) for s in summen[1:]):
            continue
        ref = _positionssumme(_wert(referenz, pfad))
        ergebnis.append(
            Unterschied(
                feld=pfad, label=label,
                werte=[fmt_number(s, 2) for s in summen],
                abweichend=[not _gleich(s, ref) for s in summen],
            )
        )
    return ergebnis


def anzahl_gleicher_felder(varianten: list[PVProject]) -> int:
    """Wie viele der verglichenen Felder in allen Varianten gleich sind -
    die Gegenprobe zur Unterschiedstabelle."""
    return len(_FELDER) + 2 - len(unterschiede(varianten, varianten[0]))


def geprueft_alle_felder(varianten: list[PVProject]) -> set[str]:
    """Modellfelder, die der Vergleich NICHT betrachtet.

    Regressionsschutz: Kommt spaeter ein Projektfeld hinzu, faellt es
    hier auf, statt still aus der Unterschiedstabelle zu verschwinden.
    """
    bekannt = {p.split(".")[0] for p in _FELDER} | {"capex", "zusatz_opex"}
    return set(varianten[0].model_dump()) - bekannt - _KEINE_ANNAHME
