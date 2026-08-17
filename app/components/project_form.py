"""
Die Projektmaske als wiederverwendbare Komponente - identisch fuer
Neuanlage und Bearbeitung.

Designentscheidung Einheiten-Umschalter:
Die Umschalter fuer Investkosten (€/kWp <-> €) und Pacht (€/kWp/Jahr <->
€/ha/Jahr) liegen bewusst AUSSERHALB von st.form(...): Formular-Inhalte
aktualisieren sich in Streamlit erst beim Absenden, Umschalter ausserhalb
loesen dagegen einen sofortigen Rerun aus, damit Beschriftungen und
Werte unmittelbar umspringen.

Designentscheidung stabile Widget-Keys:
Beim Einheiten-Wechsel schreibt DIESE Komponente den passend
umgerechneten Wert direkt in den Session-State, BEVOR das Widget im
aktuellen Run instanziiert wird - es gibt also je Feld genau EIN Widget
mit stabilem Key, nicht zwei alternative Widgets je Einheit. Widgets, die
zwischen Runs erscheinen/verschwinden, sind in Streamlit ein bekanntes
Risikomuster fuer inkonsistentes Formularverhalten.
"""

from __future__ import annotations

import contextlib
from datetime import datetime
from enum import Enum

import pandas as pd
import streamlit as st

from app import services
from app.config import monate, monate_kurz
from app.formatting import fmt_number
from engine import (
    AnlagenTyp,
    CapexBreakdown,
    CapexPosition,
    DirektvermarktungsModus,
    NegativeStundenModus,
    NegativeStundenRegel,
    OpexItem,
    PachtModus,
    PraemienModell,
    PVProject,
    TaxModus,
    TilgungsArt,
    ZinsMethode,
)
from engine.io_aurora import szenario_auswahl
from engine.models import (
    EINSPEISEKURVEN_JE_BAUFORM,
    Projektannahmen,
    pruefe_positionsname,
)
from texte import txt


def _namensfehler(eintraege: list[dict]) -> str | None:
    """Erste unbrauchbare Bezeichnung als Klartextmeldung, sonst None.

    Ohne diese Vorpruefung wuerde eine reservierte Bezeichnung erst beim
    Aufbau des Modells als Validierungsfehler auffliegen - der Nutzer
    saehe eine Streamlit-Fehlerseite statt eines Hinweises am Formular.
    """
    for eintrag in eintraege:
        try:
            pruefe_positionsname(eintrag["Position"])
        except ValueError:
            return txt(
                "oberflaeche.formular_zusatz_name_unzulaessig",
                name=eintrag["Position"],
            )
    return None


def _bereinige_positionen(tabelle: pd.DataFrame) -> list[dict]:
    """Editorzeilen in eine Liste verwertbarer Positionen ueberfuehren.

    Der dynamische Editor liefert auch die Zeile, die der Nutzer angelegt,
    aber noch nicht ausgefuellt hat. Zeilen ohne Bezeichnung entfallen
    deshalb; ein fehlender Betrag zaehlt als 0.
    """
    eintraege: list[dict] = []
    for _, zeile in tabelle.iterrows():
        name = str(zeile["Position"] or "").strip()
        if not name:
            continue
        wert = zeile["Wert"]
        eintraege.append(
            {"Position": name, "Wert": float(wert) if pd.notna(wert) else 0.0}
        )
    return eintraege


def _positionstabelle(
    form_key: str,
    schluessel: str,
    titel: str,
    hilfe: str,
    spalte_wert: str,
    einheit: str,
    vorhandene: list[dict],
    darstellung: str,
) -> list[dict]:
    """Frei benannte Kostenpositionen als dynamische Tabelle.

    Bewusst ein `st.data_editor` mit `num_rows="dynamic"` statt einzelner
    Eingabefelder mit "+"-Knopf: Der Editor bleibt ueber alle Durchlaeufe
    EIN Widget mit stabilem Key und fuehrt die Zeilen als Daten. Widgets,
    die zwischen zwei Durchlaeufen erscheinen und verschwinden, sind in
    Streamlit ein bekanntes Risikomuster (siehe Modulkopf).

    darstellung="popover" (Parameterspalte): Die Tabelle steht hinter
    einem Popover, davor nur eine Zusammenfassung. Zusatzpositionen sind
    der Ausnahmefall - in der schmalen Spalte kostete die Tabelle mehr
    Platz, als sie im Alltag wert ist. Ein Popover ist dafuer das
    richtige Mittel und kein Schalter: Sein Inhalt wird bei JEDEM
    Durchlauf ausgefuehrt, das Widget existiert also auch zugeklappt
    weiter. Der frueher benutzte Schalter erzeugte den Editor beim
    Aufklappen und entfernte ihn beim Zuklappen - unfertige Zeilen
    gingen dabei verloren.

    darstellung="offen": Tabelle ohne eigene Huelle - fuer den Fall,
    dass sie bereits IN einem Popover steht (Popover lassen sich nicht
    schachteln).

    darstellung="schalter" (Neuanlage): unveraendert ein Schalter, der
    die Tabelle bei Bedarf einblendet - im breiten Formular ist Platz,
    und dort wird nicht im Sekundentakt gerechnet.

    Rueckgabe: bereinigte Liste - Zeilen ohne Bezeichnung entfallen,
    Betraege ohne Wert zaehlen als 0 (siehe _bereinige_positionen).
    """
    def editor():
        st.caption(hilfe)
        return st.data_editor(
            pd.DataFrame(vorhandene or [], columns=["Position", "Wert"]),
            width="stretch", hide_index=True, num_rows="dynamic",
            key=f"{form_key}_{schluessel}",
            column_config={
                "Position": st.column_config.TextColumn(
                    txt("oberflaeche.formular_zusatz_spalte_position"),
                ),
                "Wert": st.column_config.NumberColumn(
                    spalte_wert, min_value=0.0
                ),
            },
        )

    if darstellung == "offen":
        st.markdown(f"**{titel}**")
        return _bereinige_positionen(editor())

    if darstellung == "schalter":
        # Neuanlage: unveraendert ein Schalter, standardmaessig
        # zugeklappt. Sind bereits Positionen hinterlegt, startet er
        # eingeschaltet - sonst waeren sie beim Bearbeiten nicht
        # auffindbar. Zuklappen loescht nichts.
        schalter_key = f"{form_key}_{schluessel}_anzeigen"
        if schalter_key not in st.session_state:
            st.session_state[schalter_key] = bool(vorhandene)
        st.toggle(titel, key=schalter_key, help=hilfe)
        if not st.session_state[schalter_key]:
            return list(vorhandene)
        return _bereinige_positionen(editor())

    st.caption(
        txt("oberflaeche.formular_zusatz_zusammenfassung",
            titel=titel, anzahl=len(vorhandene),
            summe=fmt_number(sum(z["Wert"] for z in vorhandene), 0),
            einheit=einheit)
        if vorhandene
        else txt("oberflaeche.formular_zusatz_leer", titel=titel)
    )
    with st.popover(txt("oberflaeche.formular_zusatz_bearbeiten"),
                    width="stretch", help=hilfe):
        st.markdown(f"**{titel}**")
        tabelle = editor()
    return _bereinige_positionen(tabelle)


def _pacht_wertfeld(
    ziel, form_key: str, existing, modus, einheit: str | None,
    flaeche_ha: float | None, nennleistung_kwp: float,
    mode_changed: bool, umsatzbeteiligung_pct: float,
) -> tuple[float, float]:
    """Der Pachtwert selbst - je nach Modus in €/ha, €/kWp oder Prozent.

    Rueckgabe: (pacht_eur_kwp_jahr, umsatzbeteiligung_pct). Das Modell
    fuehrt die Pacht immer in €/kWp/Jahr; die €/ha-Eingabe wird ueber
    die Projektflaeche umgerechnet.
    """
    if modus == PachtModus.UMSATZBETEILIGUNG:
        pct_key = f"{form_key}_pacht_umsatz_pct"
        if mode_changed or pct_key not in st.session_state:
            st.session_state[pct_key] = round(umsatzbeteiligung_pct * 100, 2)
        anteil = ziel.number_input(
            txt("oberflaeche.formular_pacht_umsatzbeteiligung_label"),
            min_value=0.0, max_value=100.0, step=0.1, key=pct_key,
            help=txt("oberflaeche.formular_pacht_umsatzbeteiligung_hilfe"),
        ) / 100
        # Bleibt fuer eine eventuelle spaetere Rueckschaltung auf FIX als
        # sinnvoller Vorschlag erhalten statt auf 0 zu fallen.
        return (existing.pacht_eur_kwp_jahr if existing else 4.0), anteil

    if einheit == "€/ha/Jahr":
        pacht_ha_key = f"{form_key}_pacht_ha"
        if mode_changed or pacht_ha_key not in st.session_state:
            # Zwei Nachkommastellen: Auf ganze Euro gerundet wich der
            # zurueckgerechnete €/kWp-Wert so weit ab, dass die Seite
            # eine Aenderung meldete, die niemand vorgenommen hatte.
            st.session_state[pacht_ha_key] = (
                round(
                    existing.pacht_eur_kwp_jahr * existing.nennleistung_kwp
                    / flaeche_ha,
                    2,
                )
                if existing and flaeche_ha
                else 500.0
            )
        pacht_eur_ha = ziel.number_input(
            "Pacht (€/ha/Jahr)", min_value=0.0, step=10.0, key=pacht_ha_key,
        )
        return (
            pacht_eur_ha * flaeche_ha / nennleistung_kwp
            if nennleistung_kwp and flaeche_ha
            else 0.0
        ), umsatzbeteiligung_pct

    pacht_kwp_key = f"{form_key}_pacht_kwp"
    if mode_changed or pacht_kwp_key not in st.session_state:
        st.session_state[pacht_kwp_key] = (
            existing.pacht_eur_kwp_jahr if existing else 4.0
        )
    return ziel.number_input(
        "Pacht (€/kWp/Jahr)", min_value=0.0, step=0.1, key=pacht_kwp_key,
    ), umsatzbeteiligung_pct


def _abschnitt(im_popover: bool, knopf: str, hilfe: str):
    """Ein Block, der in der Live-Spalte hinter einem Popover steht und
    im Anlageformular offen.

    Gibt einen Kontextmanager zurueck - der Aufrufer schreibt seinen
    Inhalt in beiden Faellen gleich. Ein Popover ist hier das richtige
    Mittel und kein Schalter: Sein Inhalt wird bei JEDEM Durchlauf
    ausgefuehrt, die Widgets existieren also auch zugeklappt weiter und
    behalten ihren Zustand.
    """
    if not im_popover:
        return contextlib.nullcontext()
    return st.popover(knopf, width="stretch", help=hilfe)


