"""
Seite "Globale Annahmen": zentrale Verwaltung von Marktpreisszenarien,
Standardbetriebskosten, technischen Annahmen, Finanzierung und Steuern.

Aenderungen wirken erst nach explizitem "Speichern" - und dann automatisch
auf ALLE Projekte (die Bewertungs-Caches werden dabei invalidiert, siehe
services.save_global_assumptions).
"""

from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from app import services
from app.components import (
    assumption_dialogs,
    charts,
    data_quality,
    settings_hub,
)
from app.config import FLAGS_DIR, monate_kurz
from app.formatting import fmt_number
from engine import (
    DirektvermarktungsModus,
    GlobalAssumptions,
    MarktpreisSzenario,
    MarktSystem,
    NegativeStundenModus,
    NegativeStundenRegel,
    PraemienModell,
    TaxModus,
    TilgungsArt,
    Zeitaufloesung,
    ZinsMethode,
    io_aurora,
    io_lastgang,
)
from engine.io_aurora import AuroraImportFehler
from engine.io_lastgang import LastgangFehler
from texte import txt

#: Marktsystematik-Umschalter: Code -> (Flaggen-Datei, Textschluessel).
#: Gleiche Bild-Icon-Technik wie der Sprachumschalter in
#: streamlit_app.py (echte PNG-Flaggen statt Emoji, siehe Begruendung
#: dort und in texte.SPRACHEN).
_MARKT_SYSTEME: dict[MarktSystem, tuple[str, str]] = {
    MarktSystem.OESTERREICH: ("at", "oberflaeche.annahmen_markt_oesterreich"),
    MarktSystem.DEUTSCHLAND: ("de", "oberflaeche.annahmen_markt_deutschland"),
}


def _wechsle_markt_system(ziel: MarktSystem) -> None:
    """Stellt die Marktsystematik als Paket um und speichert sofort.

    Arbeitet auf einer frischen Kopie des GESPEICHERTEN Stands, nicht auf
    dem Entwurf: Sonst gingen alle offenen Aenderungen der Seite mit in
    die Datei, obwohl der Nutzer nur das Marktsystem umgestellt hat.
    Danach zieht `sofort_abschliessen` genau die veraenderten Felder in
    Entwurf und Basis nach - alles Uebrige bleibt offen (siehe
    settings_hub).

    Oesterreich (EAG): 6h-Regel, Koerperschaftsteuer mit AfA, act/365,
    zweiseitiger CfD mit Toleranzband (§ 10 EAG).
    Deutschland (EEG): 1h-Regel, deutsche Gewerbesteuer, 30/360,
    einseitiger CfD - das EEG kennt keine Rueckzahlung des Uebergewinns,
    oberhalb des anzulegenden Werts behaelt der Betreiber den Marktwert.
    Titelzeile und Marktpraemienseite folgen dem Schalter zur Laufzeit
    (streamlit_app.py bzw. app/views/auktion.py); die einzelnen Felder
    bleiben danach weiterhin manuell aenderbar.
    """
    vorher = settings_hub.sofort_beginnen()
    ga = vorher.model_copy(deep=True)
    ga.markt_system = ziel
    if ziel == MarktSystem.OESTERREICH:
        ga.negative_stunden_regel = NegativeStundenRegel.SECHS_STUNDEN
        ga.tax_modus = TaxModus.AFA_KOERPERSCHAFTSTEUER
        # Pflichtfeld des AfA-Modus (siehe GlobalAssumptions.check_afa_fields).
        ga.afa_nutzungsdauer_jahre = ga.afa_nutzungsdauer_jahre or 20
        ga.zinsmethode = ZinsMethode.OESTERREICH
        ga.praemien_modell = PraemienModell.EAG_TOLERANZBAND
    else:
        ga.negative_stunden_regel = NegativeStundenRegel.EINE_STUNDE
        ga.tax_modus = TaxModus.GEWERBESTEUER_DE
        ga.zinsmethode = ZinsMethode.DEUTSCH
        ga.praemien_modell = PraemienModell.EINSEITIG_CFD
    services.save_global_assumptions(ga)
    settings_hub.sofort_abschliessen(vorher)


def _render_markt_system_schalter(ga: GlobalAssumptions) -> None:
    """Flaggen-Buttons im Kopf der Seite.

    Der Wechsel ist keine Zahleneingabe, sondern eine
    Systemeinstellung: Er setzt ein ganzes Paket (Foerdermodell,
    Negativpreisregel, Steuerlogik, Zinsmethode) und speichert es
    unmittelbar. Deshalb steht er im Kopf und nicht in einer Karte - und
    deshalb wirkt er, ohne dass jemand "Speichern" drueckt.
    """
    for spalte, (system, (flagge, schluessel)) in zip(
        st.columns(2), _MARKT_SYSTEME.items(), strict=False
    ):
        with spalte:
            col_flagge, col_knopf = st.columns([1, 4], vertical_alignment="center")
            flaggen_pfad = FLAGS_DIR / f"{flagge}.png"
            if flaggen_pfad.exists():
                col_flagge.image(str(flaggen_pfad), width=26)
            if col_knopf.button(
                txt(schluessel),
                key=f"marktsystem_{flagge}",
                type="primary" if ga.markt_system == system else "secondary",
                width="stretch",
                help=txt("oberflaeche.annahmen_marktsystem_hinweis"),
            ) and ga.markt_system != system:
                _wechsle_markt_system(system)
                st.rerun()


def _datei(hochgeladen) -> tuple[bytes, str] | None:
    """Streamlit-Upload zu (Inhalt, Dateiname) - oder None."""
    return (hochgeladen.getvalue(), hochgeladen.name) if hochgeladen else None


def _aurora_import(ga: GlobalAssumptions) -> None:
    """Aurora-Marktdaten zu einem Marktpreisszenario.

    Vier Dateien liefert Aurora je Szenario: Systemdatei und
    Technologiedatei, beide in Jahres- und Monatsaufloesung. Pflicht ist
    hier allein die TECHNOLOGIEDATEI IN MONATSAUFLOESUNG - aus ihr
    stammen Capture Price, Abregelungsquoten und der Ertragsverlauf. Ohne
    Monatswerte waeren die Vertragsformen der Foerderung (zweiseitiger
    CfD, Toleranzband) nicht rechenbar, weil sich in einem Jahresmittel
    nicht mehr erkennen laesst, welche Monate ueber der
    Abschoepfungsschwelle lagen.
    """
    with st.expander(txt("oberflaeche.aurora_titel"), expanded=False):
        # Zwei Wege zu denselben Kurven: die Arbeitsmappe, die Aurora als
        # "Market Forecast Data" ausliefert, oder die vier CSV-Exporte aus
        # EOS. Die Mappe ist der kuerzere Weg (eine Datei, alle
        # Preisszenarien); die CSVs tragen dafuer die monatliche Erzeugung
        # und damit die Einspeisekurve.
        tab_mappe, tab_csv = st.tabs([
            txt("oberflaeche.aurora_tab_mappe"),
            txt("oberflaeche.aurora_tab_csv"),
        ])
        with tab_mappe:
            _aurora_arbeitsmappe(ga)
        with tab_csv:
            _aurora_csv(ga)


