"""
Detailbearbeitung in grossen Dialogen.

Der erste ist die Vermarktung. Sie ist der Bereich, bei dem das
Ausprobieren am meisten bringt und die Wirkung am schwersten zu erraten
ist: Ein PPA verschiebt Erloese in die Sicherheit, kostet aber Oberseite,
und ob das Projekt dadurch besser dasteht, haengt am Preisszenario.

Der Zustand im Dialog
---------------------
Drei Zustaende, streng getrennt (siehe project_inspector.py):

    1. gespeichert   - die YAML-Datei
    2. Entwurf       - Widget-Zustand der Maske + Overlay
    3. Dialogzustand - die dlg_*-Widgets, solange der Dialog offen ist

"Abbrechen" verwirft 3 und laesst 2 unberuehrt. "Aenderungen uebernehmen"
ueberfuehrt 3 nach 2. Erst "Speichern" im Inspector ueberfuehrt 2 nach 1.
Auch das Schliessen ueber das Kreuz schreibt nichts - es passiert
schlicht nichts, weil nur der Uebernehmen-Knopf ins Overlay schreibt.

Warum eigene Schluessel (dlg_...): Dieselben Keys wie in der Maske
haetten zwei Widgets mit demselben Namen ergeben, sobald der Dialog
offen ist - Streamlit fuehrt dann beide auf denselben Zustand zurueck,
und das Tippen im Dialog aenderte den Entwurf sofort. Genau das soll
"Abbrechen" ja verhindern koennen.

Fragment-Semantik
-----------------
`st.dialog` ist ein Fragment: Eine Eingabe im Dialog laeuft nur den
Dialog neu, nicht die Seite dahinter. Der Live Impact wird deshalb IM
Dialog aus einem eigens gebauten Projekt gerechnet; die Seite draussen
bleibt so lange stehen, wie sie ist. Erst das Uebernehmen loest ueber
`st.rerun()` einen vollen Durchlauf aus.
"""

from __future__ import annotations

import streamlit as st

from app import services
from app.components import charts
from app.components.project_inspector import overlay_setzen
from app.formatting import fmt_eur_kompakt, fmt_number, fmt_pct
from engine import AnlagenTyp, PVProject
from texte import txt

#: Die Felder, die dieser Dialog verantwortet. Eine Liste statt
#: verstreuter Einzelzugriffe: Sie ist zugleich die Zusammenfassung auf
#: der Karte, der Inhalt des Overlays und die Pruefliste der Tests.
VERMARKTUNG_FELDER = (
    "ppa_anteil_pct",
    "ppa_preis_eur_mwh",
    "ppa_laufzeit_jahre",
    "ppa_start_jahr",
    "ppa_indexierung_pct_pa",
)

_MIX_HYBRID = "hybrid"
_MIX_NUR_PRAEMIE = "nur_praemie"


def _dlg_key(form_key: str, feld: str) -> str:
    return f"dlg_{form_key}_{feld}"


def dialog_state_setzen(form_key: str, entwurf: PVProject) -> None:
    """Belegt die dlg_*-Widgets aus dem AKTUELLEN Entwurf vor.

    Gerufen wird das beim OEFFNEN, nicht beim Schliessen: Nur so startet
    der Dialog garantiert auf dem Stand, den der Inspector gerade zeigt -
    auch dann, wenn er beim letzten Mal ueber das Kreuz verlassen wurde.

    Gesetzt und nicht geloescht: Ein geloeschter Schluessel entsteht erst
    wieder, wenn das Widget das naechste Mal laeuft. In der Zwischenzeit
    gibt es einen Zustand, in dem das Widget im Baum steht, sein Wert
    aber nirgends - und wer ihn dann liest, faellt auf die Nase.
    """
    st.session_state[_dlg_key(form_key, "mix")] = (
        _MIX_HYBRID if entwurf.ppa_anteil_pct > 0 else _MIX_NUR_PRAEMIE
    )
    st.session_state[_dlg_key(form_key, "anteil")] = int(
        round(entwurf.ppa_anteil_pct * 100)
    )
    st.session_state[_dlg_key(form_key, "preis")] = float(entwurf.ppa_preis_eur_mwh)
    st.session_state[_dlg_key(form_key, "laufzeit")] = int(entwurf.ppa_laufzeit_jahre)
    st.session_state[_dlg_key(form_key, "start")] = int(entwurf.ppa_start_jahr)
    st.session_state[_dlg_key(form_key, "index")] = float(
        entwurf.ppa_indexierung_pct_pa * 100
    )