#: Rueckfall der EPC-Vorbelegung je Anlagentyp in €/kWp. Gepflegt wird sie
#: in den globalen Annahmen (epc_eur_kwp_vorschlag_je_anlagentyp); diese
#: Werte greifen nur, wenn dort ein Anlagentyp fehlt.
EPC_DEFAULT_EUR_KWP = {"Agri-PV": 520.0, "Konventionell": 430.0}


# ---------------------------------------------------------------------------
# Erbfelder - "leer heisst: folgt der Vorgabe"
# ---------------------------------------------------------------------------
# Jeder Parameter der globalen Annahmen laesst sich im Projekt
# ueberschreiben (siehe engine/models.py::Projektannahmen). Entscheidend
# fuer die Bedienung ist, dass daraus KEIN zweites Bedienelement je Feld
# wird - ein "Abweichen?"-Schalter neben jedem Wert haette die Zahl der
# Bedienelemente verdoppelt. Stattdessen traegt das Feld selbst beide
# Zustaende:
#
#   Zahlen:   ein leeres Zahlenfeld, der Platzhalter nennt die Vorgabe.
#             Leeren heisst zurueck zur Vorgabe.
#   Auswahl:  eine zusaetzliche erste Option "Vorgabe (Annuität)". Sie
#             ist einem grauen Platzhalter vorzuziehen, weil sie den
#             geerbten Wert MITLIEST und sich immer wieder waehlen
#             laesst - ein Selectbox-Platzhalter ist nach der ersten
#             Wahl nicht mehr erreichbar.
#   Ja/Nein:  dieselbe Loesung mit drei Optionen.


def _vorgabe_label(wert) -> str:
    """Beschriftung der Vorgabe-Option: "Vorgabe (Annuität)"."""
    return txt("oberflaeche.erbfeld_vorgabe", wert=_lesbar(wert))


def _lesbar(wert) -> str:
    """Ein Wert so, wie er in der Oberflaeche steht."""
    if isinstance(wert, bool):
        return txt("oberflaeche.projekt_ja" if wert else "oberflaeche.projekt_nein")
    if isinstance(wert, Enum):
        # Fehlt die Uebersetzung, gibt txt() den Schluessel zurueck - dann
        # ist der Rohwert die bessere Anzeige als "oberflaeche.wert_...".
        schluessel = f"oberflaeche.wert_{wert.value}"
        beschriftung = txt(schluessel)
        return wert.value if beschriftung == schluessel else beschriftung
    if isinstance(wert, float):
        return fmt_number(wert, 2)
    return str(wert)


def _erbe_zahl(
    ziel, form_key: str, schluessel: str, label: str, vorgabe: float,
    gesetzt: float | None, *, faktor: float = 1.0, nachkomma: int = 2,
    hilfe: str | None = None, **kw,
) -> float | None:
    """Ein Zahlenfeld, das leer bleiben darf.

    `faktor` rechnet zwischen Modell und Anzeige um (Anteile werden als
    Prozent eingegeben). Rueckgabe ist der MODELLWERT oder None fuer
    "folgt der Vorgabe".
    """
    wert = ziel.number_input(
        label,
        value=None if gesetzt is None else gesetzt * faktor,
        placeholder=txt("oberflaeche.erbfeld_platzhalter",
                        wert=fmt_number(vorgabe * faktor, nachkomma)),
        key=f"{form_key}_{schluessel}", help=hilfe, **kw,
    )
    return None if wert is None else float(wert) / faktor


def _erbe_ganzzahl(
    ziel, form_key: str, schluessel: str, label: str, vorgabe: int,
    gesetzt: int | None, *, hilfe: str | None = None, **kw,
) -> int | None:
    """Wie _erbe_zahl, nur ganzzahlig (Jahre)."""
    wert = ziel.number_input(
        label, value=gesetzt, step=1,
        placeholder=txt("oberflaeche.erbfeld_platzhalter",
                        wert=fmt_number(vorgabe, 0)),
        key=f"{form_key}_{schluessel}", help=hilfe, **kw,
    )
    return None if wert is None else int(wert)


def _erbe_wahl(
    ziel, form_key: str, schluessel: str, label: str, typ,
    vorgabe, gesetzt, *, hilfe: str | None = None,
):
    """Eine Auswahl mit vorangestellter Vorgabe-Option."""
    optionen = [_vorgabe_label(vorgabe)] + [_lesbar(w) for w in typ]
    werte = [None] + list(typ)
    gewaehlt = ziel.selectbox(
        label, optionen,
        index=werte.index(gesetzt) if gesetzt in werte else 0,
        key=f"{form_key}_{schluessel}", help=hilfe,
    )
    return werte[optionen.index(gewaehlt)]


def _erbe_janein(
    ziel, form_key: str, schluessel: str, label: str,
    vorgabe: bool, gesetzt: bool | None, *, hilfe: str | None = None,
) -> bool | None:
    """Ein dreiwertiges Ja/Nein - der dritte Wert ist die Vorgabe."""
    ja = txt("oberflaeche.projekt_ja")
    nein = txt("oberflaeche.projekt_nein")
    optionen = [_vorgabe_label(vorgabe), ja, nein]
    werte = [None, True, False]
    gewaehlt = ziel.radio(
        label, optionen, index=werte.index(gesetzt),
        key=f"{form_key}_{schluessel}", help=hilfe,
    )
    return werte[optionen.index(gewaehlt)]


#: Was ein Land als Paket festlegt - dieselben Zuordnungen wie beim
#: globalen Schalter (app/views/assumptions.py::_wechsle_markt_system).
LAENDER: dict[str, dict] = {
    "Österreich": {
        "zinsmethode": ZinsMethode.OESTERREICH,
        "tax_modus": TaxModus.AFA_KOERPERSCHAFTSTEUER,
        "praemien_modell": PraemienModell.EAG_TOLERANZBAND,
        "negative_stunden_regel": NegativeStundenRegel.SECHS_STUNDEN,
    },
    "Deutschland": {
        "zinsmethode": ZinsMethode.DEUTSCH,
        "tax_modus": TaxModus.GEWERBESTEUER_DE,
        "praemien_modell": PraemienModell.EINSEITIG_CFD,
        "negative_stunden_regel": NegativeStundenRegel.EINE_STUNDE,
    },
}


def _land_schalter(form_key: str, global_assumptions, spaltig: bool) -> None:
    """Setzt Zinsmethode, Steuermodell, Praemienmodell und
    Negativstunden-Regel in einem Zug.

    Der Knopf schreibt die Werte in den Zustand der Erbfelder, BEVOR
    diese weiter unten im selben Durchlauf entstehen - dieselbe Technik
    wie beim Einheiten-Umschalter der Investkosten (siehe Modulkopf).
    Danach zeigen die vier Felder ihre Werte und lassen sich einzeln
    weiter aendern; der Schalter haelt keinen eigenen Zustand.
    """
    spalten = st.columns(len(LAENDER)) if spaltig else st.columns(
        [1] * len(LAENDER) + [3]
    )
    for spalte, (land, felder) in zip(spalten, LAENDER.items(), strict=False):
        with spalte:
            if st.button(land, key=f"{form_key}_land_{land}", width="stretch",
                         help=txt("oberflaeche.formular_land_hilfe")):
                for feld, wert in felder.items():
                    # Der Zustand der Erbfelder ist die Beschriftung der
                    # gewaehlten Option, nicht der Wert selbst.
                    st.session_state[f"{form_key}_abw_{feld}"] = _lesbar(wert)


#: Beschriftung je Abweichungsfeld - fuer die Zaehlzeile unter dem Block.
_ABWEICHUNG_LABEL: dict[str, str] = {
    "kreditlaufzeit_jahre": "oberflaeche.formular_kreditlaufzeit_label",
    "tilgungsart": "oberflaeche.formular_tilgungsart_label",
    "tilgungsfreies_anlaufjahr": "oberflaeche.formular_anlaufjahr_label",
    "zinsmethode": "oberflaeche.formular_zinsmethode_label",
    "dscr_cash_trap": "oberflaeche.formular_dscr_cash_trap_label",
    "dscr_event_of_default": "oberflaeche.formular_dscr_default_label",
    "tax_modus": "oberflaeche.formular_tax_modus_label",
    "steuersatz_pct": "oberflaeche.formular_steuersatz_label",
    "afa_nutzungsdauer_jahre": "oberflaeche.formular_afa_label",
    "freibetrag_eur": "oberflaeche.formular_freibetrag_label",
    "gewerbesteuer_hebesatz_pct": "oberflaeche.formular_gewst_hebesatz_label",
    "gewerbesteuer_freibetrag_eur": "oberflaeche.formular_gewst_freibetrag_label",
    "verlustvortrag_verrechnungsgrenze_pct": (
        "oberflaeche.formular_verlustvortrag_label"
    ),
    "kosten_inflation_pct_pa": "oberflaeche.formular_kosteninflation_label",
    "praemien_modell": "oberflaeche.formular_praemienmodell_label",
    "eag_foerderdauer_jahre": "oberflaeche.formular_foerderdauer_label",
    "eag_rueckzahlung_ab_mw": "oberflaeche.formular_rueckzahlung_ab_label",
    "eag_rueckzahlung_toleranzband_pct": "oberflaeche.formular_toleranzband_label",
    "eag_rueckzahlung_anteil_pct": (
        "oberflaeche.formular_rueckzahlung_anteil_label"
    ),
    "negative_stunden_regel": "oberflaeche.formular_negativregel_label",
    "negative_stunden_modus": "oberflaeche.formular_negativmodus_label",
    "negative_stunden_gewichtung_pct": (
        "oberflaeche.formular_negativgewichtung_label"
    ),
    "direktvermarktung_modus": "oberflaeche.formular_dv_modus_label",
    "direktvermarktung_pct_marktwert": "oberflaeche.formular_dv_pct_label",
    "marktpreis_inflation_pct_pa": "oberflaeche.formular_marktinflation_label",
    "marktpreis_inflation_basisjahr": (
        "oberflaeche.formular_marktinflation_basisjahr_label"
    ),
    "degradation_pct_pa": "oberflaeche.formular_degradation_label",
    "sicherheitsabschlag_pct": "oberflaeche.formular_sicherheitsabschlag_label",
    "betriebsdauer_jahre": "oberflaeche.formular_betriebsdauer_label",
}

#: Abweichungsfelder, die die Maske noch nicht anbietet. Sie werden
#: unveraendert aus dem gespeicherten Projekt uebernommen - sonst
#: loeschte jedes Speichern eine von Hand in der YAML gepflegte
#: Abweichung stillschweigend.
_NOCH_NICHT_IN_DER_MASKE: tuple[str, ...] = tuple(
    feld for feld in Projektannahmen.model_fields
    if feld not in _ABWEICHUNG_LABEL and feld != "opex_standard_eur_kwp"
)


