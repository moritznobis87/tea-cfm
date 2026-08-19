"""
Strukturpruefung der Globalen Annahmen.

Bewusst KLEIN gehalten. Die Karte "Datenqualitaet" soll eine Auskunft
sein und keine Validierungsplattform: Vier Pruefungen, die sich aus dem
vorhandenen Datenbestand eindeutig beantworten lassen. Alles, wofuer es
nur eine Heuristik gaebe ("sehen die Werte plausibel aus?"), bleibt
draussen - ein Fehlalarm entwertet die Karte schneller, als zehn
richtige Hinweise sie aufwerten.

Deshalb heisst die gute Nachricht auch nicht "alles korrekt", sondern
"keine strukturellen Datenprobleme": Geprueft wird die STRUKTUR der
Daten, nicht ihre fachliche Richtigkeit. Ob 8,2 ct/kWh der richtige
Marktwert fuer 2031 ist, kann diese Datei nicht wissen.

Drei Stufen:
    "ok"      - bestanden
    "hinweis" - auffaellig, aber rechenbar (gelb)
    "fehler"  - die Rechnung kann nicht stimmen (rot)
"""

from __future__ import annotations

from dataclasses import dataclass

from engine import (
    GlobalAssumptions,
    MarktSystem,
    PraemienModell,
    TaxModus,
    Zeitaufloesung,
)
from texte import txt


@dataclass(frozen=True)
class Befund:
    """Ergebnis einer Pruefung."""

    schluessel: str
    stufe: str  # "ok" | "hinweis" | "fehler"
    text: str


def _szenarien_vorhanden(ga: GlobalAssumptions) -> Befund:
    """Ohne Marktpreisszenario gibt es keinen Erloes zu rechnen."""
    if not ga.marktpreisszenarien:
        return Befund(
            "szenarien", "fehler", txt("oberflaeche.dq_szenarien_fehlen")
        )
    return Befund(
        "szenarien", "ok",
        txt("oberflaeche.dq_szenarien_ok", anzahl=len(ga.marktpreisszenarien)),
    )


def _monatswerte(ga: GlobalAssumptions) -> Befund | None:
    """Monatsmodus ohne Monatsreihen.

    Kein Fehler im engeren Sinn - das Modell faellt je Jahr ohne
    Monatsreihe auf den Jahreswert zurueck (siehe
    MarktpreisSzenario.marktwert_solar_ct_kwh_je_monat). Wer aber
    monatsscharf rechnen laesst und keine einzige Monatsreihe hat,
    rechnet in Wahrheit jaehrlich; das gehoert gesagt.

    Bei Jahresaufloesung entfaellt die Pruefung ganz - dann sind
    fehlende Monatsreihen kein Mangel.
    """
    if ga.zeitaufloesung != Zeitaufloesung.MONAT:
        return None
    if not ga.marktpreisszenarien:
        return None
    mit_monaten = sum(
        1 for s in ga.marktpreisszenarien if s.marktwert_solar_ct_kwh_je_monat
    )
    if mit_monaten == 0:
        return Befund("monat", "fehler", txt("oberflaeche.dq_monat_fehlt"))
    if mit_monaten < len(ga.marktpreisszenarien):
        return Befund(
            "monat", "hinweis",
            txt("oberflaeche.dq_monat_teilweise",
                mit=mit_monaten, gesamt=len(ga.marktpreisszenarien)),
        )
    return Befund("monat", "ok", txt("oberflaeche.dq_monat_ok"))


def _abdeckung(ga: GlobalAssumptions, letztes_modelljahr: int | None) -> Befund | None:
    """Reicht die Preiskurve bis ans Ende der Modelllaufzeit?

    `letztes_modelljahr` kommt von aussen (aus den vorhandenen
    Projekten), weil die Globalen Annahmen kein Startjahr kennen - die
    Inbetriebnahme steht im Projekt. Ohne Projekte entfaellt die
    Pruefung: Ein leerer Bestand hat keinen Modellzeitraum, den man
    verfehlen koennte.

    Der Fall ist ein HINWEIS und kein Fehler: Das Modell rechnet ueber
    das letzte Kurvenjahr hinaus mit der Marktpreisinflation weiter
    (marktpreis_inflation_pct_pa). Es rechnet also - nur eben
    fortgeschrieben statt hinterlegt, und das soll man wissen.
    """
    if letztes_modelljahr is None or not ga.marktpreisszenarien:
        return None
    jahre = [
        max(s.marktwert_solar_ct_kwh_je_kalenderjahr)
        for s in ga.marktpreisszenarien
        if s.marktwert_solar_ct_kwh_je_kalenderjahr
    ]
    if not jahre:
        return None
    ende = max(jahre)
    if ende < letztes_modelljahr:
        return Befund(
            "abdeckung", "hinweis",
            txt("oberflaeche.dq_abdeckung_kurz",
                ende=ende, modellende=letztes_modelljahr),
        )
    return Befund(
        "abdeckung", "ok", txt("oberflaeche.dq_abdeckung_ok", ende=ende)
    )


