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
from app.config import monate, monate_kurz
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
    col1, col2 = spalten(2)
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

    epc_default_eur_kwp = EPC_DEFAULT_EUR_KWP[anlagentyp_label]

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
    global_assumptions = services.get_global_assumptions()
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

    szenario_namen = (global_assumptions.szenario_namen
                      or ["Aurora Q3/26 · Pult · Central"])
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

    with _formularrahmen(form_key, mit_formular):
        # Die Finanzierung schliesst die Maske ab: Kapitalstruktur und
        # Zins sind die letzte offene Frage, wenn Kosten und Erloese
        # stehen. Sie ist der einzige Block, der noch im Formularrahmen
        # liegt - alle uebrigen enthalten Umschalter oder Popover und
        # muessen deshalb ausserhalb von st.form stehen (siehe Modulkopf).
        st.markdown(f"**{txt('oberflaeche.formular_finanzierung_titel')}**")
        # Zwei kurze Prozentfelder passen auch in der schmalen Spalte
        # nebeneinander.
        col_ek, col_fk = st.columns(2)
        # Kurzbeschriftungen in der schmalen Spalte: "Eigenkapitalanteil"
        # bricht auf halber Spaltenbreite mitten im Wort um.
        ek_anteil = col_ek.number_input(
            "EK-Anteil (%)" if spaltig else "Eigenkapitalanteil (%)",
            min_value=0.0, max_value=100.0,
            value=existing.eigenkapitalquote_pct * 100 if existing else 20.0,
            step=1.0, key=f"{form_key}_ekanteil",
        )
        fk_zins = col_fk.number_input(
            "FK-Zins (%)" if spaltig else "Fremdkapitalzins (%)",
            min_value=0.0,
            value=existing.fremdkapitalzins_pct * 100 if existing else 4.2,
            step=0.1, key=f"{form_key}_fkzins",
        )

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