def _beschriftungen(werte: dict) -> list[str]:
    """Die Beschriftungen der tatsaechlich gesetzten Felder."""
    return [
        _kurzlabel(txt(_ABWEICHUNG_LABEL[feld]))
        for feld, wert in werte.items()
        if wert is not None and feld in _ABWEICHUNG_LABEL
    ]


def _kurzlabel(label: str) -> str:
    """Beschriftung ohne Einheitenklammer - in der Zaehlzeile stehen
    Namen, keine Einheiten."""
    return label.split(" (")[0]


def _kreditvertrag_felder(
    form_key: str, global_assumptions, abweichung, spaltig: bool
) -> dict:
    """Die Konditionen des Darlehens - alles mit Vorgabe.

    Eigenkapitalanteil und Zins stehen offen darueber; Laufzeit,
    Tilgungsart, Anlaufjahr, Zinsmethode und die beiden DSCR-Schwellen
    sind Vertragsdetails, die einmal feststehen und danach nicht mehr
    angefasst werden.
    """
    st.markdown(f"**{txt('oberflaeche.formular_kreditvertrag_knopf')}**")
    st.caption(txt("oberflaeche.erbfeld_hinweis"))
    links, rechts = (st.columns(2) if spaltig else st.columns(2))
    return {
        "kreditlaufzeit_jahre": _erbe_ganzzahl(
            links, form_key, "abw_kreditlaufzeit_jahre",
            txt("oberflaeche.formular_kreditlaufzeit_label"),
            global_assumptions.kreditlaufzeit_jahre,
            abweichung.kreditlaufzeit_jahre, min_value=1,
        ),
        "tilgungsart": _erbe_wahl(
            rechts, form_key, "abw_tilgungsart",
            txt("oberflaeche.formular_tilgungsart_label"), TilgungsArt,
            global_assumptions.tilgungsart, abweichung.tilgungsart,
        ),
        "tilgungsfreies_anlaufjahr": _erbe_janein(
            st, form_key, "abw_tilgungsfreies_anlaufjahr",
            txt("oberflaeche.formular_anlaufjahr_label"),
            global_assumptions.tilgungsfreies_anlaufjahr,
            abweichung.tilgungsfreies_anlaufjahr,
            hilfe=txt("oberflaeche.formular_anlaufjahr_hilfe"),
        ),
        "zinsmethode": _erbe_wahl(
            st, form_key, "abw_zinsmethode",
            txt("oberflaeche.formular_zinsmethode_label"), ZinsMethode,
            global_assumptions.zinsmethode, abweichung.zinsmethode,
        ),
        "dscr_cash_trap": _erbe_zahl(
            links, form_key, "abw_dscr_cash_trap",
            txt("oberflaeche.formular_dscr_cash_trap_label"),
            global_assumptions.dscr_cash_trap, abweichung.dscr_cash_trap,
            min_value=0.0, step=0.05,
        ),
        "dscr_event_of_default": _erbe_zahl(
            rechts, form_key, "abw_dscr_event_of_default",
            txt("oberflaeche.formular_dscr_default_label"),
            global_assumptions.dscr_event_of_default,
            abweichung.dscr_event_of_default, min_value=0.0, step=0.05,
        ),
    }


def _steuer_felder(
    form_key: str, global_assumptions, abweichung, spaltig: bool
) -> dict:
    """Steuermodell und seine Parameter - alles mit Vorgabe.

    Die Felder der jeweils anderen Steuerart bleiben sichtbar statt zu
    verschwinden: Widgets, die zwischen Durchlaeufen kommen und gehen,
    sind in Streamlit ein Risikomuster (siehe Modulkopf), und man soll
    sehen, welche Angaben ein Wechsel braucht.
    """
    st.markdown(f"**{txt('oberflaeche.formular_steuern_titel')}**")
    st.caption(txt("oberflaeche.erbfeld_hinweis"))
    links, rechts = st.columns(2)
    werte = {
        "tax_modus": _erbe_wahl(
            st, form_key, "abw_tax_modus",
            txt("oberflaeche.formular_tax_modus_label"), TaxModus,
            global_assumptions.tax_modus, abweichung.tax_modus,
        ),
        "steuersatz_pct": _erbe_zahl(
            links, form_key, "abw_steuersatz_pct",
            txt("oberflaeche.formular_steuersatz_label"),
            global_assumptions.steuersatz_pct, abweichung.steuersatz_pct,
            faktor=100.0, nachkomma=1, min_value=0.0, max_value=100.0, step=1.0,
        ),
        "afa_nutzungsdauer_jahre": _erbe_ganzzahl(
            rechts, form_key, "abw_afa_nutzungsdauer_jahre",
            txt("oberflaeche.formular_afa_label"),
            global_assumptions.afa_nutzungsdauer_jahre or 0,
            abweichung.afa_nutzungsdauer_jahre, min_value=1,
        ),
        "freibetrag_eur": _erbe_zahl(
            links, form_key, "abw_freibetrag_eur",
            txt("oberflaeche.formular_freibetrag_label"),
            global_assumptions.freibetrag_eur, abweichung.freibetrag_eur,
            nachkomma=0, min_value=0.0, step=500.0,
        ),
        "verlustvortrag_verrechnungsgrenze_pct": _erbe_zahl(
            rechts, form_key, "abw_verlustvortrag_verrechnungsgrenze_pct",
            txt("oberflaeche.formular_verlustvortrag_label"),
            global_assumptions.verlustvortrag_verrechnungsgrenze_pct,
            abweichung.verlustvortrag_verrechnungsgrenze_pct,
            faktor=100.0, nachkomma=0, min_value=0.0, max_value=100.0, step=5.0,
        ),
        "gewerbesteuer_hebesatz_pct": _erbe_zahl(
            links, form_key, "abw_gewerbesteuer_hebesatz_pct",
            txt("oberflaeche.formular_gewst_hebesatz_label"),
            global_assumptions.gewerbesteuer_hebesatz_pct,
            abweichung.gewerbesteuer_hebesatz_pct,
            nachkomma=0, min_value=0.0, step=10.0,
        ),
        "gewerbesteuer_freibetrag_eur": _erbe_zahl(
            rechts, form_key, "abw_gewerbesteuer_freibetrag_eur",
            txt("oberflaeche.formular_gewst_freibetrag_label"),
            global_assumptions.gewerbesteuer_freibetrag_eur,
            abweichung.gewerbesteuer_freibetrag_eur,
            nachkomma=0, min_value=0.0, step=500.0,
        ),
    }
    # Der AfA-Modus braucht eine Nutzungsdauer. Weicht das Projekt auf
    # ihn ab, ohne dass global eine hinterlegt waere, faellt die
    # Rechnung sonst erst in der Steuerfunktion um.
    braucht_afa = (
        werte["tax_modus"] or global_assumptions.tax_modus
    ) in (TaxModus.AFA_KOERPERSCHAFTSTEUER, TaxModus.GEWERBESTEUER_DE)
    if (braucht_afa and werte["afa_nutzungsdauer_jahre"] is None
            and not global_assumptions.afa_nutzungsdauer_jahre):
        st.warning(txt("oberflaeche.formular_afa_fehlt"))
    return werte


def _foerdermodell_felder(
    form_key: str, global_assumptions, abweichung
) -> dict:
    """Das Regelwerk, unter dem dieses Projekt verguetet wird.

    Praemienmodell und Foerderdauer haengen am Land und am Jahrgang der
    Ausschreibung, die Negativstunden-Regel an der Rechtslage, die
    Direktvermarktung am Dienstleistervertrag. Alles Groessen, die man
    einmal setzt - deshalb hinter einem Popover und nicht offen neben
    dem Zuschlagswert.
    """
    st.markdown(f"**{txt('oberflaeche.formular_foerdermodell_knopf')}**")
    st.caption(txt("oberflaeche.erbfeld_hinweis"))
    links, rechts = st.columns(2)
    werte = {
        "praemien_modell": _erbe_wahl(
            st, form_key, "abw_praemien_modell",
            txt("oberflaeche.formular_praemienmodell_label"), PraemienModell,
            global_assumptions.praemien_modell, abweichung.praemien_modell,
        ),
        "eag_foerderdauer_jahre": _erbe_ganzzahl(
            links, form_key, "abw_eag_foerderdauer_jahre",
            txt("oberflaeche.formular_foerderdauer_label"),
            global_assumptions.eag_foerderdauer_jahre,
            abweichung.eag_foerderdauer_jahre, min_value=1,
        ),
        "eag_rueckzahlung_ab_mw": _erbe_zahl(
            rechts, form_key, "abw_eag_rueckzahlung_ab_mw",
            txt("oberflaeche.formular_rueckzahlung_ab_label"),
            global_assumptions.eag_rueckzahlung_ab_mw,
            abweichung.eag_rueckzahlung_ab_mw,
            nachkomma=1, min_value=0.0, step=0.5,
        ),
        "eag_rueckzahlung_toleranzband_pct": _erbe_zahl(
            links, form_key, "abw_eag_rueckzahlung_toleranzband_pct",
            txt("oberflaeche.formular_toleranzband_label"),
            global_assumptions.eag_rueckzahlung_toleranzband_pct,
            abweichung.eag_rueckzahlung_toleranzband_pct,
            faktor=100.0, nachkomma=0, min_value=0.0, step=5.0,
        ),
        "eag_rueckzahlung_anteil_pct": _erbe_zahl(
            rechts, form_key, "abw_eag_rueckzahlung_anteil_pct",
            txt("oberflaeche.formular_rueckzahlung_anteil_label"),
            global_assumptions.eag_rueckzahlung_anteil_pct,
            abweichung.eag_rueckzahlung_anteil_pct,
            faktor=100.0, nachkomma=0, min_value=0.0, max_value=100.0, step=1.0,
        ),
        "negative_stunden_regel": _erbe_wahl(
            st, form_key, "abw_negative_stunden_regel",
            txt("oberflaeche.formular_negativregel_label"),
            NegativeStundenRegel, global_assumptions.negative_stunden_regel,
            abweichung.negative_stunden_regel,
        ),
        "negative_stunden_modus": _erbe_wahl(
            st, form_key, "abw_negative_stunden_modus",
            txt("oberflaeche.formular_negativmodus_label"),
            NegativeStundenModus, global_assumptions.negative_stunden_modus,
            abweichung.negative_stunden_modus,
        ),
        "negative_stunden_gewichtung_pct": _erbe_zahl(
            links, form_key, "abw_negative_stunden_gewichtung_pct",
            txt("oberflaeche.formular_negativgewichtung_label"),
            global_assumptions.negative_stunden_gewichtung_pct,
            abweichung.negative_stunden_gewichtung_pct,
            faktor=100.0, nachkomma=0, min_value=0.0, max_value=100.0, step=5.0,
        ),
        "direktvermarktung_pct_marktwert": _erbe_zahl(
            rechts, form_key, "abw_direktvermarktung_pct_marktwert",
            txt("oberflaeche.formular_dv_pct_label"),
            global_assumptions.direktvermarktung_pct_marktwert,
            abweichung.direktvermarktung_pct_marktwert,
            faktor=100.0, nachkomma=1, min_value=0.0, max_value=100.0, step=1.0,
        ),
        "direktvermarktung_modus": _erbe_wahl(
            st, form_key, "abw_direktvermarktung_modus",
            txt("oberflaeche.formular_dv_modus_label"),
            DirektvermarktungsModus,
            global_assumptions.direktvermarktung_modus,
            abweichung.direktvermarktung_modus,
        ),
        "marktpreis_inflation_pct_pa": _erbe_zahl(
            links, form_key, "abw_marktpreis_inflation_pct_pa",
            txt("oberflaeche.formular_marktinflation_label"),
            global_assumptions.marktpreis_inflation_pct_pa,
            abweichung.marktpreis_inflation_pct_pa,
            faktor=100.0, nachkomma=1, min_value=0.0, step=0.25,
        ),
        "marktpreis_inflation_basisjahr": _erbe_ganzzahl(
            rechts, form_key, "abw_marktpreis_inflation_basisjahr",
            txt("oberflaeche.formular_marktinflation_basisjahr_label"),
            global_assumptions.marktpreis_inflation_basisjahr,
            abweichung.marktpreis_inflation_basisjahr,
            min_value=2000, max_value=2100,
        ),
    }
    return werte


