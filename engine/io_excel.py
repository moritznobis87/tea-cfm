"""
Excel-Export/-Import fuer GlobalAssumptions.

Bewusst nur ein alternatives Austauschformat fuer Down-/Upload durch den
Nutzer - die interne Speicherung bleibt YAML (siehe io_yaml.py). Tabellarische
Daten (Preiskurven, Betriebskosten) lassen sich in Excel deutlich bequemer
bearbeiten als in YAML; die uebrigen Skalarwerte landen auf einem dritten
Blatt als einfache Parameter-Wert-Liste.

Struktur der Arbeitsmappe:
- Blatt "Preiskurven": Kalenderjahr, Szenario, Marktwert Solar (ct/kWh),
  Anteil neg. Stunden (%) - Langformat, ein oder mehrere Szenarien
- Blatt "Betriebskosten": Position, EUR/kWp/Jahr, Index %/Jahr,
  Indexierung ab Jahr, Start Betriebsjahr
- Blatt "Einstellungen": Parameter, Wert (alle uebrigen Skalarfelder)
"""

from __future__ import annotations

import io

import pandas as pd

from .models import (
    AnlagenTyp,
    CapexBreakdown,
    GlobalAssumptions,
    MarktpreisSzenario,
    OpexItem,
    PVProject,
    TaxModus,
    TilgungsArt,
)

EINSTELLUNGEN_DEFAULTS = {
    "gueltig_ab": "",
    "gemeindeabgabe_eur_mwh_vorschlag": 2.0,
    "degradation_pct_pa": 0.5,
    "sicherheitsabschlag_pct": 0.0,
    "eag_foerderdauer_jahre": 20,
    "betriebsdauer_jahre": 25,
    "kreditlaufzeit_jahre": 20,
    "tilgungsart": "annuitaet",
    "tax_modus": "pauschal_auf_ebt",
    "steuersatz_pct": 23.0,
    "afa_nutzungsdauer_jahre": None,
    "freibetrag_eur": 0.0,
}


