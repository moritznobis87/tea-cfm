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

from ..models import BatteryConfig, EffectiveAssumptions

#: kW je MW und kWh je MWh. Die Auslegung steht in MW/MWh, die Preise in
#: EUR/kW und EUR/kWh - der Faktor gehoert benannt und nicht als nackte
#: 1000 in die Formel.
_JE_EINHEIT = 1000.0


def capex_eur(
    batterie: BatteryConfig | None, assumptions: EffectiveAssumptions
) -> float:
    """Investition in den Speicher, an der LEISTUNG bemessen.

    Die Kapazitaet geht nicht ein, und das ist eine bewusste
    Vereinfachung mit einer Folge, die man kennen muss: Ein 5-MW-Speicher
    kostet hier gleich viel, ob er zwei oder vier Stunden durchhaelt.
    Fachlich waere eine Zweiteilung genauer - Zellen skalieren mit der
    Energie, Wechselrichter und Anschluss mit der Leistung. In der Praxis
    liegt aber meist ein Angebot fuer EIN konkretes System vor, und dann
    ist der Gesamtbetrag die ehrlichere Eingabe. Genau dafuer gibt es im
    Speicherdialog den Umschalter auf einen absoluten Betrag: Er setzt
    einen Preis je kW, der zu dieser Auslegung passt.

    Ein unwirksamer Speicher kostet nichts: Wer ihn abschaltet, um seinen
    Beitrag zu isolieren, will das Projekt OHNE ihn sehen - mit seiner
    Investition im Anlagevermoegen waere es weder das eine noch das
    andere.
    """
    if batterie is None or not batterie.wirksam:
        return 0.0
    return (
        batterie.leistung_mw * _JE_EINHEIT * assumptions.speicher_capex_eur_kw
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