def _wirksames_projekt(entwurf: PVProject, werte: dict) -> PVProject:
    """Der Entwurf mit den Einstellungen des Dialogs - nur zum Rechnen.

    `model_copy(update=...)` statt einer Mutation: Der Entwurf selbst
    darf sich waehrend einer What-if-Frage nicht aendern, sonst waere
    "Abbrechen" wirkungslos.
    """
    return entwurf.model_copy(update=werte)


def _erloesmix(result) -> dict[str, float]:
    """Tatsaechliche Erloesanteile ueber die Laufzeit.

    Bewusst aus dem Cashflow und nicht aus dem PPA-Anteil: Der Anteil
    sagt, welcher Teil der MENGE unter Vertrag steht. Was davon als
    Erloes ankommt, haengt am Preis - ein PPA unter Marktwert traegt
    weniger bei, als sein Mengenanteil vermuten laesst. Die drei Spalten
    ueberschneiden sich nicht und ergeben zusammen den Erloes
    (engine/revenue.py: erloes_eur = markt + praemie - rueckzahlung).
    """
    df = result.cashflow.data
    betrieb = df[df["jahr"] >= 1]
    return {
        "ppa": float(betrieb["erloes_ppa_eur"].sum()),
        "merchant": float(betrieb["erloes_merchant_eur"].sum()),
        "praemie": float(betrieb["erloes_praemie_eur"].sum()),
    }


def _hinweis(neu, gespeichert) -> str:
    """Was die Einstellung bewirkt - ausschliesslich aus den Ergebnissen.

    Keine Interpretation, die die Zahlen nicht hergeben: Es werden genau
    die drei Groessen genannt, die sich messbar veraendert haben. Gibt
    es keine nennenswerte Aenderung, steht das auch da.
    """
    saetze: list[str] = []

    dscr_neu, dscr_alt = neu.kpis.dscr_min, gespeichert.kpis.dscr_min
    if dscr_neu is not None and dscr_alt is not None:
        unterschied = dscr_neu - dscr_alt
        if abs(unterschied) >= 0.01:
            saetze.append(txt(
                "oberflaeche.dialog_hinweis_dscr_besser"
                if unterschied > 0 else "oberflaeche.dialog_hinweis_dscr_schlechter",
                wert=fmt_number(dscr_neu, 2),
            ))

    npv_unterschied = neu.kpis.npv_eur - gespeichert.kpis.npv_eur
    if abs(npv_unterschied) >= 1000:
        saetze.append(txt(
            "oberflaeche.dialog_hinweis_wert_hoeher"
            if npv_unterschied > 0 else "oberflaeche.dialog_hinweis_wert_niedriger",
            betrag=fmt_eur_kompakt(abs(npv_unterschied)),
        ))

    irr_neu, irr_alt = neu.kpis.equity_irr, gespeichert.kpis.equity_irr
    if irr_neu is not None and irr_alt is not None:
        unterschied = irr_neu - irr_alt
        if abs(unterschied) >= 0.0005:
            saetze.append(txt(
                "oberflaeche.dialog_hinweis_irr_hoeher"
                if unterschied > 0 else "oberflaeche.dialog_hinweis_irr_niedriger",
                wert=fmt_pct(abs(unterschied), 2),
            ))

    return " ".join(saetze) if saetze else txt("oberflaeche.dialog_hinweis_neutral")


def _delta(neu: float | None, alt: float | None) -> tuple[str, str]:
    """Vorzeichenbehaftete Differenz und ihre Richtung fuer die Anzeige."""
    if neu is None or alt is None:
        return "", "neutral"
    unterschied = neu - alt
    richtung = "auf" if unterschied > 0 else ("ab" if unterschied < 0 else "neutral")
    return unterschied, richtung


def render_vermarktung_dialog(
    entwurf: PVProject, gespeichert: PVProject, form_key: str
) -> None:
    """Baut den Dialog. Aufzurufen, wenn er geoeffnet werden soll."""

    def _schliessen() -> None:
        """Das Kreuz oben rechts - es schreibt NICHTS.

        Ohne diesen Rueckruf bliebe die Marke gesetzt, und der Dialog
        ginge bei der naechsten Eingabe auf der Seite von selbst wieder
        auf. Der Dialogzustand faellt beim naechsten Oeffnen ohnehin weg
        (dialog_state_leeren) - hier ist nur die Marke zu loeschen.
        """
        st.session_state.pop(f"{form_key}__dialog_offen", None)

    @st.dialog(
        txt("oberflaeche.dialog_vermarktung_titel"),
        width="large", on_dismiss=_schliessen,
    )
    def _dialog():
        st.caption(txt(
            "oberflaeche.dialog_vermarktung_untertitel",
            projekt=entwurf.anzeigename,
        ))
        links, rechts = st.columns([0.55, 0.45], gap="large")

        with links:
            werte = _eingaben(entwurf, form_key)
        with rechts:
            _live_impact(entwurf, gespeichert, werte)

        st.divider()
        col_leer, col_ab, col_ok = st.columns([0.4, 0.3, 0.3])
        if col_ab.button(
            txt("oberflaeche.btn_abbrechen"),
            key=f"dlgbtn_{form_key}_ab", width="stretch",
        ):
            # Nichts schreiben: Der Dialogzustand faellt beim naechsten
            # Oeffnen ohnehin weg (dialog_state_leeren).
            _schliessen()
            st.rerun()
        if col_ok.button(
            txt("oberflaeche.dialog_uebernehmen"),
            key=f"dlgbtn_{form_key}_ok", type="primary", width="stretch",
        ):
            overlay_setzen(form_key, werte)
            _schliessen()
            st.rerun()
        del col_leer

    _dialog()