def _aurora_arbeitsmappe(ga: GlobalAssumptions) -> None:
    """Import aus der Aurora-Arbeitsmappe (Market Forecast Data).

    Eine Datei, drei Preisszenarien, zwei Bauformen - daraus werden
    mehrere Marktpreisszenarien auf einmal. Gesucht wird alles
    dynamisch: Aurora verschiebt zwischen den Ausgaben Kopfzeilen,
    benennt Blaetter um und fuegt Sprachspalten hinzu.
    """
    st.caption(txt("oberflaeche.aurora_mappe_hinweis"))
    hochgeladen = st.file_uploader(
        txt("oberflaeche.aurora_mappe_label"), type=["xlsx", "xlsm"],
        key="aurora_mappe", help=txt("oberflaeche.aurora_mappe_hilfe"),
    )
    if hochgeladen is None:
        return
    try:
        mappe = io_aurora.lies_arbeitsmappe(*_datei(hochgeladen))
    except AuroraImportFehler as fehler:
        st.error(str(fehler))
        return

    st.caption(
        txt("oberflaeche.aurora_mappe_gefunden",
            titel=mappe.titel or "—", geografie=mappe.geografie or "—",
            basisjahr=mappe.preisbasisjahr or "—")
    )
    col_tech, col_name = st.columns([1, 2])
    technologie = col_tech.radio(
        txt("oberflaeche.aurora_technologie_label"), mappe.technologien,
        index=(mappe.technologien.index(io_aurora.TECHNOLOGIE_STANDARD)
               if io_aurora.TECHNOLOGIE_STANDARD in mappe.technologien else 0),
        horizontal=True, help=txt("oberflaeche.aurora_bauform_hilfe"),
    )
    # Nur Herausgeber und Ausgabestand: Das Marktgebiet stand frueher
    # mit im Namen ("Aurora Q3/26 GER"), traegt aber nichts bei, solange
    # alle Mappen dasselbe Gebiet betreffen - und laesst die Legende
    # ueberlaufen.
    vorschlag = " ".join(teil for teil in ("Aurora", mappe.quartal) if teil)
    basisname = col_name.text_input(
        txt("oberflaeche.aurora_basisname_label"), value=vorschlag,
        help=txt("oberflaeche.aurora_basisname_hilfe"),
    )
    szenarien = st.multiselect(
        txt("oberflaeche.aurora_szenarien_label"), mappe.szenarien,
        default=mappe.szenarien,
        help=txt("oberflaeche.aurora_szenarien_hilfe"),
    )
    col_preis, col_infl, col_monat = st.columns(3)
    uncurtailed = col_preis.radio(
        txt("oberflaeche.aurora_preisbasis_label"), [True, False],
        format_func=lambda w: (
            txt("oberflaeche.aurora_preis_uncurtailed") if w
            else txt("oberflaeche.aurora_preis_curtailed")
        ),
        help=txt("oberflaeche.aurora_preisbasis_hilfe"),
    )
    mit_basisjahr = col_infl.checkbox(
        txt("oberflaeche.aurora_uebernimm_basisjahr"), value=True,
        help=txt("oberflaeche.aurora_uebernimm_basisjahr_hilfe"),
    )
    auf_monat = col_monat.checkbox(
        txt("oberflaeche.aurora_setze_monatsmodus"), value=True,
        key="aurora_mappe_monat",
        help=txt("oberflaeche.aurora_setze_monatsmodus_hilfe"),
    )

    if not st.button(txt("oberflaeche.aurora_importieren"), type="primary",
                     key="aurora_mappe_import"):
        return
    try:
        ergebnisse = io_aurora.importiere_arbeitsmappe(
            mappe, basisname=basisname, technologie=technologie,
            szenarien=szenarien or None, uncurtailed=uncurtailed,
        )
    except AuroraImportFehler as fehler:
        st.error(str(fehler))
        return

    namen = [e.szenario.name for e in ergebnisse]
    # Auf einer frischen Kopie des GESPEICHERTEN Stands arbeiten: Der
    # Import speichert unmittelbar, und mit dem Entwurf als Grundlage
    # gingen alle offenen Aenderungen der Seite ungefragt mit in die
    # Datei (siehe settings_hub).
    vorher = settings_hub.sofort_beginnen()
    ga = vorher.model_copy(deep=True)
    ga.marktpreisszenarien = [
        s for s in ga.marktpreisszenarien if s.name not in namen
    ] + [e.szenario for e in ergebnisse]
    if mit_basisjahr and ergebnisse[0].inflation_basisjahr:
        ga.marktpreis_inflation_basisjahr = ergebnisse[0].inflation_basisjahr
    if auf_monat:
        ga.zeitaufloesung = Zeitaufloesung.MONAT
    services.save_global_assumptions(ga)
    settings_hub.sofort_abschliessen(vorher)

    erstes = ergebnisse[0]
    st.success(
        txt("oberflaeche.aurora_mappe_erfolg", anzahl=len(ergebnisse),
            technologie=technologie, von=erstes.jahre[0], bis=erstes.jahre[1],
            namen=", ".join(namen))
    )
    for hinweis in dict.fromkeys(h for e in ergebnisse for h in e.hinweise):
        st.warning(hinweis)
    st.plotly_chart(
        charts.szenarien_linien_chart(
            [(e.szenario.name, e.szenario.marktwert_solar_ct_kwh_je_kalenderjahr)
             for e in ergebnisse],
            txt("diagramme.achse_marktwert_solar"), "ct/kWh",
        ),
        width="stretch", key="aurora_mappe_vorschau",
    )


def _aurora_csv(ga: GlobalAssumptions) -> None:
    """Import aus den vier CSV-Exporten (System/Technologie x Jahr/Monat)."""
    st.caption(txt("oberflaeche.aurora_hinweis"))

    col_t1, col_t2 = st.columns(2)
    tech_monat = col_t1.file_uploader(
        txt("oberflaeche.aurora_tech_monat"), type=["csv", "xlsx", "xlsm"],
        key="aurora_tech_monat",
        help=txt("oberflaeche.aurora_tech_monat_hilfe"),
    )
    tech_jahr = col_t2.file_uploader(
        txt("oberflaeche.aurora_tech_jahr"), type=["csv", "xlsx", "xlsm"],
        key="aurora_tech_jahr",
        help=txt("oberflaeche.aurora_tech_jahr_hilfe"),
    )
    col_s1, col_s2 = st.columns(2)
    system_jahr = col_s1.file_uploader(
        txt("oberflaeche.aurora_system_jahr"), type=["csv", "xlsx", "xlsm"],
        key="aurora_system_jahr",
        help=txt("oberflaeche.aurora_system_jahr_hilfe"),
    )
    system_monat = col_s2.file_uploader(
        txt("oberflaeche.aurora_system_monat"), type=["csv", "xlsx", "xlsm"],
        key="aurora_system_monat",
        help=txt("oberflaeche.aurora_system_monat_hilfe"),
    )

    if tech_monat is None:
        st.info(txt("oberflaeche.aurora_warte_auf_datei"))
        return

    # Die Technologieauswahl kommt aus der Datei selbst: "Solar"
    # steht je nach Marktgebiet als eigene Gruppe oder als
    # Untergruppe, das kann nur die Datei beantworten.
    try:
        auswahl = io_aurora.technologien(*_datei(tech_monat))
    except AuroraImportFehler as fehler:
        st.error(str(fehler))
        return
    if not auswahl:
        st.error(txt("oberflaeche.aurora_keine_technologien"))
        return
    vorschlag = io_aurora.vorschlag_solar(auswahl)
    technologie = st.selectbox(
        txt("oberflaeche.aurora_technologie_label"), auswahl,
        index=auswahl.index(vorschlag) if vorschlag in auswahl else 0,
        help=txt("oberflaeche.aurora_technologie_hilfe"),
    )

    col_name, col_preis = st.columns([1.2, 2])
    name = col_name.text_input(
        txt("oberflaeche.aurora_name_label"),
        value=tech_monat.name.rsplit(".", 1)[0][:40],
        help=txt("oberflaeche.aurora_name_hilfe"),
    )
    uncurtailed = col_preis.radio(
        txt("oberflaeche.aurora_preisbasis_label"),
        [True, False],
        format_func=lambda w: (
            txt("oberflaeche.aurora_preis_uncurtailed") if w
            else txt("oberflaeche.aurora_preis_curtailed")
        ),
        horizontal=True,
        help=txt("oberflaeche.aurora_preisbasis_hilfe"),
    )

    col_o1, col_o2, col_o3 = st.columns(3)
    # Vorgabe aus: Auroras Erzeugungsspalte beschreibt den Anlagenpark
    # des MARKTGEBIETS, die hinterlegte Kurve die eigene Anlage (aus
    # deren Stundenreihe abgeleitet). Angehakt ersetzte ein Reimport
    # also still die spezifischere Angabe durch die allgemeinere - eine
    # Entscheidung, die niemand getroffen hatte.
    mit_kurve = col_o1.checkbox(
        txt("oberflaeche.aurora_uebernimm_kurve"), value=False,
        help=txt("oberflaeche.aurora_uebernimm_kurve_hilfe"),
    )
    mit_inflation = col_o2.checkbox(
        txt("oberflaeche.aurora_uebernimm_inflation"), value=True,
        help=txt("oberflaeche.aurora_uebernimm_inflation_hilfe"),
    )
    auf_monat = col_o3.checkbox(
        txt("oberflaeche.aurora_setze_monatsmodus"), value=True,
        help=txt("oberflaeche.aurora_setze_monatsmodus_hilfe"),
    )

    if not st.button(txt("oberflaeche.aurora_importieren"), type="primary"):
        return

    try:
        ergebnis = io_aurora.importiere_aurora(
            name=name,
            technologie_monat=_datei(tech_monat),
            technologie_jahr=_datei(tech_jahr),
            system_jahr=_datei(system_jahr),
            system_monat=_datei(system_monat),
            technologie=technologie,
            uncurtailed=uncurtailed,
        )
    except AuroraImportFehler as fehler:
        st.error(str(fehler))
        return

    # Ein bestehendes Szenario gleichen Namens wird ersetzt, nicht
    # verdoppelt: Ein Reimport derselben Studie ist eine Korrektur.
    vorher = settings_hub.sofort_beginnen()
    ga = vorher.model_copy(deep=True)
    ga.marktpreisszenarien = [
        s for s in ga.marktpreisszenarien if s.name != ergebnis.szenario.name
    ] + [ergebnis.szenario]
    if mit_kurve and ergebnis.einspeisekurve_pct_je_monat:
        ga.einspeisekurve_pct_je_monat = ergebnis.einspeisekurve_pct_je_monat
    if mit_inflation and ergebnis.inflation_basisjahr is not None:
        ga.marktpreis_inflation_basisjahr = ergebnis.inflation_basisjahr
        if ergebnis.inflation_pct_pa is not None:
            ga.marktpreis_inflation_pct_pa = ergebnis.inflation_pct_pa
    if auf_monat:
        ga.zeitaufloesung = Zeitaufloesung.MONAT
    services.save_global_assumptions(ga)
    settings_hub.sofort_abschliessen(vorher)

    st.success(
        txt("oberflaeche.aurora_erfolg",
            name=ergebnis.szenario.name,
            technologie=ergebnis.technologie,
            von=ergebnis.jahre[0], bis=ergebnis.jahre[1],
            monatsjahre=ergebnis.monatsjahre)
    )
    if mit_inflation and ergebnis.inflation_basisjahr is not None:
        st.caption(
            txt("oberflaeche.aurora_inflation_uebernommen",
                basisjahr=ergebnis.inflation_basisjahr,
                rate=fmt_number((ergebnis.inflation_pct_pa or 0) * 100, 2))
        )
    for hinweis in ergebnis.hinweise:
        st.warning(hinweis)
    st.plotly_chart(
        charts.szenarien_linien_chart(
            [(ergebnis.szenario.name,
              ergebnis.szenario.marktwert_solar_ct_kwh_je_kalenderjahr)],
            txt("diagramme.achse_marktwert_solar"), "ct/kWh",
        ),
        width="stretch", key="aurora_vorschau",
    )


