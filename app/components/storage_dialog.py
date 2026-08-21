"""
Die Speicherauslegung als Dialog.

Zustand und Muster sind dieselben wie beim Vermarktungsdialog (siehe
project_dialogs.py): dlg_*-Widgets im Dialog, "Uebernehmen" schreibt ins
Overlay, "Speichern" im Inspector schreibt in die Datei. Anders als dort
ist der Speicher EIN Feld des Projekts (`battery`) und nicht fuenf -
das Overlay traegt deshalb ein ganzes BatteryConfig-Objekt.

Warum es hier keine Live-Wirkung gibt
-------------------------------------
Der Vermarktungsdialog zeigt neben den Eingaben sofort, was sie an IRR
und NPV bewirken. Das kann er, weil eine Bewertung Millisekunden
dauert.

Beim Speicher geht das nicht. Sein Wert entsteht erst aus dem
stundenscharfen Dispatch ueber alle Betriebsjahre, und der braucht rund
eine halbe Minute - bei jedem Tastendruck im Dialog waere das
unbenutzbar. Eine SCHAETZUNG an dieser Stelle waere die schlechtere
Loesung: Sie saehe aus wie ein Ergebnis, waere aber keins, und ihr
Abstand zum echten Lauf liesse sich nicht beziffern.

Der Dialog zeigt deshalb nur, was ohne Optimierung feststeht - nutzbarer
Hub, Speicherdauer, Investition, Betriebskosten - und verweist fuer die
Wirkung auf den Speicher-Reiter, wo der Dispatch auf Knopfdruck laeuft.
"""

from __future__ import annotations

from types import SimpleNamespace

import streamlit as st

from app import services
from app.components.project_inspector import (
    einheiten_schalter,
    overlay_setzen,
    overlay_wert,
)
from app.formatting import fmt_eur_kompakt, fmt_number
from engine import BatteryConfig, GlobalAssumptions, PVProject, SpeicherModus
from engine.storage import kosten
from texte import txt

#: Das Feld, das dieser Dialog verantwortet.
SPEICHER_FELD = "battery"

#: Kennung des Dialogs in der Marke, die die Projektseite auswertet.
DIALOG = "speicher"


def _dlg_key(form_key: str, feld: str) -> str:
    return f"dlgspeicher_{form_key}_{feld}"


def auslegung(entwurf: PVProject, form_key: str) -> BatteryConfig | None:
    """Die Auslegung, die gerade gilt - Overlay vor gespeichertem Stand."""
    return overlay_wert(form_key, SPEICHER_FELD, entwurf.battery)


#: Preisfeld im Dialog -> Feld in den Projektannahmen. Die Preise sind
#: ERBFELDER: leer heisst "es gilt die globale Vorgabe". Sie stehen
#: deshalb nicht am BatteryConfig, sondern in den Abweichungen des
#: Projekts (siehe engine/models.py::Projektannahmen).
#: (Dialogkuerzel, Feld der Projektannahmen, Beschriftung, Hilfe, Schrittweite)
_PREISZEILEN: tuple[tuple[str, str, str, str, float], ...] = (
    ("capex", "speicher_capex_eur_kw",
     "oberflaeche.speicher_capex_label",
     "oberflaeche.speicher_capex_hilfe", 10.0),
    ("opex", "speicher_opex_eur_kw_jahr",
     "oberflaeche.speicher_opex_label",
     "oberflaeche.speicher_opex_hilfe", 1.0),
)

PREISFELDER: dict[str, str] = {
    kurz: feld for kurz, feld, *_ in _PREISZEILEN
}

#: Widget-Schluessel des Einheitenschalters der Investition.
_CAPEX_ABSOLUT = "capex_absolut"


def preis_abweichung(entwurf: PVProject, form_key: str, feld: str):
    """Der gesetzte Preis dieses Projekts - None heisst "folgt der Vorgabe"."""
    return overlay_wert(form_key, feld, getattr(entwurf.annahmen, feld))