def _eingaben(entwurf: PVProject, form_key: str) -> dict:
    """Die linke Haelfte - und die einzige Stelle, die dlg_*-Keys setzt.

    Vorbelegt wird aus dem ENTWURF, nicht aus der gespeicherten Datei:
    Wer im Inspector schon etwas geaendert hat, soll im Dialog darauf
    aufsetzen und nicht auf einen aelteren Stand zurueckfallen.
    """
    st.markdown(
        f'<div class="inspector-gruppe">'
        f'{txt("oberflaeche.dialog_vermarktungsmix")}</div>',
        unsafe_allow_html=True,
    )

    mix = st.segmented_control(
        txt("oberflaeche.dialog_vermarktungsmix"),
        [_MIX_HYBRID, _MIX_NUR_PRAEMIE],
        format_func=lambda m: txt(
            "oberflaeche.dialog_mix_hybrid" if m == _MIX_HYBRID
            else "oberflaeche.dialog_mix_nur_praemie"
        ),
        key=_dlg_key(form_key, "mix"),
        label_visibility="collapsed",
    )
    # segmented_control gibt None zurueck, wenn der Nutzer die Auswahl
    # abwaehlt - dann gilt weiter, was vorher galt.
    if mix is None:
        mix = _MIX_HYBRID if entwurf.ppa_anteil_pct > 0 else _MIX_NUR_PRAEMIE

    nur_praemie = mix == _MIX_NUR_PRAEMIE
    anteil = st.slider(
        txt("oberflaeche.formular_ppa_anteil_label"),
        min_value=0, max_value=100, step=5,
        key=_dlg_key(form_key, "anteil"),
        disabled=nur_praemie,
        help=txt("oberflaeche.formular_ppa_anteil_hilfe"),
    )
    # "Nur Marktprämie" heisst PPA-Anteil null - der Regler behaelt dabei
    # seinen Wert, damit das Zurueckschalten nicht bei null landet.
    if nur_praemie:
        anteil = 0

    col1, col2 = st.columns(2)
    preis = col1.number_input(
        txt("oberflaeche.formular_ppa_preis_label"), min_value=0.0,
        step=1.0,
        key=_dlg_key(form_key, "preis"), disabled=nur_praemie,
        help=txt("oberflaeche.formular_ppa_preis_hilfe"),
    )
    laufzeit = col2.number_input(
        txt("oberflaeche.formular_ppa_laufzeit_label"), min_value=0,
        step=1,
        key=_dlg_key(form_key, "laufzeit"), disabled=nur_praemie,
        help=txt("oberflaeche.formular_ppa_laufzeit_hilfe"),
    )
    col3, col4 = st.columns(2)
    start = col3.number_input(
        txt("oberflaeche.formular_ppa_start_label"), min_value=1,
        step=1,
        key=_dlg_key(form_key, "start"), disabled=nur_praemie,
        help=txt("oberflaeche.formular_ppa_start_hilfe"),
    )
    index = col4.number_input(
        txt("oberflaeche.formular_ppa_index_label"), min_value=0.0,
        step=0.25,
        key=_dlg_key(form_key, "index"), disabled=nur_praemie,
        help=txt("oberflaeche.formular_ppa_index_hilfe"),
    )

    _marktpraemie_block(entwurf)

    return {
        "ppa_anteil_pct": anteil / 100,
        "ppa_preis_eur_mwh": preis,
        "ppa_laufzeit_jahre": int(laufzeit),
        "ppa_start_jahr": int(start),
        "ppa_indexierung_pct_pa": index / 100,
    }