#: Welches Praemienmodell und welche Steuerlogik zum Marktsystem gehoeren
#: (siehe assumptions._wechsle_markt_system - dieselbe Zuordnung, hier
#: nur zum PRUEFEN statt zum Setzen).
_ERWARTET = {
    MarktSystem.OESTERREICH: (
        (PraemienModell.EAG_TOLERANZBAND, PraemienModell.ZWEISEITIG_CFD),
        (TaxModus.AFA_KOERPERSCHAFTSTEUER, TaxModus.PAUSCHAL_AUF_EBT),
    ),
    MarktSystem.DEUTSCHLAND: (
        (PraemienModell.EINSEITIG_CFD,),
        (TaxModus.GEWERBESTEUER_DE, TaxModus.PAUSCHAL_AUF_EBT),
    ),
}


def _regelwerk(ga: GlobalAssumptions) -> Befund:
    """Passt das Regelwerk zum eingestellten Marktsystem?

    Ein HINWEIS und keine Sperre: Die Einzelfelder bleiben nach dem
    Systemwechsel bewusst aenderbar (siehe
    assumptions._wechsle_markt_system), und eine gemischte Einstellung
    kann eine bewusste Sensitivitaet sein. Sie soll nur nicht unbemerkt
    entstehen.
    """
    modelle, steuern = _ERWARTET[ga.markt_system]
    abweichend = []
    if ga.praemien_modell not in modelle:
        abweichend.append(txt("oberflaeche.dq_regelwerk_praemie"))
    if ga.tax_modus not in steuern:
        abweichend.append(txt("oberflaeche.dq_regelwerk_steuer"))
    if abweichend:
        return Befund(
            "regelwerk", "hinweis",
            txt("oberflaeche.dq_regelwerk_abweichend",
                felder=", ".join(abweichend)),
        )
    return Befund("regelwerk", "ok", txt("oberflaeche.dq_regelwerk_ok"))


def pruefe(
    ga: GlobalAssumptions, letztes_modelljahr: int | None = None
) -> list[Befund]:
    """Alle Pruefungen; uebersprungene fallen weg."""
    ergebnisse = [
        _szenarien_vorhanden(ga),
        _monatswerte(ga),
        _abdeckung(ga, letztes_modelljahr),
        _regelwerk(ga),
    ]
    return [b for b in ergebnisse if b is not None]


def gesamtstufe(befunde: list[Befund]) -> str:
    """Die schwerste Stufe entscheidet ueber die Farbe der Karte."""
    stufen = {b.stufe for b in befunde}
    if "fehler" in stufen:
        return "fehler"
    if "hinweis" in stufen:
        return "hinweis"
    return "ok"


def kurzfassung(befunde: list[Befund]) -> tuple[str, str]:
    """Hauptwert und Subline der Karte "Datenqualitaet".

    Die gute Nachricht ist bewusst zurueckhaltend formuliert: Geprueft
    wird die Struktur, nicht die fachliche Richtigkeit der Zahlen.
    """
    auffaellig = [b for b in befunde if b.stufe != "ok"]
    if not auffaellig:
        return (
            txt("oberflaeche.dq_titel_ok"),
            txt("oberflaeche.dq_sub_ok", anzahl=len(befunde)),
        )
    fehler = [b for b in auffaellig if b.stufe == "fehler"]
    kopf = (
        txt("oberflaeche.dq_titel_fehler", anzahl=len(fehler)) if fehler
        else txt("oberflaeche.dq_titel_hinweis", anzahl=len(auffaellig))
    )
    return kopf, auffaellig[0].text
