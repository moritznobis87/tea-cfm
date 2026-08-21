"""
Der Settings Hub - die Uebersichtsebene der Globalen Annahmen.

Die Seite hat seit v5.27 zwei Ebenen: eine LESBARE Uebersicht aus
Karten, die den geltenden Modellzustand zeigt, und darunter die
Bearbeitung in Dialogen bzw. einem Vollbreiten-Abschnitt. Diese Datei
liefert die Bausteine der Uebersicht und die Zustandsverwaltung; die
Felder selbst stehen in app/components/assumption_dialogs.py und
app/views/assumptions.py.

Warum es einen ENTWURF gibt
---------------------------
Bis v5.26 war die Seite eine lange Liste offener Felder, und der
Speichern-Knopf las am Ende ~60 lokale Variablen aus:

    with st.expander("Betriebskosten"):
        gemeindeabgabe = st.number_input(...)   # lokale Variable
    ...
    if st.button("Speichern"):
        ga.gemeindeabgabe_eur_kwh = gemeindeabgabe / 1000

Das funktioniert nur, weil ein Expander seinen Inhalt AUCH ZUGEKLAPPT
ausfuehrt - jedes Widget entsteht bei jedem Durchlauf, jede lokale
Variable ist gefuellt.

Ein Dialog bricht das: Streamlit fuehrt seinen Inhalt nur aus, solange
er offen ist. Ein Feld, das nur dort lebt, waere beim Speichern
verschwunden - und mit ihm sein Wert. Jedes Ausblenden von Feldern
erzwingt deshalb einen Zwischenspeicher; das ist keine Stilfrage.

Zwei Objekte, nicht eines
-------------------------
    ENTWURF  - der Arbeitsstand, in den die Dialoge schreiben
    BASIS    - der Stand, gegen den gezaehlt wird ("3 Aenderungen offen")

Beide sind vollstaendige GlobalAssumptions-Objekte und keine losen
dicts: Das Modell prueft beim Bauen (u.a. check_afa_fields), und diese
Pruefung soll beim Uebernehmen greifen und nicht erst beim Speichern.

    Dialog-Widgets  ->  ENTWURF (Session-State)  ->  YAML
      "Abbrechen"        "Uebernehmen" schreibt     "Speichern"
      schreibt nichts      hierhin                  schreibt hierhin

Die Falle: Sofortspeicher-Aktionen
----------------------------------
Vier Aktionen persistieren bewusst SOFORT und umgehen den
Speichern-Knopf - Marktsystemwechsel, Bauformwahl, Aurora-Import und das
Anlegen eines Szenarios. Jede von ihnen schreibt in die Datei, waehrend
der Entwurf noch den alten Stand haelt.

Der naive Weg - den Entwurf danach wegwerfen - waere ein stiller
Datenverlust in die andere Richtung: Wer Finanzierung und OPEX geaendert
hat und dann Aurora importiert, verlaere seine offenen Aenderungen.

Das Paar `sofort_beginnen()` / `sofort_abschliessen(vorher)` loest das
feldweise: Vor der Aktion wird der gespeicherte Stand gemerkt, danach
gegen den neuen verglichen. NUR die tatsaechlich veraenderten Felder
wandern in ENTWURF **und** BASIS und gelten damit als gespeichert; alles
Uebrige bleibt offen.

Bewusst gemessen statt aufgelistet: Eine handgepflegte Liste "welche
Felder aendert der Aurora-Import" waere in beide Richtungen gefaehrlich.
Ein vergessenes Feld erschiene hinterher als Phantomaenderung; ein zu
viel genanntes Feld ueberschriebe eine offene Aenderung des Nutzers mit
dem alten Wert - genau der stille Verlust, den das Ganze verhindern
soll. Der Vergleich kann beides nicht.

Damit das traegt, arbeiten die Sofortaktionen auf einer FRISCHEN KOPIE
des gespeicherten Stands und nicht auf dem Entwurf: Wuerden sie den
Entwurf speichern, gingen alle offenen Aenderungen ungefragt mit in die
Datei.

Ein Rest bleibt: Setzt eine Sofortaktion ein Feld, an dem der Nutzer
gerade eine offene Aenderung hat (der CSV-Import schaltet auf
Monatsaufloesung, obwohl im Entwurf Jahr steht), gewinnt die Aktion. Das
ist die richtige Reihenfolge - sie hat explizit geschrieben und
persistiert -, aber es ist eine Aenderung, die der Nutzer nicht selbst
vorgenommen hat.

Der eine Fall, der nicht zu retten ist
--------------------------------------
Aendert sich die Datei von AUSSEN (Wiederherstellung aus einer
Sicherung, eine zweite Sitzung), laesst sich nicht feldweise mitziehen -
es ist unbekannt, was sich geaendert hat. Dann wird neu angesaet und der
Entwurf faellt weg. Das passiert nicht stillschweigend: `aussen_geaendert()`
meldet es, und die Seite sagt es an.
"""