def _vorgabe(entwurf: PVProject, form_key: str) -> BatteryConfig:
    """Womit der Dialog startet.

    Gibt es noch keinen Speicher, sind es die Vorgabewerte von
    BatteryConfig - aber mit `aktiv=False`. Ein Dialog, der beim blossen
    Oeffnen einen 5-MW-Speicher anlegt, haette das Projekt veraendert,
    ohne dass jemand etwas eingestellt hat.
    """
    vorhanden = auslegung(entwurf, form_key)
    return vorhanden or BatteryConfig(aktiv=False)


def dialog_state_setzen(form_key: str, entwurf: PVProject) -> None:
    """Belegt die dlg_*-Widgets aus dem aktuellen Entwurf vor.

    Gerufen beim OEFFNEN - aus demselben Grund wie beim
    Vermarktungsdialog: Nur so startet der Dialog auf dem Stand, den der
    Inspector zeigt, auch nach einem Verlassen ueber das Kreuz.
    """
    b = _vorgabe(entwurf, form_key)
    werte = {
        "aktiv": b.aktiv,
        "modus": b.modus,
        "leistung": float(b.leistung_mw),
        "kapazitaet": float(b.kapazitaet_mwh),
        "rte": float(b.roundtrip_wirkungsgrad * 100),
        "soc_min": float(b.soc_min_pct * 100),
        "soc_max": float(b.soc_max_pct * 100),
        "soc_start": float(b.soc_start_pct * 100),
        "degradation": float(b.degradationskosten_eur_mwh),
        "netzbezug": float(b.netzbezug_limit_mw),
    }
    # Die Preise bleiben LEER, wenn das Projekt der Vorgabe folgt - None
    # und nicht der Vorgabewert selbst. Stuende der Vorgabewert im Feld,
    # liesse sich "folgt der Vorgabe" nicht mehr von "zufaellig derselbe
    # Betrag" unterscheiden, und das Uebernehmen schriebe die Vorgabe als
    # Abweichung fest - eine spaetere Preissenkung erreichte das Projekt
    # dann nie mehr.
    for kurz, feld in PREISFELDER.items():
        gesetzt = preis_abweichung(entwurf, form_key, feld)
        werte[kurz] = None if gesetzt is None else float(gesetzt)
    for feld, wert in werte.items():
        st.session_state[_dlg_key(form_key, feld)] = wert


def dialog_state_leeren(form_key: str) -> None:
    for feld in ("aktiv", "modus", "leistung", "kapazitaet", "rte", "soc_min",
                 "soc_max", "soc_start", "degradation", "netzbezug",
                 *PREISFELDER):
        st.session_state.pop(_dlg_key(form_key, feld), None)


def zusammenfassung(b: BatteryConfig | None) -> str:
    """Die Kurzfassung auf der Karte.

    Leistung, Kapazitaet und Betriebsart zusammen in EINER Zeile - sie
    sagen nur zusammen etwas aus. Dieselbe Darstellung wie im
    Variantenvergleich (app/components/varianten.py::_speicher), damit
    Karte und Vergleichstabelle nicht zwei Schreibweisen fuer dieselbe
    Auslegung haben.
    """
    if b is None or not b.wirksam:
        return txt("oberflaeche.speicher_karte_keiner")
    return txt(
        "oberflaeche.speicher_karte_kurz",
        leistung=fmt_number(b.leistung_mw, 1),
        kapazitaet=fmt_number(b.kapazitaet_mwh, 1),
        modus=_modus_label(b.modus),
    )


def _modus_label(modus: SpeicherModus) -> str:
    return txt(
        "oberflaeche.speicher_modus_gruenstrom"
        if modus == SpeicherModus.GRUENSTROM
        else "oberflaeche.speicher_modus_graustrom"
    )