def _waehle_aus_familie(stamm: str, geschwister: list[MarktpreisSzenario]):
    """Bauform und Preisszenario innerhalb eines Jahrgangs waehlen.

    Ein Reiter fuehrt den Jahrgang ("Aurora Q3/26"), nicht die einzelne
    Kurve - sechs Szenarien je Jahrgang ergaeben sonst eine
    Reiterleiste, die man scrollen muss. Traegt ein Jahrgang nur eine
    Kurve (von Hand gepflegte Bestaende), entfaellt die Auswahl.
    """
    zerlegt = {
        s.name: io_aurora.zerlege_szenarioname(s.name) for s in geschwister
    }
    bauformen = list(dict.fromkeys(
        b for _, b, _ in zerlegt.values() if b
    ))
    preisszenarien = list(dict.fromkeys(
        p for _, _, p in zerlegt.values() if p
    ))
    if len(geschwister) == 1:
        return geschwister[0]

    col_bauform, col_preis = st.columns(2)
    bauform = bauformen[0] if bauformen else ""
    if len(bauformen) > 1:
        bauform = col_bauform.radio(
            txt("oberflaeche.annahmen_familie_bauform_label"), bauformen,
            horizontal=True, key=f"familie_bauform_{stamm}",
        )
    preisszenario = preisszenarien[0] if preisszenarien else ""
    if len(preisszenarien) > 1:
        preisszenario = col_preis.radio(
            txt("oberflaeche.annahmen_familie_preis_label"), preisszenarien,
            horizontal=True, key=f"familie_preis_{stamm}",
            help=txt("oberflaeche.annahmen_familie_preis_hilfe"),
        )
    for s in geschwister:
        _, b, p = zerlegt[s.name]
        if b == bauform and p == preisszenario:
            return s
    # Nicht jede Kombination muss vorliegen - die aelteren Jahrgaenge
    # fuehren nur Central. Dann gilt die erste passende Bauform.
    for s in geschwister:
        if zerlegt[s.name][1] == bauform:
            return s
    return geschwister[0]


#: Kennung der frei bearbeiteten Kurve im Bauform-Umschalter - sie
#: gehoert zu keiner hinterlegten Bauform.
_EIGENE_KURVE = "__eigene__"

#: Auflösungen der Profilansicht. Der Schluessel ist stabil (Sessionstate,
#: Tests), das Etikett kommt aus den Sprachdateien.
_PROFIL_MONAT = "monat"
_PROFIL_TAG = "tag"
_PROFIL_STUNDE = "stunde"
_PROFIL_TAGESGANG = "tagesgang"
_PROFIL_ANSICHTEN = [_PROFIL_MONAT, _PROFIL_TAG, _PROFIL_STUNDE, _PROFIL_TAGESGANG]


def _profil_reihen(bauformen: list[str], holen) -> list[tuple[str, list[float]]]:
    """Eine Reihe je Bauform, uebersprungen was sich nicht lesen laesst.

    Eine fehlende oder kaputte CSV darf die Annahmenseite nicht
    abbrechen - sie ist Anschauungsmaterial, keine Rechengrundlage.
    """
    reihen: list[tuple[str, list[float]]] = []
    for bauform in bauformen:
        try:
            reihen.append((bauform, list(holen(bauform))))
        except LastgangFehler:
            continue
    return reihen