def _marktpraemie_block(entwurf: PVProject) -> None:
    """Die Foerderseite - hier nur zum Nachsehen, nicht zum Aendern.

    Zuschlagswert und Anlagentyp entscheiden mit ueber den Erloes und
    gehoeren deshalb ins Bild, sobald man ueber Vermarktung nachdenkt.
    Geaendert werden sie in ihren eigenen Bereichen: Der Anlagentyp ist
    eine Eigenschaft der Anlage, der Zuschlagswert das Ergebnis einer
    Ausschreibung - beides keine Vermarktungsentscheidung.

    Die Beschriftungen kommen aus dem Marktsystem der globalen Annahmen
    (EAG oder EEG), damit im Deutschlandmodus nichts Oesterreichisches
    stehenbleibt.
    """
    from app.views.assumptions import _MARKT_SYSTEME

    ga = services.get_global_assumptions()
    st.markdown(
        f'<div class="inspector-gruppe">'
        f'{txt("oberflaeche.dialog_marktpraemie")}</div>',
        unsafe_allow_html=True,
    )
    system = _MARKT_SYSTEME.get(ga.markt_system)
    systemname = txt(system[1]) if system else ga.markt_system.value

    col1, col2 = st.columns(2)
    col1.metric(
        txt("oberflaeche.dialog_zuschlagswert", system=systemname),
        f"{fmt_number(entwurf.eag_zuschlagswert_effektiv_ct_kwh, 2)} ct/kWh",
    )
    col2.metric(
        txt("oberflaeche.formular_anlagentyp_label"),
        (txt("oberflaeche.badge_agri")
         if entwurf.anlagentyp == AnlagenTyp.AGRI_PV
         else txt("oberflaeche.badge_konventionell")),
    )


def _live_impact(entwurf: PVProject, gespeichert: PVProject, werte: dict) -> None:
    """Die rechte Haelfte: was die Einstellung wirtschaftlich bedeutet.

    Genau EINE Bewertung je Zustand - das Ergebnis traegt alle drei
    Anzeigen. `services.get_valuation_fuer` cacht ueber die JSON-Fassung
    des Projekts, ein unveraenderter Zustand kostet also gar nichts.

    Verglichen wird immer mit dem GESPEICHERTEN Stand, nicht mit dem
    Zustand beim Oeffnen: Die Frage lautet "was aendert sich gegenueber
    dem, was auf der Platte liegt", und darauf muss dieselbe Antwort
    stehen, egal wie oft der Dialog zwischendurch auf war.
    """
    st.markdown(
        f'<div class="inspector-gruppe">'
        f'{txt("oberflaeche.dialog_live_impact")}</div>',
        unsafe_allow_html=True,
    )

    ergebnis = services.get_valuation_fuer(_wirksames_projekt(entwurf, werte))
    referenz = services.get_valuation_fuer(gespeichert)

    _impact_kachel(
        txt("oberflaeche.projekt_kpi_irr"),
        fmt_pct(ergebnis.kpis.equity_irr, 1)
        if ergebnis.kpis.equity_irr is not None else "—",
        *_delta(ergebnis.kpis.equity_irr, referenz.kpis.equity_irr),
        einheit="pp",
    )
    _impact_kachel(
        txt("oberflaeche.projekt_kpi_equity_value"),
        fmt_eur_kompakt(ergebnis.kpis.npv_eur),
        *_delta(ergebnis.kpis.npv_eur, referenz.kpis.npv_eur),
        einheit="eur",
    )

    st.markdown(f"**{txt('oberflaeche.dialog_erloesmix')}**")
    st.plotly_chart(
        charts.erloesmix_balken(_erloesmix(ergebnis)),
        width="stretch", config={"displayModeBar": False},
    )
    st.caption(_hinweis(ergebnis, referenz))


def _impact_kachel(titel: str, wert: str, unterschied, richtung: str,
                   *, einheit: str) -> None:
    """Eine Kennzahl mit ihrer Veraenderung gegenueber gespeichert."""
    if unterschied == "" or richtung == "neutral":
        zusatz = txt("oberflaeche.dialog_unveraendert")
    else:
        pfeil = "▲" if richtung == "auf" else "▼"
        betrag = (
            fmt_pct(abs(unterschied), 1) + " " + txt("oberflaeche.einheit_prozentpunkte")
            if einheit == "pp"
            else fmt_eur_kompakt(abs(unterschied))
        )
        vorzeichen = "+" if richtung == "auf" else "−"
        zusatz = f"{pfeil} {vorzeichen}{betrag}"

    st.markdown(
        f'<div class="impact-kachel">'
        f'<div class="impact-titel">{titel}</div>'
        f'<div class="impact-wert">{wert}</div>'
        f'<div class="impact-delta impact-{richtung}">{zusatz}</div>'
        f'<div class="impact-fuss">{txt("oberflaeche.dialog_vs_gespeichert")}</div>'
        f"</div>",
        unsafe_allow_html=True,
    )
