"""
Der Speicher-Reiter der Projektseite.

Er ist die einzige Stelle, an der ein Dispatch ANGESTOSSEN wird, und die
einzige, an der sein Ergebnis steht. Beides gehoert zusammen: Wer die
Zahlen sieht, soll auch sehen, wann sie entstanden sind und auf welchen
Preisen sie beruhen.

Der Aufbau folgt dem Zustand, in dem das Projekt gerade ist:

    kein Speicher      Ein Satz, was zu tun ist. Kein Knopf, der nur
                       eine Fehlermeldung erzeugen kann.
    keine Preisreihe   Dasselbe, mit dem Namen des Szenarios - sonst
                       raet der Nutzer, welche Datei fehlt.
    nichts gerechnet   Auslegung und Knopf. Keine Zahlen.
    veraltet           Die alten Zahlen bleiben SICHTBAR, aber deutlich
                       als veraltet gekennzeichnet und ausdruecklich
                       nicht in den Kennzahlen oben. Sie wegzuwerfen
                       waere unfreundlich - man will oft gerade
                       vergleichen, was die Aenderung bewirkt hat.
    gerechnet          Kennzahlen, Diagramme, Jahrestabelle.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from app import services, speicher
from app.components import charts
from app.components.project_inspector import overlay_setzen
from app.components.storage_dialog import zusammenfassung
from app.formatting import fmt_eur, fmt_eur_kompakt, fmt_number, fmt_pct
from engine import PVProject
from engine.storage import BatteryConfig, SolverFehler, auslegung
from texte import txt


def render_speicher_tab(projekt: PVProject, result, form_key: str = "") -> None:
    """`result` ist die Bewertung, die die Seite oben zeigt - mit
    Speicher, falls ein gueltiger Lauf vorliegt.

    `form_key` ist der Schluessel der Parametermaske. Er wird nur
    gebraucht, um eine gefundene Auslegung in den Entwurf zu schreiben;
    ohne ihn entfaellt der Uebernehmen-Knopf, alles Uebrige bleibt.
    """
    ga = services.get_global_assumptions()
    b = projekt.battery

    st.markdown(f"#### {txt('oberflaeche.speicher_tab_titel')}")

    if not speicher.hat_speicher(projekt):
        st.info(txt("oberflaeche.speicher_fehlt_auslegung"))
        return

    st.caption(zusammenfassung(b))
    # Der Vermerk steht VOR den Zahlen und nicht in einer Fussnote
    # darunter: Ein Speicherwert ohne die Angabe, an welchem Markt er
    # verdient wird, laesst sich nicht einordnen - Regelenergie und
    # Intraday sind bei realen Projekten oft der groessere Teil.
    st.info(txt("oberflaeche.speicher_markt_hinweis"))

    datei = speicher.preisreihe_datei(projekt, ga)
    if datei is None:
        st.warning(txt(
            "oberflaeche.speicher_fehlt_preisreihe_mit_szenario",
            szenario=projekt.marktpreisszenario,
        ))
        return
    if speicher.stundenform(projekt) is None:
        st.warning(txt("oberflaeche.speicher_fehlt_erzeugungsform"))
        return

    _steuerung(projekt, ga, datei)

    # Auch der VERALTETE Lauf wird gezeigt - deutlich gekennzeichnet.
    # Er fliesst nicht in `result` ein (siehe app/speicher.py::beitrag),
    # ist aber oft genau das, womit man vergleichen will.
    lauf = speicher.letzter_lauf(projekt)
    if lauf is not None:
        _kennzahlen(projekt, ga, lauf, result)
        _hinweise(lauf)
        _diagramme(projekt, ga, lauf)

    # Die Auslegungssuche steht am ENDE und nicht am Anfang, obwohl sie
    # zeitlich zuerst kaeme. Der Reiter beantwortet die Frage "was
    # bringt DIESER Speicher?"; die Suche ist der Umweg fuer den, dem die
    # Antwort nicht gefaellt. Oben stuende sie jedem im Weg, der nur
    # nachrechnen will.
    st.divider()
    _auslegung(projekt, ga, form_key)


def _steuerung(projekt: PVProject, ga, datei: str) -> None:
    """Knopf, Herkunft der Preise und der Zustand des letzten Laufs."""
    lauf = speicher.lauf(projekt, ga)
    ist_veraltet = speicher.veraltet(projekt, ga)

    col_knopf, col_status = st.columns([0.28, 0.72], vertical_alignment="center")
    with col_knopf:
        beschriftung = (
            txt("oberflaeche.speicher_btn_neu_berechnen")
            if (lauf or ist_veraltet)
            else txt("oberflaeche.speicher_btn_berechnen")
        )
        gedrueckt = st.button(
            beschriftung, key=f"speicher_rechnen_{projekt.id}",
            type="primary" if not lauf else "secondary", width="stretch",
        )

    with col_status:
        if ist_veraltet:
            st.warning(txt("oberflaeche.speicher_status_veraltet"))
        elif lauf:
            st.caption(txt(
                "oberflaeche.speicher_status_gerechnet",
                zeit=lauf.gerechnet_am.strftime("%H:%M"),
                datei=lauf.preisreihe_datei,
            ))
        else:
            st.caption(txt(
                "oberflaeche.speicher_status_offen", datei=datei
            ))

    if gedrueckt:
        balken = st.progress(0.0, text=txt("oberflaeche.speicher_rechnet"))
        try:
            speicher.berechnen(
                projekt, ga,
                lambda fertig, gesamt: balken.progress(
                    fertig / gesamt,
                    text=txt(
                        "oberflaeche.speicher_rechnet_jahr",
                        jahr=fertig, gesamt=gesamt,
                    ),
                ),
            )
        finally:
            balken.empty()
        st.rerun()


def _kennzahlen(projekt: PVProject, ga, lauf, result) -> None:
    """Was der Speicher beitraegt - und was er an der Rendite bewirkt.

    Die Wirkung auf IRR und NPV entsteht aus dem Vergleich mit derselben
    Bewertung OHNE Speicherbeitrag. Beide Laeufe teilen sich alles
    Uebrige: dasselbe Projekt, dieselben Annahmen, dieselbe Finanzierung.
    Der Unterschied ist damit genau der Speicher - Investition,
    Betriebskosten und Erloes zusammen, nicht nur seine Ertragsseite.
    """
    ohne = services.get_valuation_fuer(projekt, None, "")
    beitrag = lauf.beitrag
    werte = lauf.jahreswerte

    # Drei Kacheln je Zeile und nicht vier: Neben der Parameterspalte
    # bleiben der Ergebnisseite rund 770 Pixel, und ein Viertel davon
    # schneidet sowohl die Beschriftung als auch den Wert ab
    # ("Wertbeitrag g…", "6,06 …"). Eine abgeschnittene Kennzahl ist
    # keine Kennzahl.
    #
    # Verschleiss und Betriebskosten sind dabei herausgefallen. Beide
    # stehen weiterhin da, wo sie hingehoeren: der Verschleiss als
    # eigene Serie im Jahresdiagramm und als Spalte der Tabelle, die
    # Betriebskosten in der Auslegung und in der Kostenaufschluesselung
    # des Cashflows.
    spalten = st.columns(3)
    spalten[0].metric(
        txt("oberflaeche.speicher_kpi_wertbeitrag"),
        fmt_eur_kompakt(beitrag.wertbeitrag_gesamt_eur),
        help=txt("oberflaeche.speicher_kpi_wertbeitrag_hilfe"),
    )
    spalten[1].metric(
        txt("oberflaeche.speicher_kpi_vollzyklen"),
        fmt_number(beitrag.vollzyklen_mittel, 0),
        help=txt("oberflaeche.speicher_kpi_vollzyklen_hilfe"),
    )
    rueckgewinnung = (
        float(werte["rueckgewonnene_kappung_kwh"].mean()) / 1000.0
        if not werte.empty else 0.0
    )
    spalten[2].metric(
        txt("oberflaeche.speicher_kpi_kappung"),
        txt("oberflaeche.speicher_mwh_wert", wert=fmt_number(rueckgewinnung, 0)),
        help=txt("oberflaeche.speicher_kpi_kappung_hilfe"),
    )

    st.markdown(f"##### {txt('oberflaeche.speicher_wirkung_titel')}")
    wirkung = st.columns(3)
    _wirkung_irr(wirkung[0], result.kpis.equity_irr, ohne.kpis.equity_irr)
    _wirkung_npv(wirkung[1], result.kpis.npv_eur, ohne.kpis.npv_eur)
    wirkung[2].metric(
        txt("oberflaeche.speicher_kpi_capex"),
        fmt_eur_kompakt(beitrag.capex_eur),
        help=txt("oberflaeche.speicher_kpi_capex_hilfe"),
    )
    st.caption(txt(
        "oberflaeche.speicher_kosten_zeile",
        opex=fmt_eur_kompakt(
            beitrag.opex_eur_je_jahr[0] if beitrag.opex_eur_je_jahr else 0.0
        ),
        verschleiss=fmt_eur_kompakt(
            float(werte["degradationskosten_eur"].sum())
            if not werte.empty else 0.0
        ),
    ))

    if speicher.veraltet(projekt, ga):
        st.caption(txt("oberflaeche.speicher_wirkung_veraltet"))


def _wirkung_irr(ziel, mit: float | None, ohne: float | None) -> None:
    if mit is None or ohne is None:
        ziel.metric(txt("oberflaeche.speicher_kpi_irr"), "—")
        return
    ziel.metric(
        txt("oberflaeche.speicher_kpi_irr"),
        fmt_pct(mit, 2),
        delta=txt(
            "oberflaeche.speicher_prozentpunkte",
            wert=fmt_number((mit - ohne) * 100, 2),
        ),
        help=txt("oberflaeche.speicher_kpi_irr_hilfe"),
    )


def _wirkung_npv(ziel, mit: float, ohne: float) -> None:
    ziel.metric(
        txt("oberflaeche.speicher_kpi_npv"),
        fmt_eur_kompakt(mit),
        delta=fmt_eur_kompakt(mit - ohne),
        help=txt("oberflaeche.speicher_kpi_npv_hilfe"),
    )


def _hinweise(lauf) -> None:
    """Was der Optimierer selbst zu melden hatte.

    Diese Meldungen stammen aus dem Solver und aus der Jahresschleife -
    fehlende Preisjahre, Entartungen, Abstaende zur stetigen Schranke.
    Sie gehoeren sichtbar an das Ergebnis und nicht ins Log: Ein
    Wertbeitrag, der auf einer geklammerten Preisreihe beruht, ist eine
    schwaechere Aussage als einer auf echten Jahren.
    """
    if not lauf.beitrag.hinweise:
        return
    with st.expander(txt(
        "oberflaeche.speicher_hinweise_titel",
        anzahl=len(lauf.beitrag.hinweise),
    )):
        for hinweis in lauf.beitrag.hinweise:
            st.write(f"- {hinweis}")


def _diagramme(projekt: PVProject, ga, lauf) -> None:
    werte = lauf.jahreswerte
    if werte.empty:
        return

    st.markdown(f"##### {txt('oberflaeche.speicher_verlauf_titel')}")
    st.plotly_chart(
        charts.speicher_wertbeitrag_chart(werte),
        width="stretch", key=f"speicher_verlauf_{projekt.id}",
    )

    st.markdown(f"##### {txt('oberflaeche.speicher_woche_titel')}")
    jahre = [int(j) for j in werte["jahr"]]
    jahr = st.selectbox(
        txt("oberflaeche.speicher_jahr_label"), jahre,
        key=f"speicher_jahr_{projekt.id}",
    )
    bahn = speicher.bahn(projekt, ga, int(jahr))
    if bahn is None:
        st.info(txt("oberflaeche.speicher_woche_fehlt"))
        return
    von, bis = speicher.beispielwoche(bahn)
    st.caption(txt(
        "oberflaeche.speicher_woche_hinweis",
        kalenderjahr=bahn.attrs.get("kalenderjahr", ""),
        von=von, bis=bis,
    ))
    st.plotly_chart(
        charts.speicher_dispatch_chart(bahn, von, bis),
        width="stretch", key=f"speicher_woche_{projekt.id}",
    )

    with st.expander(txt("oberflaeche.speicher_tabelle_titel")):
        st.dataframe(
            _tabelle(werte), width="stretch", hide_index=True,
        )


def _tabelle(werte):
    """Die Jahreswerte in lesbaren Spalten."""
    tabelle = werte.copy()
    tabelle["mehrmenge_mwh"] = tabelle["mehrmenge_kwh"] / 1000.0
    tabelle["kappung_mwh"] = tabelle["rueckgewonnene_kappung_kwh"] / 1000.0
    spalten = {
        "jahr": txt("oberflaeche.speicher_spalte_jahr"),
        "kalenderjahr": txt("oberflaeche.speicher_spalte_kalenderjahr"),
        "deckungsbeitrag_eur": txt("oberflaeche.speicher_spalte_beitrag"),
        "mehrerloes_eur": txt("oberflaeche.speicher_spalte_mehrerloes"),
        "degradationskosten_eur": txt("oberflaeche.speicher_spalte_verschleiss"),
        "netzbezugskosten_eur": txt("oberflaeche.speicher_spalte_netzbezug"),
        "mehrmenge_mwh": txt("oberflaeche.speicher_spalte_mehrmenge"),
        "kappung_mwh": txt("oberflaeche.speicher_spalte_kappung"),
        "vollzyklen": txt("oberflaeche.speicher_spalte_vollzyklen"),
    }
    tabelle = tabelle[list(spalten)].rename(columns=spalten)
    for name in (spalten["deckungsbeitrag_eur"], spalten["mehrerloes_eur"],
                 spalten["degradationskosten_eur"],
                 spalten["netzbezugskosten_eur"]):
        tabelle[name] = tabelle[name].map(fmt_eur)
    for name in (spalten["mehrmenge_mwh"], spalten["kappung_mwh"]):
        tabelle[name] = tabelle[name].map(lambda w: fmt_number(w, 0))
    tabelle[spalten["vollzyklen"]] = tabelle[spalten["vollzyklen"]].map(
        lambda w: fmt_number(w, 0)
    )
    return tabelle


# ---------------------------------------------------------------------------
# Auslegungssuche
# ---------------------------------------------------------------------------
#
# Gemessen an vollen Laeufen ueber alle Betriebsjahre (Voelkermarkt,
# 2,84 MWp, neun Auslegungen): Das Raster unterschaetzt die EK-Rendite
# durchweg um 0,05 bis 0,16 Prozentpunkte - systematisch in dieselbe
# Richtung, und genau darauf kommt es an. Die Reihenfolge der besten
# fuenf Auslegungen stimmte exakt, der Sieger ohnehin; getauscht haben
# nur zwei Plaetze im hinteren Feld, die im vollen Lauf 0,03
# Prozentpunkte auseinanderlagen.

#: Sekunden je linearem Programm des Rasters, gemessen an einem Jahr mit
#: 8.784 Stunden. Nur fuer die Laufzeitschaetzung vor dem Knopfdruck -
#: eine Hausnummer, kein Versprechen.
_SEKUNDEN_JE_LAUF = 0.7

#: Der Optimierer loest EIN Modell ueber alle Stuetzjahre gemeinsam.
#: Seine Zeit waechst deshalb ueberproportional mit ihrer Zahl -
#: gemessen 15 s bei zwei und 64 s bei vier Stuetzjahren, was einem
#: quadratischen Ansatz mit diesem Faktor entspricht.
_SEKUNDEN_OPTIMIERER = 4.0


def _dauerschaetzung(punkte: int, stuetzjahre: int) -> str:
    """Wie lange der Lauf ungefaehr dauert, in lesbarer Form.

    Je Rasterpunkt und Stuetzjahr ein LP, dazu einmal je Stuetzjahr der
    Vergleichsfall und einmal der Optimierer ueber alles. Die Schaetzung
    steht VOR dem Knopf: Ein Lauf, der zwei Minuten braucht, sollte das
    vorher sagen und nicht erst, waehrend jemand wartet.
    """
    sekunden = (
        (punkte + 1) * stuetzjahre * _SEKUNDEN_JE_LAUF
        + _SEKUNDEN_OPTIMIERER * stuetzjahre ** 2
    )
    if sekunden < 90:
        return txt(
            "oberflaeche.speicher_auslegung_dauer_sekunden",
            sekunden=int(round(sekunden / 5.0) * 5),
        )
    return txt(
        "oberflaeche.speicher_auslegung_dauer_minuten",
        minuten=fmt_number(sekunden / 60.0, 1),
    )


def _rasterwahl(projekt: PVProject) -> tuple[list[float], list[int], int]:
    """Die drei Regler ueber dem Knopf."""
    spalten = st.columns([0.42, 0.35, 0.23])
    anteile = spalten[0].multiselect(
        txt("oberflaeche.speicher_auslegung_leistungen_label"),
        list(auslegung.LEISTUNGSANTEILE),
        default=list(auslegung.LEISTUNGSANTEILE_STANDARD),
        format_func=lambda a: f"{a * 100:.0f} %".replace(".", ","),
        key=f"raster_anteile_{projekt.id}",
        help=txt("oberflaeche.speicher_auslegung_leistungen_hilfe"),
    )
    dauern = spalten[1].multiselect(
        txt("oberflaeche.speicher_auslegung_dauern_label"),
        list(auslegung.DAUERN_STUNDEN),
        default=list(auslegung.DAUERN_STANDARD),
        format_func=lambda d: f"{d} h",
        key=f"raster_dauern_{projekt.id}",
        help=txt("oberflaeche.speicher_auslegung_dauern_hilfe"),
    )
    stuetzjahre = spalten[2].select_slider(
        txt("oberflaeche.speicher_auslegung_stuetzjahre_label"),
        options=[2, 3, 4, 6, 8, 10],
        value=auslegung.STUETZJAHRE_STANDARD,
        key=f"raster_stuetzjahre_{projekt.id}",
        help=txt("oberflaeche.speicher_auslegung_stuetzjahre_hilfe"),
    )
    return anteile, dauern, int(stuetzjahre)


def _auslegung(projekt: PVProject, ga, form_key: str) -> None:
    st.markdown(f"##### {txt('oberflaeche.speicher_auslegung_titel')}")
    st.caption(txt("oberflaeche.speicher_auslegung_hinweis"))

    # Die Bestaetigung ueberlebt genau EINEN Durchlauf - den nach dem
    # Uebernehmen. Sie danach stehen zu lassen hiesse, eine Meldung ueber
    # eine Handlung zu zeigen, die laengst vorbei ist.
    uebernommen = st.session_state.pop(f"raster_uebernommen_{projekt.id}", None)
    if uebernommen is not None:
        leistung, kapazitaet = uebernommen
        st.success(txt(
            "oberflaeche.speicher_auslegung_uebernommen",
            leistung=fmt_number(leistung, 2),
            kapazitaet=fmt_number(kapazitaet, 2),
        ))

    anteile, dauern, stuetzjahre = _rasterwahl(projekt)
    if not anteile or not dauern:
        st.info(txt("oberflaeche.speicher_auslegung_leer"))
        return

    punkte = len(anteile) * len(dauern)
    ergebnis, gerechnet = speicher.letztes_raster(projekt)
    aktuell = speicher.raster_abdruck(projekt, ga, anteile, dauern, stuetzjahre)
    ist_veraltet = ergebnis is not None and gerechnet != aktuell

    col_knopf, col_status = st.columns([0.28, 0.72], vertical_alignment="center")
    gedrueckt = col_knopf.button(
        txt("oberflaeche.speicher_auslegung_btn_neu") if ergebnis is not None
        else txt("oberflaeche.speicher_auslegung_btn"),
        key=f"raster_rechnen_{projekt.id}",
        type="secondary", width="stretch",
    )
    with col_status:
        if ist_veraltet:
            st.warning(txt("oberflaeche.speicher_auslegung_veraltet"))
        else:
            st.caption(txt(
                "oberflaeche.speicher_auslegung_schaetzung",
                punkte=punkte, stuetzjahre=stuetzjahre,
                dauer=_dauerschaetzung(punkte, stuetzjahre),
            ))

    if gedrueckt:
        balken = st.progress(0.0)
        try:
            speicher.raster_rechnen(
                projekt, ga,
                leistungsanteile=anteile, dauern=dauern,
                stuetzjahre=stuetzjahre,
                fortschritt=lambda n, gesamt: balken.progress(
                    n / gesamt,
                    text=txt("oberflaeche.speicher_auslegung_rechnet",
                             nummer=n, gesamt=gesamt),
                ),
            )
        except SolverFehler as fehler:
            balken.empty()
            st.error(str(fehler))
            return
        finally:
            balken.empty()
        st.rerun()

    if ergebnis is None:
        return
    _rasterergebnis(projekt, ergebnis, form_key, ist_veraltet)


def _rasterergebnis(
    projekt: PVProject, ergebnis, form_key: str, ist_veraltet: bool
) -> None:
    st.caption(txt(
        "oberflaeche.speicher_auslegung_gerechnet",
        anzahl=len(ergebnis.stuetzjahre),
        jahre=", ".join(str(s.kalenderjahr) for s in ergebnis.stuetzjahre),
    ))

    nach_rendite = ergebnis.bestes(auslegung.NACH_RENDITE)
    nach_barwert = ergebnis.bestes(auslegung.NACH_BARWERT)
    _optimumkacheln(ergebnis, nach_rendite, nach_barwert)

    if not ergebnis.einig:
        st.info(txt("oberflaeche.speicher_auslegung_uneinig"))
    _optimierer(ergebnis)

    ansicht = st.radio(
        txt("oberflaeche.speicher_auslegung_ansicht_label"),
        ["equity_irr", "npv_eur"],
        format_func=lambda s: txt(
            "oberflaeche.speicher_auslegung_ansicht_rendite" if s == "equity_irr"
            else "oberflaeche.speicher_auslegung_ansicht_barwert"
        ),
        horizontal=True, key=f"raster_ansicht_{projekt.id}",
        label_visibility="collapsed",
    )
    gezeigt = nach_rendite if ansicht == "equity_irr" else nach_barwert
    st.plotly_chart(
        charts.speicher_auslegung_chart(
            ergebnis.tabelle(), ansicht,
            ergebnis.equity_irr_ohne if ansicht == "equity_irr"
            else ergebnis.npv_eur_ohne,
            optimum=(
                (gezeigt.kandidat.leistungsanteil, gezeigt.kandidat.dauer_h)
                if gezeigt else None
            ),
        ),
        width="stretch", key=f"raster_flaeche_{projekt.id}",
    )

    _randhinweis(ergebnis, gezeigt)
    st.caption(txt("oberflaeche.speicher_auslegung_genauigkeit"))

    if form_key and not ist_veraltet:
        _uebernehmen(projekt, ergebnis, nach_rendite, nach_barwert, form_key)

    with st.expander(txt("oberflaeche.speicher_auslegung_tabelle")):
        st.dataframe(
            _rastertabelle(ergebnis), width="stretch", hide_index=True,
        )


def _optimumkacheln(ergebnis, nach_rendite, nach_barwert) -> None:
    """Drei Kacheln: die beiden Optima und der Bezugspunkt ohne Speicher.

    Der Bezugspunkt steht daneben und nicht in einer Fussnote: Eine
    Rendite von 24 % ist ohne die 13,6 % ohne Speicher keine Aussage
    ueber den Speicher, sondern eine ueber das Projekt.
    """
    kacheln = st.columns(3)
    _optimumkachel(
        kacheln[0], txt("oberflaeche.speicher_auslegung_best_rendite"),
        nach_rendite,
        fmt_pct(nach_rendite.equity_irr, 2) if nach_rendite else "—",
        txt("oberflaeche.speicher_prozentpunkte", wert=fmt_number(
            ((nach_rendite.equity_irr or 0) - (ergebnis.equity_irr_ohne or 0)) * 100,
            2,
        )) if nach_rendite and ergebnis.equity_irr_ohne is not None else None,
    )
    _optimumkachel(
        kacheln[1], txt("oberflaeche.speicher_auslegung_best_barwert"),
        nach_barwert,
        fmt_eur_kompakt(nach_barwert.npv_eur) if nach_barwert else "—",
        fmt_eur_kompakt(nach_barwert.npv_eur - ergebnis.npv_eur_ohne)
        if nach_barwert else None,
    )
    kacheln[2].metric(
        txt("oberflaeche.speicher_auslegung_ohne"),
        fmt_pct(ergebnis.equity_irr_ohne, 2)
        if ergebnis.equity_irr_ohne is not None else "—",
    )
    kacheln[2].caption(fmt_eur_kompakt(ergebnis.npv_eur_ohne))


def _optimumkachel(ziel, titel: str, punkt, wert: str, delta) -> None:
    ziel.metric(titel, wert, delta=delta)
    if punkt is not None:
        ziel.caption(txt(
            "oberflaeche.speicher_auslegung_kandidat",
            leistung=fmt_number(punkt.kandidat.leistung_mw, 2),
            kapazitaet=fmt_number(punkt.kandidat.kapazitaet_mwh, 2),
        ))


def _randhinweis(ergebnis, punkt) -> None:
    """Liegt das Optimum am Rand, ist das Raster zu klein gewaehlt.

    Der wichtigste Vorbehalt des ganzen Abschnitts: Ein Maximum am Rand
    ist keins - es ist die Stelle, an der die Suche aufgehoert hat. Ohne
    diesen Hinweis liest sich der Randpunkt wie ein Ergebnis.
    """
    if punkt is None:
        return
    anteile = sorted({p.kandidat.leistungsanteil for p in ergebnis.punkte})
    dauern = sorted({p.kandidat.dauer_h for p in ergebnis.punkte})
    am_rand_leistung = (
        len(anteile) > 1
        and punkt.kandidat.leistungsanteil in (anteile[0], anteile[-1])
    )
    am_rand_dauer = (
        len(dauern) > 1 and punkt.kandidat.dauer_h in (dauern[0], dauern[-1])
    )
    if not (am_rand_leistung or am_rand_dauer):
        return
    if am_rand_leistung and am_rand_dauer:
        richtung = "oberflaeche.speicher_auslegung_rand_beide"
    elif am_rand_leistung:
        richtung = "oberflaeche.speicher_auslegung_rand_leistung"
    else:
        richtung = "oberflaeche.speicher_auslegung_rand_dauer"
    st.warning(txt(
        "oberflaeche.speicher_auslegung_rand", richtung=txt(richtung)
    ))


def _optimierer(ergebnis) -> None:
    """Das exakte stetige Optimum - neben dem Raster, nicht darin.

    Zwei Verfahren auf dieselbe Frage, und das ist Absicht. Der
    Optimierer loest Fahrweise UND Auslegung in EINEM linearen Programm;
    seine Antwort ist exakt und stetig, beantwortet aber eine etwas
    andere Frage: Er maximiert den Barwert des Speichers nach einem
    pauschalen Steuersatz und ohne Fremdkapital. Die EK-Rendite ist
    keine lineare Funktion der Auslegung - kein LP und kein DP kann sie
    direkt maximieren.

    Liegen beide Antworten beieinander, ist das die staerkste Auskunft,
    die dieser Abschnitt geben kann: Zwei voellig verschiedene Wege
    landen an derselben Stelle.
    """
    optimum = ergebnis.optimum
    if optimum is None:
        return
    if not optimum.wirksam:
        st.info(txt("oberflaeche.speicher_auslegung_optimierer_unwirksam"))
        return

    st.markdown(f"###### {txt('oberflaeche.speicher_auslegung_optimierer')}")
    spalten = st.columns(3)
    spalten[0].metric(
        txt("oberflaeche.speicher_auslegung_optimierer_auslegung"),
        txt("oberflaeche.speicher_auslegung_kandidat",
            leistung=fmt_number(optimum.leistung_mw, 2),
            kapazitaet=fmt_number(optimum.kapazitaet_mwh, 2)),
        help=txt("oberflaeche.speicher_auslegung_optimierer_hilfe"),
    )
    spalten[1].metric(
        txt("oberflaeche.speicher_auslegung_optimierer_dauer"),
        txt("oberflaeche.speicher_dauer_wert",
            stunden=fmt_number(optimum.dauer_h, 1)),
    )
    punkt = ergebnis.optimum_punkt
    spalten[2].metric(
        txt("oberflaeche.speicher_auslegung_spalte_irr"),
        fmt_pct(punkt.equity_irr, 2)
        if punkt is not None and punkt.equity_irr is not None else "—",
        delta=fmt_eur_kompakt(punkt.npv_eur - ergebnis.npv_eur_ohne)
        if punkt is not None else None,
    )
    if optimum.am_deckel:
        st.caption(txt(
            "oberflaeche.speicher_auslegung_optimierer_am_deckel",
            leistung=fmt_number(optimum.leistung_deckel_mw or 0.0, 2),
        ))
    st.caption(txt("oberflaeche.speicher_auslegung_optimierer_hinweis"))


#: Die drei Antworten, die zur Uebernahme stehen.
_WAHL_OPTIMIERER, _WAHL_RENDITE, _WAHL_BARWERT = (
    "optimierer", "rendite", "barwert"
)


def _uebernehmen(projekt: PVProject, ergebnis, nach_rendite, nach_barwert,
                 form_key: str) -> None:
    """Schreibt die gewaehlte Groesse in den ENTWURF, nicht auf die Platte.

    Ueber das Overlay der Parametermaske - denselben Weg, den der
    Speicherdialog nimmt. Damit erscheint die Aenderung als
    ungespeicherte Aenderung, laesst sich verwerfen und wird erst mit
    "Speichern" dauerhaft.

    Zur Wahl stehen alle drei Antworten und nicht nur die gerade
    angezeigte: Welche die richtige ist, haengt daran, ob Eigenkapital
    knapp ist und ob eine krumme Auslegung ueberhaupt zu beschaffen
    waere. Das entscheidet der Nutzer, nicht dieses Modul.
    """
    moeglich: list[tuple[str, object]] = []
    if ergebnis.optimum_punkt is not None:
        moeglich.append((_WAHL_OPTIMIERER, ergebnis.optimum_punkt.kandidat))
    if nach_rendite is not None:
        moeglich.append((_WAHL_RENDITE, nach_rendite.kandidat))
    if nach_barwert is not None and (
        nach_barwert.kandidat != (nach_rendite.kandidat if nach_rendite else None)
    ):
        moeglich.append((_WAHL_BARWERT, nach_barwert.kandidat))
    if not moeglich:
        return

    spalten = st.columns([0.62, 0.38], vertical_alignment="bottom")
    wahl = spalten[0].radio(
        txt("oberflaeche.speicher_auslegung_wahl_label"),
        [kennung for kennung, _ in moeglich],
        format_func=lambda k: txt(f"oberflaeche.speicher_auslegung_wahl_{k}"),
        horizontal=True, key=f"raster_wahl_{projekt.id}",
    )
    gewaehlt = dict(moeglich)[wahl]
    if not spalten[1].button(
        txt("oberflaeche.speicher_auslegung_uebernehmen"),
        key=f"raster_uebernehmen_{projekt.id}",
        type="primary", width="stretch",
        help=txt("oberflaeche.speicher_auslegung_uebernehmen_hilfe"),
    ):
        return
    vorlage = projekt.battery or BatteryConfig()
    overlay_setzen(form_key, {"battery": gewaehlt.batterie(vorlage)})
    st.session_state[f"raster_uebernommen_{projekt.id}"] = (
        gewaehlt.leistung_mw, gewaehlt.kapazitaet_mwh
    )
    st.rerun()


def _rastertabelle(ergebnis):
    """Das Raster in lesbaren Spalten, nach Rendite absteigend."""
    tabelle = ergebnis.tabelle().sort_values("equity_irr", ascending=False)
    tabelle["anteil"] = tabelle["leistungsanteil"].map(lambda a: fmt_pct(a, 0))
    spalten = {
        "anteil": txt("oberflaeche.speicher_auslegung_spalte_anteil"),
        "leistung_mw": txt("oberflaeche.speicher_auslegung_spalte_leistung"),
        "dauer_h": txt("oberflaeche.speicher_auslegung_spalte_dauer"),
        "kapazitaet_mwh": txt("oberflaeche.speicher_auslegung_spalte_kapazitaet"),
        "capex_eur": txt("oberflaeche.speicher_auslegung_spalte_capex"),
        "wertbeitrag_eur": txt("oberflaeche.speicher_auslegung_spalte_wertbeitrag"),
        "equity_irr": txt("oberflaeche.speicher_auslegung_spalte_irr"),
        "delta_irr": txt("oberflaeche.speicher_auslegung_spalte_delta_irr"),
        "npv_eur": txt("oberflaeche.speicher_auslegung_spalte_npv"),
        "dscr_min": txt("oberflaeche.speicher_auslegung_spalte_dscr"),
        "vollzyklen": txt("oberflaeche.speicher_auslegung_spalte_vollzyklen"),
    }
    tabelle = tabelle[list(spalten)].rename(columns=spalten)
    for name in ("capex_eur", "wertbeitrag_eur", "npv_eur"):
        tabelle[spalten[name]] = tabelle[spalten[name]].map(fmt_eur_kompakt)
    for name in ("equity_irr", "delta_irr"):
        tabelle[spalten[name]] = tabelle[spalten[name]].map(
            lambda w: fmt_pct(w, 2) if w is not None and pd.notna(w) else "—"
        )
    for name, stellen in (("leistung_mw", 2), ("kapazitaet_mwh", 2),
                          ("dscr_min", 2), ("vollzyklen", 0)):
        tabelle[spalten[name]] = tabelle[spalten[name]].map(
            lambda w, n=stellen: fmt_number(w, n) if pd.notna(w) else "—"
        )
    return tabelle