def _erzeugungsprofil(ga: GlobalAssumptions) -> None:
    """Rubrik „Erzeugungsprofil": dieselbe Groesse in vier Aufloesungen.

    Gerechnet wird ausschliesslich mit den zwoelf Monatsanteilen. Die
    feineren Ansichten stehen aus zwei Gruenden hier:

    - Sie machen pruefbar, was die Monatskurve behauptet. Wer sieht,
      dass der Dezember flach ist und der April die Spitze traegt,
      erkennt eine falsche Kurve, bevor sie in einer Rendite steckt.
    - Die Stundenreihen liegen ohnehin im Repository (sie sind die
      Quelle der Monatskurven). Sollte die Rechnung eines Tages
      stundenscharf werden, ist der Ladeweg dann schon gebaut und
      geprueft.

    Der mittlere Tagesgang ist die einzige Ansicht, die etwas zeigt,
    was die Monatskurve gar nicht enthaelt: den Unterschied zwischen
    Mittagspeak und Plateau. Er wirkt im Modell ueber die Marktwertkurve
    des Szenarios, nicht ueber die Monatsanteile.
    """
    st.markdown(txt("oberflaeche.annahmen_profil_titel"))
    st.caption(txt("oberflaeche.annahmen_profil_hinweis"))

    bauformen = io_lastgang.verfuegbare_bauformen()
    if not bauformen:
        st.info(txt("oberflaeche.annahmen_profil_keine_reihen"))
        return

    etiketten = {
        _PROFIL_MONAT: txt("oberflaeche.annahmen_profil_ansicht_monat"),
        _PROFIL_TAG: txt("oberflaeche.annahmen_profil_ansicht_tag"),
        _PROFIL_STUNDE: txt("oberflaeche.annahmen_profil_ansicht_stunde"),
        _PROFIL_TAGESGANG: txt("oberflaeche.annahmen_profil_ansicht_tagesgang"),
    }
    ansicht = st.radio(
        txt("oberflaeche.annahmen_profil_ansicht_label"),
        _PROFIL_ANSICHTEN,
        format_func=lambda a: etiketten[a],
        horizontal=True,
        key="profil_ansicht",
        help=txt("oberflaeche.annahmen_profil_ansicht_hilfe"),
    )

    namen_kurz = monate_kurz()

    if ansicht == _PROFIL_MONAT:
        reihen = _profil_reihen(bauformen, io_lastgang.monatsprofil)
        # Eine von Hand gepflegte Kurve gehoert daneben - sie ist die,
        # mit der tatsaechlich gerechnet wird. Bei einer der hinterlegten
        # Bauformen laege sie deckungsgleich auf ihr und waere nur ein
        # dritter Balken ohne Aussage.
        if ga.einspeisekurve_bauform not in bauformen:
            reihen.append((
                txt("oberflaeche.annahmen_profil_serie_aktiv"),
                list(ga.einspeisekurve_pct_je_monat),
            ))
        st.plotly_chart(
            charts.erzeugung_monat_chart(reihen, bauformen, namen_kurz),
            width="stretch",
        )
        st.caption(txt("oberflaeche.annahmen_profil_monat_fussnote"))
        return

    if ansicht == _PROFIL_TAG:
        reihen = _profil_reihen(bauformen, io_lastgang.tagesprofil)
        st.plotly_chart(
            charts.erzeugung_tag_chart(
                reihen, bauformen, namen_kurz,
                io_lastgang.tagesindex_monatsgrenzen(),
            ),
            width="stretch",
        )
        st.caption(txt("oberflaeche.annahmen_profil_tag_fussnote"))
        return

    monat = _profil_monatswahl(namen_kurz, ansicht)

    if ansicht == _PROFIL_STUNDE:
        reihen = _profil_reihen(
            bauformen, lambda b: io_lastgang.stundenfenster(b, monat)
        )
        start = 0
        if monat is not None and reihen:
            start = sum(
                len(io_lastgang.stundenfenster(reihen[0][0], m))
                for m in range(1, monat)
            )
        st.plotly_chart(
            charts.erzeugung_stunde_chart(reihen, bauformen, start),
            width="stretch",
        )
        st.caption(txt("oberflaeche.annahmen_profil_stunde_fussnote"))
        return

    reihen = _profil_reihen(
        bauformen, lambda b: io_lastgang.mittlerer_tagesgang(b, monat)
    )
    st.plotly_chart(charts.tagesgang_chart(reihen, bauformen), width="stretch")
    st.caption(txt("oberflaeche.annahmen_profil_tagesgang_fussnote"))


def _profil_monatswahl(namen_kurz: list[str], ansicht: str) -> int | None:
    """Monatsfilter der beiden feinen Ansichten - None heisst ganzes Jahr.

    Nur dort, wo er etwas aendert: Die Monats- und die Tagesansicht
    zeigen ohnehin das ganze Jahr.
    """
    optionen: list[int | None] = [None] + list(range(1, 13))
    return st.selectbox(
        txt("oberflaeche.annahmen_profil_monat_label"),
        optionen,
        format_func=lambda m: (
            txt("oberflaeche.annahmen_profil_monat_alle")
            if m is None
            else namen_kurz[m - 1]
        ),
        key=f"profil_monat_{ansicht}",
        help=txt("oberflaeche.annahmen_profil_monat_hilfe"),
    )


def _bauform_auswahl(ga: GlobalAssumptions) -> None:
    """Umschalter zwischen den hinterlegten Einspeisekurven (Pult,
    Tracker - siehe EINSPEISEKURVEN_JE_BAUFORM).

    Die Auswahl wirkt sofort und nicht erst beim Speichern der Seite,
    weil die Tabelle darunter die gewaehlte Kurve zeigen muss. Wer die
    Werte danach von Hand aendert, verlaesst die Bauform - deshalb der
    dritte Eintrag "Eigene Kurve".
    """
    namen = list(ga.einspeisekurven_je_bauform)
    if not namen:
        return
    optionen = namen + [_EIGENE_KURVE]
    aktiv = (
        ga.einspeisekurve_bauform
        if ga.einspeisekurve_bauform in namen
        else _EIGENE_KURVE
    )
    wahl = st.radio(
        txt("oberflaeche.annahmen_bauform_label"),
        optionen,
        format_func=lambda n: (
            txt("oberflaeche.annahmen_bauform_eigene") if n == _EIGENE_KURVE else n
        ),
        index=optionen.index(aktiv),
        horizontal=True,
        key="einspeisekurve_bauform_wahl",
        help=txt("oberflaeche.annahmen_bauform_hilfe"),
    )
    if wahl == aktiv:
        return
    vorher = settings_hub.sofort_beginnen()
    neu_ga = vorher.model_copy(deep=True)
    if wahl == _EIGENE_KURVE:
        # Die Kurve bleibt stehen, nur die Herkunftsangabe faellt weg:
        # Wer von Hand nachbessert, rechnet nicht mehr mit der Bauform.
        neu_ga.einspeisekurve_bauform = ""
    else:
        neu_ga.einspeisekurve_bauform = wahl
        neu_ga.einspeisekurve_pct_je_monat = list(
            neu_ga.einspeisekurven_je_bauform[wahl]
        )
    # Der Editor haelt seine Aenderungen an der alten Kurve fest; ohne
    # Zuruecksetzen wuerde er die neue sofort wieder ueberschreiben.
    st.session_state.pop("einspeisekurve_editor", None)
    services.save_global_assumptions(neu_ga)
    settings_hub.sofort_abschliessen(vorher)
    st.rerun()


# ---------------------------------------------------------------------------
# Der Settings Hub
# ---------------------------------------------------------------------------
#
# Zwei Ebenen (siehe app/components/settings_hub.py):
#
#   UEBERSICHT   Karten, die den geltenden Modellzustand zeigen. Lesbar,
#                ohne dass man sie bedient.
#   BEARBEITEN   Ein Klick auf eine Karte fuehrt dorthin, wo ihre Felder
#                stehen - fuer sechs Bereiche in einen Dialog, fuer
#                "Markt & Preise" und "Daten & Import" in einen
#                Vollbreiten-Abschnitt.
#
# Warum zwei Bereiche NICHT im Dialog liegen: Markt & Preise fuehrt drei
# nebeneinanderliegende Diagramme, Szenariotabellen mit 24 Zeilen je
# Jahrgang und zwei Editoren; der Import fuehrt Dateiwahl, Vorschau und
# Optionen. Ein Dialog ist schmaler als die Seite - hier waere er eine
# Verschlechterung.

#: Die interne Bereichsnavigation. Bewusst kurz: Sie ist kein zweites
#: Hauptmenue, sondern der Wechsel zwischen Uebersicht und den beiden
#: Bereichen, die eine ganze Seite brauchen.
_NAV = (
    ("uebersicht", "oberflaeche.annahmen_nav_uebersicht"),
    ("markt", "oberflaeche.annahmen_nav_markt"),
    ("daten", "oberflaeche.annahmen_nav_daten"),
)
_NAV_KEY = "annahmen_bereich"


def _bereich() -> str:
    return st.session_state.get(_NAV_KEY, "uebersicht")


def _setze_bereich(code: str) -> None:
    st.session_state[_NAV_KEY] = code
    # Die Segmentwahl fuehrt einen eigenen Widget-Zustand; ohne
    # Zuruecksetzen spraenge sie beim naechsten Durchlauf wieder auf ihre
    # alte Auswahl, weil das Widget sie gegenueber dem Vorgabewert
    # gewinnt.
    st.session_state.pop("annahmen_navwahl", None)


# --- Kartenwerte ------------------------------------------------------------
#
# Jede Karte zeigt den EFFEKTIV geltenden Zustand, nicht das rohe Feld.
# Steht die Direktvermarktung auf "Anteil am Marktwert", nennt die Karte
# den Prozentsatz - der gespeicherte EUR/MWh-Wert wirkt dann nicht, und
# ihn trotzdem gross anzuzeigen behauptete eine Geltung, die er nicht
# hat. Dieselbe Regel gilt fuer Steuermodus, Foerdermodell und
# Zeitaufloesung.


def _lesbar_aufloesung(ga: GlobalAssumptions) -> str:
    return txt(
        "oberflaeche.annahmen_aufloesung_monat"
        if ga.zeitaufloesung == Zeitaufloesung.MONAT
        else "oberflaeche.annahmen_aufloesung_jahr"
    )


