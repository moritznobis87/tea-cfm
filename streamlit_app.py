"""
TEA PV-Projektbewertungs-Tool - Oberflaeche fuer Projektentwickler.

Bewusst NICHT am Excel-Original orientiert: Die Projektmaske zeigt nur,
was sich von Projekt zu Projekt unterscheidet. Alles Uebrige (Preiskurven,
Standardbetriebskosten, Finanzierungskonditionen, Steuerlogik) kommt aus
den Globalen Annahmen und wird automatisch angewendet.
"""

from __future__ import annotations

import io
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yaml

from engine.io_yaml import (
    load_global_assumptions_yaml,
    load_project_yaml,
    save_global_assumptions_yaml,
    save_project_yaml,
)
from engine.models import (
    AnlagenTyp,
    CapexBreakdown,
    GlobalAssumptions,
    OpexItem,
    PVProject,
    TilgungsArt,
)
from engine.pipeline import run_valuation
from engine.sensitivity import run_eag_sensitivity

DATA_DIR = Path(__file__).parent / "data"
PROJECTS_DIR = DATA_DIR / "projects"
GLOBAL_ASSUMPTIONS_PATH = DATA_DIR / "global_assumptions.yaml"

st.set_page_config(page_title="TEA PV-Projektbewertung", layout="wide", page_icon="☀️")