from __future__ import annotations

import copy
import html
from typing import Any

import streamlit as st

from app import services
from engine import GlobalAssumptions
from texte import txt

#: Session-State-Schluessel. Bewusst OHNE Widget: Streamlit fasst sie nie
#: an und raeumt sie nicht weg, wenn ein Bereich in einem Durchlauf nicht
#: gerendert wird.
_ENTWURF = "ga_entwurf"
_BASIS = "ga_basis"
#: Stempel des Dateistands, aus dem BASIS entstanden ist.
_STEMPEL = "ga_entwurf_stempel"
#: Merker fuer die Meldung "von aussen geaendert".
_AUSSEN = "ga_entwurf_aussen"

#: Praefix aller Dialog-Widgets. Sie werden beim Oeffnen aus dem Entwurf
#: vorbelegt und beim Verwerfen weggeraeumt.
DIALOG_PRAEFIX = "gadlg_"
#: Praefix der Widgets im Vollbreiten-Abschnitt "Markt & Preise". Sie
#: schreiben bei JEDEM Durchlauf in den Entwurf, solange der Abschnitt
#: sichtbar ist - ein eigener Zwischenschritt "Uebernehmen" waere dort
#: eine Huelle ohne Zweck.
ABSCHNITT_PRAEFIX = "gasec_"


def _stempel() -> float:
    """Aenderungszeit der Annahmendatei - derselbe Schluessel, mit dem
    services.get_global_assumptions seinen Cache fuehrt."""
    return services.GLOBAL_ASSUMPTIONS_PATH.stat().st_mtime


def _ansaeen() -> None:
    gespeichert = services.get_global_assumptions()
    st.session_state[_ENTWURF] = gespeichert.model_copy(deep=True)
    st.session_state[_BASIS] = gespeichert.model_copy(deep=True)
    st.session_state[_STEMPEL] = _stempel()


def _sicherstellen() -> None:
    """Saet an, wenn noch nichts da ist oder die Datei von aussen kam.

    Der Stempelvergleich ist die einzige Moeglichkeit, eine Aenderung von
    aussen zu bemerken. Eigene Sofortaktionen setzen den Stempel selbst
    nach und laufen deshalb nicht in diesen Zweig.
    """
    if _ENTWURF not in st.session_state:
        _ansaeen()
        return
    if st.session_state.get(_STEMPEL) != _stempel():
        # Was sich geaendert hat, ist unbekannt - feldweises Mitziehen
        # scheidet aus. Offene Aenderungen gehen verloren; das wird
        # gemeldet und nicht verschwiegen.
        offen = bool(geaenderte_felder())
        _ansaeen()
        st.session_state[_AUSSEN] = offen


def entwurf() -> GlobalAssumptions:
    """Der Arbeitsstand der Seite - dasselbe Objekt bis zum Speichern."""
    _sicherstellen()
    return st.session_state[_ENTWURF]


def basis() -> GlobalAssumptions:
    """Der Stand, gegen den gezaehlt wird."""
    _sicherstellen()
    return st.session_state[_BASIS]


def aussen_geaendert() -> bool:
    """Einmalige Meldung, dass ein Entwurf einer Fremdaenderung wich."""
    return bool(st.session_state.pop(_AUSSEN, False))


def sofort_beginnen() -> GlobalAssumptions:
    """Arbeitskopie des GESPEICHERTEN Stands fuer eine Sofortaktion.

    Bewusst nicht der Entwurf: Eine Sofortaktion speichert, und mit dem
    Entwurf als Grundlage gingen alle offenen Aenderungen ungefragt mit
    in die Datei.

    Der Rueckgabewert dient zugleich als Vergleichsstand fuer
    `sofort_abschliessen` - deshalb die Kopie und nicht das Original aus
    dem Cache, das die Aktion gleich mutiert.
    """
    _sicherstellen()
    return services.get_global_assumptions().model_copy(deep=True)