def _szenario_zeitraum(ga: GlobalAssumptions) -> str:
    """Von-bis ueber alle Szenarien - die Spanne, in der Kurven vorliegen."""
    jahre = [
        j
        for s in ga.marktpreisszenarien
        for j in s.marktwert_solar_ct_kwh_je_kalenderjahr
    ]
    return f"{min(jahre)}–{max(jahre)}" if jahre else ""


def _karte_markt(ga: GlobalAssumptions) -> tuple[str, str]:
    if not ga.marktpreisszenarien:
        return txt("oberflaeche.annahmen_karte_markt_leer"), ""
    # Das Leitszenario steht stellvertretend fuer den Jahrgang: Aus einer
    # Arbeitsmappe entstehen sechs Kurven, die alle dasselbe Datum
    # tragen. Welche ein Projekt rechnet, entscheidet das Projekt.
    leit = next(
        (s.name for s in ga.marktpreisszenarien if io_aurora.ist_leitszenario(s.name)),
        ga.marktpreisszenarien[0].name,
    )
    return leit, settings_hub.kurzfassung([
        _lesbar_aufloesung(ga),
        _szenario_zeitraum(ga),
        txt("oberflaeche.annahmen_karte_markt_anzahl",
            anzahl=len(ga.marktpreisszenarien)),
    ])


def _karte_vermarktung(ga: GlobalAssumptions) -> tuple[str, str]:
    if ga.direktvermarktung_modus == DirektvermarktungsModus.ABSOLUT:
        wert = txt("oberflaeche.annahmen_karte_dv_absolut",
                   wert=fmt_number(ga.direktvermarktungskosten_eur_kwh * 1000, 2))
    else:
        bezug = txt(
            "oberflaeche.annahmen_karte_dv_bezug_marktwert"
            if ga.direktvermarktung_modus
            == DirektvermarktungsModus.RELATIV_MARKTWERT
            else "oberflaeche.annahmen_karte_dv_bezug_grosshandel"
        )
        wert = txt("oberflaeche.annahmen_karte_dv_relativ",
                   wert=fmt_number(ga.direktvermarktung_pct_marktwert * 100, 1),
                   bezug=bezug)
    return wert, settings_hub.kurzfassung([
        txt("oberflaeche.annahmen_karte_ppa",
            preis=fmt_number(ga.ppa_preis_eur_mwh_vorschlag, 0),
            jahre=ga.ppa_laufzeit_jahre_vorschlag),
        txt("oberflaeche.annahmen_karte_ppa_anteil",
            anteil=fmt_number(ga.ppa_anteil_pct_vorschlag * 100, 0)),
    ])


def _karte_betriebskosten(ga: GlobalAssumptions) -> tuple[str, str]:
    summe = sum(i.basiswert_eur_kwp for i in ga.opex_standard)
    return (
        txt("oberflaeche.annahmen_karte_opex_inflation",
            wert=fmt_number(ga.kosten_inflation_pct_pa * 100, 1)),
        settings_hub.kurzfassung([
            txt("oberflaeche.annahmen_karte_opex_positionen",
                anzahl=len(ga.opex_standard), summe=fmt_number(summe, 1)),
            txt("oberflaeche.annahmen_karte_opex_pacht",
                wert=fmt_number(ga.pacht_umsatzbeteiligung_pct_vorschlag * 100, 1)),
        ]),
    )


def _karte_technik(ga: GlobalAssumptions) -> tuple[str, str]:
    limit = (
        txt("oberflaeche.annahmen_karte_technik_limit",
            wert=fmt_number(ga.einspeiselimit_pct * 100, 0))
        if ga.einspeiselimit_pct
        else ""
    )
    return (
        txt("oberflaeche.annahmen_karte_technik_vbh",
            wert=fmt_number(ga.vollbenutzungsstunden_kwh_kwp_vorschlag, 0)),
        settings_hub.kurzfassung([
            txt("oberflaeche.annahmen_karte_technik_degradation",
                wert=fmt_number(ga.degradation_pct_pa * 100, 2)),
            txt("oberflaeche.annahmen_karte_technik_dauer",
                jahre=ga.betriebsdauer_jahre),
            limit,
        ]),
    )


def _karte_finanzierung(ga: GlobalAssumptions) -> tuple[str, str]:
    tilgung = txt(
        "oberflaeche.annahmen_tilgungsart_annuitaet"
        if ga.tilgungsart == TilgungsArt.ANNUITAET
        else "oberflaeche.annahmen_tilgungsart_linear"
    )
    return (
        txt("oberflaeche.annahmen_karte_fin_kapital",
            ek=fmt_number(ga.eigenkapitalquote_pct_vorschlag * 100, 0),
            fk=fmt_number(ga.fremdkapitalzins_pct_vorschlag * 100, 2)),
        settings_hub.kurzfassung([
            txt("oberflaeche.annahmen_karte_fin_laufzeit",
                jahre=ga.kreditlaufzeit_jahre),
            tilgung,
            txt("oberflaeche.annahmen_karte_fin_dscr",
                wert=fmt_number(ga.dscr_cash_trap, 2)),
        ]),
    )


#: Praemienmodell -> Etikett. Dieselbe Zuordnung wie im Dialog; die
#: Karte darf keinen Enum-Wert zeigen ("PraemienModell.EAG_TOLERANZBAND").
_MODELL_KURZ = {
    PraemienModell.EINSEITIG_CFD: "oberflaeche.annahmen_karte_modell_einseitig",
    PraemienModell.ZWEISEITIG_CFD: "oberflaeche.annahmen_karte_modell_zweiseitig",
    PraemienModell.EAG_TOLERANZBAND: "oberflaeche.annahmen_karte_modell_eag",
}


def _karte_foerderung(ga: GlobalAssumptions) -> tuple[str, str]:
    regel = txt(
        "oberflaeche.annahmen_regel_6h"
        if ga.negative_stunden_regel == NegativeStundenRegel.SECHS_STUNDEN
        else "oberflaeche.annahmen_regel_1h"
    )
    # Toleranzband und Rueckzahlungsanteil gelten nur im EAG-Modell -
    # in den beiden CfD-Modellen bleiben die Felder stehen, wirken aber
    # nicht, und die Karte zeigt nur, was gilt.
    band = (
        txt("oberflaeche.annahmen_karte_foerder_band",
            wert=fmt_number(ga.eag_rueckzahlung_toleranzband_pct * 100, 0))
        if ga.praemien_modell == PraemienModell.EAG_TOLERANZBAND
        else ""
    )
    return (
        txt(_MODELL_KURZ[ga.praemien_modell]),
        settings_hub.kurzfassung([
            regel,
            txt("oberflaeche.annahmen_karte_foerder_dauer",
                jahre=ga.eag_foerderdauer_jahre),
            band,
        ]),
    )


def _karte_steuern(ga: GlobalAssumptions) -> tuple[str, str]:
    if ga.tax_modus == TaxModus.GEWERBESTEUER_DE:
        # Der Satz ergibt sich aus dem Hebesatz und wird nicht eingegeben
        # - die Karte zeigt deshalb den gerechneten Wert.
        satz = 0.035 * (ga.gewerbesteuer_hebesatz_pct / 100) * 100
        wert = txt("oberflaeche.annahmen_karte_steuer_gewerbe",
                   satz=fmt_number(satz, 2))
        sub = settings_hub.kurzfassung([
            txt("oberflaeche.annahmen_karte_steuer_hebesatz",
                wert=fmt_number(ga.gewerbesteuer_hebesatz_pct, 0)),
            txt("oberflaeche.annahmen_karte_steuer_afa",
                jahre=ga.afa_nutzungsdauer_jahre or 0),
        ])
        return wert, sub
    wert = txt("oberflaeche.annahmen_karte_steuer_satz",
               satz=fmt_number(ga.steuersatz_pct * 100, 0))
    teile = []
    if ga.tax_modus == TaxModus.AFA_KOERPERSCHAFTSTEUER:
        teile.append(txt("oberflaeche.annahmen_karte_steuer_afa",
                         jahre=ga.afa_nutzungsdauer_jahre or 0))
    else:
        teile.append(txt("oberflaeche.annahmen_karte_steuer_pauschal"))
    teile.append(txt("oberflaeche.annahmen_karte_steuer_verlustvortrag",
                     wert=fmt_number(ga.verlustvortrag_verrechnungsgrenze_pct * 100, 0)))
    return wert, settings_hub.kurzfassung(teile)