def global_assumptions_to_excel(ga: GlobalAssumptions) -> bytes:
    kurven_zeilen = []
    for szenario in ga.marktpreisszenarien:
        jahre = sorted(
            set(szenario.marktwert_solar_ct_kwh_je_kalenderjahr)
            | set(szenario.anteil_negativer_stunden_pct_je_kalenderjahr)
        )
        for jahr in jahre:
            kurven_zeilen.append(
                {
                    "Kalenderjahr": jahr,
                    "Szenario": szenario.name,
                    "Marktwert Solar (ct/kWh)": (
                        szenario.marktwert_solar_ct_kwh_je_kalenderjahr.get(jahr)
                    ),
                    "Anteil neg. Stunden (%)": (
                        szenario.anteil_negativer_stunden_pct_je_kalenderjahr.get(jahr)
                        or 0
                    )
                    * 100,
                }
            )
    kurven_df = pd.DataFrame(
        kurven_zeilen,
        columns=["Kalenderjahr", "Szenario", "Marktwert Solar (ct/kWh)", "Anteil neg. Stunden (%)"],
    )

    opex_df = pd.DataFrame(
        [
            {
                "Position": item.name,
                "EUR/kWp/Jahr": item.basiswert_eur_kwp,
                "Index %/Jahr": item.index_pct_pa * 100,
                "Indexierung ab Jahr": item.indexierung_ab_jahr,
                "Start Betriebsjahr": item.start_betriebsjahr,
            }
            for item in ga.opex_standard
        ]
    )

    einstellungen_df = pd.DataFrame(
        [
            ("gueltig_ab", ga.gueltig_ab),
            ("gemeindeabgabe_eur_mwh_vorschlag", ga.gemeindeabgabe_eur_kwh * 1000),
            ("degradation_pct_pa", ga.degradation_pct_pa * 100),
            ("sicherheitsabschlag_pct", ga.sicherheitsabschlag_pct * 100),
            ("eag_foerderdauer_jahre", ga.eag_foerderdauer_jahre),
            ("betriebsdauer_jahre", ga.betriebsdauer_jahre),
            ("kreditlaufzeit_jahre", ga.kreditlaufzeit_jahre),
            ("tilgungsart", ga.tilgungsart.value),
            ("tax_modus", ga.tax_modus.value),
            ("steuersatz_pct", ga.steuersatz_pct * 100),
            ("afa_nutzungsdauer_jahre", ga.afa_nutzungsdauer_jahre),
            ("freibetrag_eur", ga.freibetrag_eur),
        ],
        columns=["Parameter", "Wert"],
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        kurven_df.to_excel(writer, sheet_name="Preiskurven", index=False)
        opex_df.to_excel(writer, sheet_name="Betriebskosten", index=False)
        einstellungen_df.to_excel(writer, sheet_name="Einstellungen", index=False)
    buffer.seek(0)
    return buffer.getvalue()


def excel_to_global_assumptions(file_bytes: bytes) -> GlobalAssumptions:
    sheets = pd.read_excel(io.BytesIO(file_bytes), sheet_name=None, engine="openpyxl")

    fehlende_blaetter = {"Preiskurven", "Betriebskosten", "Einstellungen"} - set(sheets)
    if fehlende_blaetter:
        raise ValueError(f"Blätter fehlen in der Excel-Datei: {fehlende_blaetter}")

    kurven_df = sheets["Preiskurven"]
    opex_df = sheets["Betriebskosten"]
    einstellungen_df = sheets["Einstellungen"]

    szenarien: dict[str, MarktpreisSzenario] = {}
    for _, r in kurven_df.iterrows():
        if pd.isna(r["Kalenderjahr"]) or pd.isna(r["Szenario"]):
            continue
        name = str(r["Szenario"])
        if name not in szenarien:
            szenarien[name] = MarktpreisSzenario(name=name)
        jahr = int(r["Kalenderjahr"])
        if pd.notna(r["Marktwert Solar (ct/kWh)"]):
            szenarien[name].marktwert_solar_ct_kwh_je_kalenderjahr[jahr] = float(
                r["Marktwert Solar (ct/kWh)"]
            )
        if pd.notna(r["Anteil neg. Stunden (%)"]):
            szenarien[name].anteil_negativer_stunden_pct_je_kalenderjahr[jahr] = (
                float(r["Anteil neg. Stunden (%)"]) / 100
            )

    opex_items = [
        OpexItem(
            name=str(r["Position"]),
            basiswert_eur_kwp=float(r["EUR/kWp/Jahr"]),
            index_pct_pa=float(r["Index %/Jahr"]) / 100,
            indexierung_ab_jahr=int(r["Indexierung ab Jahr"]),
            start_betriebsjahr=(
                int(r["Start Betriebsjahr"])
                if "Start Betriebsjahr" in opex_df.columns
                and pd.notna(r["Start Betriebsjahr"])
                else 1
            ),
        )
        for _, r in opex_df.iterrows()
        if pd.notna(r["Position"])
    ]

    einstellungen = dict(zip(einstellungen_df["Parameter"], einstellungen_df["Wert"]))

    def get(key: str):
        wert = einstellungen.get(key, EINSTELLUNGEN_DEFAULTS[key])
        return EINSTELLUNGEN_DEFAULTS[key] if pd.isna(wert) else wert

    afa_wert = get("afa_nutzungsdauer_jahre")

    return GlobalAssumptions(
        gueltig_ab=str(get("gueltig_ab")),
        marktpreisszenarien=list(szenarien.values()),
        opex_standard=opex_items,
        gemeindeabgabe_eur_kwh=float(get("gemeindeabgabe_eur_mwh_vorschlag")) / 1000,
        degradation_pct_pa=float(get("degradation_pct_pa")) / 100,
        sicherheitsabschlag_pct=float(get("sicherheitsabschlag_pct")) / 100,
        eag_foerderdauer_jahre=int(get("eag_foerderdauer_jahre")),
        betriebsdauer_jahre=int(get("betriebsdauer_jahre")),
        kreditlaufzeit_jahre=int(get("kreditlaufzeit_jahre")),
        tilgungsart=TilgungsArt(get("tilgungsart")),
        tax_modus=TaxModus(get("tax_modus")),
        steuersatz_pct=float(get("steuersatz_pct")) / 100,
        afa_nutzungsdauer_jahre=int(afa_wert) if afa_wert not in (None, "") else None,
        freibetrag_eur=float(get("freibetrag_eur")),
    )


# ---------------------------------------------------------------------------
# Projekte: eine Zeile pro Projekt in einer gemeinsamen Excel-Datei
# ---------------------------------------------------------------------------

PROJEKT_SPALTEN = [
    "id", "name", "inbetriebnahme_jahr", "inbetriebnahme_monat", "anlagentyp",
    "nennleistung_kwp", "vollbenutzungsstunden_kwh_kwp", "pacht_eur_kwp_jahr",
    "fremdkapitalzins_pct", "eigenkapitalquote_pct", "eag_zuschlagswert_ct_kwh",
    "gemeindeabgabe_eur_mwh", "marktpreisszenario", "projektflaeche_ha",
    "capex_epc_eur", "capex_netzanschluss_eur", "capex_trasse_eur",
    "capex_sonstige_extern_eur", "capex_agm_eur", "capex_m_and_a_eur",
    "capex_poenale_puffer_eur",
]


def projects_to_excel(projects: list[PVProject]) -> bytes:
    rows = [
        {
            "id": p.id,
            "name": p.name,
            "inbetriebnahme_jahr": p.inbetriebnahme_jahr,
            "inbetriebnahme_monat": p.inbetriebnahme_monat,
            "anlagentyp": p.anlagentyp.value,
            "nennleistung_kwp": p.nennleistung_kwp,
            "vollbenutzungsstunden_kwh_kwp": p.vollbenutzungsstunden_kwh_kwp,
            "pacht_eur_kwp_jahr": p.pacht_eur_kwp_jahr,
            "fremdkapitalzins_pct": p.fremdkapitalzins_pct * 100,
            "eigenkapitalquote_pct": p.eigenkapitalquote_pct * 100,
            "eag_zuschlagswert_ct_kwh": p.eag_zuschlagswert_ct_kwh,
            "gemeindeabgabe_eur_mwh": p.gemeindeabgabe_eur_mwh,
            "marktpreisszenario": p.marktpreisszenario,
            "projektflaeche_ha": p.projektflaeche_ha,
            "capex_epc_eur": p.capex.epc_eur,
            "capex_netzanschluss_eur": p.capex.netzanschluss_eur,
            "capex_trasse_eur": p.capex.trasse_eur,
            "capex_sonstige_extern_eur": p.capex.sonstige_extern_eur,
            "capex_agm_eur": p.capex.agm_eur,
            "capex_m_and_a_eur": p.capex.m_and_a_eur,
            "capex_poenale_puffer_eur": p.capex.poenale_puffer_eur,
        }
        for p in projects
    ]
    df = pd.DataFrame(rows, columns=PROJEKT_SPALTEN)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Projekte", index=False)
    buffer.seek(0)
    return buffer.getvalue()


def excel_to_projects(file_bytes: bytes) -> list[PVProject]:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Projekte", engine="openpyxl")

    fehlende_spalten = set(PROJEKT_SPALTEN) - set(df.columns)
    if fehlende_spalten:
        raise ValueError(f"Spalten fehlen in der Excel-Datei: {fehlende_spalten}")

    projects = []
    for _, r in df.iterrows():
        if pd.isna(r["id"]) or pd.isna(r["name"]):
            continue
        projects.append(
            PVProject(
                id=str(r["id"]),
                name=str(r["name"]),
                inbetriebnahme_jahr=int(r["inbetriebnahme_jahr"]),
                inbetriebnahme_monat=int(r["inbetriebnahme_monat"]),
                anlagentyp=AnlagenTyp(r["anlagentyp"]),
                nennleistung_kwp=float(r["nennleistung_kwp"]),
                vollbenutzungsstunden_kwh_kwp=float(r["vollbenutzungsstunden_kwh_kwp"]),
                pacht_eur_kwp_jahr=float(r["pacht_eur_kwp_jahr"]),
                fremdkapitalzins_pct=float(r["fremdkapitalzins_pct"]) / 100,
                eigenkapitalquote_pct=float(r["eigenkapitalquote_pct"]) / 100,
                eag_zuschlagswert_ct_kwh=float(r["eag_zuschlagswert_ct_kwh"]),
                gemeindeabgabe_eur_mwh=float(r["gemeindeabgabe_eur_mwh"]),
                marktpreisszenario=(
                    str(r["marktpreisszenario"])
                    if pd.notna(r["marktpreisszenario"])
                    else "Aurora 10/25"
                ),
                projektflaeche_ha=(
                    float(r["projektflaeche_ha"])
                    if pd.notna(r["projektflaeche_ha"])
                    else None
                ),
                capex=CapexBreakdown(
                    epc_eur=float(r["capex_epc_eur"]),
                    netzanschluss_eur=float(r["capex_netzanschluss_eur"]),
                    trasse_eur=float(r["capex_trasse_eur"]),
                    sonstige_extern_eur=float(r["capex_sonstige_extern_eur"]),
                    agm_eur=float(r["capex_agm_eur"]),
                    m_and_a_eur=float(r["capex_m_and_a_eur"]),
                    poenale_puffer_eur=float(r["capex_poenale_puffer_eur"]),
                ),
            )
        )
    return projects
