"""
Sicht "Vergleich": alle Sensitivitaeten eines Standorts nebeneinander.

Aufbau in vier Bloecken, von der Entscheidung zur Begruendung:

1. Entscheidungstabelle - welche Variante gewinnt, gemessen am Ziel.
2. Unterschiede - warum sie gewinnt, also welche Felder abweichen.
3. DSCR je Betriebsjahr - ob die Finanzierung das ueber die Laufzeit
   traegt (die Minimalzahl allein sagt nicht, ob eine Unterdeckung
   Ausreisser oder Dauerzustand ist).
4. Kumulierter Cashflow - wann sich die Variante bezahlt macht.

Die Referenzvariante steuert alle Abweichungen: Delta-Spalte und
Hervorhebungen der Unterschiedstabelle beziehen sich auf sie.
"""

from __future__ import annotations

import html

import streamlit as st

from app import router, services
from app.components import charts
from app.components.varianten import anzahl_gleicher_felder, unterschiede
from app.formatting import fmt_eur, fmt_eur_kompakt, fmt_number, fmt_pct
from app.theme import Colors
from engine import PVProject
from texte import txt

#: Obergrenze des Zielbalkens in der Entscheidungstabelle. Der Balken
#: soll die Lage zum Ziel zeigen, nicht die Rendite ausmessen - deshalb
#: eine feste Skala statt einer, die mit dem besten Wert mitwandert.
_BALKEN_MAX_PCT = 0.20


def _zielbalken(irr: float | None, ziel_pct: float) -> str:
    """Ein schmaler Balken mit Zielmarke - die Einordnung, die eine
    Prozentzahl allein nicht liefert."""
    if irr is None:
        return ""
    anteil = min(max(irr, 0.0) / _BALKEN_MAX_PCT, 1.0)
    farbe = Colors.BRAND if irr >= ziel_pct else Colors.NEGATIVE
    ziel_anteil = min(ziel_pct / _BALKEN_MAX_PCT, 1.0)
    return (
        f'<span class="vgl-balken">'
        f'<span class="vgl-balken-fuell" style="width:{anteil * 100:.1f}%;'
        f'background:{farbe}"></span>'
        f'<span class="vgl-balken-ziel" style="left:{ziel_anteil * 100:.1f}%">'
        f"</span></span>"
    )


def _entscheidungstabelle(zeilen: list[dict], referenz: dict,
                          ziel_pct: float, dscr_grenze: float) -> None:
    kopf = [
        txt("oberflaeche.vergleich_spalte_variante"),
        txt("oberflaeche.vergleich_spalte_irr"),
        txt("oberflaeche.vergleich_spalte_delta"),
        txt("oberflaeche.vergleich_spalte_npv"),
        txt("oberflaeche.vergleich_spalte_equity_value"),
        txt("oberflaeche.vergleich_spalte_dscr"),
        txt("oberflaeche.vergleich_spalte_capex"),
        txt("oberflaeche.vergleich_spalte_payback"),
    ]
    teile = ['<table class="vgl-tabelle"><thead><tr>']
    for i, k in enumerate(kopf):
        klasse = "" if i == 0 else ' class="num"'
        teile.append(f"<th{klasse}>{html.escape(k)}</th>")
    teile.append("</tr></thead><tbody>")

    bester = max(
        (z for z in zeilen if z["irr"] is not None),
        key=lambda z: z["irr"], default=None,
    )
    for z in zeilen:
        klassen = []
        if bester is not None and z["id"] == bester["id"]:
            klassen.append("best")
        if z["id"] == referenz["id"]:
            klassen.append("referenz")
        tr = f' class="{" ".join(klassen)}"' if klassen else ""
        name = html.escape(z["label"])
        if z["leitvariante"]:
            name += (
                f' <span class="vgl-leit">'
                f'{html.escape(txt("oberflaeche.vergleich_leitvariante_marke"))}'
                f"</span>"
            )
        delta = (
            txt("oberflaeche.vergleich_referenz")
            if z["id"] == referenz["id"]
            else _delta_text(z["irr"], referenz["irr"])
        )
        dscr_klasse = " unter" if z["dscr"] is not None and z["dscr"] < dscr_grenze else ""
        teile.append(
            f"<tr{tr}>"
            f'<td class="name">{name}</td>'
            f'<td class="num">{_zielbalken(z["irr"], ziel_pct)}'
            f'<b>{fmt_pct(z["irr"], 2)}</b></td>'
            f'<td class="num">{delta}</td>'
            f'<td class="num{"" if (z["npv"] or 0) >= 0 else " unter"}">'
            f'{fmt_eur(z["npv"])}</td>'
            f'<td class="num">{fmt_eur(z["equity_value"])}</td>'
            f'<td class="num{dscr_klasse}">{fmt_number(z["dscr"], 2)}x</td>'
            f'<td class="num">{fmt_eur_kompakt(z["capex"])}</td>'
            f'<td class="num">{_payback(z["payback"])}</td>'
            "</tr>"
        )
    teile.append("</tbody></table>")
    st.markdown("".join(teile), unsafe_allow_html=True)


def _delta_text(irr: float | None, referenz_irr: float | None) -> str:
    if irr is None or referenz_irr is None:
        return "—"
    delta = (irr - referenz_irr) * 100
    farbe = Colors.BRAND if delta >= 0 else Colors.NEGATIVE
    return (
        f'<span style="color:{farbe};font-weight:600">'
        f'{fmt_number(delta, 2, mit_vorzeichen=True)} pp</span>'
    )


def _payback(jahre) -> str:
    if jahre is None:
        return "—"
    return txt("oberflaeche.vergleich_payback_jahre", jahre=int(jahre))