def _letztes_modelljahr() -> int | None:
    """Das spaeteste Jahr, bis zu dem irgendein Projekt rechnet.

    Die Globalen Annahmen kennen kein Startjahr - die Inbetriebnahme
    steht im Projekt. Ohne Projekte gibt es keinen Modellzeitraum, den
    eine Preiskurve verfehlen koennte; dann entfaellt die Pruefung.
    """
    projekte = services.list_projects()
    if not projekte:
        return None
    dauer = services.get_global_assumptions().betriebsdauer_jahre
    return max(p.inbetriebnahme_jahr for p in projekte) + dauer - 1


def _karte_speicher(ga: GlobalAssumptions) -> tuple[str, str]:
    """Der Investitionspreis als Hauptwert - er entscheidet ueber die
    Wirtschaftlichkeit am staerksten.

    Die Subline nennt den Markt mit, an dem gerechnet wird: Ein
    Speicherwert ohne die Angabe, WO er verdient wird, ist nicht
    einzuordnen."""
    return (
        txt("oberflaeche.annahmen_karte_speicher_capex",
            wert=fmt_number(ga.speicher_capex_leistung_eur_kw, 0),
            energie=fmt_number(ga.speicher_capex_energie_eur_kwh, 0)),
        settings_hub.kurzfassung([
            txt("oberflaeche.annahmen_karte_speicher_opex",
                wert=fmt_number(ga.speicher_opex_eur_kw_jahr, 0)),
            txt("oberflaeche.annahmen_karte_speicher_markt"),
        ]),
    )


# --- Uebersicht -------------------------------------------------------------

#: Bereich -> (Titelschluessel, Wertfunktion, Ziel). Ziel ist entweder
#: ein Dialogname oder - mit "nav:" davor - ein Bereich der internen
#: Navigation. So steht die ganze Uebersicht an EINER Stelle und nicht
#: als acht kopierte Kartenbloecke.
_KARTEN = (
    ("markt", "oberflaeche.annahmen_karte_markt", _karte_markt, "nav:markt"),
    ("vermarktung", "oberflaeche.annahmen_karte_vermarktung",
     _karte_vermarktung, "vermarktung"),
    ("betriebskosten", "oberflaeche.annahmen_karte_betriebskosten",
     _karte_betriebskosten, "betriebskosten"),
    ("technik", "oberflaeche.annahmen_karte_technik", _karte_technik, "technik"),
    ("finanzierung", "oberflaeche.annahmen_karte_finanzierung",
     _karte_finanzierung, "finanzierung"),
    ("foerderung", "oberflaeche.annahmen_karte_foerderung",
     _karte_foerderung, "foerderung"),
    ("steuern", "oberflaeche.annahmen_karte_steuern", _karte_steuern, "steuern"),
    ("speicher", "oberflaeche.annahmen_karte_speicher",
     _karte_speicher, "speicher"),
)


def _uebersicht(e: GlobalAssumptions, geaendert: set[str]) -> None:
    """Das Kartenraster - die Startansicht der Seite."""
    offen = settings_hub.aenderungen_je_bereich(geaendert)
    spalten = st.columns(3, gap="small")
    for i, (bereich, titel, wertfunktion, ziel) in enumerate(_KARTEN):
        wert, subline = wertfunktion(e)
        with spalten[i % 3], settings_hub.settings_card(
            txt(titel), wert, subline,
            geaendert=offen.get(bereich, 0), key=bereich,
        ):
            if st.button(
                txt("oberflaeche.annahmen_karte_bearbeiten"),
                key=f"gakarte_{bereich}", width="content",
            ):
                if ziel.startswith("nav:"):
                    _setze_bereich(ziel.removeprefix("nav:"))
                else:
                    assumption_dialogs.dialog_oeffnen(ziel, e)
                st.rerun()

    # Die Datenqualitaet steht zuletzt und traegt keinen
    # Bearbeiten-Knopf: Sie ist eine Auskunft ueber den Datenbestand und
    # kein Parameter, den man einstellt.
    befunde = data_quality.pruefe(e, _letztes_modelljahr())
    stufe = data_quality.gesamtstufe(befunde)
    wert, subline = data_quality.kurzfassung(befunde)
    with spalten[len(_KARTEN) % 3], settings_hub.settings_card(
        txt("oberflaeche.annahmen_karte_datenqualitaet"), wert, subline,
        status=txt(f"oberflaeche.dq_marke_{stufe}"),
        ton={"ok": "neutral", "hinweis": "warnung", "fehler": "fehler"}[stufe],
        key="datenqualitaet",
    ):
        if st.button(
            txt("oberflaeche.annahmen_karte_bearbeiten"),
            key="gakarte_datenqualitaet", width="content",
        ):
            _setze_bereich("daten")
            st.rerun()


# --- Abschnitt "Markt & Preise" ---------------------------------------------
#
# Vollbreite, aber KEIN Rueckfall in die alte Einstellungsseite: erst der
# geltende Zustand in wenigen Feldern, dann die Szenarien als kompakte
# Liste, dann die Kurven als Bild - die Zahlentabellen und der
# Kurveneditor erst auf Anforderung.


_MARKT_FELDER = (
    assumption_dialogs.Feld(
        "zeitaufloesung", "enum", "oberflaeche.annahmen_zeitaufloesung_label",
        hilfe="oberflaeche.annahmen_zeitaufloesung_hilfe",
        enum=Zeitaufloesung,
        labels={
            Zeitaufloesung.JAHR.value: "oberflaeche.annahmen_aufloesung_jahr",
            Zeitaufloesung.MONAT.value: "oberflaeche.annahmen_aufloesung_monat",
        },
    ),
    assumption_dialogs.Feld(
        "marktpreis_inflation_pct_pa", "prozent",
        "oberflaeche.annahmen_inflation_marktwerte_label", schritt=0.1,
    ),
    assumption_dialogs.Feld(
        "marktpreis_inflation_basisjahr", "zahl",
        "oberflaeche.annahmen_basisjahr_label",
        hilfe="oberflaeche.annahmen_basisjahr_hilfe",
        schritt=1, minimum=2000, maximum=2100, ganzzahl=True,
    ),
    assumption_dialogs.Feld(
        "negative_stunden_gewichtung_pct", "prozent",
        "oberflaeche.annahmen_gewichtung_label",
        schritt=5.0, maximum=100.0,
    ),
    assumption_dialogs.Feld(
        "negative_stunden_modus", "enum",
        "oberflaeche.annahmen_negativstunden_modus_label",
        hilfe="oberflaeche.annahmen_negativstunden_modus_hilfe",
        enum=NegativeStundenModus,
        labels={
            NegativeStundenModus.ABREGELUNG.value:
                "oberflaeche.annahmen_modus_abregelung",
            NegativeStundenModus.MARKTWERT.value:
                "oberflaeche.annahmen_modus_marktwert",
        },
    ),
)


def _markt_einstellungen(e: GlobalAssumptions) -> None:
    """Der Kopf des Abschnitts: was gerade gilt, in fuenf Feldern."""
    assumption_dialogs.abschnitt_rendern(_MARKT_FELDER[:3], e, 3)
    assumption_dialogs.abschnitt_rendern(_MARKT_FELDER[3:], e, 2)


def _szenarienliste(e: GlobalAssumptions) -> None:
    """Die Szenarien als kompakte Liste statt als Tabellenstapel.

    Je Jahrgang eine Zeile mit Zeitraum, Aufloesung und Anzahl der
    Kurven. Die Zahlen dahinter stehen auf Anforderung - sie sind der
    Ausnahmefall, nicht die Frage, mit der man hierherkommt.
    """
    familien: dict[str, list[MarktpreisSzenario]] = {}
    for s in e.marktpreisszenarien:
        familien.setdefault(io_aurora.zerlege_szenarioname(s.name)[0], []).append(s)
    for stamm, geschwister in familien.items():
        jahre = sorted(
            j for s in geschwister for j in s.marktwert_solar_ct_kwh_je_kalenderjahr
        )
        monatsjahre = sum(
            1 for s in geschwister if s.marktwert_solar_ct_kwh_je_monat
        )
        st.markdown(
            f'<div class="szenario-zeile">'
            f'<span class="szenario-name">{html.escape(stamm)}</span>'
            f'<span class="szenario-sub">'
            + html.escape(settings_hub.kurzfassung([
                f"{jahre[0]}–{jahre[-1]}" if jahre else "",
                txt("oberflaeche.annahmen_karte_markt_anzahl",
                    anzahl=len(geschwister)),
                txt("oberflaeche.annahmen_szenario_monatsreihen",
                    anzahl=monatsjahre) if monatsjahre else "",
            ]))
            + "</span></div>",
            unsafe_allow_html=True,
        )


