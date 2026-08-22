"""
Was ein Speicher kostet.

Zwei Zeilen Arithmetik, aber ein eigenes Modul - und das hat einen
Grund. Die Rechnung verbindet zwei Dinge, die bewusst getrennt
gespeichert sind:

    BatteryConfig          wie der Speicher gebaut ist (MW, MWh)
    EffectiveAssumptions   was ein MW und ein MWh kosten

Die Trennung ist keine Formsache. Die Auslegung gehoert zum Projekt -
sie folgt aus Flaeche, Netzanschluss und Vermarktungsidee. Der Preis
gehoert nicht dorthin: Batteriepreise sind eine Marktannahme und fallen
Jahr fuer Jahr spuerbar. Stuenden sie an der Auslegung, muesste eine
Preissenkung in jedem einzelnen Projekt nachgetragen werden, und die
globalen Annahmen waeren fuer diesen Posten keine Vorgabe mehr.

Zusammengefuehrt wird hier, an genau einer Stelle. Waere die Formel an
zwei Orten - etwa einmal im Cashflow und einmal in der Anzeige des
Dialogs -, liefen sie irgendwann auseinander, und niemand saehe der
Zahl an, welche der beiden sie ist.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import BatteryConfig, EffectiveAssumptions, GlobalAssumptions

#: kW je MW und kWh je MWh. Die Auslegung steht in MW/MWh, die Preise in
#: EUR/kW und EUR/kWh - der Faktor gehoert benannt und nicht als nackte
#: 1000 in die Formel.
_JE_EINHEIT = 1000.0


@dataclass(frozen=True)
class Kalibrierung:
    """Ein Satz Preisparameter mit seiner Herkunft.

    Die Quelle steht mit im Objekt und nicht nur im Kommentar: Zwei
    Kalibrierungen unterscheiden sich hier um mehr als den Faktor zwei,
    und welche gerade gilt, entscheidet ueber die Wirtschaftlichkeit
    eines Speichers. Wer die Zahl sieht, soll auch sehen, woher sie
    kommt.
    """

    schluessel: str
    #: Leistungsbezogen: Umrichter/PCS, Trafo, Schaltanlage, Anschluss.
    leistung_eur_kw: float
    #: Energiebezogen: Zellen, Module, Racks, Thermomanagement.
    energie_eur_kwh: float
    quelle: str
    #: Wo die Kalibrierung belastbar ist - und wo nicht.
    geltungsbereich: str = ""


#: Die hinterlegten Kalibrierungen. Frei editierbar bleiben die Werte
#: trotzdem: Diese hier sind Vorschlaege, keine Schranken.
KALIBRIERUNGEN: dict[str, Kalibrierung] = {
    "markt": Kalibrierung(
        schluessel="markt",
        leistung_eur_kw=48.0,
        energie_eur_kwh=82.0,
        quelle="BloombergNEF/Ember, Turnkey-Preisumfrage 2025 (global)",
        geltungsbereich=(
            "Zwei-Punkt-Kalibrierung aus 2h- und 4h-Marktdaten. Nur zwei "
            "Stuetzstellen - am belastbarsten zwischen zwei und vier "
            "Stunden Speicherdauer, darueber und darunter eine "
            "Extrapolation."
        ),
    ),
    "engineering": Kalibrierung(
        schluessel="engineering",
        leistung_eur_kw=318.0,
        energie_eur_kwh=206.0,
        quelle=(
            "NREL, Cost Projections for Utility-Scale Battery Storage, "
            "2025 Update, Mid Case (USD 2024, umgerechnet mit 0,856 EUR/USD)"
        ),
        geltungsbereich=(
            "Bottom-up aus Komponentenkosten - konservativer als die "
            "Marktpreise schluesselfertiger Anlagen."
        ),
    ),
}

#: Womit gerechnet wird, solange niemand etwas anderes einstellt.
KALIBRIERUNG_STANDARD = "markt"


def spezifisch_eur_kwh(
    dauer_h: float, leistung_eur_kw: float, energie_eur_kwh: float
) -> float:
    """Spezifische Kosten je kWh bei gegebener Speicherdauer.

        CAPEX / kWh = a / Dauer + b

    Die Kurve zeigt, was das Zweiparametermodell ausmacht: Bei kurzer
    Dauer dominiert der Leistungsanteil und die spezifischen Kosten
    steigen steil an; ab etwa vier Stunden laufen sie flach gegen `b`.
    Genau diesen Verlauf konnte die reine EUR/kW-Rechnung nicht abbilden -
    dort waren die spezifischen Kosten umgekehrt proportional zur Dauer,
    ohne Untergrenze.
    """
    if dauer_h <= 0:
        return 0.0
    return leistung_eur_kw / dauer_h + energie_eur_kwh


def verschleiss_eur_mwh(
    assumptions: EffectiveAssumptions | GlobalAssumptions,
) -> float:
    """Was ein Zyklus kostet, je MWh Durchsatz.

        Verschleiss = Energieanteil der Investition / Zyklenlebensdauer

    Bei 82 EUR/kWh und 6.000 Vollzyklen also 13,7 EUR/MWh. Die Groesse
    ist keine Erfindung, sondern schlichte Buchhaltung: Ein Vollzyklus
    verbraucht einen Anteil 1/Lebensdauer der Zelle, und ein Vollzyklus
    hat definitionsgemaess einen Durchsatz von einer nutzbaren
    Kilowattstunde (siehe economics.vollzyklen).

    Warum abgeleitet und nicht eingetragen
    --------------------------------------
    Die frueher fest eingetragenen 2 EUR/MWh waren um das Siebenfache zu
    niedrig - und sie blieben es auch, wenn die Zellpreise fielen. Ein
    fester Satz altert still: Bei 50 EUR/kWh waeren es 8,3 EUR/MWh, und
    niemand haette den Eintrag nachgezogen. Abgeleitet bleibt er
    stimmig, ohne dass jemand daran denken muss.

    Wozu der Satz dient - und wozu nicht
    ------------------------------------
    Er ist ein SCHATTENPREIS in der Zielfunktion des Dispatch: Ein
    Zyklus verbraucht Restlebensdauer, und der Optimierer muss das gegen
    den Preisunterschied halten. Ohne ihn zykliert das lineare Programm
    fuer jeden Spread oberhalb der Roundtrip-Verluste - fuer einen Euro
    Gewinn eine Zelle verschleissen.

    Dass derselbe Betrag derzeit AUCH vom Cashflow abgezogen wird, ist
    eine Vereinfachung: Er steht dort stellvertretend fuer die
    Ersatzinvestition, die das Modell noch nicht kennt. Gerechnet an
    einem 6-h-Speicher deckt er sie zu rund 86 Prozent. Sobald der
    Ersatz ausdruecklich gebucht wird, gehoert der Abzug aus dem
    Cashflow heraus - sonst waere die Batterie zweimal bezahlt.
    """
    # Beide Annahmenobjekte tragen die zwei Felder: die globalen als
    # Vorgabe, die aufgeloesten als das, was fuer dieses Projekt gilt.
    # Der Dialog fragt mit den globalen, der Dispatch mit den
    # aufgeloesten - dieselbe Rechnung, damit im Feld dieselbe Zahl
    # steht, mit der spaeter gerechnet wird.
    lebensdauer = assumptions.speicher_zyklenlebensdauer
    if lebensdauer <= 0:
        return 0.0
    return assumptions.speicher_capex_energie_eur_kwh / lebensdauer * _JE_EINHEIT


def mit_verschleiss(
    batterie: BatteryConfig | None,
    assumptions: EffectiveAssumptions | GlobalAssumptions,
) -> BatteryConfig | None:
    """Die Auslegung mit dem GELTENDEN Verschleisssatz.

    Ein eingetragener Satz bleibt stehen (eigene Zellgarantie), ein
    leerer wird abgeleitet. Aufgerufen an den wenigen Stellen, an denen
    eine Batterie in eine Optimierung geht - so gibt es genau einen Ort
    je Rechenweg, an dem die Aufloesung passiert.
    """
    if batterie is None or batterie.degradationskosten_eur_mwh is not None:
        return batterie
    return batterie.model_copy(update={
        "degradationskosten_eur_mwh": verschleiss_eur_mwh(assumptions)
    })


def capex_eur(
    batterie: BatteryConfig | None, assumptions: EffectiveAssumptions
) -> float:
    """Investition in den Speicher.

    Zwei Wege, und welcher gilt, haengt daran, ob fuer DIESES Projekt ein
    Angebot vorliegt:

        Angebot   Das Projekt hat einen eigenen Preis je kW hinterlegt.
                  Dann gilt er, und die Kapazitaet geht nicht ein - ein
                  Angebot ist bereits die feste Zahl fuer genau diese
                  Auslegung. Ein Modell darueberzulegen hiesse, eine
                  belastbare Angabe durch eine Schaetzung zu ersetzen.

        Modell    Sonst die zentrale Kalibrierung, zweiparametrig:

                      CAPEX = a * Leistung[kW] + b * Kapazitaet[kWh]

                  `a` traegt Umrichter, Trafo, Schaltanlage und
                  Anschluss, `b` die Zellen. Nur so kostet ein Speicher
                  mit doppelter Kapazitaet auch mehr - vorher tat er das
                  nicht, und ein 3-MW-Speicher mit 24 MWh war so teuer
                  wie einer mit 12 MWh.

    Ein unwirksamer Speicher kostet nichts: Wer ihn abschaltet, um seinen
    Beitrag zu isolieren, will das Projekt OHNE ihn sehen - mit seiner
    Investition im Anlagevermoegen waere es weder das eine noch das
    andere.
    """
    if batterie is None or not batterie.wirksam:
        return 0.0
    angebot = assumptions.speicher_capex_eur_kw
    if angebot is not None:
        return batterie.leistung_mw * _JE_EINHEIT * angebot
    return (
        batterie.leistung_mw * _JE_EINHEIT
        * assumptions.speicher_capex_leistung_eur_kw
        + batterie.kapazitaet_mwh * _JE_EINHEIT
        * assumptions.speicher_capex_energie_eur_kwh
    )


def opex_jahr_eur(
    batterie: BatteryConfig | None, assumptions: EffectiveAssumptions
) -> float:
    """Feste Betriebskosten je Jahr - an der Leistung bemessen.

    Nicht an der Kapazitaet: Wartung, Versicherung und Netzentgelte eines
    Speichers haengen an seiner Anschlussleistung, nicht daran, wie viele
    Stunden er durchhaelt.
    """
    if batterie is None or not batterie.wirksam:
        return 0.0
    return (
        batterie.leistung_mw * _JE_EINHEIT * assumptions.speicher_opex_eur_kw_jahr
    )