def render_speicher_dialog(entwurf: PVProject, form_key: str) -> None:
    """Baut den Dialog. Aufzurufen, wenn er geoeffnet werden soll."""

    def _schliessen() -> None:
        st.session_state.pop(f"{form_key}__dialog_offen", None)

    @st.dialog(
        txt("oberflaeche.speicher_dialog_titel"),
        width="large", on_dismiss=_schliessen,
    )
    def _dialog():
        st.caption(txt(
            "oberflaeche.speicher_dialog_untertitel", projekt=entwurf.anzeigename
        ))
        # Auch hier, nicht nur im Reiter: Wer die Auslegung einstellt,
        # trifft damit eine Vermarktungsannahme mit - und soll sie
        # sehen, bevor er Leistung und Kapazitaet waehlt.
        st.info(txt("oberflaeche.speicher_markt_hinweis"))
        vorgaben = services.get_global_assumptions()
        links, rechts = st.columns([0.58, 0.42], gap="large")
        with links:
            neu, preise = _eingaben(form_key, vorgaben)
        with rechts:
            _kennzahlen(neu, preise, vorgaben)

        st.divider()
        col_leer, col_ab, col_ok = st.columns([0.4, 0.3, 0.3])
        if col_ab.button(
            txt("oberflaeche.btn_abbrechen"),
            key=f"dlgspbtn_{form_key}_ab", width="stretch",
        ):
            _schliessen()
            st.rerun()
        # Gesperrt, solange die Eingabe sich widerspricht: `neu` ist dann
        # None, und ein Uebernehmen schriebe None ins Overlay - es
        # LOESCHTE also den Speicher, statt die fehlerhafte Aenderung
        # abzulehnen. Genau die stille Zerstoerung, gegen die der
        # Fehlerhinweis daneben steht.
        if col_ok.button(
            txt("oberflaeche.dialog_uebernehmen"),
            key=f"dlgspbtn_{form_key}_ok", type="primary", width="stretch",
            disabled=neu is None,
        ):
            # Auslegung UND Preisabweichungen wandern gemeinsam ins
            # Overlay - sie werden in einem Zug eingestellt und muessen
            # in einem Zug uebernommen werden. Die Preise landen dabei
            # nicht am Speicher, sondern in den Abweichungen des
            # Projekts (siehe project_form.SPEICHER_PREISFELDER).
            overlay_setzen(form_key, {SPEICHER_FELD: neu, **preise})
            _schliessen()
            st.rerun()
        del col_leer

    _dialog()