def sofort_abschliessen(vorher: GlobalAssumptions) -> set[str]:
    """Nach der Persistenz genau die veraenderten Felder nachziehen.

    `vorher` ist der Rueckgabewert von `sofort_beginnen`. Verglichen wird
    gegen den frisch gespeicherten Stand; nur was sich unterscheidet,
    wandert in Entwurf UND Basis und gilt damit als gespeichert. Alle
    uebrigen offenen Aenderungen bleiben unberuehrt und weiterhin
    gezaehlt.

    Der Stempel wird mitgesetzt, damit `_sicherstellen` die eigene
    Schreiboperation nicht fuer eine Fremdaenderung haelt und den Entwurf
    wegwirft.

    Zusaetzlich fallen die Dialog-Widgets weg: Sie wurden aus dem alten
    Stand vorbelegt und zeigten sonst Werte, die es nicht mehr gibt.

    Gibt die betroffenen Feldnamen zurueck - die Tests pruefen daran,
    dass eine Aktion genau das anfasst, was sie soll.
    """
    neu = services.get_global_assumptions()
    betroffen = {
        feld
        for feld in type(neu).model_fields
        if getattr(neu, feld) != getattr(vorher, feld)
    }
    for ziel in (st.session_state[_ENTWURF], st.session_state[_BASIS]):
        for feld in betroffen:
            setattr(ziel, feld, copy.deepcopy(getattr(neu, feld)))
    st.session_state[_STEMPEL] = _stempel()
    dialogzustand_leeren()
    return betroffen


def dialogzustand_leeren() -> None:
    """Raeumt die Widgets der Dialoge und Abschnitte weg.

    Die Dialoge belegen ihre Widgets beim OEFFNEN aus dem Entwurf vor;
    dieser Aufruf ist der zweite Riegel gegen alte Werte. Die
    Abschnittswidgets belegen sich beim naechsten Zeichnen selbst neu -
    fuer sie ist das Raeumen der einzige Riegel, weil sie keinen
    Oeffnen-Zeitpunkt haben.
    """
    for schluessel in [
        k
        for k in list(st.session_state)
        if str(k).startswith((DIALOG_PRAEFIX, ABSCHNITT_PRAEFIX))
    ]:
        st.session_state.pop(schluessel, None)


def entwurf_verwerfen() -> None:
    """Zurueck auf den gespeicherten Stand."""
    _ansaeen()
    dialogzustand_leeren()


def entwurf_speichern() -> None:
    """Persistiert den Entwurf und invalidiert die Bewertungs-Caches.

    Erst hier - und nur hier - werden alle Projekte neu bewertet (siehe
    services.save_global_assumptions). Waehrend im Dialog gedreht wird,
    passiert nichts davon.
    """
    services.save_global_assumptions(st.session_state[_ENTWURF])
    _ansaeen()
    dialogzustand_leeren()


# --- Aenderungsstand --------------------------------------------------------
#
# Verglichen wird FELDWEISE gegen die Basis und nicht gegen einen Merker
# "hier wurde geklickt": Wer einen Wert aendert und wieder zuruecksetzt,
# hat nichts geaendert, und die Seite soll das auch sagen.

#: Feld -> Bereich. Ein Feld ohne Eintrag zaehlt in die Gesamtzahl, aber
#: in keine Karte - so faellt ein spaeter ergaenztes Modellfeld nicht
#: stumm aus der Anzeige.
FELDER_JE_BEREICH: dict[str, tuple[str, ...]] = {
    "markt": (
        "marktpreisszenarien", "marktpreis_inflation_pct_pa",
        "marktpreis_inflation_basisjahr", "zeitaufloesung",
        "einspeisekurve_pct_je_monat", "einspeisekurve_bauform",
        "einspeisekurven_je_bauform",
        "negative_stunden_gewichtung_pct", "negative_stunden_modus",
    ),
    "vermarktung": (
        "direktvermarktung_modus", "direktvermarktungskosten_eur_kwh",
        "direktvermarktung_pct_marktwert", "ppa_anteil_pct_vorschlag",
        "ppa_preis_eur_mwh_vorschlag", "ppa_laufzeit_jahre_vorschlag",
        "ppa_indexierung_pct_pa_vorschlag",
    ),
    "betriebskosten": (
        "opex_standard", "kosten_inflation_pct_pa", "gemeindeabgabe_eur_kwh",
        "pacht_umsatzbeteiligung_pct_vorschlag",
        "pacht_mindestpacht_eur_ha_jahr_vorschlag",
    ),
    "technik": (
        "degradation_pct_pa", "sicherheitsabschlag_pct", "betriebsdauer_jahre",
        "einspeiselimit_pct", "nennleistung_kwp_vorschlag",
        "vollbenutzungsstunden_kwh_kwp_vorschlag",
        "epc_eur_kwp_vorschlag_je_anlagentyp",
    ),
    "finanzierung": (
        "eigenkapitalquote_pct_vorschlag", "fremdkapitalzins_pct_vorschlag",
        "kreditlaufzeit_jahre", "tilgungsart", "tilgungsfreies_anlaufjahr",
        "zinsmethode", "dscr_cash_trap", "dscr_event_of_default",
    ),
    "foerderung": (
        "praemien_modell", "negative_stunden_regel", "eag_foerderdauer_jahre",
        "eag_rueckzahlung_ab_mw", "eag_rueckzahlung_toleranzband_pct",
        "eag_rueckzahlung_anteil_pct", "de_marktpraemie_erwartet_ct_kwh",
    ),
    "steuern": (
        "tax_modus", "steuersatz_pct", "afa_nutzungsdauer_jahre",
        "freibetrag_eur", "gewerbesteuer_hebesatz_pct",
        "gewerbesteuer_freibetrag_eur",
        "verlustvortrag_verrechnungsgrenze_pct",
    ),
    # Eigener Bereich und kein Anhaengsel an "Betriebskosten" oder
    # "Technik": Batteriepreise sind ein Thema fuer sich, sie fallen
    # schneller als alles andere in diesem Modell, und sie sind die
    # Stelle, an die man geht, wenn eine Co-Location-Rechnung nicht
    # aufgeht.
    "speicher": (
        "speicher_capex_leistung_eur_kw", "speicher_capex_energie_eur_kwh",
        "speicher_opex_eur_kw_jahr", "speicher_kalibrierung",
    ),
}


