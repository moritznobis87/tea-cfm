"""
Service-Schicht zwischen UI und Engine.

Aufgaben:
- Datei-Zugriff buendeln (die Views kennen keine Pfade und kein YAML)
- Berechnungen cachen: Bewertungen werden nur neu gerechnet, wenn sich
  die Projekt-Datei ODER die Globalen Annahmen tatsaechlich geaendert
  haben (mtime als Cache-Schluessel). Ohne diesen Cache wuerde die
  Portfolioseite bei jedem Streamlit-Rerun jedes Projekt komplett neu
  durchrechnen.
- Projekt-Lebenszyklus: anlegen, aktualisieren, duplizieren, loeschen,
  eindeutige IDs vergeben.
"""

from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

import pandas as pd
import streamlit as st

from engine import (
    GlobalAssumptions,
    PVProject,
    ValuationResult,
    run_eag_sensitivity,
    run_valuation,
)
from engine.io_yaml import (
    load_global_assumptions_yaml,
    load_project_yaml,
    save_global_assumptions_yaml,
    save_project_yaml,
)

from .config import GLOBAL_ASSUMPTIONS_PATH, PROJECTS_DIR

# ---------------------------------------------------------------------------
# Globale Annahmen
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def _load_global_assumptions_cached(mtime: float) -> GlobalAssumptions:
    return load_global_assumptions_yaml(GLOBAL_ASSUMPTIONS_PATH)


def get_global_assumptions() -> GlobalAssumptions:
    """Laedt die Globalen Annahmen; mtime im Cache-Schluessel macht
    Aenderungen nach dem Speichern sofort sichtbar, ohne bei jedem Rerun
    von Platte zu lesen."""
    mtime = GLOBAL_ASSUMPTIONS_PATH.stat().st_mtime
    return _load_global_assumptions_cached(mtime)


def save_global_assumptions(assumptions: GlobalAssumptions) -> None:
    save_global_assumptions_yaml(assumptions, GLOBAL_ASSUMPTIONS_PATH)
    _load_global_assumptions_cached.clear()
    _run_valuation_cached.clear()
    _run_sensitivity_cached.clear()
    _clear_analytics_caches()


# ---------------------------------------------------------------------------
# Projekte: Zugriff
# ---------------------------------------------------------------------------


def list_project_files() -> dict[str, Path]:
    """Alle Projekt-Dateien, alphabetisch, als {projekt_id: pfad}."""
    return {f.stem: f for f in sorted(PROJECTS_DIR.glob("*.yaml"))}


def get_project(project_id: str) -> PVProject | None:
    path = PROJECTS_DIR / f"{project_id}.yaml"
    if not path.exists():
        return None
    return load_project_yaml(path)


# ---------------------------------------------------------------------------
# Bewertung (gecacht auf Datei-Aenderungen)
# ---------------------------------------------------------------------------


@st.cache_data(show_spinner=False)
def _run_valuation_cached(
    project_path: str, project_mtime: float, ga_mtime: float
) -> ValuationResult:
    project = load_project_yaml(project_path)
    return run_valuation(project, get_global_assumptions())


def get_valuation(project_id: str) -> ValuationResult | None:
    """Vollstaendige Projektbewertung - neu gerechnet nur bei geaenderter
    Projekt-Datei oder geaenderten Globalen Annahmen."""
    path = PROJECTS_DIR / f"{project_id}.yaml"
    if not path.exists():
        return None
    return _run_valuation_cached(
        str(path), path.stat().st_mtime, GLOBAL_ASSUMPTIONS_PATH.stat().st_mtime
    )


@st.cache_data(show_spinner=False)
def _run_sensitivity_cached(
    project_path: str, project_mtime: float, ga_mtime: float
) -> pd.DataFrame:
    project = load_project_yaml(project_path)
    return run_eag_sensitivity(project, get_global_assumptions())