def _eingaben(
    form_key: str, vorgaben: GlobalAssumptions
) -> tuple[BatteryConfig | None, dict]:
    """Die Eingabeseite - und die einzige Stelle, die dlg_*-Keys liest.

    Rueckgabe: die Auslegung und die Preis-ABWEICHUNGEN. Zweiteres ist
    ein dict nach Feldnamen der Projektannahmen, in dem None bedeutet
    "folgt der globalen Vorgabe".
    """
    aktiv = st.toggle(
        txt("oberflaeche.speicher_aktiv_label"),
        key=_dlg_key(form_key, "aktiv"),
        help=txt("oberflaeche.speicher_aktiv_hilfe"),
    )

    modus = st.segmented_control(
        txt("oberflaeche.speicher_modus_label"),
        [SpeicherModus.GRUENSTROM, SpeicherModus.GRAUSTROM],
        format_func=_modus_label,
        key=_dlg_key(form_key, "modus"),
        disabled=not aktiv,
    )
    if modus is None:
        modus = SpeicherModus.GRUENSTROM
    st.caption(txt(
        "oberflaeche.speicher_modus_hilfe_gruenstrom"
        if modus == SpeicherModus.GRUENSTROM
        else "oberflaeche.speicher_modus_hilfe_graustrom"
    ))

    col1, col2 = st.columns(2)
    leistung = col1.number_input(
        txt("oberflaeche.speicher_leistung_label"), min_value=0.0, step=0.5,
        key=_dlg_key(form_key, "leistung"), disabled=not aktiv,
        help=txt("oberflaeche.speicher_leistung_hilfe"),
    )
    kapazitaet = col2.number_input(
        txt("oberflaeche.speicher_kapazitaet_label"), min_value=0.0, step=1.0,
        key=_dlg_key(form_key, "kapazitaet"), disabled=not aktiv,
        help=txt("oberflaeche.speicher_kapazitaet_hilfe"),
    )

    col3, col4 = st.columns(2)
    rte = col3.number_input(
        txt("oberflaeche.speicher_rte_label"),
        min_value=1.0, max_value=100.0, step=1.0,
        key=_dlg_key(form_key, "rte"), disabled=not aktiv,
        help=txt("oberflaeche.speicher_rte_hilfe"),
    )
    degradation = col4.number_input(
        txt("oberflaeche.speicher_degradation_label"), min_value=0.0, step=0.5,
        key=_dlg_key(form_key, "degradation"), disabled=not aktiv,
        help=txt("oberflaeche.speicher_degradation_hilfe"),
    )

    # Der Netzbezug steht beim Graustromspeicher und sonst nirgends: Beim
    # Gruenstromspeicher ist er per Definition null, und ein Feld, das
    # nachweislich nichts bewirkt, gehoert nicht in die Maske.
    netzbezug = 0.0
    if modus == SpeicherModus.GRAUSTROM:
        netzbezug = st.number_input(
            txt("oberflaeche.speicher_netzbezug_label"), min_value=0.0, step=0.5,
            key=_dlg_key(form_key, "netzbezug"), disabled=not aktiv,
            help=txt("oberflaeche.speicher_netzbezug_hilfe"),
        )

    st.markdown(
        f'<div class="inspector-gruppe">'
        f'{txt("oberflaeche.speicher_gruppe_kosten")}</div>',
        unsafe_allow_html=True,
    )
    st.caption(txt("oberflaeche.speicher_preise_hilfe"))
    # Beim Umschalten der Einheit wird der EINGEGEBENE Wert umgerechnet,
    # nicht neu vorbelegt - eine bereits erfasste Zahl geht damit nicht
    # verloren, und ihre Bedeutung aendert sich nicht klammheimlich mit
    # der Beschriftung. Dasselbe Muster wie bei den Investkosten
    # (project_form.capex_feld).
    _einheit_umrechnen(form_key, leistung)

    preise: dict = {}
    spalten = st.columns(2)
    for spalte, (kurz, feld, label, hilfe, schritt) in zip(
        spalten, _PREISZEILEN, strict=True
    ):
        absolut = kurz == "capex" and st.session_state.get(
            _dlg_key(form_key, _CAPEX_ABSOLUT), False
        )
        # Der Platzhalter zeigt, was OHNE Angebot gilt - und das ist beim
        # Investitionsfeld keine feste Zahl mehr, sondern das Ergebnis
        # des Zweiparametermodells fuer GENAU DIESE Auslegung
        # (a * kW + b * kWh). Stuende dort weiterhin ein blosser
        # Leistungspreis, saehe man der Vorgabe nicht an, dass sie mit
        # der Kapazitaet waechst - genau die Blindheit, die das alte
        # Modell hatte.
        if kurz == "capex":
            gesamt = vorgaben.speicher_capex_leistung_eur_kw * leistung * 1000 \
                + vorgaben.speicher_capex_energie_eur_kwh * kapazitaet * 1000
            vorgabe_anzeige = (
                gesamt if absolut
                else (gesamt / (leistung * 1000) if leistung > 0 else 0.0)
            )
        else:
            vorgabe_anzeige = float(getattr(vorgaben, feld))
        # Leer heisst "folgt der Vorgabe" - dieselbe Regel und dieselbe
        # Darstellung wie bei den Erbfeldern der Parameterspalte
        # (project_form._erbe_zahl): Der Vorgabewert steht als
        # Platzhalter im leeren Feld, nicht als Wert darin.
        wert = spalte.number_input(
            txt("oberflaeche.speicher_capex_label_absolut") if absolut
            else txt(label),
            min_value=0.0, step=1000.0 if absolut else schritt,
            placeholder=txt(
                "oberflaeche.erbfeld_platzhalter",
                wert=fmt_number(vorgabe_anzeige, 0 if absolut else 2),
            ),
            key=_dlg_key(form_key, kurz), disabled=not aktiv,
            help=txt(hilfe),
        )
        if kurz == "capex":
            einheiten_schalter(
                spalte, _dlg_key(form_key, _CAPEX_ABSOLUT), f"sp_{form_key}",
                spezifisch="oberflaeche.speicher_einheit_spezifisch",
                hilfe="oberflaeche.speicher_capex_toggle_hilfe",
                disabled=not aktiv,
            )
            # Gespeichert wird IMMER je kW - eine Groesse, zwei
            # Schreibweisen. Ein Gesamtbetrag, der als solcher in den
            # Annahmen laege, muesste bei jeder Aenderung der Leistung von
            # Hand nachgezogen werden, ohne dass jemand daran erinnert.
            if absolut and wert is not None:
                wert = (wert / (leistung * 1000)) if leistung > 0 else 0.0
        preise[feld] = None if wert is None else float(wert)

    with st.expander(txt("oberflaeche.speicher_gruppe_fuellstand")):
        st.caption(txt("oberflaeche.speicher_fuellstand_hilfe"))
        col8, col9, col10 = st.columns(3)
        soc_min = col8.number_input(
            txt("oberflaeche.speicher_soc_min_label"),
            min_value=0.0, max_value=100.0, step=1.0,
            key=_dlg_key(form_key, "soc_min"), disabled=not aktiv,
        )
        soc_max = col9.number_input(
            txt("oberflaeche.speicher_soc_max_label"),
            min_value=0.0, max_value=100.0, step=1.0,
            key=_dlg_key(form_key, "soc_max"), disabled=not aktiv,
        )
        soc_start = col10.number_input(
            txt("oberflaeche.speicher_soc_start_label"),
            min_value=0.0, max_value=100.0, step=1.0,
            key=_dlg_key(form_key, "soc_start"), disabled=not aktiv,
        )

    # Der Fuellstandsbereich ist die einzige Eingabe, die sich in sich
    # widersprechen kann. Statt die Pydantic-Ausnahme durchschlagen zu
    # lassen - die im Dialog als roter Streamlit-Absturz erschiene -
    # wird sie hier abgefangen und als Satz gemeldet.
    if soc_min >= soc_max:
        st.error(txt("oberflaeche.speicher_soc_widerspruch"))
        return None, preise

    return BatteryConfig(
        aktiv=bool(aktiv),
        modus=modus,
        leistung_mw=leistung,
        kapazitaet_mwh=kapazitaet,
        roundtrip_wirkungsgrad=rte / 100,
        soc_min_pct=soc_min / 100,
        soc_max_pct=soc_max / 100,
        soc_start_pct=soc_start / 100,
        degradationskosten_eur_mwh=degradation,
        netzbezug_limit_mw=netzbezug,
    ), preise