def _abschnitt_markt(e: GlobalAssumptions) -> None:
    st.markdown(f"### {txt('oberflaeche.annahmen_nav_markt')}")
    st.caption(txt("oberflaeche.annahmen_szenarien_hinweis"))
    _markt_einstellungen(e)

    st.divider()
    st.markdown(f"**{txt('oberflaeche.annahmen_szenarien_uebersicht')}**")
    if not e.marktpreisszenarien:
        st.info(txt("oberflaeche.annahmen_kein_szenario"))
    else:
        _szenarienliste(e)
        _szenarien_charts(e)
        _szenarien_zahlen(e)

    st.divider()
    _neues_szenario(e)

    st.divider()
    _einspeisekurve(e)


def _szenarien_charts(e: GlobalAssumptions) -> None:
    """Die Kurven als Bild - eine Linie je Jahrgang.

    Aus einer Arbeitsmappe entstehen sechs Szenarien je Jahrgang.
    Nebeneinander gezeichnet sind das zwanzig Linien, von denen die
    meisten dasselbe sagen: Low und High sind die Spanne um Central, der
    Tracker laeuft dicht neben dem Pult.
    """
    gezeigt = [
        s for s in e.marktpreisszenarien if io_aurora.ist_leitszenario(s.name)
    ]
    verdeckt = len(e.marktpreisszenarien) - len(gezeigt)
    if verdeckt and st.checkbox(
        txt("oberflaeche.annahmen_szenarien_alle_zeigen", anzahl=verdeckt),
        key="szenarien_alle_zeigen",
        help=txt("oberflaeche.annahmen_szenarien_alle_zeigen_hilfe"),
    ):
        gezeigt = list(e.marktpreisszenarien)
    elif verdeckt:
        st.caption(
            txt("oberflaeche.annahmen_szenarien_auswahl_hinweis",
                bauform=io_aurora.TECHNOLOGIE_STANDARD,
                preisszenario=io_aurora.PREISSZENARIO_STANDARD)
        )
    if not gezeigt:
        return

    col_preis, col_baseload, col_negativ = st.columns(3)
    with col_preis:
        st.plotly_chart(
            charts.szenarien_linien_chart(
                [(s.name, s.marktwert_solar_ct_kwh_je_kalenderjahr) for s in gezeigt],
                txt("diagramme.achse_marktwert_solar"), "ct/kWh",
            ),
            width="stretch", key="szenarien_marktwert",
        )
    with col_baseload:
        # Der Grosshandelspreis ist die Bezugsgroesse der
        # Direktvermarktungskosten und der Massstab, an dem sich der
        # Marktwert Solar messen laesst (Kannibalisierung). Er kommt aus
        # dem Aurora-Import; aeltere Szenarien fuehren ihn nicht.
        if any(s.baseload_ct_kwh_je_kalenderjahr for s in gezeigt):
            st.plotly_chart(
                charts.szenarien_linien_chart(
                    [(s.name, s.baseload_ct_kwh_je_kalenderjahr) for s in gezeigt],
                    txt("diagramme.achse_grosshandelspreis"), "ct/kWh",
                ),
                width="stretch", key="szenarien_baseload",
            )
        else:
            st.info(txt("oberflaeche.annahmen_kein_baseload"))
    with col_negativ:
        st.plotly_chart(
            charts.szenarien_linien_chart(
                [
                    (s.name, {
                        j: w * 100 for j, w in
                        s.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr.items()
                    })
                    for s in gezeigt
                ],
                txt("diagramme.achse_anteil_negativ"), "%",
            ),
            width="stretch", key="szenarien_negativ",
        )


def _szenarien_zahlen(e: GlobalAssumptions) -> None:
    """Die Jahreswerte als Tabelle - auf Anforderung, je Jahrgang.

    Der Editor schreibt unmittelbar in den Entwurf: Er steht in einem
    Abschnitt, nicht in einem Dialog, und ein eigener Uebernehmen-Schritt
    je Tabelle waere hier nur eine weitere Huelle.
    """
    familien: dict[str, list[MarktpreisSzenario]] = {}
    for s in e.marktpreisszenarien:
        familien.setdefault(io_aurora.zerlege_szenarioname(s.name)[0], []).append(s)
    for stamm, geschwister in familien.items():
        if not st.checkbox(
            txt("oberflaeche.annahmen_zahlen_zeigen_jahrgang", jahrgang=stamm),
            key=f"kurven_zahlen_{stamm}",
        ):
            continue
        szenario = _waehle_aus_familie(stamm, geschwister)
        jahre = sorted(set(szenario.marktwert_solar_ct_kwh_je_kalenderjahr))
        tabelle = pd.DataFrame(
            {
                "Kalenderjahr": jahre,
                "Marktwert Solar (ct/kWh)": [
                    szenario.marktwert_solar_ct_kwh_je_kalenderjahr.get(j)
                    for j in jahre
                ],
                "Großhandelspreis (ct/kWh)": [
                    szenario.baseload_ct_kwh_je_kalenderjahr.get(j) for j in jahre
                ],
                "Erzeugungsmenge neg. Stunden 6h (%)": [
                    (szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr.get(j) or 0)
                    * 100
                    for j in jahre
                ],
                "Erzeugungsmenge neg. Stunden 1h (%)": [
                    (szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr.get(j) or 0)
                    * 100
                    for j in jahre
                ],
            }
        )
        bearbeitet = st.data_editor(
            tabelle, width="stretch", hide_index=True, num_rows="dynamic",
            key=f"szenario_editor_{szenario.name}",
            column_config={
                "Kalenderjahr": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_col_kalenderjahr"), format="%d",
                ),
                "Marktwert Solar (ct/kWh)": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_col_marktwert_solar"),
                ),
                "Großhandelspreis (ct/kWh)": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_col_baseload"),
                ),
                "Erzeugungsmenge neg. Stunden 6h (%)":
                    st.column_config.NumberColumn(
                        txt("oberflaeche.annahmen_col_neg6h"),
                    ),
                "Erzeugungsmenge neg. Stunden 1h (%)":
                    st.column_config.NumberColumn(
                        txt("oberflaeche.annahmen_col_neg1h"),
                    ),
            },
        )
        _uebernimm_szenario(e, szenario, bearbeitet)


def _uebernimm_szenario(
    e: GlobalAssumptions, szenario: MarktpreisSzenario, bearbeitet: pd.DataFrame
) -> None:
    """Baut das Szenario aus der Tabelle neu - MIT seinen Monatsreihen.

    Der Editor zeigt nur die Jahreswerte. Ein Neuaufbau ohne die
    Monatsreihen loeschte sie beim Speichern still (siehe
    tests/test_lastgang.py::test_speichern_verliert_die_kurven_nicht).
    """
    def spalte(name: str, faktor: float = 1.0) -> dict[int, float]:
        return {
            int(r["Kalenderjahr"]): float(r[name]) * faktor
            for _, r in bearbeitet.iterrows()
            if pd.notna(r["Kalenderjahr"]) and pd.notna(r[name])
        }

    neu = MarktpreisSzenario(
        name=szenario.name,
        marktwert_solar_ct_kwh_je_monat=szenario.marktwert_solar_ct_kwh_je_monat,
        erzeugungsmenge_negativ_6h_pct_je_monat=(
            szenario.erzeugungsmenge_negativ_6h_pct_je_monat
        ),
        erzeugungsmenge_negativ_1h_pct_je_monat=(
            szenario.erzeugungsmenge_negativ_1h_pct_je_monat
        ),
        baseload_ct_kwh_je_monat=szenario.baseload_ct_kwh_je_monat,
        baseload_ct_kwh_je_kalenderjahr=spalte("Großhandelspreis (ct/kWh)"),
        marktwert_solar_ct_kwh_je_kalenderjahr=spalte("Marktwert Solar (ct/kWh)"),
        erzeugungsmenge_negativ_6h_pct_je_kalenderjahr=spalte(
            "Erzeugungsmenge neg. Stunden 6h (%)", 0.01
        ),
        erzeugungsmenge_negativ_1h_pct_je_kalenderjahr=spalte(
            "Erzeugungsmenge neg. Stunden 1h (%)", 0.01
        ),
    )
    e.marktpreisszenarien = [
        neu if s.name == szenario.name else s for s in e.marktpreisszenarien
    ]


