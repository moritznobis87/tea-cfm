"""
Die Bearbeitungsdialoge der Globalen Annahmen.

Sechs Bereiche, die reine Feldgruppen sind, liegen hinter je einem
`st.dialog`: Vermarktung, Betriebskosten, Technik, Finanzierung,
Foerderung und Steuern. Markt & Preise liegt bewusst NICHT hier - dieser
Bereich fuehrt drei nebeneinanderliegende Diagramme, Szenariotabellen und
zwei Editoren und braucht die volle Seitenbreite (siehe
app/views/assumptions.py).

Wie ein Dialog seinen Zustand fuehrt
------------------------------------
Drei Zustaende, streng getrennt (dieselbe Ordnung wie im Project
Cockpit, siehe project_dialogs.py):

    1. gespeichert   - die YAML-Datei
    2. ENTWURF       - GlobalAssumptions im Session-State
    3. Dialogzustand - die gadlg_*-Widgets, solange der Dialog offen ist

"Abbrechen" und das Kreuz verwerfen 3 und lassen 2 unberuehrt - sie
schreiben schlicht nichts. "Aenderungen uebernehmen" ueberfuehrt 3 nach
2. Erst "Speichern" auf der Hauptseite ueberfuehrt 2 nach 1 und
invalidiert die Bewertungs-Caches.

Die Widgets werden beim OEFFNEN aus dem Entwurf vorbelegt
(`felder_ansaeen`) und nicht beim Schliessen geraeumt: Nur so startet
ein Dialog garantiert auf dem Stand, den die Karte gerade zeigt - auch
dann, wenn er beim letzten Mal ueber das Kreuz verlassen wurde.

Warum Felddeklarationen statt Widget-Code
-----------------------------------------
Die sechs Dialoge fuehren zusammen rund vierzig Felder. Als Widget-Code
waeren das vierzig Mal dieselben vier Zeilen (Schluessel bilden,
vorbelegen, rendern, zuruecklesen) - und vierzig Gelegenheiten, eine
Umrechnung an einer Stelle zu vergessen. Ein `Feld` beschreibt stattdessen
EINMAL, wie ein Modellfeld aussieht; Vorbelegen, Rendern und Zuruecklesen
leiten sich daraus ab. Felder, die sich der Systematik entziehen
(Tabellen, landesabhaengige Bloecke), stehen weiterhin ausgeschrieben.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import pandas as pd
import streamlit as st

from app.components.settings_hub import ABSCHNITT_PRAEFIX, DIALOG_PRAEFIX
from engine import (
    DirektvermarktungsModus,
    GlobalAssumptions,
    NegativeStundenRegel,
    OpexItem,
    PraemienModell,
    TaxModus,
    TilgungsArt,
    ZinsMethode,
)
from texte import txt

# --- Felddeklaration --------------------------------------------------------


@dataclass(frozen=True)
class Feld:
    """Ein Modellfeld, wie es im Dialog erscheint.

    `art` bestimmt Widget und Umrechnung:
        "zahl"     - Zahl, 1:1
        "prozent"  - im Modell 0-1, in der Maske 0-100
        "promille" - im Modell EUR/kWh, in der Maske EUR/MWh (Faktor 1000)
        "enum"     - Radio ueber die Werte von `enum`
        "schalter" - Toggle
    """

    name: str
    art: str
    label: str
    hilfe: str = ""
    schritt: float = 1.0
    minimum: float = 0.0
    maximum: float | None = None
    ganzzahl: bool = False
    enum: type[Enum] | None = None
    labels: dict[str, str] = field(default_factory=dict)
    horizontal: bool = True
    #: Ist das Feld im aktuellen Zusammenhang wirksam? Unwirksame Felder
    #: bleiben SICHTBAR und gesperrt statt zu verschwinden: Ein
    #: ausgeblendetes Feld faellt beim naechsten Moduswechsel stumm auf
    #: seinen alten Wert zurueck, und niemand sieht, was gilt.
    aktiv: Callable[[dict[str, Any]], bool] | None = None


def _schluessel(f: Feld, praefix: str = DIALOG_PRAEFIX) -> str:
    """Widget-Schluessel eines Feldes.

    Der Praefix ist ein Parameter, weil dieselbe Felddeklaration an zwei
    Orten gerendert wird: im Dialog (gadlg_) und im Vollbreiten-Abschnitt
    (gasec_). Zwei Widgets mit demselben Schluessel waeren fuer Streamlit
    dasselbe Widget - eine Eingabe im Abschnitt aenderte dann den Dialog
    und umgekehrt.
    """
    return f"{praefix}{f.name}"


def _nach_widget(f: Feld, wert):
    """Modellwert -> Anzeigewert."""
    if f.art == "prozent":
        return float(wert or 0.0) * 100
    if f.art == "promille":
        return float(wert or 0.0) * 1000
    if f.art == "enum":
        return wert.value if isinstance(wert, Enum) else wert
    if f.art == "zahl":
        if wert is None:
            return 0 if f.ganzzahl else 0.0
        return int(wert) if f.ganzzahl else float(wert)
    return wert


def _nach_modell(f: Feld, wert):
    """Anzeigewert -> Modellwert."""
    if f.art == "prozent":
        return float(wert) / 100
    if f.art == "promille":
        return float(wert) / 1000
    if f.art == "enum":
        return f.enum(wert)
    if f.art == "zahl":
        return int(wert) if f.ganzzahl else float(wert)
    return wert


def felder_ansaeen(felder: tuple[Feld, ...], e: GlobalAssumptions) -> None:
    """Belegt die Widgets eines Dialogs aus dem Entwurf vor.

    Unbedingt und nicht nur beim ersten Mal: Der Dialog soll auf dem
    Stand starten, den die Karte zeigt.
    """
    for f in felder:
        st.session_state[_schluessel(f)] = _nach_widget(f, getattr(e, f.name))


def _luecken_fuellen(felder: tuple[Feld, ...], e: GlobalAssumptions) -> None:
    """Ergaenzt fehlende Widget-Zustaende aus dem Entwurf.

    Der Riegel gegen einen Dialog, der ohne `dialog_oeffnen` ins Bild
    kommt - etwa weil Streamlit den Zustand eines Durchlaufs weggeraeumt
    hat, in dem der Dialog nicht gezeichnet wurde. Ohne ihn faellt das
    Einsammeln beim Uebernehmen mit einem KeyError um, und der Nutzer
    verliert seine Eingaben.

    Nur FEHLENDE Schluessel: Vorhandene sind entweder die Vorbelegung
    oder eine Eingabe, die gerade gemacht wurde.
    """
    for f in felder:
        schluessel = _schluessel(f)
        if schluessel not in st.session_state:
            st.session_state[schluessel] = _nach_widget(f, getattr(e, f.name))


def _rendern(
    f: Feld, ziel, gesperrt: bool, praefix: str = DIALOG_PRAEFIX
) -> None:
    beschriftung = txt(f.label)
    hilfe = txt(f.hilfe) if f.hilfe else None
    schluessel = _schluessel(f, praefix)
    if f.art == "enum":
        optionen = [w.value for w in f.enum]
        ziel.radio(
            beschriftung, optionen,
            format_func=lambda v: txt(f.labels[v]),
            key=schluessel, horizontal=f.horizontal,
            disabled=gesperrt, help=hilfe,
        )
        return
    if f.art == "schalter":
        ziel.toggle(
            beschriftung, key=schluessel, disabled=gesperrt, help=hilfe
        )
        return
    ziel.number_input(
        beschriftung,
        min_value=int(f.minimum) if f.ganzzahl else float(f.minimum),
        max_value=(
            None if f.maximum is None
            else (int(f.maximum) if f.ganzzahl else float(f.maximum))
        ),
        step=int(f.schritt) if f.ganzzahl else float(f.schritt),
        key=schluessel, disabled=gesperrt, help=hilfe,
    )


class _Stand:
    """Lesezugriff auf den Widget-Zustand des GANZEN Dialogs.

    `Feld.aktiv` fragt oft nach einem Feld aus einer anderen Gruppe: Ob
    die Rueckzahlungsfelder wirksam sind, haengt am Praemienmodell, und
    das steht in der Gruppe darueber. Ein dict nur aus den Feldern der
    laufenden Gruppe lieferte dafuer None - und sperrte die Felder
    dauerhaft, egal was eingestellt war. Genau das war der Fall bei
    "Rueckzahlung des Uebergewinns".
    """

    def get(self, name: str, vorgabe=None):
        return st.session_state.get(f"{DIALOG_PRAEFIX}{name}", vorgabe)


def _gitter(felder: tuple[Feld, ...], spalten: int = 2) -> None:
    """Rendert eine Feldgruppe im Raster.

    Der aktuelle Widget-Zustand wird beim Sperren mitgelesen: Ob die
    Direktvermarktungskosten wirksam sind, haengt am Modus-Radio DESSELBEN
    Durchlaufs - der Entwurf kennt ihn noch nicht.
    """
    stand = _Stand()
    reihe: list = []
    for i, f in enumerate(felder):
        if i % spalten == 0:
            reihe = list(st.columns(spalten))
        _rendern(f, reihe[i % spalten], bool(f.aktiv and not f.aktiv(stand)))


def _einsammeln(
    felder: tuple[Feld, ...], praefix: str = DIALOG_PRAEFIX
) -> dict[str, Any]:
    """Die Widgets zurueck in Modellwerte."""
    return {
        f.name: _nach_modell(f, st.session_state[_schluessel(f, praefix)])
        for f in felder
    }


def abschnitt_rendern(
    felder: tuple[Feld, ...], e: GlobalAssumptions, spalten: int
) -> None:
    """Dieselben Felder in einem Vollbreiten-Abschnitt statt im Dialog.

    Zwei Unterschiede zum Dialog, beide beabsichtigt:

    1. Vorbelegt wird nur, wenn der Schluessel FEHLT. Ein Abschnitt hat
       keinen Oeffnen-Zeitpunkt; unbedingtes Saeen bei jedem Durchlauf
       ueberschriebe die Eingabe, die gerade gemacht wurde.
    2. Geschrieben wird SOFORT in den Entwurf. Ein "Uebernehmen" waere
       hier eine Huelle ohne Zweck - gespeichert wird ohnehin erst mit
       dem Knopf im Kopf der Seite.
    """
    praefix = ABSCHNITT_PRAEFIX
    for f in felder:
        schluessel = _schluessel(f, praefix)
        if schluessel not in st.session_state:
            st.session_state[schluessel] = _nach_widget(f, getattr(e, f.name))
    reihe: list = []
    for i, f in enumerate(felder):
        if i % spalten == 0:
            reihe = list(st.columns(spalten))
        _rendern(f, reihe[i % spalten], False, praefix)
    for name, wert in _einsammeln(felder, praefix).items():
        setattr(e, name, wert)


# --- Dialograhmen -----------------------------------------------------------

#: Der geoeffnete Bereich; None heisst: kein Dialog.
OFFEN = "ga_dialog_offen"


def dialog_schliessen() -> None:
    st.session_state.pop(OFFEN, None)


def dialog_oeffnen(bereich: str, e: GlobalAssumptions) -> None:
    """Merkt den Bereich vor und belegt seine Widgets aus dem Entwurf vor.

    Erst RAEUMEN, dann saeen: Die Tabelleneditoren (OPEX, EPC) fuehren
    ihren Bearbeitungsstand unter eigenen Schluesseln, die keine
    Felddeklaration hat. Ohne das Raeumen kaemen nach "Abbrechen" beim
    naechsten Oeffnen genau die verworfenen Zeilen wieder hoch.
    """
    from app.components.settings_hub import dialogzustand_leeren

    dialogzustand_leeren()
    felder_ansaeen(DIALOGE[bereich][0], e)
    st.session_state[OFFEN] = bereich


def _fuss(uebernehmen: Callable[[], None], bereich: str) -> None:
    """Die beiden Knoepfe unten - in jedem Dialog gleich."""
    st.divider()
    _leer, col_ab, col_ok = st.columns([0.4, 0.3, 0.3])
    if col_ab.button(
        txt("oberflaeche.btn_abbrechen"),
        key=f"gadlgbtn_{bereich}_ab", width="stretch",
    ):
        # Nichts schreiben: Der Dialogzustand wird beim naechsten Oeffnen
        # ohnehin neu aus dem Entwurf gesaet.
        dialog_schliessen()
        st.rerun()
    if col_ok.button(
        txt("oberflaeche.dialog_uebernehmen"),
        key=f"gadlgbtn_{bereich}_ok", type="primary", width="stretch",
    ):
        uebernehmen()
        dialog_schliessen()
        st.rerun()
    del _leer


def _uebernehmen(e: GlobalAssumptions, werte: dict[str, Any]) -> None:
    for name, wert in werte.items():
        setattr(e, name, wert)


# --- Vermarktung ------------------------------------------------------------
#
# Direktvermarktungskosten und die PPA-Vorbelegung. Beides ist die Frage
# "wie kommt der Strom an den Markt" - die Kosten gelten fuer alle
# Projekte, die PPA-Werte sind Vorbelegung der Projektmaske.

_DV_LABELS = {
    DirektvermarktungsModus.ABSOLUT.value: "oberflaeche.annahmen_dv_modus_absolut",
    DirektvermarktungsModus.RELATIV_GROSSHANDEL.value:
        "oberflaeche.annahmen_dv_modus_grosshandel",
    DirektvermarktungsModus.RELATIV_MARKTWERT.value:
        "oberflaeche.annahmen_dv_modus_relativ",
}


def _dv_absolut(stand: dict) -> bool:
    return stand.get("direktvermarktung_modus") == DirektvermarktungsModus.ABSOLUT.value


def _dv_relativ(stand: dict) -> bool:
    return not _dv_absolut(stand)


VERMARKTUNG: tuple[Feld, ...] = (
    Feld("direktvermarktung_modus", "enum",
         "oberflaeche.annahmen_dv_modus_label",
         hilfe="oberflaeche.annahmen_dv_modus_hilfe",
         enum=DirektvermarktungsModus, labels=_DV_LABELS, horizontal=False),
    Feld("direktvermarktungskosten_eur_kwh", "promille",
         "oberflaeche.annahmen_dv_vorschlagswert_label",
         hilfe="oberflaeche.annahmen_dv_vorschlagswert_hilfe",
         schritt=0.1, aktiv=_dv_absolut),
    Feld("direktvermarktung_pct_marktwert", "prozent",
         "oberflaeche.annahmen_dv_anteil_marktwert_label",
         hilfe="oberflaeche.annahmen_dv_anteil_marktwert_hilfe",
         schritt=0.5, maximum=100.0, aktiv=_dv_relativ),
    Feld("ppa_anteil_pct_vorschlag", "prozent",
         "oberflaeche.annahmen_ppa_anteil_label", schritt=5.0, maximum=100.0),
    Feld("ppa_preis_eur_mwh_vorschlag", "zahl",
         "oberflaeche.annahmen_ppa_preis_label", schritt=1.0),
    Feld("ppa_laufzeit_jahre_vorschlag", "zahl",
         "oberflaeche.annahmen_ppa_laufzeit_label", schritt=1, ganzzahl=True),
    Feld("ppa_indexierung_pct_pa_vorschlag", "prozent",
         "oberflaeche.annahmen_ppa_index_label", schritt=0.25),
)


def render_vermarktung(e: GlobalAssumptions) -> None:
    @st.dialog(txt("oberflaeche.annahmen_karte_vermarktung"),
               width="large", on_dismiss=dialog_schliessen)
    def _dlg():
        _luecken_fuellen(VERMARKTUNG, e)
        st.caption(txt("oberflaeche.annahmen_dlg_vermarktung_hinweis"))
        _abschnitt("oberflaeche.annahmen_direktvermarktung_titel")
        _gitter(VERMARKTUNG[:1], 1)
        _gitter(VERMARKTUNG[1:3], 2)
        _abschnitt("oberflaeche.annahmen_ppa_titel",
                   "oberflaeche.annahmen_ppa_hinweis")
        _gitter(VERMARKTUNG[3:], 2)
        _fuss(lambda: _uebernehmen(e, _einsammeln(VERMARKTUNG)), "vermarktung")

    _dlg()


# --- Betriebskosten ---------------------------------------------------------

BETRIEBSKOSTEN: tuple[Feld, ...] = (
    Feld("kosten_inflation_pct_pa", "prozent",
         "oberflaeche.annahmen_kosteninflation_label",
         hilfe="oberflaeche.annahmen_kosteninflation_hilfe", schritt=0.1),
    Feld("gemeindeabgabe_eur_kwh", "promille",
         "oberflaeche.annahmen_gemeindeabgabe_label",
         hilfe="oberflaeche.annahmen_gemeindeabgabe_hilfe", schritt=0.5),
    Feld("pacht_umsatzbeteiligung_pct_vorschlag", "prozent",
         "oberflaeche.annahmen_pacht_umsatzbeteiligung_vorschlag_label",
         hilfe="oberflaeche.annahmen_pacht_umsatzbeteiligung_vorschlag_hilfe",
         schritt=0.5, maximum=100.0),
    Feld("pacht_mindestpacht_eur_ha_jahr_vorschlag", "zahl",
         "oberflaeche.annahmen_pacht_mindestpacht_vorschlag_label",
         schritt=50.0),
)


#: Die Arbeitsliste der Betriebskostenpositionen, solange der Dialog
#: offen ist: [(Name, EUR/kWp/Jahr), ...]. Bewusst eine eigene Liste und
#: nicht der Entwurf: Hinzufuegen und Entfernen sollen "Abbrechen"
#: ueberleben koennen - also erst mit "Uebernehmen" wirken.
_OPEX_LISTE = f"{DIALOG_PRAEFIX}opex_liste"


def _opex_ansaeen(e: GlobalAssumptions) -> None:
    if _OPEX_LISTE not in st.session_state:
        st.session_state[_OPEX_LISTE] = [
            (i.name, float(i.basiswert_eur_kwp)) for i in e.opex_standard
        ]


def _opex_felder() -> None:
    """Je Position ein gewoehnliches Eingabefeld.

    Frueher war das ein Tabelleneditor mit vier Spalten - Wert,
    Indexrate und Startjahr je Position. Das sah technischer aus, als
    die Sache ist: In der Praxis laeuft EINE Kosteninflation ueber alle
    Positionen, und wann sie einsetzt, hat noch niemand je Position
    verschieden gebraucht. Beides steht jetzt einmal im Block darunter;
    hier bleibt der Betrag, um den es geht.
    """
    liste = st.session_state[_OPEX_LISTE]
    for i, (name, wert) in enumerate(liste):
        schluessel = f"{DIALOG_PRAEFIX}opex_wert_{i}"
        if schluessel not in st.session_state:
            st.session_state[schluessel] = float(wert)
        col_wert, col_weg = st.columns([6, 1], vertical_alignment="bottom")
        col_wert.number_input(
            f"{name} ({txt('oberflaeche.annahmen_opex_einheit')})",
            min_value=0.0, step=0.5, key=schluessel,
        )
        if col_weg.button(
            "✕", key=f"{DIALOG_PRAEFIX}opex_weg_{i}",
            help=txt("oberflaeche.annahmen_opex_entfernen"),
        ):
            st.session_state[_OPEX_LISTE] = [
                z for j, z in enumerate(liste) if j != i
            ]
            # Die Werte der nachrueckenden Positionen haengen an ihrem
            # Index; ohne Raeumen zeigte die Liste danach verschobene
            # Betraege.
            _opex_werte_raeumen()
            st.rerun(scope="fragment")

    with st.expander(txt("oberflaeche.annahmen_opex_hinzufuegen")):
        col_name, col_wert, col_knopf = st.columns(
            [4, 2, 1], vertical_alignment="bottom"
        )
        name = col_name.text_input(
            txt("oberflaeche.annahmen_opex_name"),
            key=f"{DIALOG_PRAEFIX}opex_neu_name",
        )
        wert = col_wert.number_input(
            txt("oberflaeche.annahmen_opex_einheit"),
            min_value=0.0, step=0.5, key=f"{DIALOG_PRAEFIX}opex_neu_wert",
        )
        if col_knopf.button(
            txt("oberflaeche.annahmen_opex_uebernehmen_knopf"),
            key=f"{DIALOG_PRAEFIX}opex_neu_ok", width="stretch",
        ) and name.strip():
            st.session_state[_OPEX_LISTE] = [
                *st.session_state[_OPEX_LISTE], (name.strip(), float(wert))
            ]
            st.session_state[f"{DIALOG_PRAEFIX}opex_neu_name"] = ""
            st.rerun(scope="fragment")


def _opex_werte_raeumen() -> None:
    for schluessel in [
        k for k in list(st.session_state)
        if str(k).startswith(f"{DIALOG_PRAEFIX}opex_wert_")
    ]:
        st.session_state.pop(schluessel, None)


def _opex_einsammeln(inflation: float) -> list[OpexItem]:
    """Die Positionen mit EINER Inflationsrate fuer alle.

    `index_pct_pa` bleibt im Modell erhalten (Bestandsdateien fuehren es,
    und die Cashflow-Rechnung liest es je Position), wird hier aber
    einheitlich aus der Kosteninflation gesetzt. `indexierung_ab_jahr`
    steht auf 1: Die Indexierung beginnt mit dem ersten Betriebsjahr.
    """
    return [
        OpexItem(
            name=name,
            basiswert_eur_kwp=float(
                st.session_state.get(f"{DIALOG_PRAEFIX}opex_wert_{i}", wert)
            ),
            index_pct_pa=inflation,
            indexierung_ab_jahr=1,
        )
        for i, (name, wert) in enumerate(st.session_state[_OPEX_LISTE])
    ]


def render_betriebskosten(e: GlobalAssumptions) -> None:
    @st.dialog(txt("oberflaeche.annahmen_karte_betriebskosten"),
               width="large", on_dismiss=dialog_schliessen)
    def _dlg():
        _luecken_fuellen(BETRIEBSKOSTEN, e)
        _opex_ansaeen(e)
        st.caption(txt("oberflaeche.annahmen_dlg_betriebskosten_hinweis"))
        _abschnitt("oberflaeche.annahmen_standardbetriebskosten_titel")
        _opex_felder()
        _abschnitt("oberflaeche.annahmen_dlg_weitere_kosten")
        _gitter(BETRIEBSKOSTEN, 2)

        def uebernehmen():
            werte = _einsammeln(BETRIEBSKOSTEN)
            _uebernehmen(e, werte)
            # Eine Inflationsrate fuer alle Positionen - dieselbe, die
            # der Block darueber fuehrt.
            e.opex_standard = _opex_einsammeln(werte["kosten_inflation_pct_pa"])

        _fuss(uebernehmen, "betriebskosten")

    _dlg()


# --- Technische Projektdefaults ---------------------------------------------
#
# "Projektdefaults" und nicht "Technik": Was hier steht, sind
# VORSCHLAGSWERTE der Projektmaske und der Ertragsrechnung, keine Daten
# einer konkreten Anlage.

TECHNIK: tuple[Feld, ...] = (
    Feld("degradation_pct_pa", "prozent",
         "oberflaeche.annahmen_degradation_label",
         hilfe="oberflaeche.annahmen_degradation_hilfe", schritt=0.05),
    Feld("sicherheitsabschlag_pct", "prozent",
         "oberflaeche.annahmen_sicherheitsabschlag_label",
         hilfe="oberflaeche.annahmen_sicherheitsabschlag_hilfe",
         schritt=0.5, maximum=100.0),
    Feld("betriebsdauer_jahre", "zahl",
         "oberflaeche.annahmen_betrachtungsdauer_label",
         schritt=1, minimum=1, ganzzahl=True),
    Feld("einspeiselimit_pct", "prozent",
         "oberflaeche.annahmen_einspeiselimit_label",
         hilfe="oberflaeche.annahmen_einspeiselimit_hilfe",
         schritt=1.0, maximum=100.0),
    Feld("nennleistung_kwp_vorschlag", "zahl",
         "oberflaeche.annahmen_vorbelegung_leistung_label",
         schritt=100.0, minimum=1.0),
    Feld("vollbenutzungsstunden_kwh_kwp_vorschlag", "zahl",
         "oberflaeche.annahmen_vorbelegung_vbh_label",
         schritt=10.0, minimum=1.0),
)


def render_technik(e: GlobalAssumptions) -> None:
    @st.dialog(txt("oberflaeche.annahmen_karte_technik"),
               width="large", on_dismiss=dialog_schliessen)
    def _dlg():
        _luecken_fuellen(TECHNIK, e)
        st.caption(txt("oberflaeche.annahmen_dlg_technik_hinweis"))
        _abschnitt("oberflaeche.annahmen_dlg_ertragsrechnung")
        _gitter(TECHNIK[:4], 2)
        _abschnitt("oberflaeche.annahmen_vorbelegung_titel",
                   "oberflaeche.annahmen_vorbelegung_hinweis")
        _gitter(TECHNIK[4:], 2)
        epc = st.data_editor(
            pd.DataFrame(
                [{"Anlagentyp": typ, "EPC (€/kWp)": wert}
                 for typ, wert in e.epc_eur_kwp_vorschlag_je_anlagentyp.items()],
                columns=["Anlagentyp", "EPC (€/kWp)"],
            ),
            width="stretch", hide_index=True, num_rows="fixed",
            key=f"{DIALOG_PRAEFIX}epc_vorschlag",
            column_config={
                "Anlagentyp": st.column_config.TextColumn(
                    txt("oberflaeche.annahmen_vorbelegung_typ_label"),
                    disabled=True,
                ),
                "EPC (€/kWp)": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_vorbelegung_epc_label"),
                    format="%.0f", min_value=0.0,
                ),
            },
        )

        def uebernehmen():
            werte = _einsammeln(TECHNIK)
            # Ein Einspeiselimit von 0 % waere eine Anlage, die nichts
            # einspeisen darf - das Modell meint damit "keine Grenze".
            if not werte["einspeiselimit_pct"]:
                werte["einspeiselimit_pct"] = None
            _uebernehmen(e, werte)
            e.epc_eur_kwp_vorschlag_je_anlagentyp = {
                str(z["Anlagentyp"]): float(z["EPC (€/kWp)"])
                for _, z in epc.iterrows()
                if pd.notna(z["EPC (€/kWp)"])
            }

        _fuss(uebernehmen, "technik")

    _dlg()


# --- Finanzierung -----------------------------------------------------------

_TILGUNG_LABELS = {
    TilgungsArt.ANNUITAET.value: "oberflaeche.annahmen_tilgungsart_annuitaet",
    TilgungsArt.LINEAR.value: "oberflaeche.annahmen_tilgungsart_linear",
}
_ZINS_LABELS = {
    ZinsMethode.OESTERREICH.value: "oberflaeche.annahmen_zinsmethode_oesterreich",
    ZinsMethode.DEUTSCH.value: "oberflaeche.annahmen_zinsmethode_deutsch",
}

FINANZIERUNG: tuple[Feld, ...] = (
    Feld("eigenkapitalquote_pct_vorschlag", "prozent",
         "oberflaeche.annahmen_vorbelegung_ek_label",
         schritt=1.0, maximum=100.0),
    Feld("fremdkapitalzins_pct_vorschlag", "prozent",
         "oberflaeche.annahmen_vorbelegung_fk_label", schritt=0.1),
    Feld("kreditlaufzeit_jahre", "zahl",
         "oberflaeche.annahmen_kreditlaufzeit_label",
         schritt=1, minimum=1, ganzzahl=True),
    Feld("tilgungsart", "enum", "oberflaeche.annahmen_tilgungsart_label",
         enum=TilgungsArt, labels=_TILGUNG_LABELS),
    Feld("tilgungsfreies_anlaufjahr", "schalter",
         "oberflaeche.annahmen_tilgungsfreies_anlaufjahr_label",
         hilfe="oberflaeche.annahmen_tilgungsfreies_anlaufjahr_hilfe"),
    Feld("zinsmethode", "enum", "oberflaeche.annahmen_zinsmethode_label",
         hilfe="oberflaeche.annahmen_zinsmethode_hilfe",
         enum=ZinsMethode, labels=_ZINS_LABELS),
    Feld("dscr_cash_trap", "zahl",
         "oberflaeche.annahmen_dscr_cash_trap_label",
         hilfe="oberflaeche.annahmen_dscr_cash_trap_hilfe",
         schritt=0.05, maximum=5.0),
    Feld("dscr_event_of_default", "zahl",
         "oberflaeche.annahmen_dscr_event_of_default_label",
         hilfe="oberflaeche.annahmen_dscr_event_of_default_hilfe",
         schritt=0.05, maximum=5.0),
)


def render_finanzierung(e: GlobalAssumptions) -> None:
    @st.dialog(txt("oberflaeche.annahmen_karte_finanzierung"),
               width="large", on_dismiss=dialog_schliessen)
    def _dlg():
        _luecken_fuellen(FINANZIERUNG, e)
        st.caption(txt("oberflaeche.annahmen_dlg_finanzierung_hinweis"))
        _abschnitt("oberflaeche.annahmen_dlg_kapitalstruktur")
        _gitter(FINANZIERUNG[:2], 2)
        _abschnitt("oberflaeche.annahmen_dlg_kreditvertrag")
        _gitter(FINANZIERUNG[2:6], 2)
        _abschnitt("oberflaeche.annahmen_dlg_kovenanten",
                   "oberflaeche.annahmen_dlg_kovenanten_hinweis")
        _gitter(FINANZIERUNG[6:], 2)
        _fuss(lambda: _uebernehmen(e, _einsammeln(FINANZIERUNG)), "finanzierung")

    _dlg()


# --- Foerderung und Marktlogik ----------------------------------------------

_MODELL_LABELS = {
    PraemienModell.EINSEITIG_CFD.value: "oberflaeche.annahmen_modell_einseitig",
    PraemienModell.ZWEISEITIG_CFD.value: "oberflaeche.annahmen_modell_zweiseitig",
    PraemienModell.EAG_TOLERANZBAND.value: "oberflaeche.annahmen_modell_eag",
}
_REGEL_LABELS = {
    NegativeStundenRegel.SECHS_STUNDEN.value: "oberflaeche.annahmen_regel_6h",
    NegativeStundenRegel.EINE_STUNDE.value: "oberflaeche.annahmen_regel_1h",
}


def _toleranzband(stand: dict) -> bool:
    return stand.get("praemien_modell") == PraemienModell.EAG_TOLERANZBAND.value


FOERDERUNG: tuple[Feld, ...] = (
    Feld("praemien_modell", "enum",
         "oberflaeche.annahmen_praemienmodell_label",
         enum=PraemienModell, labels=_MODELL_LABELS, horizontal=False),
    Feld("negative_stunden_regel", "enum",
         "oberflaeche.annahmen_regel_label",
         enum=NegativeStundenRegel, labels=_REGEL_LABELS),
    Feld("eag_foerderdauer_jahre", "zahl",
         "oberflaeche.annahmen_eag_foerderdauer_label",
         schritt=1, minimum=1, ganzzahl=True),
    Feld("eag_rueckzahlung_ab_mw", "zahl",
         "oberflaeche.annahmen_eag_ab_mw_label",
         hilfe="oberflaeche.annahmen_eag_ab_mw_hilfe",
         schritt=0.5, aktiv=_toleranzband),
    Feld("eag_rueckzahlung_toleranzband_pct", "prozent",
         "oberflaeche.annahmen_eag_band_label",
         hilfe="oberflaeche.annahmen_eag_band_hilfe",
         schritt=5.0, aktiv=_toleranzband),
    Feld("eag_rueckzahlung_anteil_pct", "prozent",
         "oberflaeche.annahmen_eag_anteil_label",
         hilfe="oberflaeche.annahmen_eag_anteil_hilfe",
         schritt=1.0, maximum=100.0, aktiv=_toleranzband),
)


def render_foerderung(e: GlobalAssumptions) -> None:
    @st.dialog(txt("oberflaeche.annahmen_karte_foerderung"),
               width="large", on_dismiss=dialog_schliessen)
    def _dlg():
        _luecken_fuellen(FOERDERUNG, e)
        st.caption(txt("oberflaeche.annahmen_dlg_foerderung_hinweis"))
        _abschnitt("oberflaeche.annahmen_praemienmodell_titel",
                   "oberflaeche.annahmen_praemienmodell_hinweis")
        _gitter(FOERDERUNG[:1], 1)
        _gitter(FOERDERUNG[1:3], 2)
        _abschnitt("oberflaeche.annahmen_dlg_rueckzahlung",
                   "oberflaeche.annahmen_eag_rueckzahlung_hinweis")
        _gitter(FOERDERUNG[3:], 3)
        _fuss(lambda: _uebernehmen(e, _einsammeln(FOERDERUNG)), "foerderung")

    _dlg()


# --- Steuern ----------------------------------------------------------------
#
# Der einzige Dialog, dessen Feldbestand vom gewaehlten Modus abhaengt.
# Bewusst so: Eine universelle Maske mit ausgegrauten deutschen Feldern
# in einem oesterreichischen Modell waere schwerer zu lesen als zwei
# klare Varianten.

_TAX_LABELS = {
    TaxModus.PAUSCHAL_AUF_EBT.value: "oberflaeche.annahmen_steuermodus_pauschal",
    TaxModus.AFA_KOERPERSCHAFTSTEUER.value: "oberflaeche.annahmen_steuermodus_afa",
    TaxModus.GEWERBESTEUER_DE.value:
        "oberflaeche.annahmen_steuermodus_gewerbesteuer_de",
}

STEUERN: tuple[Feld, ...] = (
    Feld("tax_modus", "enum", "oberflaeche.annahmen_steuermodus_label",
         enum=TaxModus, labels=_TAX_LABELS, horizontal=False),
    Feld("steuersatz_pct", "prozent", "oberflaeche.annahmen_steuersatz_label",
         hilfe="oberflaeche.annahmen_steuersatz_hilfe",
         schritt=0.5, maximum=100.0),
    Feld("verlustvortrag_verrechnungsgrenze_pct", "prozent",
         "oberflaeche.annahmen_verlustvortrag_label",
         hilfe="oberflaeche.annahmen_verlustvortrag_hilfe",
         schritt=5.0, maximum=100.0),
    Feld("afa_nutzungsdauer_jahre", "zahl",
         "oberflaeche.annahmen_afa_nutzungsdauer_label",
         hilfe="oberflaeche.annahmen_afa_nutzungsdauer_hilfe",
         schritt=1, minimum=1, ganzzahl=True),
    Feld("freibetrag_eur", "zahl", "oberflaeche.annahmen_freibetrag_label",
         schritt=100.0),
    Feld("gewerbesteuer_hebesatz_pct", "zahl",
         "oberflaeche.annahmen_gewerbesteuer_hebesatz_label",
         hilfe="oberflaeche.annahmen_gewerbesteuer_hebesatz_hilfe",
         schritt=10.0),
    Feld("gewerbesteuer_freibetrag_eur", "zahl",
         "oberflaeche.annahmen_gewerbesteuer_freibetrag_label",
         hilfe="oberflaeche.annahmen_gewerbesteuer_freibetrag_hilfe",
         schritt=500.0),
)

#: Feldname -> Feld, damit die modusabhaengigen Bloecke lesbar bleiben.
_STEUER = {f.name: f for f in STEUERN}


def render_steuern(e: GlobalAssumptions) -> None:
    @st.dialog(txt("oberflaeche.annahmen_karte_steuern"),
               width="large", on_dismiss=dialog_schliessen)
    def _dlg():
        _luecken_fuellen(STEUERN, e)
        st.caption(txt("oberflaeche.annahmen_dlg_steuern_hinweis"))
        _gitter((_STEUER["tax_modus"],), 1)
        modus = st.session_state[_schluessel(_STEUER["tax_modus"])]

        if modus == TaxModus.GEWERBESTEUER_DE.value:
            st.caption(txt("oberflaeche.annahmen_gewerbesteuer_hinweis"))
            _gitter((_STEUER["afa_nutzungsdauer_jahre"],
                     _STEUER["gewerbesteuer_hebesatz_pct"],
                     _STEUER["gewerbesteuer_freibetrag_eur"]), 3)
            hebesatz = st.session_state[
                _schluessel(_STEUER["gewerbesteuer_hebesatz_pct"])
            ]
            st.caption(txt(
                "oberflaeche.annahmen_gewerbesteuer_effektiv_hinweis",
                satz=f"{0.035 * (float(hebesatz) / 100) * 100:.2f}",
            ))
            gezeigt = ("tax_modus", "afa_nutzungsdauer_jahre",
                       "gewerbesteuer_hebesatz_pct",
                       "gewerbesteuer_freibetrag_eur")
        else:
            _gitter((_STEUER["steuersatz_pct"],
                     _STEUER["verlustvortrag_verrechnungsgrenze_pct"]), 2)
            gezeigt = ("tax_modus", "steuersatz_pct",
                       "verlustvortrag_verrechnungsgrenze_pct")
            if modus == TaxModus.AFA_KOERPERSCHAFTSTEUER.value:
                _gitter((_STEUER["afa_nutzungsdauer_jahre"],
                         _STEUER["freibetrag_eur"]), 2)
                gezeigt += ("afa_nutzungsdauer_jahre", "freibetrag_eur")
            else:
                st.caption(txt("oberflaeche.annahmen_afa_pauschal_hinweis"))

        def uebernehmen():
            # Nur die GEZEIGTEN Felder: Ein Feld, das dieser Modus nicht
            # fuehrt, behaelt seinen Wert im Entwurf - sonst uebernaehme
            # ein Moduswechsel stillschweigend die Vorbelegung.
            _uebernehmen(
                e, _einsammeln(tuple(_STEUER[n] for n in gezeigt))
            )

        _fuss(uebernehmen, "steuern")

    _dlg()


# --- gemeinsam --------------------------------------------------------------


def _abschnitt(titel: str, hinweis: str = "") -> None:
    st.markdown(f"**{txt(titel)}**")
    if hinweis:
        st.caption(txt(hinweis))


#: Bereich -> (Felddeklaration, Renderfunktion). Die Seite braucht beides:
#: die Felder zum Vorbelegen beim Oeffnen, die Funktion zum Zeichnen.
DIALOGE: dict[str, tuple[tuple[Feld, ...], Callable[[GlobalAssumptions], None]]] = {
    "vermarktung": (VERMARKTUNG, render_vermarktung),
    "betriebskosten": (BETRIEBSKOSTEN, render_betriebskosten),
    "technik": (TECHNIK, render_technik),
    "finanzierung": (FINANZIERUNG, render_finanzierung),
    "foerderung": (FOERDERUNG, render_foerderung),
    "steuern": (STEUERN, render_steuern),
}