def get_eag_sensitivity(project_id: str) -> pd.DataFrame | None:
    """EAG-Zuschlag-Sensitivitaet (5 Bewertungslaeufe) - gecacht, weil sie
    sonst bei jedem Oeffnen des Sensitivitaets-Tabs neu laufen wuerde."""
    path = PROJECTS_DIR / f"{project_id}.yaml"
    if not path.exists():
        return None
    return _run_sensitivity_cached(
        str(path), path.stat().st_mtime, GLOBAL_ASSUMPTIONS_PATH.stat().st_mtime
    )


# ---------------------------------------------------------------------------
# Projekte: Lebenszyklus
# ---------------------------------------------------------------------------

_UMLAUT_MAP = str.maketrans(
    {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "ae", "Ö": "oe", "Ü": "ue", "ß": "ss"}
)


def slugify(name: str) -> str:
    """Erzeugt einen dateisystem- und URL-sicheren Slug ohne
    Kollisionsaufloesung - fuer Anzeigezwecke wie Download-Dateinamen, bei
    denen zwei gleichnamige Dateien harmlos sind (der Browser haengt bei
    Bedarf selbst '(1)' etc. an).

    'Sonnenfeld Süd (Bauabschnitt 2)' -> 'sonnenfeld-sued-bauabschnitt-2'.
    """
    slug = name.strip().translate(_UMLAUT_MAP)
    slug = unicodedata.normalize("NFKD", slug).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", slug.lower()).strip("-") or "projekt"


def make_project_id(name: str, existing_ids: set[str] | None = None) -> str:
    """Erzeugt eine dateisystem- und URL-sichere, eindeutige Projekt-ID.

    Diese ID wird EINMALIG bei Anlage/Duplizierung vergeben und bleibt
    danach stabil - sie ist der Dateiname der YAML-Datei und damit die
    Identitaet des Projekts (siehe save_project). Ein spaeteres Umbenennen
    des Projekts aendert die ID bewusst NICHT, sonst wuerde die Datei
    umbenannt bzw. eine zweite entstehen. Fuer Anzeigezwecke (z.B.
    Download-Dateinamen), die dem AKTUELLEN Namen folgen sollen, siehe
    slugify().

    'Sonnenfeld Süd (Bauabschnitt 2)' -> 'sonnenfeld-sued-bauabschnitt-2'.
    Bei Kollision wird '-2', '-3', ... angehaengt statt still zu
    ueberschreiben.
    """
    slug = slugify(name)

    existing = existing_ids if existing_ids is not None else set(list_project_files())
    if slug not in existing:
        return slug
    laufnummer = 2
    while f"{slug}-{laufnummer}" in existing:
        laufnummer += 1
    return f"{slug}-{laufnummer}"


def save_project(project: PVProject, path: Path | None = None) -> Path:
    """Speichert ein Projekt (Standard: data/projects/<id>.yaml).

    `path` kann explizit uebergeben werden, wenn eine bereits geoeffnete
    Datei ueberschrieben werden soll - id und Dateiname koennen (z.B. durch
    manuelle YAML-Bearbeitung) auseinanderlaufen, und dann soll die
    tatsaechlich geoeffnete Datei aktualisiert werden, nicht versehentlich
    eine zweite entstehen.
    """
    target = path if path is not None else PROJECTS_DIR / f"{project.id}.yaml"
    save_project_yaml(project, target)
    _run_valuation_cached.clear()
    _run_sensitivity_cached.clear()
    _clear_analytics_caches()
    return target


def duplicate_project(project_id: str) -> PVProject | None:
    """Legt eine Kopie eines Projekts mit neuer ID und '(Kopie)'-Namen an."""
    original = get_project(project_id)
    if original is None:
        return None
    kopie = original.model_copy(deep=True)
    kopie.name = f"{original.name} (Kopie)"
    kopie.id = make_project_id(kopie.name)
    save_project(kopie)
    return kopie


