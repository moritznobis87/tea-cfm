# Nobis Analytics – PV-Projektbewertung

Wirtschaftlichkeitsrechnung für PV-Projekte nach dem **österreichischen
EAG-Marktprämienmodell** (gleitende Marktprämie) – ausgerichtet am
Arbeitsablauf eines Projektentwicklers: Ein neues Projekt ist in unter
zwei Minuten angelegt, alles selten Geänderte (Preiskurven,
Standardbetriebskosten, Finanzierungs- und Steuerlogik) wird zentral in
den Globalen Annahmen gepflegt und automatisch angewendet.

## Schnellstart

```bash
# Nutzung
pip install -r requirements.txt
streamlit run streamlit_app.py

# Entwicklung
pip install -e ".[dev]"
make test      # Test-Suite (Engine + UI-Smoke-Tests)
make lint      # Statische Analyse (ruff)
make run       # App starten
```

## Funktionsumfang

- **Portfolio**: aggregierte Kennzahlen, Rendite-Risiko-Landkarte
  (Bubble-Chart: spezifisches Invest × IRR × Leistung), Projekt-Ranking,
  sortierbare Vergleichstabelle und Projektkarten mit
  Cashflow-Sparkline und Typ-Badge.
- **Projekt-Dashboard** (7 Analyse-Tabs): EK-Rendite (XIRR), NPV,
  min. DSCR, Payback, **LCOE**, spezifisches Invest; Wertbrücke
  (Waterfall) über die Gesamtlaufzeit, Cashflow-Diagramme, DSCR-Verlauf,
  Schuldenprofil mit Restschuld, Kapital- und Investitionsstruktur
  (Donuts), NPV-Kurve mit IRR-Nullstelle und ein Transparenz-Tab mit dem
  vollständig aufgelösten Parametersatz.
- **Erlösanalyse**: Vergütungssatz vs. Marktwert im Zeitverlauf (die
  Fläche dazwischen ist die Marktprämie), Aufteilung der Erlöse in
  Markterlös und Marktprämie (Förderabhängigkeit auf einen Blick).
- **Sensitivitäts-Studio**: Tornado-Diagramm über sieben Werttreiber
  (±10 %), IRR-Heatmap über zwei frei wählbare Treiber mit
  Break-even-Farbumschlag, EAG-Zuschlag-Varianten (±5 %/±10 %) und ein
  **Gebotsassistent** (minimaler anzulegender Wert für eine
  Ziel-EK-Rendite - Untergrenze für das EAG-Auktionsgebot).
- **Monte-Carlo-Simulation**: gleichzeitige Variation von Ertrag,
  Marktwert-Niveau, CAPEX und OPEX (einstellbare Sigmas, fester Seed,
  200-1000 Läufe); IRR-Verteilung mit P10/P50/P90,
  Erfolgswahrscheinlichkeit gegen eine Ziel-Rendite und Fächerdiagramm
  des kumulierten Equity-Cashflows.
- **Szenarienvergleich**: identisches Projekt über alle hinterlegten
  Marktpreisszenarien (IRR/NPV je Szenario, kumulierte Cashflows).
- **Projektverwaltung**: Anlegen, Bearbeiten, Duplizieren, Löschen (mit
  Bestätigung), Cashflow-Export als Excel, Sichern/Wiederherstellen von
  Projekten und Globalen Annahmen über Excel-Dateien.
- **Fachlogik**: EAG-Marktprämie `MAX(Marktwert Solar, Zuschlagswert)`
  während der Förderdauer, danach reiner Marktverkauf; Ausfall der
  Förderung in Stunden negativer Preise; Inflationierung realer
  Marktwert-Kurven (der EAG-Zuschlag bleibt gesetzlich nominal fix);
  Annuitäten-/lineare Tilgung; KöSt mit AfA, Freibetrag und
  Verlustvortrag inkl. 75-%-Verrechnungsgrenze (§8 Abs. 4 Z 2 KStG).
- **Modelloptionen**: Verhalten in Stunden negativer Preise umschaltbar
  (Abregelung vs. Rückfall auf Jahresmarktwert), tilgungsfreies
  Anlaufjahr (On/Off), NPV-Diskontsatz der KPI-Kachel frei wählbar
  (0–10 %, exakte XNPV-Berechnung).