CUSTOM_CSS = """
<style>
    .block-container { padding-top: 2rem; max-width: 1200px; }
    div[data-testid="stMetric"] {
        background: #F7F9F8;
        border: 1px solid #E3E8E6;
        border-radius: 10px;
        padding: 16px 18px 12px 18px;
    }
    div[data-testid="stMetric"] label { color: #5B6B66; }
    .project-card {
        border: 1px solid #E3E8E6;
        border-radius: 10px;
        padding: 14px 18px;
        margin-bottom: 10px;
        background: white;
    }
    h1, h2, h3 { color: #163832; }
    .stTabs [data-baseweb="tab"] { font-weight: 500; }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Daten laden/speichern
# ---------------------------------------------------------------------------


def list_projects() -> dict[str, Path]:
    return {f.stem: f for f in sorted(PROJECTS_DIR.glob("*.yaml"))}


@st.cache_data
def _load_global_assumptions_cached(mtime: float) -> GlobalAssumptions:
    return load_global_assumptions_yaml(GLOBAL_ASSUMPTIONS_PATH)


def load_global_assumptions() -> GlobalAssumptions:
    # mtime im Cache-Key sorgt dafuer, dass Aenderungen nach dem Speichern
    # sofort sichtbar werden, ohne bei jedem Rerun neu von Platte zu lesen.
    mtime = GLOBAL_ASSUMPTIONS_PATH.stat().st_mtime
    return _load_global_assumptions_cached(mtime)


def format_pct(value: float | None, digits: int = 2) -> str:
    return f"{value:.{digits}%}" if value is not None else "n/a"


def format_eur(value: float) -> str:
    return f"{value:,.0f} €".replace(",", ".")


# ---------------------------------------------------------------------------
# Seite: Neues Projekt
# ---------------------------------------------------------------------------


def render_project_form(
    existing: PVProject | None, form_key: str
) -> PVProject | None:
    """Rendert die Projektmaske. Ohne `existing` = Neuanlage (leere
    Defaults), mit `existing` = Bearbeiten (vorausgefuellt, gleiche id).
    Gibt das neue/aktualisierte PVProject zurueck, wenn abgeschickt wurde,
    sonst None.

    Die Einheiten-Umschalter fuer Investkosten (€/kWp <-> €) und Pacht
    (€/kWp/Jahr <-> €/ha/Jahr) liegen bewusst AUSSERHALB von st.form(...):
    Formular-Inhalte aktualisieren sich in Streamlit erst beim Absenden,
    Umschalter ausserhalb loesen dagegen einen sofortigen Rerun aus, damit
    Beschriftungen/Felder unmittelbar umspringen.
    """
    st.markdown("**Technische Anlagenparameter**")
    col1, col2, col3 = st.columns(3)
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

    MONATE = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ]
    col_ibn1, col_ibn2 = st.columns(2)
    inbetriebnahme_jahr = col_ibn1.number_input(
        "Inbetriebnahme – Jahr", min_value=2000, max_value=2100,
        value=existing.inbetriebnahme_jahr if existing else datetime.now().year + 1,
        step=1, key=f"{form_key}_ibn_jahr_live",
    )
    inbetriebnahme_monat_label = col_ibn2.selectbox(
        "Inbetriebnahme – Monat", MONATE,
        index=(existing.inbetriebnahme_monat - 1) if existing else 0,
        key=f"{form_key}_ibn_monat_live",
    )
    inbetriebnahme_monat = MONATE.index(inbetriebnahme_monat_label) + 1
    st.caption(
        "ℹ️ Bestimmt das erste (anteilige) Betriebsjahr und die Cashflow-Daten. "
        "Hinweis: Die Preiskurven in den Globalen Annahmen sind aktuell nach "
        "Betriebsjahr (1, 2, 3, …) indiziert, nicht nach Kalenderjahr."
    )

    st.markdown("**Investkosten**")
    capex_defaults = existing.capex if existing else CapexBreakdown()
    capex_einheit = st.radio(
        "Einheit", options=["€/kWp", "€"], horizontal=True,
        key=f"{form_key}_capex_einheit",
    )

    # Stabile Widget-Keys (KEIN Wechsel des Keys je Einheit!): ein
    # Einheiten-Wechsel triggert einen Rerun ausserhalb des Formulars, und
    # WIR schreiben den passend umgerechneten Wert direkt in den
    # Session-State, BEVOR das Widget in diesem Run instanziiert wird. Das
    # vermeidet, dass sich die Menge der Formular-Widgets je nach Einheit
    # aendert - das kann in Streamlit zu inkonsistentem Formularverhalten
    # fuehren (Widgets, die zwischen Runs erscheinen/verschwinden, sind ein
    # bekanntes Risikomuster).
    capex_mode_key = f"{form_key}_capex_mode_prev"
    capex_mode_changed = st.session_state.get(capex_mode_key) != capex_einheit
    st.session_state[capex_mode_key] = capex_einheit

    def capex_feld(col, label: str, default_abs_eur: float, key_suffix: str) -> float:
        key = f"{form_key}_{key_suffix}"
        if capex_mode_changed or key not in st.session_state:
            if capex_einheit == "€/kWp":
                st.session_state[key] = (
                    round(default_abs_eur / nennleistung_kwp, 1) if nennleistung_kwp else 0.0
                )
            else:
                st.session_state[key] = default_abs_eur
        einheit_label = "€/kWp" if capex_einheit == "€/kWp" else "€"
        schritt = 1.0 if capex_einheit == "€/kWp" else 1000.0
        eingabe = col.number_input(
            f"{label} ({einheit_label})", min_value=0.0, step=schritt, key=key,
        )
        return eingabe * nennleistung_kwp if capex_einheit == "€/kWp" else eingabe

    st.markdown("**Pacht**")
    pacht_einheit = st.radio(
        "Einheit", options=["€/ha/Jahr", "€/kWp/Jahr"], horizontal=True,
        key=f"{form_key}_pacht_einheit",
    )
    pacht_mode_key = f"{form_key}_pacht_mode_prev"
    pacht_mode_changed = st.session_state.get(pacht_mode_key) != pacht_einheit
    st.session_state[pacht_mode_key] = pacht_einheit

    with st.form(form_key, clear_on_submit=False):
        name = st.text_input(
            "Projektname",
            value=existing.name if existing else "",
            placeholder="z.B. Sonnenfeld Agri-PV",
            key=f"{form_key}_name",
        )

        st.markdown("**Wirtschaftliche Parameter**")
        col5, col6, col7, col8 = st.columns(4)
        fk_zins = col5.number_input(
            "Fremdkapitalzins (%)", min_value=0.0,
            value=existing.fremdkapitalzins_pct * 100 if existing else 3.5,
            step=0.1, key=f"{form_key}_fkzins",
        )
        ek_anteil = col6.number_input(
            "Eigenkapitalanteil (%)", min_value=0.0, max_value=100.0,
            value=existing.eigenkapitalquote_pct * 100 if existing else 20.0,
            step=1.0, key=f"{form_key}_ekanteil",
        )
        eag_zuschlag = col7.number_input(
            "EAG-Zuschlagswert (ct/kWh)", min_value=0.0,
            value=existing.eag_zuschlagswert_ct_kwh if existing else 7.2,
            step=0.1, key=f"{form_key}_eag",
        )
        gemeindeabgabe_default = (
            existing.gemeindeabgabe_eur_mwh
            if existing
            else load_global_assumptions().gemeindeabgabe_eur_kwh * 1000
        )
        gemeindeabgabe_mwh = col8.number_input(
            "Gemeindeabgabe (€/MWh)", min_value=0.0,
            value=gemeindeabgabe_default, step=0.5,
            key=f"{form_key}_gemeindeabgabe",
        )
        if anlagentyp_label == "Konventionell":
            st.caption(
                f"ℹ️ Konventionell: automatischer Abschlag von 25 % wird angewendet "
                f"→ effektiv {eag_zuschlag * 0.75:.2f} ct/kWh"
            )

        if pacht_einheit == "€/ha/Jahr":
            flaeche_key = f"{form_key}_flaeche"
            if pacht_mode_changed or flaeche_key not in st.session_state:
                st.session_state[flaeche_key] = (
                    existing.projektflaeche_ha
                    if existing and existing.projektflaeche_ha
                    else 10.0
                )
            flaeche_ha = st.number_input(
                "Projektfläche (ha)", min_value=0.01, step=0.5, key=flaeche_key,
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
                pacht_eur_ha * flaeche_ha / nennleistung_kwp if nennleistung_kwp else 0.0
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

        st.markdown("**Investkosten (Details)**")
        c1, c2, c3, c4 = st.columns(4)
        epc = capex_feld(
            c1, "EPC",
            capex_defaults.epc_eur if existing else nennleistung_kwp * 600,
            "epc",
        )
        netzanschluss = capex_feld(
            c2, "Netzanschluss",
            capex_defaults.netzanschluss_eur if existing else 150000.0,
            "netz",
        )
        trasse = capex_feld(
            c3, "Trasse",
            capex_defaults.trasse_eur if existing else 60000.0,
            "trasse",
        )
        sonstige_extern = capex_feld(
            c4, "Sonstige Extern",
            capex_defaults.sonstige_extern_eur if existing else 40000.0,
            "sonst",
        )
        c5, c6, c7 = st.columns(3)
        agm = capex_feld(
            c5, "AGM",
            capex_defaults.agm_eur if existing else 30000.0,
            "agm",
        )
        m_and_a = capex_feld(
            c6, "M&A",
            capex_defaults.m_and_a_eur if existing else 20000.0,
            "ma",
        )
        poenale = capex_feld(
            c7, "Pönale + Puffer",
            capex_defaults.poenale_puffer_eur if existing else 35000.0,
            "poenale",
        )

        button_label = "Änderungen speichern" if existing else "Projekt anlegen und berechnen"
        submitted = st.form_submit_button(button_label, type="primary")

    if not submitted:
        return None
    if not name.strip():
        st.error("Bitte einen Projektnamen angeben.")
        return None

    project_id = existing.id if existing else name.strip().lower().replace(" ", "-")
    return PVProject(
        id=project_id,
        name=name.strip(),
        inbetriebnahme_jahr=inbetriebnahme_jahr,
        inbetriebnahme_monat=inbetriebnahme_monat,
        anlagentyp=AnlagenTyp.AGRI_PV
        if anlagentyp_label == "Agri-PV"
        else AnlagenTyp.KONVENTIONELL,
        nennleistung_kwp=nennleistung_kwp,
        vollbenutzungsstunden_kwh_kwp=vollbenutzungsstunden,
        pacht_eur_kwp_jahr=pacht_eur_kwp_jahr,
        projektflaeche_ha=flaeche_ha,
        fremdkapitalzins_pct=fk_zins / 100,
        eigenkapitalquote_pct=ek_anteil / 100,
        eag_zuschlagswert_ct_kwh=eag_zuschlag,
        gemeindeabgabe_eur_mwh=gemeindeabgabe_mwh,
        capex=CapexBreakdown(
            epc_eur=epc,
            netzanschluss_eur=netzanschluss,
            trasse_eur=trasse,
            sonstige_extern_eur=sonstige_extern,
            agm_eur=agm,
            m_and_a_eur=m_and_a,
            poenale_puffer_eur=poenale,
        ),
    )


def render_new_project_form() -> None:
    st.subheader("Neues Projekt anlegen")
    st.caption(
        "Nur projektspezifische Angaben. Preiskurven, Standardbetriebskosten, "
        "Kreditlaufzeit und Steuerlogik werden automatisch aus den "
        "Globalen Annahmen übernommen."
    )

    project = render_project_form(existing=None, form_key="neues_projekt")
    if project is None:
        return

    save_path = PROJECTS_DIR / f"{project.id}.yaml"
    save_project_yaml(project, save_path)
    st.session_state["selected_project"] = project.id
    st.cache_data.clear()

    st.success(f"Projekt „{project.name}“ angelegt und berechnet.")
    st.divider()
    global_assumptions = load_global_assumptions()
    render_project_dashboard(project, global_assumptions, save_path)


# ---------------------------------------------------------------------------
# Seite: Projektuebersicht + Dashboard
# ---------------------------------------------------------------------------


def render_import_export() -> None:
    with st.expander("📤 Projekte sichern / wiederherstellen"):
        st.caption(
            "Streamlit Cloud hat kein dauerhaftes Dateisystem: Neu angelegte "
            "Projekte gehen bei einem Reboot/Redeploy verloren, wenn sie "
            "nicht im GitHub-Repo liegen. Laden Sie Ihre Projekte hier als "
            "YAML herunter und committen Sie sie ins Repo, um sie dauerhaft "
            "zu sichern - oder stellen Sie zuvor gesicherte Projekte wieder "
            "her, indem Sie die YAML-Dateien hier hochladen."
        )
        col_dl, col_ul = st.columns(2)

        with col_dl:
            st.markdown("**Herunterladen**")
            projects = list_projects()
            if projects:
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                    for path in projects.values():
                        zf.write(path, arcname=path.name)
                buffer.seek(0)
                st.download_button(
                    "⬇️ Alle Projekte als ZIP",
                    data=buffer,
                    file_name="projekte.zip",
                    mime="application/zip",
                    width="stretch",
                )
            else:
                st.caption("Keine Projekte vorhanden.")

        with col_ul:
            st.markdown("**Hochladen**")
            uploaded_files = st.file_uploader(
                "YAML-Dateien (auch mehrere gleichzeitig)",
                type=["yaml", "yml"],
                accept_multiple_files=True,
                key="project_upload",
            )
            if uploaded_files and st.button(
                "Hochgeladene Projekte speichern", type="primary", width="stretch"
            ):
                erfolgreich = []
                fehler = []
                for f in uploaded_files:
                    try:
                        raw = yaml.safe_load(f.getvalue().decode("utf-8"))
                        project = PVProject.model_validate(raw)
                        save_project_yaml(project, PROJECTS_DIR / f"{project.id}.yaml")
                        erfolgreich.append(project.name)
                    except Exception as exc:
                        fehler.append(f"„{f.name}“: {exc}")
                if erfolgreich:
                    st.success("Gespeichert: " + ", ".join(erfolgreich))
                if fehler:
                    st.error("Fehler bei " + "; ".join(fehler))
                st.cache_data.clear()
                st.rerun()


def render_project_overview() -> None:
    render_import_export()

    projects = list_projects()
    if not projects:
        st.info("Noch keine Projekte angelegt. Starten Sie mit „Neues Projekt“.")
        return

    global_assumptions = load_global_assumptions()

    st.subheader("Projekte")
    selected = st.session_state.get("selected_project")
    cols = st.columns(min(len(projects), 4))
    for i, (pid, path) in enumerate(projects.items()):
        project = load_project_yaml(path)
        result = run_valuation(project, global_assumptions)
        with cols[i % len(cols)]:
            typ_label = "Agri-PV" if project.anlagentyp == AnlagenTyp.AGRI_PV else "Konventionell"
            st.markdown(
                f"""<div class="project-card">
                <b>{project.name}</b><br/>
                <span style="color:#5B6B66;">{typ_label} · {project.nennleistung_kwp:,.0f} kWp</span><br/>
                <span style="font-size:1.4em; font-weight:600;">{format_pct(result.kpis.equity_irr)}</span>
                <span style="color:#5B6B66;"> EK-Rendite</span>
                </div>""".replace(",", "."),
                unsafe_allow_html=True,
            )
            if st.button("Öffnen", key=f"open_{pid}", width="stretch"):
                st.session_state["selected_project"] = pid
                st.rerun()

    if not selected or selected not in projects:
        return

    st.divider()
    project = load_project_yaml(projects[selected])
    render_project_dashboard(project, global_assumptions, projects[selected])


def render_project_dashboard(
    project: PVProject, global_assumptions: GlobalAssumptions, file_path: Path
) -> None:
    with st.expander("✏️ Projekt bearbeiten"):
        updated = render_project_form(existing=project, form_key=f"edit_{project.id}")
        if updated is not None:
            # Bewusst file_path statt project.id verwenden: id und Dateiname
            # koennen (z.B. durch manuelle YAML-Bearbeitung) auseinanderlaufen -
            # wir wollen immer die tatsaechlich geoeffnete Datei ueberschreiben,
            # nicht versehentlich eine zweite Datei erzeugen.
            save_project_yaml(updated, file_path)
            st.cache_data.clear()
            st.success("Projekt aktualisiert.")
            st.rerun()

    result = run_valuation(project, global_assumptions)
    df = result.cashflow.data
    kpis = result.kpis

    MONATE_KURZ = [
        "Jan", "Feb", "Mär", "Apr", "Mai", "Jun",
        "Jul", "Aug", "Sep", "Okt", "Nov", "Dez",
    ]
    typ_label = "Agri-PV" if project.anlagentyp == AnlagenTyp.AGRI_PV else "Konventionell"
    st.markdown(f"### {project.name}")
    st.caption(
        f"{typ_label} · {project.nennleistung_kwp:,.0f} kWp · "
        f"Inbetriebnahme {MONATE_KURZ[project.inbetriebnahme_monat - 1]} {project.inbetriebnahme_jahr} · "
        f"effektiver EAG-Zuschlag {project.eag_zuschlagswert_effektiv_ct_kwh:.2f} ct/kWh"
        .replace(",", ".")
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("EK-Rendite (IRR)", format_pct(kpis.equity_irr))
    col2.metric("NPV bei 5 %", format_eur(kpis.npv_eur))
    col3.metric(
        "Min. DSCR (Kreditlaufzeit)",
        f"{kpis.dscr_min:.2f}x" if kpis.dscr_min is not None else "n/a",
    )
    col4.metric("Investitionsvolumen", format_eur(kpis.capex_total_eur))

    if kpis.dscr_min is not None and kpis.dscr_min < 1.0:
        st.warning(
            f"⚠️ Der minimale DSCR liegt bei {kpis.dscr_min:.2f}x und damit unter 1,0x: "
            f"Der operative Cashflow deckt den Schuldendienst in mindestens einem Jahr "
            f"der Kreditlaufzeit nicht vollständig. Mit den aktuellen Annahmen müsste "
            f"während der Fremdfinanzierungsphase zusätzliches Eigenkapital nachgeschossen "
            f"werden. Details siehe Tab DSCR – meist hilft eine niedrigere "
            f"Fremdkapitalquote oder eine längere Kreditlaufzeit."
        )

    tab_cf, tab_dscr, tab_npv, tab_sens = st.tabs(
        ["Cashflow", "DSCR", "NPV-Sensitivität (Diskontsatz)", "Sensitivität EAG-Zuschlag"]
    )

    with tab_cf:
        # 1) Umsatzerlöse
        st.markdown("**Umsatzerlöse**")
        fig_erloes = go.Figure()
        fig_erloes.add_bar(
            x=df["jahr"], y=df["erloes_eur"], name="Umsatzerlöse",
            marker_color="#2E7D32",
        )
        fig_erloes.update_layout(
            yaxis=dict(title="€"), margin=dict(t=20, b=20), height=360,
            showlegend=False,
        )
        st.plotly_chart(fig_erloes, width="stretch")

        # 2) Betriebskosten, gestapelt nach Einzelposten (inkl. Gemeindeabgabe)
        st.markdown("**Betriebskosten (nach Position)**")
        st.caption(
            "Klicken Sie auf einzelne Positionen in der Legende, um sie "
            "ein-/auszublenden."
        )
        fig_opex = go.Figure()
        farben_opex = [
            "#C0392B", "#E67E22", "#D68910", "#B9770E", "#A04000",
            "#873600", "#6E2C00", "#943126",
        ]
        for i, posten in enumerate(result.cashflow.opex_posten):
            fig_opex.add_bar(
                x=df["jahr"], y=df[posten], name=posten,
                marker_color=farben_opex[i % len(farben_opex)],
            )
        fig_opex.add_bar(
            x=df["jahr"], y=df["gemeindeabgabe_eur"], name="Gemeindeabgabe",
            marker_color="#7B241C",
        )
        fig_opex.update_layout(
            barmode="stack",
            yaxis=dict(title="€"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=40, b=20),
            height=420,
        )
        st.plotly_chart(fig_opex, width="stretch")

        # 3) Operativer Cashflow (Umsatzerlöse - Betriebskosten)
        st.markdown("**Operativer Cashflow (Umsatzerlöse − Betriebskosten)**")
        st.caption(
            "Vereinfachte Betrachtung vor Zinsen und Steuer. Die für "
            "EK-Rendite/NPV massgebliche Cashflow-Definition (inkl. Zinsen "
            "und Steuer) finden Sie in der Tabelle unten."
        )
        opex_minus_erloes = df["erloes_eur"] - df["opex_gesamt_eur"]
        fig_op = go.Figure()
        fig_op.add_bar(
            x=df["jahr"], y=opex_minus_erloes, name="Operativer Cashflow",
            marker_color=["#2E7D32" if v >= 0 else "#C0392B" for v in opex_minus_erloes],
        )
        fig_op.update_layout(
            yaxis=dict(title="€"), margin=dict(t=20, b=20), height=360,
            showlegend=False,
        )
        st.plotly_chart(fig_op, width="stretch")

        # 4) Cashflow aus Finanzierungstätigkeit
        st.markdown("**Cashflow aus Finanzierungstätigkeit**")
        st.caption(
            "Aufgeschlüsselt nach Kreditaufnahme (Jahr 0) und Tilgung "
            "(laufend). Zinsen sind hier nicht enthalten - sie fliessen "
            "bereits in den operativen Cashflow ein. Die Investitionsauszahlung "
            "(CAPEX) ist bewusst nicht dargestellt, da dafür auch die "
            "Eigenkapitaleinlage gezeigt werden müsste."
        )
        kreditaufnahme_eur = df["cf_finanzierung_eur"] + df["tilgung_eur"]
        fig_fin = go.Figure()
        fig_fin.add_bar(
            x=df["jahr"], y=kreditaufnahme_eur, name="Kreditaufnahme",
            marker_color="#2E7D32",
        )
        fig_fin.add_bar(
            x=df["jahr"], y=-df["tilgung_eur"], name="Tilgung",
            marker_color="#8AA6A0",
        )
        fig_fin.update_layout(
            barmode="relative",
            yaxis=dict(title="€"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=40, b=20),
            height=420,
        )
        st.plotly_chart(fig_fin, width="stretch")

        # 5) Gesamt-Cashflow (Summe aller Kategorien) + kumulierte Kurve
        st.markdown("**Gesamt-Cashflow**")
        st.caption(
            "Summe aus operativem, Investitions- und Finanzierungs-Cashflow "
            "je Jahr (Balken) sowie kumuliert über die Zeit (Linie, rechte "
            "Achse)."
        )
        fig_gesamt = go.Figure()
        fig_gesamt.add_bar(
            x=df["jahr"], y=df["cf_gesamt_eur"], name="Cashflow (Jahr)",
            marker_color=["#2E7D32" if v >= 0 else "#C0392B" for v in df["cf_gesamt_eur"]],
        )
        fig_gesamt.add_scatter(
            x=df["jahr"], y=df["cf_kumuliert_eur"], name="Kumulierter Cashflow",
            mode="lines+markers", line=dict(color="#163832", width=2),
            yaxis="y2",
        )
        fig_gesamt.update_layout(
            yaxis=dict(title="Cashflow (Jahr) in €"),
            yaxis2=dict(title="Kumuliert in €", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=40, b=20),
            height=440,
        )
        st.plotly_chart(fig_gesamt, width="stretch")

        with st.expander("Detailtabelle (Erlöse, Betriebskosten, Zinsen, Steuer)"):
            detail_df = df[
                [
                    "jahr", "erloes_eur", "opex_gesamt_eur", "gemeindeabgabe_eur",
                    "zinsen_eur", "tilgung_eur", "steuer_eur",
                ]
            ].copy()
            for col in detail_df.columns:
                if col != "jahr":
                    detail_df[col] = detail_df[col].round(0)
            detail_df.columns = [
                "Jahr", "Erlöse (€)", "Betriebskosten gesamt (€)",
                "davon Gemeindeabgabe (€)", "Zinsen (€)", "Tilgung (€)", "Steuer (€)",
            ]
            st.dataframe(detail_df, width="stretch", hide_index=True)

        display_df = df[
            [
                "jahr", "cf_operativ_eur", "cf_invest_eur",
                "cf_finanzierung_eur", "cf_gesamt_eur", "cf_kumuliert_eur",
            ]
        ].copy()
        for col in [
            "cf_operativ_eur", "cf_invest_eur", "cf_finanzierung_eur",
            "cf_gesamt_eur", "cf_kumuliert_eur",
        ]:
            display_df[col] = display_df[col].round(0)
        st.dataframe(display_df, width="stretch", hide_index=True)

    with tab_dscr:
        dscr_df = df.dropna(subset=["dscr"]).copy()
        if dscr_df.empty:
            st.info("Kein DSCR verfügbar (keine Fremdfinanzierung in diesem Projekt).")
        else:
            fig = go.Figure()
            fig.add_bar(
                x=dscr_df["jahr"], y=dscr_df["dscr"], name="DSCR",
                marker_color=[
                    "#C0392B" if v < 1.0 else "#2E7D32" for v in dscr_df["dscr"]
                ],
            )
            fig.add_hline(
                y=1.0, line_dash="dot", line_color="gray",
                annotation_text="DSCR = 1,0x (Deckungsgrenze)",
            )
            fig.update_layout(
                xaxis_title="Betriebsjahr",
                yaxis_title="DSCR (x)",
                margin=dict(t=20, b=20),
                height=420,
                showlegend=False,
            )
            st.plotly_chart(fig, width="stretch")

            dscr_display = dscr_df[["jahr", "dscr"]].copy()
            dscr_display["dscr"] = dscr_display["dscr"].round(2)
            dscr_display.columns = ["Jahr", "DSCR (x)"]
            st.dataframe(dscr_display, width="stretch", hide_index=True)

    with tab_npv:
        npv_df = result.npv_curve.copy()
        fig = go.Figure()
        fig.add_scatter(
            x=npv_df["diskontsatz_pct"] * 100,
            y=npv_df["npv_eur"],
            mode="lines+markers",
            name="NPV",
        )
        fig.add_hline(y=0, line_dash="dot", line_color="gray")
        if kpis.equity_irr is not None:
            fig.add_vline(
                x=kpis.equity_irr * 100,
                line_dash="dot",
                line_color="#2E7D32",
                annotation_text="IRR",
            )
        fig.update_layout(
            xaxis_title="Diskontsatz (%)",
            yaxis_title="NPV (€)",
            margin=dict(t=20, b=20),
            height=420,
        )
        st.plotly_chart(fig, width="stretch")

        npv_display = npv_df.copy()
        npv_display["diskontsatz_pct"] = (npv_display["diskontsatz_pct"] * 100).round(1)
        npv_display["npv_eur"] = npv_display["npv_eur"].round(0)
        npv_display.columns = ["Diskontsatz (%)", "NPV (€)"]
        st.dataframe(npv_display, width="stretch", hide_index=True)

    with tab_sens:
        sens_df = run_eag_sensitivity(project, global_assumptions)
        # Defensiv: einzelne Varianten koennen eine nicht berechenbare IRR
        # (None) liefern, wenn der Cashflow keinen Vorzeichenwechsel mehr
        # hat (z.B. durchgehend negativ bei einem -10%-Downside-Szenario).
        # Ohne explizite Behandlung wuerde "* 100" auf einer Spalte mit
        # gemischten float/None-Werten abstuerzen.
        irr_werte = pd.to_numeric(sens_df["equity_irr"], errors="coerce")
        irr_pct = (irr_werte * 100).tolist()
        eag_werte = sens_df["eag_zuschlagswert_ct_kwh"].astype(float).tolist()
        varianten = sens_df["variante"].astype(str).tolist()
        bar_text = [format_pct(v) if v is not None and pd.notna(v) else "n/a"
                    for v in sens_df["equity_irr"]]

        fig = go.Figure()
        fig.add_bar(
            x=eag_werte,
            y=irr_pct,
            width=0.15,
            marker_color=[
                "#2E7D32" if v == "Basis" else "#8AA6A0" for v in varianten
            ],
            customdata=varianten,
            hovertemplate="%{customdata}: %{x:.2f} ct/kWh → %{text}<extra></extra>",
            text=bar_text,
        )
        # Beschriftung ueber feste Annotationen statt textposition="outside":
        # "outside" würde bei negativer IRR unterhalb des Balkens landen
        # (Plotly richtet sich nach dem Vorzeichen). yshift ist ein reiner
        # Pixel-Offset und sitzt dadurch immer oberhalb der Balkenspitze,
        # unabhängig vom Vorzeichen.
        for x_wert, y_wert, text in zip(eag_werte, irr_pct, bar_text):
            fig.add_annotation(
                x=x_wert, y=y_wert if pd.notna(y_wert) else 0,
                text=text, showarrow=False, yshift=14,
                font=dict(size=12, color="#163832"),
            )
        fig.update_layout(
            xaxis=dict(
                title="EAG-Zuschlagswert (ct/kWh)",
                tickmode="array",
                tickvals=eag_werte,
                tickformat=".2f",
            ),
            yaxis=dict(title="EK-Rendite", ticksuffix="%"),
            margin=dict(t=20, b=20),
            height=380,
        )
        st.plotly_chart(fig, width="stretch")

        sens_display = sens_df.copy()
        sens_display["eag_zuschlagswert_ct_kwh"] = sens_display[
            "eag_zuschlagswert_ct_kwh"
        ].round(3)
        sens_display["equity_irr"] = sens_display["equity_irr"].apply(format_pct)
        sens_display["npv_eur"] = sens_display["npv_eur"].round(0)
        sens_display = sens_display[
            ["variante", "eag_zuschlagswert_ct_kwh", "equity_irr", "npv_eur"]
        ]
        sens_display.columns = ["Variante", "EAG-Zuschlag (ct/kWh)", "EK-Rendite", "NPV (€)"]
        st.dataframe(sens_display, width="stretch", hide_index=True)


# ---------------------------------------------------------------------------
# Seite: Globale Annahmen
# ---------------------------------------------------------------------------


def render_global_assumptions_page() -> None:
    st.subheader("Globale Annahmen")
    st.caption(
        "Gelten für alle Projekte, sofern nicht projektspezifisch überschrieben. "
        "Änderungen wirken sich erst nach „Speichern“ auf alle Projekte aus."
    )

    ga = load_global_assumptions()

    with st.expander("Preiskurven (Marktwert Solar & negative Stunden)", expanded=True):
        jahre = sorted(
            set(ga.marktwert_solar_ct_kwh_je_jahr)
            | set(ga.anteil_negativer_stunden_pct_je_jahr)
        )
        kurven_df = pd.DataFrame(
            {
                "Jahr": jahre,
                "Marktwert Solar (ct/kWh)": [
                    ga.marktwert_solar_ct_kwh_je_jahr.get(j) for j in jahre
                ],
                "Anteil neg. Stunden (%)": [
                    (ga.anteil_negativer_stunden_pct_je_jahr.get(j) or 0) * 100
                    for j in jahre
                ],
            }
        )
        edited_kurven = st.data_editor(
            kurven_df, width="stretch", hide_index=True, num_rows="dynamic",
            key="kurven_editor",
        )

    with st.expander("Standardbetriebskosten"):
        opex_df = pd.DataFrame(
            [
                {
                    "Position": item.name,
                    "EUR/kWp/Jahr": item.basiswert_eur_kwp,
                    "Index %/Jahr": item.index_pct_pa * 100,
                    "Indexierung ab Jahr": item.indexierung_ab_jahr,
                }
                for item in ga.opex_standard
            ]
        )
        edited_opex = st.data_editor(
            opex_df, width="stretch", hide_index=True, num_rows="dynamic",
            key="opex_editor",
        )
        gemeindeabgabe = st.number_input(
            "Gemeindeabgabe – Vorschlagswert für neue Projekte (€/MWh)",
            min_value=0.0, value=ga.gemeindeabgabe_eur_kwh * 1000, step=0.5,
            help="Produktionsbasierte Abgabe an die Standortgemeinde. Dient "
                 "nur als Vorbelegung beim Anlegen eines neuen Projekts - die "
                 "tatsächlich angewendete Abgabe wird pro Projekt festgelegt "
                 "(im Projektformular unter 'Wirtschaftliche Parameter'), da "
                 "sie je nach Gemeinde unterschiedlich sein kann.",
        )

    with st.expander("Förderung, Finanzierung, Steuer"):
        col1, col2, col3 = st.columns(3)
        eag_foerderdauer = col1.number_input(
            "EAG-Förderdauer (Jahre)", min_value=1, value=ga.eag_foerderdauer_jahre
        )
        betriebsdauer = col2.number_input(
            "Betrachtungsdauer (Jahre)", min_value=1, value=ga.betriebsdauer_jahre
        )
        kreditlaufzeit = col3.number_input(
            "Kreditlaufzeit (Jahre)", min_value=1, value=ga.kreditlaufzeit_jahre
        )
        col4, col5, col6 = st.columns(3)
        degradation = col4.number_input(
            "Degradation (%/Jahr)", min_value=0.0, value=ga.degradation_pct_pa * 100, step=0.05
        )
        steuersatz = col5.number_input(
            "Steuersatz (%)", min_value=0.0, value=ga.steuersatz_pct * 100, step=0.5
        )
        tilgungsart = col6.selectbox(
            "Tilgungsart", ["annuitaet", "linear"],
            index=0 if ga.tilgungsart.value == "annuitaet" else 1,
        )

    if st.button("Speichern", type="primary"):
        ga.marktwert_solar_ct_kwh_je_jahr = {
            int(r["Jahr"]): float(r["Marktwert Solar (ct/kWh)"])
            for _, r in edited_kurven.iterrows()
            if pd.notna(r["Jahr"]) and pd.notna(r["Marktwert Solar (ct/kWh)"])
        }
        ga.anteil_negativer_stunden_pct_je_jahr = {
            int(r["Jahr"]): float(r["Anteil neg. Stunden (%)"]) / 100
            for _, r in edited_kurven.iterrows()
            if pd.notna(r["Jahr"]) and pd.notna(r["Anteil neg. Stunden (%)"])
        }
        ga.opex_standard = [
            OpexItem(
                name=r["Position"],
                basiswert_eur_kwp=float(r["EUR/kWp/Jahr"]),
                index_pct_pa=float(r["Index %/Jahr"]) / 100,
                indexierung_ab_jahr=int(r["Indexierung ab Jahr"]),
            )
            for _, r in edited_opex.iterrows()
            if pd.notna(r["Position"])
        ]
        ga.eag_foerderdauer_jahre = int(eag_foerderdauer)
        ga.betriebsdauer_jahre = int(betriebsdauer)
        ga.kreditlaufzeit_jahre = int(kreditlaufzeit)
        ga.degradation_pct_pa = degradation / 100
        ga.steuersatz_pct = steuersatz / 100
        ga.tilgungsart = TilgungsArt(tilgungsart)
        ga.gemeindeabgabe_eur_kwh = gemeindeabgabe / 1000

        save_global_assumptions_yaml(ga, GLOBAL_ASSUMPTIONS_PATH)
        st.cache_data.clear()
        st.success("Globale Annahmen gespeichert.")
        st.rerun()


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------


st.title("☀️ TEA PV-Projektbewertung")

nav = st.sidebar.radio(
    "Navigation",
    ["Projektübersicht", "Neues Projekt", "Globale Annahmen"],
    key="nav",
)

if nav == "Projektübersicht":
    render_project_overview()
elif nav == "Neues Projekt":
    render_new_project_form()
else:
    render_global_assumptions_page()
