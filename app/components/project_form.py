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

import pandas as pd
import streamlit as st

from app import services
from app.config import monate
from app.formatting import fmt_number
from engine import (
    AnlagenTyp,
    CapexBreakdown,
    CapexPosition,
    DirektvermarktungsModus,
    OpexItem,
    PachtModus,
    PVProject,
)
from engine.models import pruefe_positionsname
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
    im_popover: bool,
) -> list[dict]:
    """Frei benannte Kostenpositionen als dynamische Tabelle.

    Bewusst ein `st.data_editor` mit `num_rows="dynamic"` statt einzelner
    Eingabefelder mit "+"-Knopf: Der Editor bleibt ueber alle Durchlaeufe
    EIN Widget mit stabilem Key und fuehrt die Zeilen als Daten. Widgets,
    die zwischen zwei Durchlaeufen erscheinen und verschwinden, sind in
    Streamlit ein bekanntes Risikomuster (siehe Modulkopf).

    im_popover=True (Parameterspalte): Die Tabelle steht hinter einem
    Popover, davor nur eine Zusammenfassung. Zusatzpositionen sind der
    Ausnahmefall - in der schmalen Spalte kostete die Tabelle mehr Platz,
    als sie im Alltag wert ist. Ein Popover ist dafuer das richtige
    Mittel und kein Schalter: Sein Inhalt wird bei JEDEM Durchlauf
    ausgefuehrt, das Widget existiert also auch zugeklappt weiter. Der
    frueher benutzte Schalter erzeugte den Editor beim Aufklappen und
    entfernte ihn beim Zuklappen - unfertige Zeilen gingen dabei
    verloren.

    im_popover=False (Neuanlage): unveraendert ein Schalter, der die
    Tabelle bei Bedarf einblendet - im breiten Formular ist Platz, und
    dort wird nicht im Sekundentakt gerechnet.

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

    if not im_popover:
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


#: EPC-Vorbelegung je Anlagentyp in €/kWp (Erfahrungswerte 2025/26).
EPC_DEFAULT_EUR_KWP = {"Agri-PV": 520.0, "Konventionell": 430.0}


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

    st.markdown("**Technische Anlagenparameter**")
    col1, col2, col3 = spalten(3)
    nennleistung_kwp = col1.number_input(
        "Leistung (kWp)", min_value=0.0,
        value=existing.nennleistung_kwp if existing else 5000.0,
        step=100.0, key=f"{form_key}_leistung_live",
    )
    vollbenutzungsstunden = col2.number_input(
        "Vollbenutzungsstunden (kWh/kWp)", min_value=0.0,
        value=existing.vollbenutzungsstunden_kwh_kwp if existing else 1050.0,
        step=10.0, key=f"{form_key}_vbh_live",
    )
    anlagentyp_options = ["Agri-PV", "Konventionell"]
    anlagentyp_index = (
        1 if existing and existing.anlagentyp == AnlagenTyp.KONVENTIONELL else 0
    )
    anlagentyp_label = col3.radio(
        "Anlagentyp", anlagentyp_options, index=anlagentyp_index,
        horizontal=True, key=f"{form_key}_typ_live",
    )

    col_ibn1, col_ibn2 = spalten(2)
    inbetriebnahme_jahr = col_ibn1.number_input(
        txt("oberflaeche.formular_ibn_jahr_label"), min_value=2000, max_value=2100,
        value=existing.inbetriebnahme_jahr if existing else datetime.now().year + 1,
        step=1, key=f"{form_key}_ibn_jahr_live",
    )
    inbetriebnahme_monat_label = col_ibn2.selectbox(
        txt("oberflaeche.formular_ibn_monat_label"), monate(),
        index=(existing.inbetriebnahme_monat - 1) if existing else 0,
        key=f"{form_key}_ibn_monat_live",
    )
    inbetriebnahme_monat = monate().index(inbetriebnahme_monat_label) + 1
    st.caption(txt("oberflaeche.formular_ibn_monat_hilfe"))

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

    epc_default_eur_kwp = EPC_DEFAULT_EUR_KWP[anlagentyp_label]
    c1, c2, c3, c4 = spalten(4)
    epc = capex_feld(
        c1, "EPC",
        capex_defaults.epc_eur
        if existing
        else nennleistung_kwp * epc_default_eur_kwp,
        "epc",
    )
    netzanschluss = capex_feld(
        c2, "Netzanschluss",
        capex_defaults.netzanschluss_eur if existing else nennleistung_kwp * 50.0,
        "netz",
    )
    trasse = capex_feld(
        c3, "Trasse",
        capex_defaults.trasse_eur if existing else nennleistung_kwp * 40.0,
        "trasse",
    )
    widmung = capex_feld(
        c4, "Widmung",
        capex_defaults.widmung_eur if existing else 10000.0,
        "widmung",
        default_eur_kwp=1.0,
    )
    c5, c6, c7, c8 = spalten(4)
    genehmigung = capex_feld(
        c5, "Genehmigung",
        capex_defaults.genehmigung_eur if existing else 80000.0,
        "genehmigung",
        default_eur_kwp=8.0,
    )
    sonstige_extern = capex_feld(
        c6, "Sonstige Extern",
        capex_defaults.sonstige_extern_eur if existing else 40000.0,
        "sonst",
    )
    agm = capex_feld(
        c7, "AGM", capex_defaults.agm_eur if existing else 30000.0, "agm",
    )
    m_and_a = capex_feld(
        c8, "M&A", capex_defaults.m_and_a_eur if existing else 20000.0, "ma",
    )
    c9, _, _, _ = spalten(4)
    poenale = capex_feld(
        c9, txt("oberflaeche.formular_capex_poenale"),
        capex_defaults.poenale_puffer_eur if existing else 35000.0,
        "poenale",
    )

    zusatz_capex = _positionstabelle(
        form_key=form_key,
        schluessel="capex_zusatz",
        titel=txt("oberflaeche.formular_capex_zusatz_titel"),
        hilfe=txt("oberflaeche.formular_capex_zusatz_hilfe"),
        spalte_wert=txt("oberflaeche.formular_capex_zusatz_betrag"),
        einheit="€",
        im_popover=spaltig,
        vorhandene=[
            {"Position": z.name, "Wert": z.betrag_eur}
            for z in (existing.capex.zusatzpositionen if existing else [])
        ],
    )
    zusatz_opex = _positionstabelle(
        form_key=form_key,
        schluessel="opex_zusatz",
        titel=txt("oberflaeche.formular_opex_zusatz_titel"),
        hilfe=txt("oberflaeche.formular_opex_zusatz_hilfe"),
        spalte_wert=txt("oberflaeche.formular_opex_zusatz_betrag"),
        einheit="€/kWp/Jahr",
        im_popover=spaltig,
        vorhandene=[
            {"Position": z.name, "Wert": z.basiswert_eur_kwp}
            for z in (existing.zusatz_opex if existing else [])
        ],
    )

    st.markdown("**Pacht**")
    global_assumptions = services.get_global_assumptions()
    pachtmodus_fix = txt("oberflaeche.formular_pachtmodus_fix")
    pachtmodus_umsatz = txt("oberflaeche.formular_pachtmodus_umsatzbeteiligung")
    pachtmodus_label = st.radio(
        txt("oberflaeche.formular_pachtmodus_label"),
        [pachtmodus_fix, pachtmodus_umsatz],
        index=1 if existing and existing.pacht_modus == PachtModus.UMSATZBETEILIGUNG
        else 0,
        horizontal=True, key=f"{form_key}_pachtmodus",
        help=txt("oberflaeche.formular_pachtmodus_hilfe"),
    )
    pacht_modus = (
        PachtModus.UMSATZBETEILIGUNG if pachtmodus_label == pachtmodus_umsatz
        else PachtModus.FIX
    )

    pacht_einheit = None
    if pacht_modus == PachtModus.FIX:
        pacht_einheit = st.radio(
            "Einheit", options=["€/ha/Jahr", "€/kWp/Jahr"], horizontal=True,
            key=f"{form_key}_pacht_einheit",
        )
    pacht_mode_key = f"{form_key}_pacht_mode_prev"
    pacht_mode_changed = st.session_state.get(pacht_mode_key) != (
        pachtmodus_label, pacht_einheit
    )
    st.session_state[pacht_mode_key] = (pachtmodus_label, pacht_einheit)

    with _formularrahmen(form_key, mit_formular):
        st.markdown("**Wirtschaftliche Parameter**")
        col5, col6, col7, col8 = spalten(4)
        fk_zins = col5.number_input(
            "Fremdkapitalzins (%)", min_value=0.0,
            value=existing.fremdkapitalzins_pct * 100 if existing else 4.2,
            step=0.1, key=f"{form_key}_fkzins",
        )
        ek_anteil = col6.number_input(
            "Eigenkapitalanteil (%)", min_value=0.0, max_value=100.0,
            value=existing.eigenkapitalquote_pct * 100 if existing else 20.0,
            step=1.0, key=f"{form_key}_ekanteil",
        )
        eag_zuschlag = col7.number_input(
            "EAG-Zuschlagswert (ct/kWh)", min_value=0.0,
            value=existing.eag_zuschlagswert_ct_kwh
            if existing
            else float(st.session_state.get("empfohlenes_gebot_ct", 6.5)),
            step=0.1, key=f"{form_key}_eag",
        )
        gemeindeabgabe_default = (
            existing.gemeindeabgabe_eur_mwh
            if existing
            else global_assumptions.gemeindeabgabe_eur_kwh * 1000
        )
        gemeindeabgabe_mwh = col8.number_input(
            "Gemeindeabgabe (€/MWh)", min_value=0.0,
            value=gemeindeabgabe_default, step=0.5,
            key=f"{form_key}_gemeindeabgabe",
        )
        col9, _, _, _ = spalten(4)
        direktvermarktung_default = (
            existing.direktvermarktungskosten_eur_mwh
            if existing
            else global_assumptions.direktvermarktungskosten_eur_kwh * 1000
        )
        if (
            global_assumptions.direktvermarktung_modus
            == DirektvermarktungsModus.RELATIV_MARKTWERT
        ):
            # Der projektspezifische EUR/MWh-Wert ist im Relativ-Modus ohne
            # Wirkung - er bleibt gespeichert (fuer einen spaeteren
            # Moduswechsel), wird aber nicht zur Eingabe angeboten.
            direktvermarktungskosten_mwh = direktvermarktung_default
            col9.caption(
                "DV-Kosten: "
                f"{global_assumptions.direktvermarktung_pct_marktwert * 100:.1f} % "
                "vom nominalen Jahresmarktwert (Modus 'Relativ zum Marktwert', "
                "siehe Globale Annahmen)."
            )
        else:
            direktvermarktungskosten_mwh = col9.number_input(
                "DV-Kosten (€/MWh)", min_value=0.0,
                value=direktvermarktung_default, step=0.1,
                key=f"{form_key}_direktvermarktung",
                help=txt("oberflaeche.formular_direktvermarktung_hilfe"),
            )
        if anlagentyp_label == "Konventionell":
            st.caption(txt(
                "oberflaeche.formular_konventionell_abschlag_hinweis",
                wert=f"{eag_zuschlag * 0.75:.2f}",
            ))

        szenario_namen = global_assumptions.szenario_namen or ["Aurora Q3/26 · Pult · Central"]
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

        # --- Hybride Vermarktung: PPA-Anteil -------------------------------
        # Der Anteil steht oben und allein: Er entscheidet, ob die drei
        # Vertragsfelder ueberhaupt eine Rolle spielen. Bei 0 % bleiben
        # sie sichtbar, aber gesperrt - so ist zu sehen, welche Angaben
        # ein Vertrag braucht, ohne dass sie stumm mitrechnen.
        st.markdown(txt("oberflaeche.formular_ppa_titel"))
        ppa_anteil = st.slider(
            txt("oberflaeche.formular_ppa_anteil_label"),
            min_value=0, max_value=100,
            value=int(round((existing.ppa_anteil_pct if existing else 0.0) * 100)),
            step=5, key=f"{form_key}_ppa_anteil",
            help=txt("oberflaeche.formular_ppa_anteil_hilfe"),
        )
        ohne_ppa = ppa_anteil == 0
        col_ppa1, col_ppa2, col_ppa3 = spalten(3)
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
        ppa_index = col_ppa3.number_input(
            txt("oberflaeche.formular_ppa_index_label"), min_value=0.0,
            value=((existing.ppa_indexierung_pct_pa if existing
                    else global_assumptions.ppa_indexierung_pct_pa_vorschlag) * 100),
            step=0.25, key=f"{form_key}_ppa_index", disabled=ohne_ppa,
            help=txt("oberflaeche.formular_ppa_index_hilfe"),
        )
        ppa_start = st.number_input(
            txt("oberflaeche.formular_ppa_start_label"), min_value=1,
            value=(existing.ppa_start_jahr if existing else 1),
            step=1, key=f"{form_key}_ppa_start", disabled=ohne_ppa,
            help=txt("oberflaeche.formular_ppa_start_hilfe"),
        )

        pacht_umsatzbeteiligung_pct = (
            existing.pacht_umsatzbeteiligung_pct if existing
            else global_assumptions.pacht_umsatzbeteiligung_pct_vorschlag
        )
        pacht_mindestpacht_eur_ha_jahr = (
            existing.pacht_mindestpacht_eur_ha_jahr if existing else 0.0
        )

        if pacht_modus == PachtModus.UMSATZBETEILIGUNG:
            flaeche_key = f"{form_key}_flaeche_umsatz"
            if pacht_mode_changed or flaeche_key not in st.session_state:
                st.session_state[flaeche_key] = (
                    existing.projektflaeche_ha
                    if existing and existing.projektflaeche_ha
                    else 10.0
                )
            flaeche_ha = st.number_input(
                txt("oberflaeche.formular_projektflaeche_label"),
                min_value=0.01, step=0.5, key=flaeche_key,
                help=txt("oberflaeche.formular_pacht_flaeche_umsatz_hilfe"),
            )
            col_pct, col_min = spalten(2)
            pct_key = f"{form_key}_pacht_umsatz_pct"
            if pacht_mode_changed or pct_key not in st.session_state:
                st.session_state[pct_key] = round(
                    pacht_umsatzbeteiligung_pct * 100, 2
                )
            pacht_umsatzbeteiligung_pct = col_pct.number_input(
                txt("oberflaeche.formular_pacht_umsatzbeteiligung_label"),
                min_value=0.0, max_value=100.0, step=0.1, key=pct_key,
                help=txt("oberflaeche.formular_pacht_umsatzbeteiligung_hilfe"),
            ) / 100
            min_key = f"{form_key}_pacht_mindest_ha"
            if pacht_mode_changed or min_key not in st.session_state:
                st.session_state[min_key] = pacht_mindestpacht_eur_ha_jahr
            pacht_mindestpacht_eur_ha_jahr = col_min.number_input(
                txt("oberflaeche.formular_pacht_mindestpacht_label"),
                min_value=0.0, step=50.0, key=min_key,
                help=txt("oberflaeche.formular_pacht_mindestpacht_hilfe"),
            )
            # Bleibt fuer eine eventuelle spaetere Rueckschaltung auf FIX
            # als sinnvoller Vorschlag erhalten statt auf 0 zu fallen.
            pacht_eur_kwp_jahr = existing.pacht_eur_kwp_jahr if existing else 4.0
        elif pacht_einheit == "€/ha/Jahr":
            flaeche_key = f"{form_key}_flaeche"
            if pacht_mode_changed or flaeche_key not in st.session_state:
                st.session_state[flaeche_key] = (
                    existing.projektflaeche_ha
                    if existing and existing.projektflaeche_ha
                    else 10.0
                )
            flaeche_ha = st.number_input(
                txt("oberflaeche.formular_projektflaeche_label"),
                min_value=0.01, step=0.5, key=flaeche_key,
            )

            pacht_ha_key = f"{form_key}_pacht_ha"
            if pacht_mode_changed or pacht_ha_key not in st.session_state:
                st.session_state[pacht_ha_key] = (
                    round(
                        existing.pacht_eur_kwp_jahr
                        * existing.nennleistung_kwp
                        / flaeche_ha,
                        0,
                    )
                    if existing and flaeche_ha
                    else 500.0
                )
            pacht_eur_ha = st.number_input(
                "Pacht (€/ha/Jahr)", min_value=0.0, step=10.0, key=pacht_ha_key,
            )
            pacht_eur_kwp_jahr = (
                pacht_eur_ha * flaeche_ha / nennleistung_kwp
                if nennleistung_kwp
                else 0.0
            )
        else:
            pacht_kwp_key = f"{form_key}_pacht_kwp"
            if pacht_mode_changed or pacht_kwp_key not in st.session_state:
                st.session_state[pacht_kwp_key] = (
                    existing.pacht_eur_kwp_jahr if existing else 4.0
                )
            pacht_eur_kwp_jahr = st.number_input(
                "Pacht (€/kWp/Jahr)", min_value=0.0, step=0.1, key=pacht_kwp_key,
            )
            flaeche_ha = existing.projektflaeche_ha if existing else None

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
        pacht_eur_kwp_jahr=pacht_eur_kwp_jahr,
        pacht_modus=pacht_modus,
        pacht_umsatzbeteiligung_pct=pacht_umsatzbeteiligung_pct,
        pacht_mindestpacht_eur_ha_jahr=pacht_mindestpacht_eur_ha_jahr,
        projektflaeche_ha=flaeche_ha,
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