def _unterschiedstabelle(varianten: list[PVProject], referenz: PVProject,
                         labels: list[str]) -> None:
    zeilen = unterschiede(varianten, referenz)
    if not zeilen:
        st.info(txt("oberflaeche.vergleich_keine_unterschiede"))
        return

    teile = ['<table class="vgl-tabelle diff"><thead><tr><th></th>']
    for label in labels:
        teile.append(f'<th class="num">{html.escape(label)}</th>')
    teile.append("</tr></thead><tbody>")
    for zeile in zeilen:
        teile.append(f'<td class="name">{html.escape(zeile.label)}</td>')
        for wert, abweichend in zip(zeile.werte, zeile.abweichend, strict=False):
            marke = ' class="num abw"' if abweichend else ' class="num"'
            teile.append(f"<td{marke}>{html.escape(wert)}</td>")
        teile.append("</tr><tr>")
    teile.append("</tr></tbody></table>")
    st.markdown("".join(teile).replace("<tbody></tr>", "<tbody>"),
                unsafe_allow_html=True)
    st.caption(
        txt("oberflaeche.vergleich_gleiche_felder",
            anzahl=anzahl_gleicher_felder(varianten))
    )


def render_vergleich(varianten: list[PVProject], offene_id: str,
                     ziel_pct: float, npv_satz_pct: float) -> None:
    """Die vollstaendige Vergleichssicht eines Standorts."""
    if len(varianten) < 2:
        st.info(txt("oberflaeche.vergleich_nur_eine_variante"))
        if st.button(txt("oberflaeche.btn_neue_variante"), key="vergleich_neu"):
            neue = services.duplicate_project(offene_id)
            if neue is not None:
                router.gehe_zu("projekt", projekt_id=neue.id, tab="vergleich")
        return

    ga = services.get_global_assumptions()
    labels = [v.variantenlabel for v in varianten]

    # Referenzwahl: Vorbelegung ist die Leitvariante - der Fall, gegen
    # den man ueblicherweise misst.
    leit = services.leitvariante_von(varianten)
    key = f"vergleich_referenz_{varianten[0].name}"
    st.session_state.setdefault(key, leit.variantenlabel)
    col_ref, col_leit = st.columns([1.1, 2.4], vertical_alignment="bottom")
    with col_ref:
        gewaehlt = st.selectbox(
            txt("oberflaeche.vergleich_referenz_label"), labels, key=key,
            help=txt("oberflaeche.vergleich_referenz_hilfe"),
        )
    referenz = varianten[labels.index(gewaehlt)]

    offen = next((v for v in varianten if v.id == offene_id), varianten[0])
    with col_leit:
        if offen.leitvariante:
            st.caption(txt("oberflaeche.vergleich_ist_leitvariante",
                           name=offen.variantenlabel))
        elif st.button(
            txt("oberflaeche.vergleich_als_leitvariante", name=offen.variantenlabel),
            key="vergleich_setze_leit",
            help=txt("oberflaeche.vergleich_als_leitvariante_hilfe"),
        ):
            services.setze_leitvariante(offen.id)
            st.rerun()

    # --- Block 1: Entscheidungstabelle --------------------------------------
    zeilen = []
    reihen = []
    for variante in varianten:
        result = services.get_valuation(variante.id)
        if result is None:
            continue
        kpis = result.kpis
        from engine.kpis import npv_at

        npv = npv_at(result.cashflow, npv_satz_pct / 100)
        zeilen.append(
            {
                "id": variante.id,
                "label": variante.variantenlabel,
                "leitvariante": variante.leitvariante,
                "irr": kpis.equity_irr,
                "npv": npv,
                "equity_value": npv + kpis.eigenkapital_eur,
                "dscr": kpis.dscr_min,
                "capex": kpis.capex_total_eur,
                "payback": kpis.payback_jahre,
            }
        )
        reihen.append((variante.variantenlabel, result.cashflow.data))

    referenz_zeile = next(z for z in zeilen if z["id"] == referenz.id)
    st.markdown(f"#### {txt('oberflaeche.vergleich_entscheidung_titel')}")
    st.caption(txt("oberflaeche.vergleich_entscheidung_hilfe",
                   ziel=fmt_pct(ziel_pct, 1),
                   dscr=fmt_number(ga.dscr_cash_trap, 2)))
    _entscheidungstabelle(zeilen, referenz_zeile, ziel_pct, ga.dscr_cash_trap)

    # --- Block 2: Unterschiede ----------------------------------------------
    st.markdown(f"#### {txt('oberflaeche.vergleich_unterschiede_titel')}")
    st.caption(txt("oberflaeche.vergleich_unterschiede_hilfe"))
    _unterschiedstabelle(varianten, referenz, labels)

    # --- Block 3 und 4: Verlaeufe -------------------------------------------
    col_dscr, col_cf = st.columns(2)
    with col_dscr:
        st.markdown(f"#### {txt('oberflaeche.vergleich_dscr_titel')}")
        st.caption(txt("oberflaeche.vergleich_dscr_hilfe"))
        st.plotly_chart(
            charts.varianten_dscr_chart(
                reihen, ga.dscr_cash_trap, ga.dscr_event_of_default
            ),
            width="stretch",
        )
    with col_cf:
        st.markdown(f"#### {txt('oberflaeche.vergleich_cashflow_titel')}")
        st.caption(txt("oberflaeche.vergleich_cashflow_hilfe"))
        st.plotly_chart(charts.varianten_kumuliert_chart(reihen), width="stretch")

    st.caption(txt("oberflaeche.vergleich_gespeicherter_stand"))