def _einheit_umrechnen(form_key: str, leistung_mw: float) -> None:
    """Rechnet den eingetragenen Investitionsbetrag um, wenn die Einheit
    wechselt.

    Ohne diese Umrechnung bliebe die Zahl stehen und bedeutete ploetzlich
    etwas anderes: 450 wechselte von "450 EUR je kW" zu "450 EUR
    insgesamt" - ein Faktor von fuenftausend, ohne dass jemand etwas
    eingegeben haette.

    Ist das Feld leer (das Projekt folgt der Vorgabe), gibt es nichts
    umzurechnen; die Vorgabe wird ohnehin bei jedem Durchlauf frisch in
    die passende Einheit gebracht.
    """
    schalter = _dlg_key(form_key, _CAPEX_ABSOLUT)
    vorher = f"{schalter}__vorher"
    absolut = bool(st.session_state.get(schalter, False))
    zuvor = st.session_state.get(vorher)
    st.session_state[vorher] = absolut
    if zuvor is None or zuvor == absolut or leistung_mw <= 0:
        return
    feld = _dlg_key(form_key, "capex")
    wert = st.session_state.get(feld)
    if wert is None:
        return
    kw = leistung_mw * 1000
    st.session_state[feld] = (
        round(float(wert) * kw, 0) if absolut else round(float(wert) / kw, 2)
    )


