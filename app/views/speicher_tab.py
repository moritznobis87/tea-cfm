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

import streamlit as st

from app import services, speicher
from app.components import charts
from app.components.storage_dialog import zusammenfassung
from app.formatting import fmt_eur, fmt_eur_kompakt, fmt_number, fmt_pct
from engine import PVProject
from texte import txt


def render_speicher_tab(projekt: PVProject, result) -> None:
    """`result` ist die Bewertung, die die Seite oben zeigt - mit
    Speicher, falls ein gueltiger Lauf vorliegt."""
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
    if lauf is None:
        return

    _kennzahlen(projekt, ga, lauf, result)
    _hinweise(lauf)
    _diagramme(projekt, ga, lauf)


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