def delete_project(project_id: str) -> bool:
    path = PROJECTS_DIR / f"{project_id}.yaml"
    if not path.exists():
        return False
    path.unlink()
    _run_valuation_cached.clear()
    _run_sensitivity_cached.clear()
    _clear_analytics_caches()
    return True


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def cashflow_to_excel(result: ValuationResult) -> bytes:
    """Exportiert die vollstaendige Cashflow-Zeitreihe eines Projekts als
    Excel-Arbeitsmappe (ein Blatt Cashflow, ein Blatt KPIs)."""
    kpis = result.kpis
    kpi_df = pd.DataFrame(
        [
            ("EK-Rendite (IRR)", kpis.equity_irr),
            ("NPV bei 8 %", kpis.npv_eur),
            ("Payback (Jahre)", kpis.payback_jahre),
            ("Investitionsvolumen (€)", kpis.capex_total_eur),
            ("Eigenkapitaleinsatz (€)", kpis.eigenkapital_eur),
            ("Min. DSCR", kpis.dscr_min),
        ],
        columns=["Kennzahl", "Wert"],
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        result.cashflow.data.to_excel(writer, sheet_name="Cashflow", index=False)
        kpi_df.to_excel(writer, sheet_name="KPIs", index=False)
    buffer.seek(0)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Erweiterte Analytik (v3) - gecacht auf Datei-Aenderungen + Parameter
# ---------------------------------------------------------------------------


def _mtimes(project_id: str) -> tuple[str, float, float] | None:
    path = PROJECTS_DIR / f"{project_id}.yaml"
    if not path.exists():
        return None
    return str(path), path.stat().st_mtime, GLOBAL_ASSUMPTIONS_PATH.stat().st_mtime


@st.cache_data(show_spinner=False)
def _tornado_cached(project_path: str, pm: float, gm: float) -> pd.DataFrame:
    from engine import run_tornado

    return run_tornado(load_project_yaml(project_path), get_global_assumptions())


def get_tornado(project_id: str) -> pd.DataFrame | None:
    key = _mtimes(project_id)
    return _tornado_cached(*key) if key else None


@st.cache_data(show_spinner=False)
def _heatmap_cached(
    project_path: str, pm: float, gm: float, achse_x: str, achse_y: str
) -> pd.DataFrame:
    from engine import run_irr_heatmap

    return run_irr_heatmap(
        load_project_yaml(project_path), get_global_assumptions(),
        achse_x=achse_x, achse_y=achse_y,
    )


def get_irr_heatmap(project_id: str, achse_x: str, achse_y: str) -> pd.DataFrame | None:
    key = _mtimes(project_id)
    return _heatmap_cached(*key, achse_x, achse_y) if key else None


@st.cache_data(show_spinner=False)
def _monte_carlo_cached(
    project_path: str, pm: float, gm: float,
    n_laeufe: int, sigma_items: tuple[tuple[str, float], ...],
    diskontsatz_pct: float,
    gebots_key: tuple | None,
):
    from engine import run_monte_carlo

    ziehungen = None
    if gebots_key is not None:
        # Ziehungen deterministisch aus der (gecachten) Prognose ableiten -
        # der Cache-Schluessel sind Modus + Prognoseparameter.
        prognose = get_gebots_prognose(*gebots_key)
        ziehungen = prognose.gebots_ziehungen(n_laeufe)
    return run_monte_carlo(
        load_project_yaml(project_path), get_global_assumptions(),
        n_laeufe=n_laeufe, sigmas=dict(sigma_items), diskontsatz_pct=diskontsatz_pct,
        gebot_ziehungen=ziehungen,
    )


def get_monte_carlo(
    project_id: str, n_laeufe: int, sigmas: dict[str, float],
    diskontsatz_pct: float,
    gebots_key: tuple | None = None,
):
    """gebots_key = (Modus, Preisobergrenze, sigma_pm, Ordnung, Lambdas)
    aktiviert die Ziehung des EAG-Zuschlagswerts aus dem Ausschreibungs-
    modell; Modus 'letzte' oder 'prognose' (None = fixer Projektwert,
    d.h. die harte Ueberschreibung ueber die Projektmaske)."""
    key = _mtimes(project_id)
    if key is None:
        return None
    return _monte_carlo_cached(
        *key, n_laeufe, tuple(sorted(sigmas.items())), diskontsatz_pct, gebots_key
    )


@st.cache_data(show_spinner=False)
def _break_even_cached(
    project_path: str, pm: float, gm: float, ziel_irr: float
) -> float | None:
    from engine import break_even_zuschlag

    return break_even_zuschlag(
        load_project_yaml(project_path), get_global_assumptions(), ziel_irr
    )


def get_break_even_zuschlag(project_id: str, ziel_irr: float) -> float | None:
    key = _mtimes(project_id)
    return _break_even_cached(*key, ziel_irr) if key else None


@st.cache_data(show_spinner=False)
def _szenarien_cached(project_path: str, pm: float, gm: float, diskontsatz_pct: float):
    from engine import run_scenario_comparison

    return run_scenario_comparison(
        load_project_yaml(project_path), get_global_assumptions(),
        diskontsatz_pct=diskontsatz_pct,
    )


def get_scenario_comparison(project_id: str, diskontsatz_pct: float):
    key = _mtimes(project_id)
    return _szenarien_cached(*key, diskontsatz_pct) if key else None


def _clear_analytics_caches() -> None:
    for fn in (
        _tornado_cached, _heatmap_cached, _monte_carlo_cached,
        _break_even_cached, _szenarien_cached,
    ):
        fn.clear()


# ---------------------------------------------------------------------------
# PDF-Ergebnisbericht
# ---------------------------------------------------------------------------


def build_project_report(project_id: str, diskontsatz_pct: float,
                         ziel_irr_pct: float = 0.08) -> bytes | None:
    """Stellt alle Berichtsbausteine aus den (gecachten) Services zusammen
    und erzeugt den PDF-Bericht. Monte Carlo laeuft mit den dokumentierten
    Standardparametern (400 Laeufe, Standard-Sigmas, fester Seed)."""
    from app.config import LOGO_PATH
    from app.report import ReportInputs, build_pdf_report
    from engine import MC_STANDARD_SIGMAS, calculate_lcoe
    from engine.kpis import npv_at

    path = PROJECTS_DIR / f"{project_id}.yaml"
    result = get_valuation(project_id)
    if result is None or not path.exists():
        return None
    project = load_project_yaml(path)

    inputs = ReportInputs(
        project=project,
        global_assumptions=get_global_assumptions(),
        result=result,
        tornado=get_tornado(project_id),
        eag_sensitivitaet=get_eag_sensitivity(project_id),
        monte_carlo=get_monte_carlo(
            project_id, 400, MC_STANDARD_SIGMAS, diskontsatz_pct
        ),
        szenarien=get_scenario_comparison(project_id, diskontsatz_pct),
        break_even_ct=get_break_even_zuschlag(project_id, ziel_irr_pct),
        lcoe_ct=calculate_lcoe(result.cashflow.data, diskontsatz_pct),
        npv_eur=npv_at(result.cashflow, diskontsatz_pct),
        diskontsatz_pct=diskontsatz_pct,
        ziel_irr_pct=ziel_irr_pct,
        logo_path=LOGO_PATH,
        auktion=_auktions_paket_fuer_bericht(),
    )
    return build_pdf_report(inputs)


def _auktions_paket_fuer_bericht() -> dict | None:
    """Historie + Momentum-Prognose (Standardparameter) fuer das
    Ausschreibungskapitel des PDF-Berichts."""
    try:
        _, df = get_ausschreibungen()
        modell = get_auktions_modell()
        letzte = modell.letzte_runde
        prognose = get_gebots_prognose(
            "prognose", float(letzte.ausschreibung.preisobergrenze_ct),
        )
        wett = sorted((f.ausschreibung for f in modell.fits
                       if not f.ausschreibung.unterzeichnet),
                      key=lambda a: a.datum)
        def _de(v: float) -> str:
            return f"{v:.2f}".replace(".", ",")

        maxes = " → ".join(_de(a.zuschlag_max_ct) for a in wett)
        from texte import txt

        formel = txt(
            "bericht.auktion_formel_zeile", maxes=maxes,
            grenzzuschlag=_de(prognose.grenzzuschlag_zentral_ct),
            mittel=_de(prognose.mittel_prognose_ct),
        )
        return {"df": df, "prognose": prognose, "modell": modell,
                "formel_zeile": formel}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# EAG-Ausschreibungsmodell (Gebotsverteilung)
# ---------------------------------------------------------------------------

from app.config import DATA_DIR as _DATA_DIR  # noqa: E402

AUSSCHREIBUNGEN_PATH = _DATA_DIR / "ausschreibungen.yaml"


@st.cache_data(show_spinner=False)
def _auktions_daten_cached(mtime: float):
    from engine import ausschreibungen_dataframe, load_ausschreibungen

    runden = load_ausschreibungen(AUSSCHREIBUNGEN_PATH)
    return runden, ausschreibungen_dataframe(runden)


def get_ausschreibungen():
    return _auktions_daten_cached(AUSSCHREIBUNGEN_PATH.stat().st_mtime)


@st.cache_resource(show_spinner=False)
def _auktions_modell_cached(mtime: float, familie: str):
    from engine import kalibriere_modell

    runden, _ = _auktions_daten_cached(mtime)
    return kalibriere_modell(runden, familie)


AUKTIONS_FAMILIE = "Gespiegelte Inverse Gamma"


def get_auktions_modell(familie: str = AUKTIONS_FAMILIE):
    return _auktions_modell_cached(AUSSCHREIBUNGEN_PATH.stat().st_mtime, familie)


@st.cache_resource(show_spinner=False)
def _gebots_prognose_cached(mtime: float, familie: str, modus: str,
                            cap: float, sigma_pm: float, ordnung: int,
                            lambdas: tuple[float, ...]):
    from engine import prognose_letzte_runde, prognose_naechste_runde

    modell = _auktions_modell_cached(mtime, familie)
    if modus == "letzte":
        return prognose_letzte_runde(modell)
    return prognose_naechste_runde(
        modell, cap, sigma_pm_ct=sigma_pm if sigma_pm > 0 else None,
        ordnung=ordnung, lambdas=lambdas or None,
    )


def get_gebots_prognose(modus: str, cap: float = 0.0, sigma_pm: float = 0.0,
                        ordnung: int = 2,
                        lambdas: tuple[float, ...] = (),
                        familie: str = AUKTIONS_FAMILIE):
    """modus='letzte' (letzte Ausschreibung als gesetzt) oder
    modus='prognose' (Differenzenextrapolation der naechsten Runde;
    ordnung = maximale Differenzenordnung, lambdas = Daempfung je
    Ordnung, leer -> alle 1; sigma_pm <= 0 -> Standard aus historischen
    Rundenaenderungen). Die Wettbewerbsquote ist impliziert."""
    if modus == "letzte":
        cap = sigma_pm = 0.0
        ordnung, lambdas = 0, ()
    return _gebots_prognose_cached(
        AUSSCHREIBUNGEN_PATH.stat().st_mtime, familie, modus, cap, sigma_pm,
        ordnung, tuple(lambdas),
    )


@st.cache_data(show_spinner=False)
def get_auktions_validierung(familie: str = AUKTIONS_FAMILIE):
    from engine import validiere_einschritt, vergleiche_familien

    runden, _ = get_ausschreibungen()
    return vergleiche_familien(runden), validiere_einschritt(runden, familie)


def build_pipeline_excel(n_mc: int = 300) -> bytes:
    """Ergebnis-Export der gesamten Pipeline: Blatt 'Übersicht' plus je
    Projekt ein Reiter mit allen Auswertungen als native Excel-
    Diagramme (inaktive Projekte enthalten und markiert)."""
    from engine import pipeline_ergebnis_excel

    projekte = [
        (get_project(pid), get_project(pid).name)
        for pid in list_project_files()
    ]
    return pipeline_ergebnis_excel(projekte, get_global_assumptions(), n_mc=n_mc)