def _geltend(preise: dict, vorgaben: GlobalAssumptions, feld: str) -> float:
    """Der Preis, der fuer dieses Projekt gilt: Abweichung vor Vorgabe.

    Dieselbe Regel wie in pipeline.resolve_assumptions - hier fuer die
    Anzeige im Dialog, wo das aufgeloeste Projekt noch nicht vorliegt.
    """
    gesetzt = preise.get(feld)
    return float(vorgaben.__getattribute__(feld) if gesetzt is None else gesetzt)


def _kennzahlen(
    b: BatteryConfig | None, preise: dict, vorgaben: GlobalAssumptions
) -> None:
    """Was ohne Optimierung feststeht.

    Kein IRR, kein NPV - siehe Modulkopf. Die vier Groessen hier folgen
    unmittelbar aus der Eingabe und beantworten die Fragen, die man beim
    Auslegen stellt: Wie lange haelt der Speicher durch, wie viel davon
    ist nutzbar, was kostet er.

    Investition und Betriebskosten entstehen aus derselben Formel wie im
    Cashflow (engine/storage/kosten.py); gerechnet wird hier auf einem
    Behelfssatz aus Abweichung und Vorgabe, weil im Dialog noch keine
    aufgeloesten Annahmen vorliegen. Der Weg zur Zahl ist damit
    derselbe - nur die Quelle der Preise ist eine Stufe frueher.
    """
    st.markdown(
        f'<div class="inspector-gruppe">'
        f'{txt("oberflaeche.speicher_gruppe_auslegung")}</div>',
        unsafe_allow_html=True,
    )
    if b is None or not b.wirksam:
        st.info(txt("oberflaeche.speicher_dialog_inaktiv"))
        return

    st.metric(
        txt("oberflaeche.speicher_kennzahl_dauer"),
        txt("oberflaeche.speicher_dauer_wert", stunden=fmt_number(b.dauer_h, 1)),
        help=txt("oberflaeche.speicher_kennzahl_dauer_hilfe"),
    )
    st.metric(
        txt("oberflaeche.speicher_kennzahl_hub"),
        txt(
            "oberflaeche.speicher_hub_wert",
            hub=fmt_number(b.nutzbare_kapazitaet_mwh, 1),
        ),
        help=txt("oberflaeche.speicher_kennzahl_hub_hilfe"),
    )
    # Derselbe Rechenweg wie im Cashflow: Ein gesetztes Angebot gilt,
    # sonst das Zweiparametermodell. `speicher_capex_eur_kw` bleibt
    # deshalb None, wenn das Feld leer ist - genau daran unterscheidet
    # engine/storage/kosten.py die beiden Faelle.
    behelf = SimpleNamespace(
        speicher_capex_eur_kw=preise.get("speicher_capex_eur_kw"),
        speicher_capex_leistung_eur_kw=vorgaben.speicher_capex_leistung_eur_kw,
        speicher_capex_energie_eur_kwh=vorgaben.speicher_capex_energie_eur_kwh,
        speicher_opex_eur_kw_jahr=_geltend(
            preise, vorgaben, "speicher_opex_eur_kw_jahr"
        ),
    )
    st.metric(
        txt("oberflaeche.speicher_kennzahl_capex"),
        fmt_eur_kompakt(kosten.capex_eur(b, behelf)),
        help=txt("oberflaeche.speicher_kennzahl_capex_hilfe"),
    )
    st.metric(
        txt("oberflaeche.speicher_kennzahl_opex"),
        fmt_eur_kompakt(kosten.opex_jahr_eur(b, behelf)),
        help=txt("oberflaeche.speicher_kennzahl_opex_hilfe"),
    )
    st.caption(txt("oberflaeche.speicher_dialog_wirkung_hinweis"))