def _neues_szenario(e: GlobalAssumptions) -> None:
    """Ein leeres Szenario anlegen - in den ENTWURF, nicht in die Datei.

    Frueher wurde es sofort gespeichert. Das war schon damals eine
    Ausnahme ohne Grund: Ein leeres Szenario ist eine Eingabe wie jede
    andere und gehoert in denselben Speichervorgang.
    """
    col_name, col_knopf = st.columns([3, 1], vertical_alignment="bottom")
    name = col_name.text_input(
        txt("oberflaeche.annahmen_neues_szenario_label"),
        key="neues_szenario_name",
        placeholder=txt("oberflaeche.annahmen_neues_szenario_platzhalter"),
    )
    if col_knopf.button(
        txt("oberflaeche.annahmen_szenario_hinzufuegen"), width="stretch"
    ) and name.strip():
        if name.strip() in [s.name for s in e.marktpreisszenarien]:
            st.error(txt("oberflaeche.annahmen_szenario_existiert_bereits"))
        else:
            e.marktpreisszenarien = [
                *e.marktpreisszenarien,
                MarktpreisSzenario(name=name.strip()),
            ]
            st.rerun()


def _einspeisekurve(e: GlobalAssumptions) -> None:
    """Bauform, Monatskurve und das Erzeugungsprofil."""
    st.markdown(f"**{txt('oberflaeche.annahmen_einspeisekurve_titel')}**")
    st.caption(txt("oberflaeche.annahmen_einspeisekurve_hinweis"))
    _bauform_auswahl(services.get_global_assumptions())

    if st.checkbox(
        txt("oberflaeche.annahmen_kurve_bearbeiten"),
        key="einspeisekurve_bearbeiten",
    ):
        bearbeitet = st.data_editor(
            pd.DataFrame(
                {
                    "Monat": monate_kurz(),
                    "Anteil (%)": [w * 100 for w in e.einspeisekurve_pct_je_monat],
                }
            ),
            width="stretch", hide_index=True, key="einspeisekurve_editor",
            column_config={
                "Monat": st.column_config.TextColumn(
                    txt("oberflaeche.annahmen_col_monat"), disabled=True,
                ),
                "Anteil (%)": st.column_config.NumberColumn(
                    txt("oberflaeche.annahmen_col_anteil_jahreserzeugung"),
                    min_value=0.0, format="%.2f",
                ),
            },
        )
        anteile = [
            float(w) / 100
            for w in pd.to_numeric(
                bearbeitet["Anteil (%)"], errors="coerce"
            ).fillna(0)
        ]
        summe = sum(anteile) * 100
        st.caption(txt("oberflaeche.annahmen_einspeisekurve_summe",
                       summe=fmt_number(summe, 1)))
        # Eine leere oder nur aus Nullen bestehende Kurve waere eine
        # Anlage ohne Erzeugung - dann bleibt die bisherige stehen.
        if len(anteile) == 12 and sum(anteile) > 0:
            e.einspeisekurve_pct_je_monat = anteile

    st.divider()
    _erzeugungsprofil(e)


# --- Abschnitt "Daten & Import" ---------------------------------------------


def _abschnitt_daten(e: GlobalAssumptions) -> None:
    st.markdown(f"### {txt('oberflaeche.annahmen_nav_daten')}")

    befunde = data_quality.pruefe(e, _letztes_modelljahr())
    st.markdown(f"**{txt('oberflaeche.annahmen_karte_datenqualitaet')}**")
    st.caption(txt("oberflaeche.dq_hinweis"))
    for befund in befunde:
        if befund.stufe == "fehler":
            st.error(befund.text)
        elif befund.stufe == "hinweis":
            st.warning(befund.text)
        else:
            st.caption(f"✓ {befund.text}")

    st.divider()
    _aurora_import(e)


# --- Seite ------------------------------------------------------------------


def _kopf(e: GlobalAssumptions, geaendert: set[str]) -> None:
    """Titel, Marktsystem und die Speicherleiste.

    Der Aenderungsstand steht als Marke neben dem Titel und nicht als
    eigene Zeile: Er ist eine Randnotiz, solange nichts offen ist, und
    soll dann auch keinen Platz kosten.
    """
    marke = (
        '<span class="settings-marke">'
        + html.escape(txt("oberflaeche.annahmen_offen", anzahl=len(geaendert)))
        + "</span>"
        if geaendert
        else ""
    )
    st.markdown(
        f'<div class="settings-kopf">'
        f'<span class="settings-titel">'
        f'{html.escape(txt("oberflaeche.nav_globale_annahmen"))}</span>'
        f"{marke}</div>"
        f'<div class="settings-untertitel">'
        f'{html.escape(txt("oberflaeche.annahmen_untertitel"))}</div>',
        unsafe_allow_html=True,
    )
    col_system, col_verwerfen, col_speichern = st.columns(
        [3, 1, 1], vertical_alignment="bottom"
    )
    with col_system:
        _render_markt_system_schalter(e)
    if col_verwerfen.button(
        txt("oberflaeche.btn_verwerfen"), key="ga_verwerfen",
        width="stretch", disabled=not geaendert,
    ):
        settings_hub.entwurf_verwerfen()
        st.rerun()
    if col_speichern.button(
        txt("oberflaeche.btn_speichern"), key="ga_speichern", type="primary",
        width="stretch", disabled=not geaendert,
    ):
        settings_hub.entwurf_speichern()
        st.success(txt("oberflaeche.annahmen_gespeichert"))
        st.rerun()


def _navigation() -> str:
    codes = [code for code, _ in _NAV]
    beschriftungen = [txt(schluessel) for _, schluessel in _NAV]
    aktuell = _bereich()
    wahl = st.segmented_control(
        txt("oberflaeche.annahmen_nav_label"), beschriftungen,
        default=beschriftungen[codes.index(aktuell)],
        key="annahmen_navwahl", label_visibility="collapsed",
    )
    gewaehlt = codes[beschriftungen.index(wahl)] if wahl in beschriftungen else aktuell
    st.session_state[_NAV_KEY] = gewaehlt
    return gewaehlt


def render_assumptions() -> None:
    """Die Seite "Globale Annahmen" als Settings Hub.

    Der Ablauf ist bewusst kurz: Zustand holen, Kopf zeichnen, den
    gewaehlten Bereich zeichnen, einen etwaigen Dialog nachziehen. Alles
    Weitere steht in den Bausteinen - die View orchestriert nur.
    """
    e = settings_hub.entwurf()
    if settings_hub.aussen_geaendert():
        # Nicht stillschweigend: Ein Entwurf ist einer Fremdaenderung
        # gewichen (Wiederherstellung, zweite Sitzung).
        st.warning(txt("oberflaeche.annahmen_fremdaenderung"))
    geaendert = settings_hub.geaenderte_felder()

    _kopf(e, geaendert)
    bereich = _navigation()
    if bereich == "markt":
        _abschnitt_markt(e)
    elif bereich == "daten":
        _abschnitt_daten(e)
    else:
        _uebersicht(e, geaendert)

    # Der Dialog wird ZULETZT gezeichnet: st.dialog legt sich ueber die
    # Seite, und sein Inhalt soll den Entwurf sehen, wie ihn die
    # Abschnitte dieses Durchlaufs hinterlassen haben.
    offen = st.session_state.get(assumption_dialogs.OFFEN)
    if offen in assumption_dialogs.DIALOGE:
        assumption_dialogs.DIALOGE[offen][1](e)