- **Geschäftsregel**: Konventionelle Anlagen erhalten automatisch einen
  Abschlag von 25 % auf den EAG-Zuschlagswert gegenüber Agri-PV
  (`KONVENTIONELL_ZUSCHLAG_ABSCHLAG_PCT` in `engine/models.py`).

## Architektur

```
streamlit_app.py        Entry-Point: Seitenkonfiguration, Theme, Navigation
app/                    UI-Schicht (kennt die Engine, aber keine Dateiformate)
  config.py             Pfade, Konstanten, Session-State-Schlüssel
  theme.py              Design-Tokens, CSS, zentrales Plotly-Template
  formatting.py         Deutsche Zahlenformatierung (einzige Stelle dafür)
  services.py           Gecachter Datenzugriff, Bewertungs-Cache,
                        Projekt-Lebenszyklus (anlegen/duplizieren/löschen)
  components/           Wiederverwendbare Bausteine
    charts.py           Alle Plotly-Diagramme (DataFrame rein, Figure raus)
    project_form.py     Projektmaske (Neuanlage + Bearbeiten)
    sidebar.py          Excel-Import/-Export
  views/                Die Seiten der App
    overview.py         Portfolio + ausgewähltes Projekt-Dashboard
    project_detail.py   Dashboard mit Tabs und Aktionen
    new_project.py      Neuanlage
    assumptions.py      Globale Annahmen
engine/                 Reine Fachlogik – kein Streamlit-Import
  analytics.py          Tornado, IRR-Heatmap, Monte Carlo, Gebotsassistent,
                        LCOE, Szenarienvergleich
  models.py             PVProject, GlobalAssumptions, EffectiveAssumptions
  pipeline.py           resolve_assumptions() (Merge), run_valuation()
  timeline / energy / revenue / opex / financing / tax / cashflow / kpis
  sensitivity.py        EAG-Zuschlag ±5/±10 %
  io_yaml.py, io_excel.py   Persistenz und Austauschformate
data/                   global_assumptions.yaml + ein YAML pro Projekt
tests/                  46 Tests: Engine-Einheiten, Pipeline-E2E,
                        IO-Roundtrips, Formatierung, UI-Smoke (AppTest)
```

Details und Begründungen der Designentscheidungen: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Datenhaltung

Projekte und Globale Annahmen liegen als YAML unter `data/` – bewusst
keine Datenbank (siehe ARCHITECTURE.md). **Streamlit Cloud hat kein
dauerhaftes Dateisystem**: Neu angelegte Projekte gehen bei einem
Reboot/Redeploy verloren, wenn sie nicht im Repo liegen. Der
Excel-Download in der Sidebar ist der vorgesehene Sicherungsweg.

## Qualitätssicherung

| Werkzeug | Zweck |
| --- | --- |
| `pytest` (78 Tests) | Fachlogik (handgerechnete Erwartungswerte), E2E-Pipeline, IO-Roundtrips, UI-Smoke-Tests |
| `ruff` | Lint + Import-Sortierung (Konfiguration in `pyproject.toml`) |
| GitHub Actions | CI auf Python 3.11/3.12: Lint + Tests bei jedem Push/PR |

## Bekannte Einschränkungen

- Die Beispiel-Preiskurven in `data/global_assumptions.yaml` sind
  plausible Platzhalter, keine validierten Marktprognosen – vor echtem
  Einsatz durch aktuelle Marktwert-Solar-/Preisszenario-Daten ersetzen.
- Betriebsperioden werden als volle Kalenderjahre modelliert (das erste
  Jahr anteilig); der Excel-Sonderfall „Vertragsende am Jahrestag" ist
  bewusst nicht abgebildet.
- Kein Nutzer-/Rechtemodell, kein Mehrbenutzerbetrieb.
- `pyarrow` ist auf `<25` gepinnt: Version 25.0.0 hat einen
  reproduzierbaren Segmentation Fault beim Rendern von `st.dataframe()`.

## Roadmap

1. Reale Marktpreiskurven statt Platzhalter
2. Korrelierte Zufallsvariablen in der Monte-Carlo-Simulation
   (z.B. Marktwert-Niveau × Anteil negativer Stunden)
3. Mehrjahres-Portfolioplanung (IBN-Staffelung, Kapitalbindung)