def _ertrag_felder(form_key: str, global_assumptions, abweichung) -> dict:
    """Degradation, Sicherheitsabschlag und Betrachtungsdauer.

    Sie haengen an Modul, Ertragsgutachten und Pachtvertrag - alles
    projektspezifisch, bisher aber nur global einstellbar.
    """
    st.markdown(f"**{txt('oberflaeche.formular_ertrag_knopf')}**")
    st.caption(txt("oberflaeche.erbfeld_hinweis"))
    links, rechts = st.columns(2)
    return {
        "degradation_pct_pa": _erbe_zahl(
            links, form_key, "abw_degradation_pct_pa",
            txt("oberflaeche.formular_degradation_label"),
            global_assumptions.degradation_pct_pa,
            abweichung.degradation_pct_pa,
            faktor=100.0, nachkomma=2, min_value=0.0, step=0.05,
        ),
        "sicherheitsabschlag_pct": _erbe_zahl(
            rechts, form_key, "abw_sicherheitsabschlag_pct",
            txt("oberflaeche.formular_sicherheitsabschlag_label"),
            global_assumptions.sicherheitsabschlag_pct,
            abweichung.sicherheitsabschlag_pct,
            faktor=100.0, nachkomma=1, min_value=0.0, max_value=100.0, step=0.5,
        ),
        "betriebsdauer_jahre": _erbe_ganzzahl(
            st, form_key, "abw_betriebsdauer_jahre",
            txt("oberflaeche.formular_betriebsdauer_label"),
            global_assumptions.betriebsdauer_jahre,
            abweichung.betriebsdauer_jahre, min_value=1,
        ),
    }


def _standard_opex_tabelle(
    form_key: str, global_assumptions, abweichung
) -> dict[str, float]:
    """Die globalen Standardpositionen mit den Werten dieses Projekts.

    Frueh im Projekt sind das Erfahrungswerte, mit zunehmender Reife
    werden daraus Angebote - und die unterscheiden sich von Standort zu
    Standort erheblich. Bis v5.16 liessen sie sich nur global pflegen;
    wer eine Position anpassen wollte, musste sie als Zusatzposition mit
    Differenzbetrag nachbilden.

    Eine Tabelle statt eines Feldes je Position: fuenf Zahlenfelder
    untereinander kosteten in der schmalen Spalte mehr Platz, als sie
    wert sind, und die Spalte "Vorgabe" daneben ist genau die
    Information, die man beim Eintragen braucht.

    Rueckgabe: nur die tatsaechlich abweichenden Positionen.
    """
    st.markdown(f"**{txt('oberflaeche.formular_opex_standard_titel')}**")
    st.caption(txt("oberflaeche.formular_opex_standard_hilfe"))
    eigen = abweichung.opex_standard_eur_kwp
    tabelle = st.data_editor(
        pd.DataFrame([
            {
                "Position": item.name,
                "Vorgabe": item.basiswert_eur_kwp,
                "Projekt": eigen.get(item.name),
            }
            for item in global_assumptions.opex_standard
        ], columns=["Position", "Vorgabe", "Projekt"]),
        width="stretch", hide_index=True, num_rows="fixed",
        key=f"{form_key}_abw_opex_standard",
        column_config={
            "Position": st.column_config.TextColumn(
                txt("oberflaeche.formular_zusatz_spalte_position"), disabled=True,
            ),
            # Die Vorgabe steht daneben, ist aber nicht hier zu aendern -
            # dafuer sind die Globalen Annahmen da.
            "Vorgabe": st.column_config.NumberColumn(
                txt("oberflaeche.formular_opex_spalte_vorgabe"),
                format="%.2f", disabled=True,
            ),
            "Projekt": st.column_config.NumberColumn(
                txt("oberflaeche.formular_opex_spalte_projekt"),
                format="%.2f", min_value=0.0,
            ),
        },
    )
    return {
        str(zeile["Position"]): float(zeile["Projekt"])
        for _, zeile in tabelle.iterrows()
        if pd.notna(zeile["Projekt"])
    }


def _abweichungszeile(abweichungen: list[str]) -> None:
    """Zeigt unter einem Block, ob und worin er von der Vorgabe abweicht.

    Ohne sie faellt in einem halben Jahr niemandem mehr auf, dass dieses
    Projekt einer spaeteren Aenderung der globalen Annahmen nicht mehr
    folgt - das ist die eigentliche Gefahr an ueberschreibbaren
    Vorgaben.
    """
    if not abweichungen:
        st.caption(txt("oberflaeche.erbfeld_alles_vorgabe"))
        return
    st.caption(txt(
        "oberflaeche.erbfeld_abweichungen",
        anzahl=len(abweichungen),
        felder=", ".join(abweichungen),
    ))


@contextlib.contextmanager
def _formularrahmen(form_key: str, mit_formular: bool):
    """st.form nur dort, wo auf ein Absenden gewartet wird."""
    if mit_formular:
        with st.form(form_key, clear_on_submit=False):
            yield
    else:
        yield


def render_project_form(
    existing: PVProject | None, form_key: str
) -> PVProject | None:
    """Projektmaske in voller Seitenbreite, mit Absenden-Knopf.

    Ohne `existing` = Neuanlage (sinnvolle Defaults), mit `existing` =
    Bearbeiten (vorausgefuellt, gleiche id). Gibt das neue/aktualisierte
    PVProject zurueck, wenn abgeschickt wurde, sonst None.
    """
    return _felder(existing, form_key, spaltig=False, mit_formular=True)


def render_parameter_spalte(
    existing: PVProject | None, form_key: str
) -> PVProject | None:
    """Projektmaske als schmale Spalte neben dem Ergebnis.

    Gibt bei jedem Durchlauf den aktuellen ENTWURF zurueck - er wird
    gerechnet, aber nicht gespeichert. Das Speichern ist ein eigener
    Schritt (siehe app/views/project_page.py), damit sich gefahrlos
    ausprobieren laesst.

    Ohne Stammdaten: Name, Standort und Variantenname sind keine
    What-if-Groessen - man dreht nicht am Projektnamen, um eine Rendite
    zu sehen. Sie stehen im Ueberlaufmenue bzw. in der Variantenleiste
    und werden hier unveraendert aus dem gespeicherten Projekt
    uebernommen.
    """
    return _felder(
        existing, form_key, spaltig=True, mit_formular=False,
        mit_stammdaten=False,
    )


def verwirf_entwurf(form_key: str) -> None:
    """Loescht alle Widget-Zustaende der Parameterspalte.

    Danach lesen die Felder ihre Vorbelegung wieder aus dem gespeicherten
    Projekt - das ist genau die Wirkung von "Verwerfen".
    """
    for schluessel in [s for s in st.session_state if s.startswith(f"{form_key}_")]:
        del st.session_state[schluessel]