def geaenderte_felder() -> set[str]:
    """Namen aller Felder, die vom gespeicherten Stand abweichen."""
    neu = st.session_state[_ENTWURF]
    alt = st.session_state[_BASIS]
    return {
        feld
        for feld in type(neu).model_fields
        if getattr(neu, feld) != getattr(alt, feld)
    }


def aenderungen_je_bereich(geaendert: set[str]) -> dict[str, int]:
    """Anzahl offener Aenderungen je Kartenbereich."""
    return {
        bereich: sum(1 for feld in felder if feld in geaendert)
        for bereich, felder in FELDER_JE_BEREICH.items()
    }


# --- Darstellung ------------------------------------------------------------


def settings_card(
    titel: str,
    wert: str,
    subline: str = "",
    *,
    status: str = "",
    ton: str = "neutral",
    geaendert: int = 0,
    key: str,
):
    """Eine Karte der Uebersicht.

    Gibt den Container zurueck, in den der Aufrufer seinen
    Bearbeiten-Knopf setzt - dieselbe Bauweise wie die Themenkarten des
    Project Inspectors, damit Cockpit und Settings Hub wie ein Produkt
    wirken (siehe project_inspector.summary_card und die gemeinsamen
    Regeln in app/theme.py).

    Aufbau bewusst dreiteilig: Titel (worum geht es), Hauptwert (was gilt
    gerade), Subline (die zwei bis drei Angaben, die den Hauptwert
    einordnen). Mehr traegt eine Uebersichtskarte nicht - alles Weitere
    steht hinter "Bearbeiten".

    ton: "neutral" | "warnung" | "fehler" - faerbt allein das
    Statusabzeichen, nicht die ganze Karte. Eine vollflaechig eingefaerbte
    Karte behauptet mehr Dringlichkeit, als eine Einstellungsseite je
    hat.
    """
    kasten = st.container(key=f"gacard_{key}")
    with kasten:
        marken = ""
        if status:
            marken += (
                f'<span class="settings-status settings-status-{html.escape(ton)}">'
                f"{html.escape(status)}</span>"
            )
        if geaendert:
            marken += (
                '<span class="settings-marke">'
                + html.escape(
                    txt("oberflaeche.annahmen_karte_geaendert", anzahl=geaendert)
                )
                + "</span>"
            )
        st.markdown(
            f'<div class="settings-karte-text">'
            f'<div class="settings-karte-kopf">'
            f'<span class="settings-karte-titel">{html.escape(titel)}</span>'
            f"{marken}</div>"
            f'<div class="settings-karte-wert">{html.escape(wert)}</div>'
            + (
                f'<div class="settings-karte-sub">{html.escape(subline)}</div>'
                if subline
                else ""
            )
            + "</div>",
            unsafe_allow_html=True,
        )
    return kasten


def kurzfassung(teile: list[Any]) -> str:
    """Verbindet Angaben einer Subline - leere fallen weg."""
    return " · ".join(str(t) for t in teile if t)
