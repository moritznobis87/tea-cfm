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
- Blatt "Preiskurven Monate": Kalenderjahr, Szenario, Monat, Marktwert
  Solar (ct/kWh), Erzeugungsmenge neg. Stunden 6h/1h (%) - optional; nur
  noetig, wenn in Monatsaufloesung gerechnet wird
- Blatt "Einspeisekurve": Monat, Anteil an der Jahreserzeugung (%)
- Blatt "Einstellungen": Parameter, Wert (alle uebrigen Skalarfelder)

Die beiden Monatsblaetter sind optional: Eine frueher gesicherte Datei
kennt sie nicht und bleibt trotzdem lesbar - es gilt dann die
Jahresaufloesung mit der Standard-Einspeisekurve.
"""

from __future__ import annotations

import io
import json

import pandas as pd

from .models import (
    AnlagenTyp,
    CapexBreakdown,
    CapexPosition,
    EINSPEISEKURVE_STANDARD_PCT,
    DirektvermarktungsModus,
    GlobalAssumptions,
    MarktpreisSzenario,
    NegativeStundenModus,
    NegativeStundenRegel,
    OpexItem,
    PachtModus,
    PraemienModell,
    PVProject,
    TaxModus,
    TilgungsArt,
    Zeitaufloesung,
    ZinsMethode,
)

EINSTELLUNGEN_DEFAULTS = {
    "gueltig_ab": "",
    "gemeindeabgabe_eur_mwh_vorschlag": 2.0,
    "pacht_umsatzbeteiligung_pct_vorschlag": 5.5,
    "direktvermarktungskosten_eur_mwh_vorschlag": 1.0,
    "direktvermarktung_modus": "absolut",
    "negative_stunden_regel": "6h",
    "kosten_inflation_pct_pa": 0.02,
    "direktvermarktung_pct_marktwert": 10.0,
    "negative_stunden_gewichtung_pct": 100.0,
    "negative_stunden_modus": "marktwert",
    "degradation_pct_pa": 0.25,
    "sicherheitsabschlag_pct": 0.0,
    "eag_foerderdauer_jahre": 20,
    "betriebsdauer_jahre": 25,
    "kreditlaufzeit_jahre": 20,
    "tilgungsart": "annuitaet",
    "tilgungsfreies_anlaufjahr": "NEIN",
    "zinsmethode": "oesterreich_act_365",
    "dscr_cash_trap": 1.10,
    "dscr_event_of_default": 1.05,
    "tax_modus": "afa_koerperschaftsteuer",
    "steuersatz_pct": 23.0,
    "afa_nutzungsdauer_jahre": None,
    "freibetrag_eur": 0.0,
    "gewerbesteuer_hebesatz_pct": 400.0,
    "gewerbesteuer_freibetrag_eur": 24_500.0,
    "verlustvortrag_verrechnungsgrenze_pct": 75.0,
    "marktpreis_inflation_pct_pa": 2.0,
    "marktpreis_inflation_basisjahr": 2025,
    # seit v5.4 (Monatsaufloesung, Praemienmodelle, hybride PPA)
    "zeitaufloesung": "jahr",
    "praemien_modell": "einseitig_cfd",
    "eag_rueckzahlung_ab_mw": 5.0,
    "eag_rueckzahlung_toleranzband_pct": 40.0,
    "eag_rueckzahlung_anteil_pct": 66.0,
    "ppa_anteil_pct_vorschlag": 50.0,
    "ppa_preis_eur_mwh_vorschlag": 65.0,
    "ppa_laufzeit_jahre_vorschlag": 10,
    "ppa_indexierung_pct_pa_vorschlag": 1.0,
}


def global_assumptions_to_excel(ga: GlobalAssumptions) -> bytes:
    kurven_zeilen = []
    for szenario in ga.marktpreisszenarien:
        jahre = sorted(
            set(szenario.marktwert_solar_ct_kwh_je_kalenderjahr)
            | set(szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr)
            | set(szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr)
            | set(szenario.baseload_ct_kwh_je_kalenderjahr)
        )
        for jahr in jahre:
            kurven_zeilen.append(
                {
                    "Kalenderjahr": jahr,
                    "Szenario": szenario.name,
                    "Marktwert Solar (ct/kWh)": (
                        szenario.marktwert_solar_ct_kwh_je_kalenderjahr.get(jahr)
                    ),
                    "Erzeugungsmenge neg. Stunden 6h (%)": (
                        szenario.erzeugungsmenge_negativ_6h_pct_je_kalenderjahr.get(
                            jahr
                        )
                        or 0
                    )
                    * 100,
                    "Erzeugungsmenge neg. Stunden 1h (%)": (
                        szenario.erzeugungsmenge_negativ_1h_pct_je_kalenderjahr.get(
                            jahr
                        )
                        or 0
                    )
                    * 100,
                    "Baseload (ct/kWh)": (
                        szenario.baseload_ct_kwh_je_kalenderjahr.get(jahr)
                    ),
                }
            )
    kurven_df = pd.DataFrame(
        kurven_zeilen,
        columns=[
            "Kalenderjahr", "Szenario", "Marktwert Solar (ct/kWh)",
            "Erzeugungsmenge neg. Stunden 6h (%)",
            "Erzeugungsmenge neg. Stunden 1h (%)",
            "Baseload (ct/kWh)",
        ],
    )

    # Monatsreihen im Langformat: eine Zeile je Szenario, Jahr und Monat.
    # Breitformat (zwoelf Spalten) waere kompakter, liesse sich aber nicht
    # um weitere Groessen erweitern, ohne die Blattstruktur zu aendern.
    monats_zeilen = []
    for szenario in ga.marktpreisszenarien:
        jahre = sorted(
            set(szenario.marktwert_solar_ct_kwh_je_monat)
            | set(szenario.erzeugungsmenge_negativ_6h_pct_je_monat)
            | set(szenario.erzeugungsmenge_negativ_1h_pct_je_monat)
            | set(szenario.baseload_ct_kwh_je_monat)
        )
        for jahr in jahre:
            marktwerte = szenario.marktwert_solar_ct_kwh_je_monat.get(jahr)
            baseload = szenario.baseload_ct_kwh_je_monat.get(jahr)
            neg6 = szenario.erzeugungsmenge_negativ_6h_pct_je_monat.get(jahr)
            neg1 = szenario.erzeugungsmenge_negativ_1h_pct_je_monat.get(jahr)
            for monat in range(1, 13):
                monats_zeilen.append(
                    {
                        "Kalenderjahr": jahr,
                        "Szenario": szenario.name,
                        "Monat": monat,
                        "Marktwert Solar (ct/kWh)": (
                            marktwerte[monat - 1] if marktwerte else None
                        ),
                        "Erzeugungsmenge neg. Stunden 6h (%)": (
                            neg6[monat - 1] * 100 if neg6 else None
                        ),
                        "Erzeugungsmenge neg. Stunden 1h (%)": (
                            neg1[monat - 1] * 100 if neg1 else None
                        ),
                        "Baseload (ct/kWh)": (
                            baseload[monat - 1] if baseload else None
                        ),
                    }
                )
    monats_df = pd.DataFrame(
        monats_zeilen,
        columns=[
            "Kalenderjahr", "Szenario", "Monat", "Marktwert Solar (ct/kWh)",
            "Erzeugungsmenge neg. Stunden 6h (%)",
            "Erzeugungsmenge neg. Stunden 1h (%)",
            "Baseload (ct/kWh)",
        ],
    )

    einspeisekurve_df = pd.DataFrame(
        {
            "Monat": list(range(1, 13)),
            "Anteil Jahreserzeugung (%)": [
                wert * 100 for wert in ga.einspeisekurve_pct_je_monat
            ],
        }
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
            (
                "pacht_umsatzbeteiligung_pct_vorschlag",
                ga.pacht_umsatzbeteiligung_pct_vorschlag * 100,
            ),
            (
                "direktvermarktungskosten_eur_mwh_vorschlag",
                ga.direktvermarktungskosten_eur_kwh * 1000,
            ),
            ("direktvermarktung_modus", ga.direktvermarktung_modus.value),
            ("negative_stunden_regel", ga.negative_stunden_regel.value),
            (
                "direktvermarktung_pct_marktwert",
                ga.direktvermarktung_pct_marktwert * 100,
            ),
            (
                "negative_stunden_gewichtung_pct",
                ga.negative_stunden_gewichtung_pct * 100,
            ),
            ("degradation_pct_pa", ga.degradation_pct_pa * 100),
            ("sicherheitsabschlag_pct", ga.sicherheitsabschlag_pct * 100),
            ("eag_foerderdauer_jahre", ga.eag_foerderdauer_jahre),
            ("betriebsdauer_jahre", ga.betriebsdauer_jahre),
            ("kreditlaufzeit_jahre", ga.kreditlaufzeit_jahre),
            ("tilgungsart", ga.tilgungsart.value),
            ("tilgungsfreies_anlaufjahr", "JA" if ga.tilgungsfreies_anlaufjahr else "NEIN"),
            ("zinsmethode", ga.zinsmethode.value),
            ("dscr_cash_trap", ga.dscr_cash_trap),
            ("dscr_event_of_default", ga.dscr_event_of_default),
            ("negative_stunden_modus", ga.negative_stunden_modus.value),
            ("tax_modus", ga.tax_modus.value),
            ("steuersatz_pct", ga.steuersatz_pct * 100),
            ("afa_nutzungsdauer_jahre", ga.afa_nutzungsdauer_jahre),
            ("freibetrag_eur", ga.freibetrag_eur),
            ("gewerbesteuer_hebesatz_pct", ga.gewerbesteuer_hebesatz_pct),
            ("gewerbesteuer_freibetrag_eur", ga.gewerbesteuer_freibetrag_eur),
            (
                "verlustvortrag_verrechnungsgrenze_pct",
                ga.verlustvortrag_verrechnungsgrenze_pct * 100,
            ),
            ("marktpreis_inflation_pct_pa", ga.marktpreis_inflation_pct_pa * 100),
            ("marktpreis_inflation_basisjahr", ga.marktpreis_inflation_basisjahr),
            ("kosten_inflation_pct_pa", ga.kosten_inflation_pct_pa),
            ("zeitaufloesung", ga.zeitaufloesung.value),
            ("praemien_modell", ga.praemien_modell.value),
            ("eag_rueckzahlung_ab_mw", ga.eag_rueckzahlung_ab_mw),
            (
                "eag_rueckzahlung_toleranzband_pct",
                ga.eag_rueckzahlung_toleranzband_pct * 100,
            ),
            ("eag_rueckzahlung_anteil_pct", ga.eag_rueckzahlung_anteil_pct * 100),
            ("ppa_anteil_pct_vorschlag", ga.ppa_anteil_pct_vorschlag * 100),
            ("ppa_preis_eur_mwh_vorschlag", ga.ppa_preis_eur_mwh_vorschlag),
            ("ppa_laufzeit_jahre_vorschlag", ga.ppa_laufzeit_jahre_vorschlag),
            (
                "ppa_indexierung_pct_pa_vorschlag",
                ga.ppa_indexierung_pct_pa_vorschlag * 100,
            ),
        ],
        columns=["Parameter", "Wert"],
    )

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        kurven_df.to_excel(writer, sheet_name="Preiskurven", index=False)
        monats_df.to_excel(writer, sheet_name="Preiskurven Monate", index=False)
        einspeisekurve_df.to_excel(writer, sheet_name="Einspeisekurve", index=False)
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
        # Aktuelles Format: je Regel eine eigene Spalte. Aeltere Exporte
        # kennen nur "Anteil neg. Stunden (%)" - der Wert gilt dann fuer
        # beide Regeln.
        spalte_6h = "Erzeugungsmenge neg. Stunden 6h (%)"
        spalte_1h = "Erzeugungsmenge neg. Stunden 1h (%)"
        legacy_spalte = "Anteil neg. Stunden (%)"
        if spalte_6h in kurven_df.columns and pd.notna(r.get(spalte_6h)):
            szenarien[name].erzeugungsmenge_negativ_6h_pct_je_kalenderjahr[jahr] = (
                float(r[spalte_6h]) / 100
            )
        if spalte_1h in kurven_df.columns and pd.notna(r.get(spalte_1h)):
            szenarien[name].erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[jahr] = (
                float(r[spalte_1h]) / 100
            )
        if "Baseload (ct/kWh)" in kurven_df.columns and pd.notna(
            r.get("Baseload (ct/kWh)")
        ):
            szenarien[name].baseload_ct_kwh_je_kalenderjahr[jahr] = float(
                r["Baseload (ct/kWh)"]
            )
        if legacy_spalte in kurven_df.columns and pd.notna(r.get(legacy_spalte)):
            wert = float(r[legacy_spalte]) / 100
            szenarien[name].erzeugungsmenge_negativ_6h_pct_je_kalenderjahr[jahr] = wert
            szenarien[name].erzeugungsmenge_negativ_1h_pct_je_kalenderjahr[jahr] = wert

    # Monatsreihen (optional): Sie ergaenzen die Jahreskurven, ersetzen
    # sie aber nicht - fehlt das Blatt, bleibt alles beim Jahreswert.
    monats_df = sheets.get("Preiskurven Monate")
    if monats_df is not None:
        for _, r in monats_df.iterrows():
            if pd.isna(r.get("Kalenderjahr")) or pd.isna(r.get("Szenario")):
                continue
            name = str(r["Szenario"])
            if name not in szenarien:
                szenarien[name] = MarktpreisSzenario(name=name)
            jahr, monat = int(r["Kalenderjahr"]), int(r["Monat"])
            if not 1 <= monat <= 12:
                continue
            for spalte, ziel, teiler in (
                ("Marktwert Solar (ct/kWh)",
                 szenarien[name].marktwert_solar_ct_kwh_je_monat, 1.0),
                ("Erzeugungsmenge neg. Stunden 6h (%)",
                 szenarien[name].erzeugungsmenge_negativ_6h_pct_je_monat, 100.0),
                ("Erzeugungsmenge neg. Stunden 1h (%)",
                 szenarien[name].erzeugungsmenge_negativ_1h_pct_je_monat, 100.0),
                ("Baseload (ct/kWh)",
                 szenarien[name].baseload_ct_kwh_je_monat, 1.0),
            ):
                if spalte not in monats_df.columns or pd.isna(r.get(spalte)):
                    continue
                # Eine angefangene Reihe wird mit Nullen aufgefuellt und
                # dann an der richtigen Stelle beschrieben - so bleibt sie
                # auch dann zwoelfstellig, wenn in der Tabelle einzelne
                # Monate fehlen.
                ziel.setdefault(jahr, [0.0] * 12)[monat - 1] = (
                    float(r[spalte]) / teiler
                )

    einspeisekurve_df = sheets.get("Einspeisekurve")
    einspeisekurve = None
    if einspeisekurve_df is not None and "Monat" in einspeisekurve_df.columns:
        spalte = "Anteil Jahreserzeugung (%)"
        werte = [0.0] * 12
        for _, r in einspeisekurve_df.iterrows():
            if pd.isna(r.get("Monat")) or pd.isna(r.get(spalte)):
                continue
            monat = int(r["Monat"])
            if 1 <= monat <= 12:
                werte[monat - 1] = float(r[spalte]) / 100
        if sum(werte) > 0:
            einspeisekurve = werte

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

    einstellungen = dict(zip(einstellungen_df["Parameter"], einstellungen_df["Wert"], strict=True))

    def get(key: str):
        wert = einstellungen.get(key, EINSTELLUNGEN_DEFAULTS[key])
        return EINSTELLUNGEN_DEFAULTS[key] if pd.isna(wert) else wert

    afa_wert = get("afa_nutzungsdauer_jahre")

    return GlobalAssumptions(
        gueltig_ab=str(get("gueltig_ab")),
        marktpreisszenarien=list(szenarien.values()),
        opex_standard=opex_items,
        gemeindeabgabe_eur_kwh=float(get("gemeindeabgabe_eur_mwh_vorschlag")) / 1000,
        pacht_umsatzbeteiligung_pct_vorschlag=(
            float(get("pacht_umsatzbeteiligung_pct_vorschlag")) / 100
        ),
        direktvermarktungskosten_eur_kwh=float(
            get("direktvermarktungskosten_eur_mwh_vorschlag")
        )
        / 1000,
        direktvermarktung_modus=DirektvermarktungsModus(
            str(get("direktvermarktung_modus")).strip().lower()
        ),
        negative_stunden_regel=NegativeStundenRegel(
            str(get("negative_stunden_regel")).strip().lower()
        ),
        direktvermarktung_pct_marktwert=float(
            get("direktvermarktung_pct_marktwert")
        )
        / 100,
        negative_stunden_gewichtung_pct=float(get("negative_stunden_gewichtung_pct"))
        / 100,
        degradation_pct_pa=float(get("degradation_pct_pa")) / 100,
        sicherheitsabschlag_pct=float(get("sicherheitsabschlag_pct")) / 100,
        eag_foerderdauer_jahre=int(get("eag_foerderdauer_jahre")),
        betriebsdauer_jahre=int(get("betriebsdauer_jahre")),
        kreditlaufzeit_jahre=int(get("kreditlaufzeit_jahre")),
        tilgungsart=TilgungsArt(get("tilgungsart")),
        tilgungsfreies_anlaufjahr=str(get("tilgungsfreies_anlaufjahr")).strip().upper()
        in ("JA", "TRUE", "1", "WAHR"),
        zinsmethode=ZinsMethode(get("zinsmethode")),
        dscr_cash_trap=float(get("dscr_cash_trap")),
        dscr_event_of_default=float(get("dscr_event_of_default")),
        negative_stunden_modus=NegativeStundenModus(
            str(get("negative_stunden_modus")).strip().lower()
        ),
        tax_modus=TaxModus(get("tax_modus")),
        steuersatz_pct=float(get("steuersatz_pct")) / 100,
        afa_nutzungsdauer_jahre=int(afa_wert) if afa_wert not in (None, "") else None,
        freibetrag_eur=float(get("freibetrag_eur")),
        gewerbesteuer_hebesatz_pct=float(get("gewerbesteuer_hebesatz_pct")),
        gewerbesteuer_freibetrag_eur=float(get("gewerbesteuer_freibetrag_eur")),
        verlustvortrag_verrechnungsgrenze_pct=float(
            get("verlustvortrag_verrechnungsgrenze_pct")
        )
        / 100,
        marktpreis_inflation_pct_pa=float(get("marktpreis_inflation_pct_pa")) / 100,
        marktpreis_inflation_basisjahr=int(get("marktpreis_inflation_basisjahr")),
        kosten_inflation_pct_pa=float(get("kosten_inflation_pct_pa")),
        zeitaufloesung=Zeitaufloesung(str(get("zeitaufloesung")).strip().lower()),
        einspeisekurve_pct_je_monat=(
            einspeisekurve if einspeisekurve is not None else EINSPEISEKURVE_STANDARD_PCT
        ),
        praemien_modell=PraemienModell(str(get("praemien_modell")).strip().lower()),
        eag_rueckzahlung_ab_mw=float(get("eag_rueckzahlung_ab_mw")),
        eag_rueckzahlung_toleranzband_pct=(
            float(get("eag_rueckzahlung_toleranzband_pct")) / 100
        ),
        eag_rueckzahlung_anteil_pct=float(get("eag_rueckzahlung_anteil_pct")) / 100,
        ppa_anteil_pct_vorschlag=float(get("ppa_anteil_pct_vorschlag")) / 100,
        ppa_preis_eur_mwh_vorschlag=float(get("ppa_preis_eur_mwh_vorschlag")),
        ppa_laufzeit_jahre_vorschlag=int(get("ppa_laufzeit_jahre_vorschlag")),
        ppa_indexierung_pct_pa_vorschlag=(
            float(get("ppa_indexierung_pct_pa_vorschlag")) / 100
        ),
    )


# ---------------------------------------------------------------------------
# Projekte: eine Zeile pro Projekt in einer gemeinsamen Excel-Datei
# ---------------------------------------------------------------------------

PROJEKT_SPALTEN = [
    # "name" ist der Standort, "variante" die Sensitivitaet an diesem
    # Standort (leer = Grundfall). Zwei Zeilen mit gleichem Namen und
    # verschiedener Variante sind zwei Rechnungen desselben Projekts.
    "id", "name", "standort", "variante", "leitvariante",
    "aktiv", "inbetriebnahme_jahr", "inbetriebnahme_monat",
    "anlagentyp",
    "nennleistung_kwp", "vollbenutzungsstunden_kwh_kwp", "bauform",
    "pacht_eur_kwp_jahr",
    "pacht_modus", "pacht_umsatzbeteiligung_pct", "pacht_mindestpacht_eur_ha_jahr",
    "fremdkapitalzins_pct", "eigenkapitalquote_pct", "eag_zuschlagswert_ct_kwh",
    "gemeindeabgabe_eur_mwh", "direktvermarktungskosten_eur_mwh",
    "marktpreisszenario", "projektflaeche_ha",
    "ppa_anteil_pct", "ppa_preis_eur_mwh", "ppa_start_jahr",
    "ppa_laufzeit_jahre", "ppa_indexierung_pct_pa",
    "capex_epc_eur", "capex_netzanschluss_eur", "capex_trasse_eur",
    "capex_widmung_eur", "capex_genehmigung_eur",
    "capex_sonstige_extern_eur", "capex_agm_eur", "capex_m_and_a_eur",
    "capex_poenale_puffer_eur",
    # Frei benannte Zusatzpositionen als JSON-Text in EINER Spalte: Ihre
    # Anzahl ist projektabhaengig, feste Spalten scheiden damit aus. Der
    # Import kommt ohne diese Spalten aus (aeltere Exporte).
    "capex_zusatzpositionen_json", "zusatz_opex_json",
]

#: Spalten, die erst nachtraeglich hinzugekommen sind und in einer aelteren
#: Exportdatei deshalb fehlen duerfen. Fuer jede von ihnen haelt
#: excel_to_projects() eine Vorbelegung bereit.
#:
#: WICHTIG beim Ergaenzen einer neuen Spalte: Sie gehoert in DIESE Menge,
#: sonst scheitert der Import jeder frueher gespeicherten Datei mit
#: "Spalten fehlen" - und zwar bevor die .get()-Vorbelegung ueberhaupt
#: erreicht wird.
OPTIONALE_PROJEKT_SPALTEN = frozenset(
    {
        # seit v4.5
        "aktiv",
        # seit v4.19 (Pacht als Umsatzbeteiligung)
        "pacht_modus", "pacht_umsatzbeteiligung_pct",
        "pacht_mindestpacht_eur_ha_jahr",
        # seit v4.22 (Widmung/Genehmigung als eigene CAPEX-Kategorien)
        "capex_widmung_eur", "capex_genehmigung_eur",
        # seit v4.28 (frei benannte Zusatzpositionen)
        "capex_zusatzpositionen_json", "zusatz_opex_json",
        # seit v5.1 (Standort + Variante); fehlt sie, ist jede Zeile der
        # Grundfall ihres Standorts
        "variante",
        # seit v5.2 (Leitvariante je Standort); fehlt sie, gilt je
        # Standort die erste Variante als Leitfall
        "leitvariante",
        # seit v5.3 (Kurzbezeichnung des Ortes); fehlt sie, wird die
        # Projektkennung auch als Beschriftung verwendet
        "standort",
        # seit v5.4 (hybride Vermarktung); fehlen sie, rechnet das
        # Projekt wie bisher rein merchant
        "ppa_anteil_pct", "ppa_preis_eur_mwh", "ppa_start_jahr",
        "ppa_laufzeit_jahre", "ppa_indexierung_pct_pa",
    }
)


def _zahl(reihe, spalte: str, standard: float = 0.0) -> float:
    """Zahlenwert einer Zelle, tolerant gegen fehlende Spalte und Leerzelle.

    Eine leere Zelle liest pandas als NaN. NaN ist in Python wahrheitswertig
    wahr, ein ``wert or standard`` wuerde den Fehlwert also durchreichen und
    die Investitionssumme unbrauchbar machen.
    """
    if spalte not in reihe:
        return standard
    wert = reihe[spalte]
    if wert is None or pd.isna(wert):
        return standard
    return float(wert)


def _text(reihe, spalte: str, standard: str = "") -> str:
    """Textwert einer Zelle, tolerant gegen fehlende Spalte und Leerzelle.

    ``str(reihe[spalte])`` allein taugt nicht: Eine leere Zelle liest
    pandas als NaN, und str(NaN) ergibt die Zeichenkette "nan" - die
    stuende dann als Variantenname in der Oberflaeche.
    """
    if spalte not in reihe:
        return standard
    wert = reihe[spalte]
    if wert is None or pd.isna(wert):
        return standard
    return str(wert).strip()


def _wahrheitswert(reihe, spalte: str, standard: bool = False) -> bool:
    """Ja/Nein-Zelle, tolerant gegen fehlende Spalte und Leerzelle.

    Excel liefert je nach Herkunft True/False, 1/0 oder Text ("WAHR",
    "ja", "x"). bool("FALSCH") waere wahr - deshalb die Textliste.
    """
    if spalte not in reihe:
        return standard
    wert = reihe[spalte]
    if wert is None or pd.isna(wert):
        return standard
    if isinstance(wert, str):
        return wert.strip().lower() in {"wahr", "true", "ja", "yes", "x", "1"}
    return bool(wert)


def _json_liste(wert) -> list[dict]:
    """Liest eine als JSON-Text gespeicherte Positionsliste.

    Fehlt die Spalte (aeltere Exportdatei) oder ist sie leer, ergibt sich
    eine leere Liste - der Import bleibt damit abwaertskompatibel.
    """
    if wert is None or (isinstance(wert, float) and pd.isna(wert)):
        return []
    text = str(wert).strip()
    if not text or text.lower() == "nan":
        return []
    try:
        eintraege = json.loads(text)
    except json.JSONDecodeError as fehler:
        raise ValueError(
            f"Zusatzpositionen sind kein gueltiges JSON: {text[:60]}"
        ) from fehler
    return list(eintraege)


def projects_to_excel(projects: list[PVProject]) -> bytes:
    rows = [
        {
            "id": p.id,
            "name": p.name,
            "standort": p.standort,
            "variante": p.variante,
            "leitvariante": p.leitvariante,
            "aktiv": p.aktiv,
            "inbetriebnahme_jahr": p.inbetriebnahme_jahr,
            "inbetriebnahme_monat": p.inbetriebnahme_monat,
            "anlagentyp": p.anlagentyp.value,
            "nennleistung_kwp": p.nennleistung_kwp,
            "vollbenutzungsstunden_kwh_kwp": p.vollbenutzungsstunden_kwh_kwp,
            "bauform": p.bauform,
            "pacht_eur_kwp_jahr": p.pacht_eur_kwp_jahr,
            "pacht_modus": p.pacht_modus.value,
            "pacht_umsatzbeteiligung_pct": p.pacht_umsatzbeteiligung_pct * 100,
            "pacht_mindestpacht_eur_ha_jahr": p.pacht_mindestpacht_eur_ha_jahr,
            "fremdkapitalzins_pct": p.fremdkapitalzins_pct * 100,
            "eigenkapitalquote_pct": p.eigenkapitalquote_pct * 100,
            "eag_zuschlagswert_ct_kwh": p.eag_zuschlagswert_ct_kwh,
            "gemeindeabgabe_eur_mwh": p.gemeindeabgabe_eur_mwh,
            "direktvermarktungskosten_eur_mwh": p.direktvermarktungskosten_eur_mwh,
            "marktpreisszenario": p.marktpreisszenario,
            "projektflaeche_ha": p.projektflaeche_ha,
            "ppa_anteil_pct": p.ppa_anteil_pct * 100,
            "ppa_preis_eur_mwh": p.ppa_preis_eur_mwh,
            "ppa_start_jahr": p.ppa_start_jahr,
            "ppa_laufzeit_jahre": p.ppa_laufzeit_jahre,
            "ppa_indexierung_pct_pa": p.ppa_indexierung_pct_pa * 100,
            "capex_epc_eur": p.capex.epc_eur,
            "capex_netzanschluss_eur": p.capex.netzanschluss_eur,
            "capex_trasse_eur": p.capex.trasse_eur,
            "capex_widmung_eur": p.capex.widmung_eur,
            "capex_genehmigung_eur": p.capex.genehmigung_eur,
            "capex_sonstige_extern_eur": p.capex.sonstige_extern_eur,
            "capex_agm_eur": p.capex.agm_eur,
            "capex_m_and_a_eur": p.capex.m_and_a_eur,
            "capex_poenale_puffer_eur": p.capex.poenale_puffer_eur,
            "capex_zusatzpositionen_json": json.dumps(
                [pos.model_dump() for pos in p.capex.zusatzpositionen],
                ensure_ascii=False,
            ),
            "zusatz_opex_json": json.dumps(
                [pos.model_dump() for pos in p.zusatz_opex], ensure_ascii=False
            ),
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

    # Nachtraeglich hinzugekommene Spalten duerfen fehlen, damit aeltere
    # Exportdateien importierbar bleiben - fuer sie greifen weiter unten
    # die Vorbelegungen. Diese Pruefung darf sie deshalb nicht als
    # "fehlend" blockieren, sonst wird die Vorbelegung nie erreicht.
    fehlende_spalten = (
        set(PROJEKT_SPALTEN) - OPTIONALE_PROJEKT_SPALTEN - set(df.columns)
    )
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
                standort=_text(r, "standort"),
                variante=_text(r, "variante"),
                leitvariante=_wahrheitswert(r, "leitvariante"),
                aktiv=bool(r.get("aktiv", True))
                if not pd.isna(r.get("aktiv", True)) else True,
                inbetriebnahme_jahr=int(r["inbetriebnahme_jahr"]),
                inbetriebnahme_monat=int(r["inbetriebnahme_monat"]),
                anlagentyp=AnlagenTyp(r["anlagentyp"]),
                nennleistung_kwp=float(r["nennleistung_kwp"]),
                vollbenutzungsstunden_kwh_kwp=float(r["vollbenutzungsstunden_kwh_kwp"]),
                pacht_eur_kwp_jahr=float(r["pacht_eur_kwp_jahr"]),
                pacht_modus=PachtModus(r["pacht_modus"])
                if "pacht_modus" in r and pd.notna(r["pacht_modus"])
                else PachtModus.FIX,
                pacht_umsatzbeteiligung_pct=(
                    float(r["pacht_umsatzbeteiligung_pct"]) / 100
                    if "pacht_umsatzbeteiligung_pct" in r
                    and pd.notna(r["pacht_umsatzbeteiligung_pct"])
                    else 0.055
                ),
                pacht_mindestpacht_eur_ha_jahr=(
                    float(r["pacht_mindestpacht_eur_ha_jahr"])
                    if "pacht_mindestpacht_eur_ha_jahr" in r
                    and pd.notna(r["pacht_mindestpacht_eur_ha_jahr"])
                    else 0.0
                ),
                fremdkapitalzins_pct=float(r["fremdkapitalzins_pct"]) / 100,
                eigenkapitalquote_pct=float(r["eigenkapitalquote_pct"]) / 100,
                eag_zuschlagswert_ct_kwh=float(r["eag_zuschlagswert_ct_kwh"]),
                gemeindeabgabe_eur_mwh=float(r["gemeindeabgabe_eur_mwh"]),
                direktvermarktungskosten_eur_mwh=float(
                    r["direktvermarktungskosten_eur_mwh"]
                ),
                marktpreisszenario=(
                    str(r["marktpreisszenario"])
                    if pd.notna(r["marktpreisszenario"])
                    else "Aurora Q3/26 · Central"
                ),
                # Fehlt die Spalte (Export vor v5.15), holt der
                # Migrationsschritt in PVProject die Bauform aus dem
                # Szenarionamen - deshalb hier nur setzen, wenn sie
                # tatsaechlich dasteht.
                **(
                    {"bauform": str(r["bauform"])}
                    if "bauform" in r and pd.notna(r["bauform"])
                    else {}
                ),
                projektflaeche_ha=(
                    float(r["projektflaeche_ha"])
                    if pd.notna(r["projektflaeche_ha"])
                    else None
                ),
                # Hybride Vermarktung - fehlen die Spalten (aeltere
                # Exportdatei), rechnet das Projekt rein merchant.
                ppa_anteil_pct=_zahl(r, "ppa_anteil_pct") / 100,
                ppa_preis_eur_mwh=_zahl(r, "ppa_preis_eur_mwh", 65.0),
                ppa_start_jahr=int(_zahl(r, "ppa_start_jahr", 1)) or 1,
                ppa_laufzeit_jahre=int(_zahl(r, "ppa_laufzeit_jahre", 10)),
                ppa_indexierung_pct_pa=_zahl(r, "ppa_indexierung_pct_pa") / 100,
                capex=CapexBreakdown(
                    epc_eur=float(r["capex_epc_eur"]),
                    netzanschluss_eur=float(r["capex_netzanschluss_eur"]),
                    trasse_eur=float(r["capex_trasse_eur"]),
                    # Aeltere Exporte kennen die Spalten noch nicht -> 0.
                    widmung_eur=_zahl(r, "capex_widmung_eur"),
                    genehmigung_eur=_zahl(r, "capex_genehmigung_eur"),
                    sonstige_extern_eur=float(r["capex_sonstige_extern_eur"]),
                    agm_eur=float(r["capex_agm_eur"]),
                    m_and_a_eur=float(r["capex_m_and_a_eur"]),
                    poenale_puffer_eur=float(r["capex_poenale_puffer_eur"]),
                    zusatzpositionen=[
                        CapexPosition(**eintrag)
                        for eintrag in _json_liste(r.get("capex_zusatzpositionen_json"))
                    ],
                ),
                zusatz_opex=[
                    OpexItem(**eintrag)
                    for eintrag in _json_liste(r.get("zusatz_opex_json"))
                ],
            )
        )
    return projects