def _felder(
    existing: PVProject | None,
    form_key: str,
    *,
    spaltig: bool,
    mit_formular: bool,
    mit_stammdaten: bool = True,
) -> PVProject | None:
    """Gemeinsamer Rumpf beider Darstellungen der Projektmaske.

    spaltig=False  - breite Anordnung mit mehreren Feldern nebeneinander
                     (Neuanlage, volle Seitenbreite).
    spaltig=True   - alles untereinander fuer die schmale Parameterspalte
                     neben dem Ergebnis.
    mit_formular=True  - Eingaben wirken erst beim Absenden (st.form).
    mit_formular=False - jede Aenderung loest einen Rerun aus, und der
                     Entwurf wird bei JEDEM Durchlauf zurueckgegeben. Das
                     ist die Grundlage der sofortigen Neuberechnung neben
                     dem Ergebnis; gespeichert wird davon nichts.
    mit_stammdaten=False - Name, Standort und Variantenname werden nicht
                     zur Eingabe angeboten, sondern unveraendert aus
                     `existing` uebernommen (siehe
                     render_parameter_spalte).
    """

    def spalten(anzahl: int):
        """In der schmalen Spalte gibt es keine Nebeneinander-Anordnung;
        st selbst verhaelt sich wie ein Spaltencontainer."""
        return st.columns(anzahl) if not spaltig else [st] * anzahl

    global_assumptions = services.get_global_assumptions()
    # Die gespeicherten Abweichungen dieses Projekts. Ohne Projekt (Neuanlage)
    # ein leerer Block: Ein neues Projekt folgt in allem der Vorgabe.
    gespeicherte_abweichung = (
        existing.annahmen if existing else Projektannahmen()
    )

    if not mit_stammdaten:
        # Kein Widget, keine Eingabe - die Werte kommen aus dem
        # gespeicherten Projekt und laufen unveraendert in den Entwurf.
        # Ohne `existing` gaebe es nichts zu uebernehmen; diesen Fall
        # gibt es nur bei der Neuanlage, die ihre Stammdaten selbst
        # erfasst.
        name = existing.name if existing else ""
        standort = existing.standort if existing else ""
        variante = existing.variante if existing else ""

    # Der Projektname steht ganz oben - in der schmalen Parameterspalte
    # war er zwischen Investkosten und Pacht praktisch unauffindbar.
    # Bewusst ausserhalb des Formularrahmens: In der Spalte gibt es
    # keinen Absenden-Knopf, der Wert muss sofort in den Entwurf laufen.
    if mit_stammdaten:
        name = st.text_input(
            txt("oberflaeche.formular_name_label"),
            value=existing.name if existing else "",
            placeholder=txt("oberflaeche.formular_name_platzhalter"),
            key=f"{form_key}_name",
            help=txt("oberflaeche.formular_name_hilfe"),
        )
        # Der Standort ist die Kurzbezeichnung fuer Diagramme - die
        # vollstaendige Kennung darueber ist als Punktbeschriftung zu lang.
        standort = st.text_input(
            txt("oberflaeche.formular_standort_label"),
            value=existing.standort if existing else "",
            placeholder=txt("oberflaeche.formular_standort_platzhalter"),
            key=f"{form_key}_standort",
            help=txt("oberflaeche.formular_standort_hilfe"),
        )
        # Der Variantenname macht die Sensitivitaet benennbar. Er darf leer
        # bleiben - das ist der Grundfall des Standorts; die Oberflaeche
        # nennt ihn "Basis".
        variante = st.text_input(
            txt("oberflaeche.formular_variante_label"),
            value=existing.variante if existing else "",
            placeholder=txt("oberflaeche.formular_variante_platzhalter"),
            key=f"{form_key}_variante",
            help=txt("oberflaeche.formular_variante_hilfe"),
        )

    # --- Regelwerk des Standorts ------------------------------------------
    # Zinsmethode, Steuerberechnung und Praemienmodell haengen am Land und
    # wechseln gemeinsam. Sie einzeln in drei verschiedenen Popovern zu
    # suchen, waere die haeufigste Aufgabe zur muehsamsten gemacht -
    # deshalb steht hier ein Schalter, der alle drei auf einmal setzt.
    #
    # Bewusst KEIN eigenes Modellfeld: Der Schalter schreibt die drei
    # Erbfelder und ist danach fertig. Ein gespeichertes "Land" waere
    # eine vierte Wahrheit, die dem Inhalt der drei Felder widersprechen
    # koennte, sobald jemand eines davon einzeln aendert.
    _land_schalter(form_key, global_assumptions, spaltig)

    st.markdown("**Technische Anlagenparameter**")
    col1, col2 = spalten(2)
    nennleistung_kwp = col1.number_input(
        "Leistung (kWp)", min_value=0.0,
        value=(existing.nennleistung_kwp if existing
               else global_assumptions.nennleistung_kwp_vorschlag),
        step=100.0, key=f"{form_key}_leistung_live",
    )
    vollbenutzungsstunden = col2.number_input(
        "Vollbenutzungsstunden (kWh/kWp)", min_value=0.0,
        value=(existing.vollbenutzungsstunden_kwh_kwp if existing
               else global_assumptions.vollbenutzungsstunden_kwh_kwp_vorschlag),
        step=10.0, key=f"{form_key}_vbh_live",
    )
    # Die Bauform ist der zweite technische Grundzug neben der Leistung:
    # Sie entscheidet ueber die Einspeisekurve UND ueber die
    # Marktwertkurve des gewaehlten Preisszenarios. Frueher steckte sie
    # im Szenarionamen ("Aurora Q3/26 · Pult · Central") - dort las sie
    # sich wie eine Marktmeinung, obwohl sie eine Eigenschaft der Anlage
    # ist.
    bauform_options = list(EINSPEISEKURVEN_JE_BAUFORM)
    bauform_index = (
        bauform_options.index(existing.bauform)
        if existing and existing.bauform in bauform_options
        else 0
    )
    bauform = st.radio(
        txt("oberflaeche.formular_bauform_label"), bauform_options,
        index=bauform_index, horizontal=True, key=f"{form_key}_bauform_live",
        help=txt("oberflaeche.formular_bauform_hilfe"),
    )
    # Der Anlagentyp steht NICHT hier, sondern weiter unten unter
    # "Erloese": Agri-PV gegen konventionell ist eine EAG-Kategorie - sie
    # entscheidet ueber den Zuschlagswert, nicht ueber die Technik. Der
    # EPC-Vorschlag haengt aber an ihm, und die Investkosten kommen
    # frueher. Das Radio traegt einen festen Schluessel und wird bei
    # jedem Durchlauf gerendert; sein Wert steht also ab dem zweiten
    # Durchlauf im Session-State bereit, beim ersten greift die
    # Vorbelegung aus dem Projekt.
    anlagentyp_options = ["Agri-PV", "Konventionell"]
    anlagentyp_key = f"{form_key}_typ_live"
    anlagentyp_index = (
        1 if existing and existing.anlagentyp == AnlagenTyp.KONVENTIONELL else 0
    )
    anlagentyp_label = st.session_state.get(
        anlagentyp_key, anlagentyp_options[anlagentyp_index]
    )

    # Monat und Jahr nebeneinander, auch in der schmalen Spalte: Zwei
    # kurze Felder, die eine Angabe bilden - untereinander kosteten sie
    # doppelt so viel Hoehe, ohne etwas klarer zu machen. Der lange
    # Erklaertext steht als Tooltip am Feld statt als Bildunterschrift;
    # er nahm drei Zeilen ein, ohne beim Ausprobieren gebraucht zu
    # werden.
    if spaltig:
        # Kurze Beschriftungen: "Inbetriebnahme - Monat" bricht in einer
        # halben Spaltenbreite mitten im Wort um. Die Angabe steht als
        # Ueberschrift darueber, die Felder tragen nur noch Monat und
        # Jahr.
        st.caption(txt("oberflaeche.formular_ibn_titel"))
        monat_label = txt("oberflaeche.formular_ibn_kurz_monat")
        jahr_label = txt("oberflaeche.formular_ibn_kurz_jahr")
    else:
        monat_label = txt("oberflaeche.formular_ibn_monat_label")
        jahr_label = txt("oberflaeche.formular_ibn_jahr_label")
    col_ibn1, col_ibn2 = st.columns(2)
    # In der halben Spaltenbreite passt "Dezember" nicht - die Auswahl
    # zeigt dort die dreibuchstabige Kurzform, die ohnehin schon fuer
    # Diagramme gepflegt ist.
    monatsnamen = monate_kurz() if spaltig else monate()
    inbetriebnahme_monat_label = col_ibn1.selectbox(
        monat_label, monatsnamen,
        index=(existing.inbetriebnahme_monat - 1) if existing else 0,
        key=f"{form_key}_ibn_monat_live",
        help=txt("oberflaeche.formular_ibn_monat_hilfe"),
    )
    inbetriebnahme_jahr = col_ibn2.number_input(
        jahr_label, min_value=2000, max_value=2100,
        value=existing.inbetriebnahme_jahr if existing else datetime.now().year + 1,
        step=1, key=f"{form_key}_ibn_jahr_live",
        help=txt("oberflaeche.formular_ibn_monat_hilfe"),
    )
    inbetriebnahme_monat = monatsnamen.index(inbetriebnahme_monat_label) + 1

    ertrag_zeile = st.container()
    with _abschnitt(spaltig,
                    knopf=txt("oberflaeche.formular_ertrag_knopf"),
                    hilfe=txt("oberflaeche.formular_ertrag_hilfe")):
        ertrag = _ertrag_felder(
            form_key, global_assumptions, gespeicherte_abweichung
        )
    with ertrag_zeile:
        _abweichungszeile(_beschriftungen(ertrag))

    def zusatz_capex_tabelle(darstellung: str):
        return _positionstabelle(
            form_key=form_key,
            schluessel="capex_zusatz",
            titel=txt("oberflaeche.formular_capex_zusatz_titel"),
            hilfe=txt("oberflaeche.formular_capex_zusatz_hilfe"),
            spalte_wert=txt("oberflaeche.formular_capex_zusatz_betrag"),
            einheit="€",
            darstellung=darstellung,
            vorhandene=[
                {"Position": z.name, "Wert": z.betrag_eur}
                for z in (existing.capex.zusatzpositionen if existing else [])
            ],
        )

    def zusatz_opex_tabelle(darstellung: str):
        return _positionstabelle(
            form_key=form_key,
            schluessel="opex_zusatz",
            titel=txt("oberflaeche.formular_opex_zusatz_titel"),
            hilfe=txt("oberflaeche.formular_opex_zusatz_hilfe"),
            spalte_wert=txt("oberflaeche.formular_opex_zusatz_betrag"),
            einheit="€/kWp/Jahr",
            darstellung=darstellung,
            vorhandene=[
                {"Position": z.name, "Wert": z.basiswert_eur_kwp}
                for z in (existing.zusatz_opex if existing else [])
            ],
        )

    st.markdown(txt("oberflaeche.formular_investkosten_titel"))
    capex_defaults = existing.capex if existing else CapexBreakdown()

    # Der EPC-Default haengt vom Anlagentyp ab. Ein Anlagentyp-Wechsel muss
    # den vorbelegten Wert deshalb ebenfalls neu triggern, sonst bleibt der
    # beim ersten Rendern gesetzte Session-State-Wert stehen (gleiche
    # Problematik wie beim Einheiten-Wechsel, siehe Modulkopf).
    anlagentyp_mode_key = f"{form_key}_anlagentyp_prev"
    anlagentyp_changed = st.session_state.get(anlagentyp_mode_key) != anlagentyp_label
    st.session_state[anlagentyp_mode_key] = anlagentyp_label
    if anlagentyp_changed and not existing:
        st.session_state.pop(f"{form_key}_epc", None)

    def capex_feld(
        col,
        label: str,
        default_abs_eur: float,
        key_suffix: str,
        default_eur_kwp: float | None = None,
    ) -> float:
        """Ein Investkosten-Feld mit eigenem Einheiten-Umschalter.

        Jedes Feld laesst sich einzeln zwischen spezifischer Eingabe
        (€/kWp, Vorbelegung) und Gesamtbetrag (€) umschalten. Der
        Umschalter steht unter dem Feld und wird VOR dem Zahlenfeld
        ausgewertet: Streamlit hat den neuen Schalterzustand beim
        folgenden Rerun bereits im Session-State, sodass Beschriftung
        und Wert im selben Durchlauf zusammenpassen.

        Beim Umschalten wird der EINGEGEBENE Wert umgerechnet, nicht die
        Vorbelegung neu gesetzt - eine bereits erfasste Zahl geht damit
        nicht verloren.

        default_eur_kwp: expliziter Vorbelegungswert fuer den
        €/kWp-Modus (z.B. Widmung 1 €/kWp bei 10.000 € absolut) - ohne
        Angabe wird er aus dem Absolutwert abgeleitet.
        """
        key = f"{form_key}_{key_suffix}"
        schalter_key = f"{key}_absolut"
        vorher_key = f"{key}_absolut_prev"
        absolut = bool(st.session_state.get(schalter_key, False))
        vorher = st.session_state.get(vorher_key)

        if key not in st.session_state:
            if absolut:
                st.session_state[key] = default_abs_eur
            elif default_eur_kwp is not None and not existing:
                st.session_state[key] = default_eur_kwp
            else:
                # Zwei Nachkommastellen: Mit nur einer verliert der
                # Rueckweg (Anzeige -> Gesamtbetrag) bei kleinen Positionen
                # mehrere hundert Euro, und die Seite meldete Aenderungen,
                # die niemand vorgenommen hat.
                st.session_state[key] = (
                    round(default_abs_eur / nennleistung_kwp, 2)
                    if nennleistung_kwp
                    else 0.0
                )
        elif vorher is not None and vorher != absolut and nennleistung_kwp:
            wert = float(st.session_state[key])
            st.session_state[key] = (
                round(wert * nennleistung_kwp, 0) if absolut
                else round(wert / nennleistung_kwp, 2)
            )
        st.session_state[vorher_key] = absolut

        einheit_label = "€" if absolut else "€/kWp"
        eingabe = col.number_input(
            f"{label} ({einheit_label})", min_value=0.0,
            step=1000.0 if absolut else 1.0, key=key,
        )
        col.toggle(
            txt("oberflaeche.formular_capex_toggle_absolut"),
            key=schalter_key,
            help=txt("oberflaeche.formular_capex_toggle_hilfe"),
        )
        return eingabe if absolut else eingabe * nennleistung_kwp

    epc_default_eur_kwp = global_assumptions.epc_eur_kwp_vorschlag_je_anlagentyp.get(
        anlagentyp_label, EPC_DEFAULT_EUR_KWP[anlagentyp_label]
    )

    def epc_feld(col):
        return capex_feld(
            col, "EPC",
            capex_defaults.epc_eur
            if existing
            else nennleistung_kwp * epc_default_eur_kwp,
            "epc",
        )

    def netz_feld(col):
        return capex_feld(
            col, "Netzanschluss",
            capex_defaults.netzanschluss_eur if existing
            else nennleistung_kwp * 50.0,
            "netz",
        )

    def trasse_feld(col):
        return capex_feld(
            col, "Trasse",
            capex_defaults.trasse_eur if existing else nennleistung_kwp * 40.0,
            "trasse",
        )

    def weitere_capex_felder(spaltensatz):
        """Die sechs Positionen hinter den drei grossen."""
        s1, s2, s3, s4, s5, s6 = spaltensatz
        return (
            capex_feld(
                s1, "Widmung",
                capex_defaults.widmung_eur if existing else 10000.0,
                "widmung", default_eur_kwp=1.0,
            ),
            capex_feld(
                s2, "Genehmigung",
                capex_defaults.genehmigung_eur if existing else 80000.0,
                "genehmigung", default_eur_kwp=8.0,
            ),
            capex_feld(
                s3, "Sonstige Extern",
                capex_defaults.sonstige_extern_eur if existing else 40000.0,
                "sonst",
            ),
            capex_feld(
                s4, "AGM", capex_defaults.agm_eur if existing else 30000.0,
                "agm",
            ),
            capex_feld(
                s5, "M&A", capex_defaults.m_and_a_eur if existing else 20000.0,
                "ma",
            ),
            capex_feld(
                s6, txt("oberflaeche.formular_capex_poenale"),
                capex_defaults.poenale_puffer_eur if existing else 35000.0,
                "poenale",
            ),
        )

    if spaltig:
        # Drei Positionen tragen den Grossteil des Invests und sind die,
        # an denen man beim Durchspielen dreht - EPC rund 80 %, dazu
        # Netzanschluss und Trasse, die zusammen am Anschlusspunkt
        # haengen. Die uebrigen sechs sind Projektfakten, die einmal
        # erfasst und selten wieder angefasst werden; sie stehen im
        # Popover, jede weiterhin mit ihrem eigenen Einheitenschalter.
        summenzeile = st.container()
        epc = epc_feld(st)
        netzanschluss = netz_feld(st)
        trasse = trasse_feld(st)
        weitere = st.container()
        with st.popover(txt("oberflaeche.formular_capex_weitere_knopf"),
                        width="stretch",
                        help=txt("oberflaeche.formular_capex_weitere_hilfe")):
            st.markdown(f"**{txt('oberflaeche.formular_capex_weitere_titel')}**")
            (widmung, genehmigung, sonstige_extern, agm, m_and_a,
             poenale) = weitere_capex_felder([st] * 6)
            # Frei benannte Investkosten gehoeren in dieselbe Huelle wie
            # die festen - es sind Investkosten. Hier offen und nicht
            # hinter einem weiteren Popover: Popover lassen sich nicht
            # schachteln.
            st.divider()
            zusatz_capex = zusatz_capex_tabelle("offen")
    else:
        summenzeile = None
        weitere = None
        c1, c2, c3, c4 = spalten(4)
        epc = epc_feld(c1)
        netzanschluss = netz_feld(c2)
        trasse = trasse_feld(c3)
        (widmung, genehmigung, sonstige_extern, agm, m_and_a,
         poenale) = weitere_capex_felder(list(spalten(3)) + list(spalten(3)))
        zusatz_capex = zusatz_capex_tabelle("schalter")

    if summenzeile is not None:
        gesamt = (epc + netzanschluss + trasse + widmung + genehmigung
                  + sonstige_extern + agm + m_and_a + poenale)
        with summenzeile:
            # Die Summe steht ueber den Feldern: Sie ist die Zahl, auf
            # die es beim Drehen ankommt - das spezifische Invest ist
            # zwischen Projekten vergleichbar, der Gesamtbetrag nicht.
            st.caption(
                txt("oberflaeche.formular_capex_summe",
                    spezifisch=fmt_number(gesamt / nennleistung_kwp, 0)
                    if nennleistung_kwp else "–",
                    gesamt=fmt_number(gesamt / 1e6, 2))
            )
        with weitere:
            st.caption(
                txt("oberflaeche.formular_capex_weitere_summe",
                    spezifisch=fmt_number(
                        (widmung + genehmigung + sonstige_extern + agm
                         + m_and_a + poenale) / nennleistung_kwp, 0)
                    if nennleistung_kwp else "–")
            )

    # --- Betriebskosten ---------------------------------------------------
    # Pacht, Gemeindeabgabe und Direktvermarktungskosten stehen unter EINER
    # Ueberschrift: Alle drei sind jaehrliche Betriebskosten (siehe
    # engine/opex.py). Die beiden Abgaben je MWh standen frueher unter
    # "Erloese" - sie haengen zwar am Umsatz, sind aber Kosten, und wer
    # die Kostenseite eines Projekts prueft, suchte sie dort vergeblich.
    #
    # Der ganze Block liegt ausserhalb des Formularrahmens: Er enthaelt
    # Umschalter, und die duerfen nicht in st.form stehen (siehe
    # Modulkopf).
    st.markdown(f"**{txt('oberflaeche.formular_betriebskosten_titel')}**")
    pachtmodus_fix = txt("oberflaeche.formular_pachtmodus_fix")
    pachtmodus_umsatz = txt("oberflaeche.formular_pachtmodus_umsatzbeteiligung")

    # Hausueblicher Fall ist die Umsatzbeteiligung mit einer Mindestpacht;
    # ein neues Projekt startet deshalb dort statt bei der Fixpacht.
    pacht_modus_default_umsatz = (
        existing.pacht_modus == PachtModus.UMSATZBETEILIGUNG if existing else True
    )
    pacht_umsatzbeteiligung_pct = (
        existing.pacht_umsatzbeteiligung_pct if existing
        else global_assumptions.pacht_umsatzbeteiligung_pct_vorschlag
    )
    pacht_mindestpacht_eur_ha_jahr = (
        existing.pacht_mindestpacht_eur_ha_jahr if existing
        else global_assumptions.pacht_mindestpacht_eur_ha_jahr_vorschlag
    )

    gemeindeabgabe_default = (
        existing.gemeindeabgabe_eur_mwh if existing
        else global_assumptions.gemeindeabgabe_eur_kwh * 1000
    )
    direktvermarktung_default = (
        existing.direktvermarktungskosten_eur_mwh if existing
        else global_assumptions.direktvermarktungskosten_eur_kwh * 1000
    )
    nur_relativ = (
        global_assumptions.direktvermarktung_modus
        == DirektvermarktungsModus.RELATIV_MARKTWERT
    )

    def pacht_konfiguration():
        """Vertragsform und Einheit.

        Zwei Umschalter, die den Rest des Blocks bestimmen: fix oder
        Umsatzbeteiligung, und bei Fixpacht die Bezugsgroesse.
        """
        modus_label = st.radio(
            txt("oberflaeche.formular_pachtmodus_label"),
            [pachtmodus_fix, pachtmodus_umsatz],
            index=1 if pacht_modus_default_umsatz else 0,
            horizontal=not spaltig, key=f"{form_key}_pachtmodus",
            help=txt("oberflaeche.formular_pachtmodus_hilfe"),
        )
        modus = (PachtModus.UMSATZBETEILIGUNG if modus_label == pachtmodus_umsatz
                 else PachtModus.FIX)
        einheit = None
        if modus == PachtModus.FIX:
            # Vorbelegung aus dem Projekt: Ein Bestand ohne Flaeche ist in
            # €/kWp gepflegt - ihn im €/ha-Modus zu oeffnen, rechnete den
            # Wert ueber eine erfundene Flaeche um.
            einheiten = ["€/ha/Jahr", "€/kWp/Jahr"]
            einheit_key = f"{form_key}_pacht_einheit"
            if einheit_key not in st.session_state:
                st.session_state[einheit_key] = (
                    "€/ha/Jahr"
                    if not existing or existing.projektflaeche_ha
                    else "€/kWp/Jahr"
                )
            einheit = st.radio(
                "Einheit", options=einheiten, horizontal=True, key=einheit_key,
            )
        return modus_label, modus, einheit

    def pacht_flaeche(schluessel: str, mode_changed: bool,
                      hilfe: str | None = None) -> float:
        flaeche_key = f"{form_key}_{schluessel}"
        if mode_changed or flaeche_key not in st.session_state:
            st.session_state[flaeche_key] = (
                existing.projektflaeche_ha
                if existing and existing.projektflaeche_ha
                else 10.0
            )
        return st.number_input(
            txt("oberflaeche.formular_projektflaeche_label"),
            min_value=0.01, step=0.5, key=flaeche_key, help=hilfe,
        )

    def pacht_felder():
        """Der vollstaendige Pachtblock - Modus, Bezugsgroessen, Wert.

        Reihenfolge: erst die Vertragsform, dann der Wert, dann die
        Bezugsgroessen. Bei der Umsatzbeteiligung braucht das Wertfeld
        keine Flaeche, bei der Fixpacht in €/ha schon - dort steht die
        Flaeche deshalb vor dem Wert.
        """
        nonlocal pacht_mindestpacht_eur_ha_jahr
        modus_label, modus, einheit = pacht_konfiguration()
        mode_key = f"{form_key}_pacht_mode_prev"
        mode_changed = st.session_state.get(mode_key) != (modus_label, einheit)
        st.session_state[mode_key] = (modus_label, einheit)

        if modus == PachtModus.UMSATZBETEILIGUNG:
            wert, anteil = _pacht_wertfeld(
                st, form_key, existing, modus, einheit, None,
                nennleistung_kwp, mode_changed, pacht_umsatzbeteiligung_pct,
            )
            flaeche = pacht_flaeche(
                "flaeche_umsatz", mode_changed,
                txt("oberflaeche.formular_pacht_flaeche_umsatz_hilfe"),
            )
            min_key = f"{form_key}_pacht_mindest_ha"
            if mode_changed or min_key not in st.session_state:
                st.session_state[min_key] = pacht_mindestpacht_eur_ha_jahr
            pacht_mindestpacht_eur_ha_jahr = st.number_input(
                txt("oberflaeche.formular_pacht_mindestpacht_label"),
                min_value=0.0, step=50.0, key=min_key,
                help=txt("oberflaeche.formular_pacht_mindestpacht_hilfe"),
            )
            return modus, flaeche, wert, anteil

        if einheit == "€/ha/Jahr":
            flaeche = pacht_flaeche("flaeche", mode_changed)
        else:
            flaeche = existing.projektflaeche_ha if existing else None
        wert, anteil = _pacht_wertfeld(
            st, form_key, existing, modus, einheit, flaeche,
            nennleistung_kwp, mode_changed, pacht_umsatzbeteiligung_pct,
        )
        return modus, flaeche, wert, anteil

    def abgaben_felder(col_gemeinde, col_dv):
        """Gemeindeabgabe und Direktvermarktung - Kosten je MWh."""
        gemeinde = col_gemeinde.number_input(
            "Gemeindeabgabe (€/MWh)", min_value=0.0,
            value=gemeindeabgabe_default, step=0.5,
            key=f"{form_key}_gemeindeabgabe",
        )
        if nur_relativ:
            # Der projektspezifische EUR/MWh-Wert ist im Relativ-Modus
            # ohne Wirkung - er bleibt gespeichert (fuer einen spaeteren
            # Moduswechsel), wird aber nicht zur Eingabe angeboten.
            col_dv.caption(txt(
                "oberflaeche.formular_direktvermarktung_relativ_hinweis",
                anteil=f"{global_assumptions.direktvermarktung_pct_marktwert * 100:.1f}",
            ))
            return gemeinde, direktvermarktung_default
        return gemeinde, col_dv.number_input(
            "DV-Kosten (€/MWh)", min_value=0.0,
            value=direktvermarktung_default, step=0.1,
            key=f"{form_key}_direktvermarktung",
            help=txt("oberflaeche.formular_direktvermarktung_hilfe"),
        )

    if spaltig:
        # In der Live-Spalte steckt der ganze Block hinter einem Popover:
        # Vertragsform, Flaeche und Abgaben je MWh sind Vertrags- und
        # Standortfakten, an denen beim Durchspielen niemand dreht. Was
        # darin steht, muss von aussen ablesbar sein - die Bildunterschrift
        # nennt Pachtmodell, Flaeche und die beiden Abgaben.
        hinweisbereich = st.container()
        with st.popover(txt("oberflaeche.formular_betriebskosten_knopf"),
                        width="stretch",
                        help=txt("oberflaeche.formular_betriebskosten_hilfe")):
            st.markdown(f"**{txt('oberflaeche.formular_pacht_titel')}**")
            (pacht_modus, flaeche_ha, pacht_eur_kwp_jahr,
             pacht_umsatzbeteiligung_pct) = pacht_felder()
            st.divider()
            st.markdown(f"**{txt('oberflaeche.formular_abgaben_titel')}**")
            col_abg1, col_abg2 = st.columns(2)
            gemeindeabgabe_mwh, direktvermarktungskosten_mwh = abgaben_felder(
                col_abg1, col_abg2
            )
            st.divider()
            opex_standard = _standard_opex_tabelle(
                form_key, global_assumptions, gespeicherte_abweichung
            )
            kosten_inflation = _erbe_zahl(
                st, form_key, "abw_kosten_inflation_pct_pa",
                txt("oberflaeche.formular_kosteninflation_label"),
                global_assumptions.kosten_inflation_pct_pa,
                gespeicherte_abweichung.kosten_inflation_pct_pa,
                faktor=100.0, nachkomma=1, min_value=0.0, step=0.25,
                hilfe=txt("oberflaeche.formular_kosteninflation_hilfe"),
            )
        with hinweisbereich:
            st.caption(
                txt("oberflaeche.formular_betriebskosten_zusammenfassung",
                    pacht=(
                        fmt_number(pacht_umsatzbeteiligung_pct * 100, 1) + " %"
                        if pacht_modus == PachtModus.UMSATZBETEILIGUNG
                        else fmt_number(pacht_eur_kwp_jahr, 2) + " €/kWp"
                    ),
                    flaeche=(fmt_number(flaeche_ha, 1) + " ha") if flaeche_ha
                    else "–",
                    dv=fmt_number(direktvermarktungskosten_mwh, 2),
                    gemeinde=fmt_number(gemeindeabgabe_mwh, 2))
            )
    else:
        (pacht_modus, flaeche_ha, pacht_eur_kwp_jahr,
         pacht_umsatzbeteiligung_pct) = pacht_felder()
        st.markdown(f"**{txt('oberflaeche.formular_abgaben_titel')}**")
        gemeindeabgabe_mwh, direktvermarktungskosten_mwh = abgaben_felder(
            *spalten(2)
        )
        opex_standard = _standard_opex_tabelle(
            form_key, global_assumptions, gespeicherte_abweichung
        )
        kosten_inflation = _erbe_zahl(
            st, form_key, "abw_kosten_inflation_pct_pa",
            txt("oberflaeche.formular_kosteninflation_label"),
            global_assumptions.kosten_inflation_pct_pa,
            gespeicherte_abweichung.kosten_inflation_pct_pa,
            faktor=100.0, nachkomma=1, min_value=0.0, step=0.25,
            hilfe=txt("oberflaeche.formular_kosteninflation_hilfe"),
        )

    # Frei benannte Betriebskosten schliessen den Block ab: dieselbe
    # Groessenordnung, derselbe Zeitbezug - jaehrliche Kosten je kWp.
    zusatz_opex = zusatz_opex_tabelle("popover" if spaltig else "schalter")

    # --- Erloese ----------------------------------------------------------
    # Der Block steht VOR dem Formularrahmen und damit ausserhalb von
    # st.form: Er enthaelt den Anlagentyp, und dessen Wechsel muss sofort
    # wirken - er belegt den EPC-Vorschlag vor und schaltet den
    # Abschlagshinweis. Innerhalb eines Formulars loest kein Widget einen
    # Neulauf aus, der Wechsel wuerde also erst beim Abschicken sichtbar.
    st.markdown(f"**{txt('oberflaeche.formular_erloese_titel')}**")
    # Agri-PV gegen konventionell ist eine EAG-Kategorie: Sie entscheidet
    # ueber den anzuwendenden Zuschlagswert, nicht ueber die Technik der
    # Anlage. Deshalb steht das Radio hier und nicht bei den technischen
    # Parametern.
    anlagentyp_label = st.radio(
        txt("oberflaeche.formular_anlagentyp_label"), anlagentyp_options,
        index=anlagentyp_index, horizontal=True, key=anlagentyp_key,
        help=txt("oberflaeche.formular_anlagentyp_hilfe"),
    )
    col7, col8 = spalten(2)
    eag_zuschlag = col7.number_input(
        "EAG-Zuschlagswert (ct/kWh)", min_value=0.0,
        value=existing.eag_zuschlagswert_ct_kwh
        if existing
        else float(st.session_state.get("empfohlenes_gebot_ct", 6.5)),
        step=0.1, key=f"{form_key}_eag",
        help=txt("oberflaeche.formular_eag_zuschlag_hilfe"),
    )
    if anlagentyp_label == "Konventionell":
        st.caption(txt(
            "oberflaeche.formular_konventionell_abschlag_hinweis",
            wert=f"{eag_zuschlag * 0.75:.2f}",
        ))

    # Die Auswahl fuehrt die Szenarien OHNE Bauform: "Aurora Q3/26 ·
    # Central" statt zweier Eintraege fuer Pult und Tracker. Welche der
    # beiden Kurven gerechnet wird, entscheidet das Bauform-Radio oben
    # bei den technischen Parametern.
    szenario_namen = (szenario_auswahl(global_assumptions)
                      or ["Aurora Q3/26 · Central"])
    default_szenario = existing.marktpreisszenario if existing else szenario_namen[0]
    szenario_index = (
        szenario_namen.index(default_szenario)
        if default_szenario in szenario_namen
        else 0
    )
    marktpreisszenario = st.selectbox(
        txt("oberflaeche.formular_marktpreisszenario_label"), szenario_namen,
        index=szenario_index, key=f"{form_key}_marktpreisszenario",
        help=txt("oberflaeche.formular_marktpreisszenario_hilfe"),
    )

    # --- Hybride Vermarktung ------------------------------------------------
    # In der Live-Spalte hinter einem Popover: PPA-Vertragsdaten sind
    # Vertragsfakten, keine Groessen, an denen man beim Durchspielen
    # dreht. Die Widgets existieren darin unveraendert weiter - der
    # Inhalt eines Popovers wird bei JEDEM Durchlauf ausgefuehrt.
    if spaltig:
        # Was im Popover steckt, muss von aussen ablesbar sein - sonst
        # weiss niemand, ob dort ein PPA wartet.
        ppa_anteil_gespeichert = int(round(
            (existing.ppa_anteil_pct if existing else 0.0) * 100
        ))
        st.caption(
            txt("oberflaeche.formular_vermarktung_ppa_anteil",
                anteil=ppa_anteil_gespeichert)
            if ppa_anteil_gespeichert
            else txt("oberflaeche.formular_vermarktung_ohne_ppa")
        )
    vermarktung = _abschnitt(
        spaltig,
        knopf=txt("oberflaeche.formular_vermarktung_knopf"),
        hilfe=txt("oberflaeche.formular_vermarktung_hilfe"),
    )
    with vermarktung:
        if spaltig:
            st.markdown(f"**{txt('oberflaeche.formular_ppa_titel_kurz')}**")
        else:
            st.markdown(txt("oberflaeche.formular_ppa_titel"))
        ppa_anteil = st.slider(
            txt("oberflaeche.formular_ppa_anteil_label"),
            min_value=0, max_value=100,
            value=int(round(
                (existing.ppa_anteil_pct if existing else 0.0) * 100
            )),
            step=5, key=f"{form_key}_ppa_anteil",
            help=txt("oberflaeche.formular_ppa_anteil_hilfe"),
        )
        # Bei 0 % bleiben die Vertragsfelder sichtbar, aber gesperrt - so
        # ist zu sehen, welche Angaben ein Vertrag braucht, ohne dass sie
        # stumm mitrechnen. Sie verschwinden bewusst NICHT: Widgets, die
        # zwischen Durchlaeufen kommen und gehen, sind in Streamlit ein
        # Risikomuster (siehe Modulkopf).
        ohne_ppa = ppa_anteil == 0
        col_ppa1, col_ppa2 = st.columns(2) if spaltig else spalten(2)
        ppa_preis = col_ppa1.number_input(
            txt("oberflaeche.formular_ppa_preis_label"), min_value=0.0,
            value=(existing.ppa_preis_eur_mwh if existing
                   else global_assumptions.ppa_preis_eur_mwh_vorschlag),
            step=1.0, key=f"{form_key}_ppa_preis", disabled=ohne_ppa,
            help=txt("oberflaeche.formular_ppa_preis_hilfe"),
        )
        ppa_laufzeit = col_ppa2.number_input(
            txt("oberflaeche.formular_ppa_laufzeit_label"), min_value=0,
            value=(existing.ppa_laufzeit_jahre if existing
                   else global_assumptions.ppa_laufzeit_jahre_vorschlag),
            step=1, key=f"{form_key}_ppa_laufzeit", disabled=ohne_ppa,
            help=txt("oberflaeche.formular_ppa_laufzeit_hilfe"),
        )
        col_ppa3, col_ppa4 = st.columns(2) if spaltig else spalten(2)
        ppa_index = col_ppa3.number_input(
            txt("oberflaeche.formular_ppa_index_label"), min_value=0.0,
            value=((existing.ppa_indexierung_pct_pa if existing
                    else global_assumptions.ppa_indexierung_pct_pa_vorschlag)
                   * 100),
            step=0.25, key=f"{form_key}_ppa_index", disabled=ohne_ppa,
            help=txt("oberflaeche.formular_ppa_index_hilfe"),
        )
        ppa_start = col_ppa4.number_input(
            txt("oberflaeche.formular_ppa_start_label"), min_value=1,
            value=(existing.ppa_start_jahr if existing else 1),
            step=1, key=f"{form_key}_ppa_start", disabled=ohne_ppa,
            help=txt("oberflaeche.formular_ppa_start_hilfe"),
        )

    foerdermodell_zeile = st.container()
    with _abschnitt(spaltig,
                    knopf=txt("oberflaeche.formular_foerdermodell_knopf"),
                    hilfe=txt("oberflaeche.formular_foerdermodell_hilfe")):
        foerdermodell = _foerdermodell_felder(
            form_key, global_assumptions, gespeicherte_abweichung
        )
    with foerdermodell_zeile:
        _abweichungszeile(_beschriftungen(foerdermodell))

    # --- Finanzierung -------------------------------------------------------
    # Kapitalstruktur und Zins sind die letzte offene Frage, wenn Kosten
    # und Erloese stehen. Der Block liegt - wie inzwischen alle -
    # ausserhalb des Formularrahmens: Er enthaelt ein Popover, und
    # Popover duerfen nicht in st.form stehen (siehe Modulkopf).
    st.markdown(f"**{txt('oberflaeche.formular_finanzierung_titel')}**")
    # Zwei kurze Prozentfelder passen auch in der schmalen Spalte
    # nebeneinander.
    col_ek, col_fk = st.columns(2)
    # Kurzbeschriftungen in der schmalen Spalte: "Eigenkapitalanteil"
    # bricht auf halber Spaltenbreite mitten im Wort um.
    ek_anteil = col_ek.number_input(
        "EK-Anteil (%)" if spaltig else "Eigenkapitalanteil (%)",
        min_value=0.0, max_value=100.0,
        value=((existing.eigenkapitalquote_pct if existing
                else global_assumptions.eigenkapitalquote_pct_vorschlag) * 100),
        step=1.0, key=f"{form_key}_ekanteil",
    )
    fk_zins = col_fk.number_input(
        "FK-Zins (%)" if spaltig else "Fremdkapitalzins (%)",
        min_value=0.0,
        value=((existing.fremdkapitalzins_pct if existing
                else global_assumptions.fremdkapitalzins_pct_vorschlag) * 100),
        step=0.1, key=f"{form_key}_fkzins",
    )
    kreditvertrag_zeile = st.container()
    with _abschnitt(spaltig,
                    knopf=txt("oberflaeche.formular_kreditvertrag_knopf"),
                    hilfe=txt("oberflaeche.formular_kreditvertrag_hilfe")):
        kreditvertrag = _kreditvertrag_felder(
            form_key, global_assumptions, gespeicherte_abweichung, spaltig
        )
    with kreditvertrag_zeile:
        _abweichungszeile(_beschriftungen(kreditvertrag))

    # --- Steuern ------------------------------------------------------------
    # Bisher gab es diesen Block im Projekt gar nicht - die Steuer war
    # ausschliesslich global. Sie haengt aber an Sitz und Rechtsform der
    # Projektgesellschaft, nicht am Portfolio.
    st.markdown(f"**{txt('oberflaeche.formular_steuern_titel')}**")
    steuern_zeile = st.container()
    with _abschnitt(spaltig,
                    knopf=txt("oberflaeche.formular_steuern_knopf"),
                    hilfe=txt("oberflaeche.formular_steuern_hilfe")):
        steuern = _steuer_felder(
            form_key, global_assumptions, gespeicherte_abweichung, spaltig
        )
    with steuern_zeile:
        _abweichungszeile(_beschriftungen(steuern))

    abweichungen = Projektannahmen(
        **kreditvertrag, **steuern, **foerdermodell, **ertrag,
        kosten_inflation_pct_pa=kosten_inflation,
        opex_standard_eur_kwp=opex_standard,
        **{
            feld: getattr(gespeicherte_abweichung, feld)
            for feld in _NOCH_NICHT_IN_DER_MASKE
        },
    )

    with _formularrahmen(form_key, mit_formular):
        if mit_formular:
            button_label = (
                txt("oberflaeche.formular_btn_speichern") if existing
                else txt("oberflaeche.formular_btn_anlegen")
            )
            abgeschickt = st.form_submit_button(button_label, type="primary")
        else:
            # Ohne Formular gibt es nichts abzuschicken - der Entwurf
            # entsteht bei jedem Durchlauf neu.
            abgeschickt = True

    if not abgeschickt:
        return None
    if not name.strip():
        if mit_formular:
            st.error(txt("oberflaeche.projekt_name_fehlt"))
        return None
    positionsfehler = _namensfehler(zusatz_capex + zusatz_opex)
    if positionsfehler:
        st.error(positionsfehler)
        return None

    project_id = (
        existing.id if existing
        else services.make_project_id(f"{name} {variante}".strip())
    )
    return PVProject(
        id=project_id,
        name=name.strip(),
        standort=standort.strip(),
        variante=variante.strip(),
        # Ohne diese Uebernahme wuerde jedes Speichern aus der
        # Parameterspalte ein stillgelegtes Projekt wieder aktivieren -
        # der Aktiv-Schalter liegt im Ueberlaufmenue, nicht im Formular.
        aktiv=existing.aktiv if existing else True,
        # Dasselbe fuer den Leitfall: Er wird in der Variantenreihe
        # gesetzt, nicht hier. Ohne Uebernahme meldete schon das blosse
        # Oeffnen eines Leitfalls eine offene Aenderung - und Speichern
        # haette die Markierung stillschweigend geloescht.
        leitvariante=existing.leitvariante if existing else False,
        inbetriebnahme_jahr=inbetriebnahme_jahr,
        inbetriebnahme_monat=inbetriebnahme_monat,
        anlagentyp=AnlagenTyp.AGRI_PV
        if anlagentyp_label == "Agri-PV"
        else AnlagenTyp.KONVENTIONELL,
        nennleistung_kwp=nennleistung_kwp,
        vollbenutzungsstunden_kwh_kwp=vollbenutzungsstunden,
        bauform=bauform,
        pacht_eur_kwp_jahr=pacht_eur_kwp_jahr,
        pacht_modus=pacht_modus,
        pacht_umsatzbeteiligung_pct=pacht_umsatzbeteiligung_pct,
        pacht_mindestpacht_eur_ha_jahr=pacht_mindestpacht_eur_ha_jahr,
        projektflaeche_ha=flaeche_ha,
        annahmen=abweichungen,
        fremdkapitalzins_pct=fk_zins / 100,
        eigenkapitalquote_pct=ek_anteil / 100,
        eag_zuschlagswert_ct_kwh=eag_zuschlag,
        gemeindeabgabe_eur_mwh=gemeindeabgabe_mwh,
        direktvermarktungskosten_eur_mwh=direktvermarktungskosten_mwh,
        marktpreisszenario=marktpreisszenario,
        ppa_anteil_pct=ppa_anteil / 100,
        ppa_preis_eur_mwh=ppa_preis,
        ppa_start_jahr=int(ppa_start),
        ppa_laufzeit_jahre=int(ppa_laufzeit),
        ppa_indexierung_pct_pa=ppa_index / 100,
        zusatz_opex=[
            OpexItem(
                name=eintrag["Position"],
                basiswert_eur_kwp=eintrag["Wert"],
                index_pct_pa=global_assumptions.kosten_inflation_pct_pa,
            )
            for eintrag in zusatz_opex
        ],
        capex=CapexBreakdown(
            epc_eur=epc,
            netzanschluss_eur=netzanschluss,
            trasse_eur=trasse,
            widmung_eur=widmung,
            genehmigung_eur=genehmigung,
            sonstige_extern_eur=sonstige_extern,
            agm_eur=agm,
            m_and_a_eur=m_and_a,
            poenale_puffer_eur=poenale,
            zusatzpositionen=[
                CapexPosition(name=eintrag["Position"], betrag_eur=eintrag["Wert"])
                for eintrag in zusatz_capex
            ],
        ),
    )
