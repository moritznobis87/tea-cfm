# Architektur

## Leitidee: drei Schichten, eine Richtung

```
┌─────────────────────────────────────────────────────┐
│ streamlit_app.py   (Entry: Konfiguration, Navigation)│
├─────────────────────────────────────────────────────┤
│ app/               UI-Schicht                        │
│   views/  ── nutzt ──▶ components/ + services.py     │
│   services.py  ── nutzt ──▶ engine (+ Caching)       │
├─────────────────────────────────────────────────────┤
│ engine/            Fachlogik (kein Streamlit-Import) │
│   pipeline ─▶ timeline ─▶ energy ─▶ revenue ─▶ opex  │
│            ─▶ financing ─▶ tax ─▶ cashflow ─▶ kpis   │
└─────────────────────────────────────────────────────┘
```

Abhängigkeiten zeigen ausschließlich nach unten. Die Engine ist ein
reines Python-Paket und ohne UI testbar; die 40 Engine-Tests laufen in
unter zwei Sekunden.

## Datenmodell: zwei Ebenen + Merge

- **`PVProject` (Projektmaske)** enthält nur, was sich von Projekt zu
  Projekt tatsächlich unterscheidet – Ziel: Anlage in unter zwei Minuten.
- **`GlobalAssumptions`** bündelt alles selten Geänderte (Preiskurven,
  Standard-OPEX, Kreditlaufzeit, Steuerlogik, Degradation …).
- **`resolve_assumptions()`** führt beide zu **`EffectiveAssumptions`**
  zusammen – dem vollständig aufgelösten Parametersatz, mit dem alle
  Rechenmodule arbeiten. Die UI zeigt genau dieses Objekt im
  „Annahmen"-Tab des Dashboards (Nachvollziehbarkeit jeder Berechnung).

**Pydantic für Annahmen-Objekte, pandas-DataFrames für Zeitreihen**:
Validierung und Serialisierung dort, wo Nutzereingaben ankommen;
vektorisierte Berechnung dort, wo über 25–30 Jahre gerechnet wird.
`CashflowTimeseries` ist ein dünner dataclass-Wrapper, der das
Spaltenschema erzwingt und Metadaten (project_id, OPEX-Einzelposten)
trägt.

## Fachliche Kernentscheidungen (bewusst so, bitte nicht „aufräumen")

- **EAG-Marktprämie:** Vergütung = `MAX(Marktwert Solar, Zuschlagswert)`
  während der Förderdauer; in Stunden negativer Preise entfällt die
  Förderung vollständig (gesetzliche Regelung, keine Vereinfachung).
- **Kalenderjahr-Indizierung der Preiskurven:** Kurven sind nach echtem
  Kalenderjahr indiziert, nicht nach Betriebsjahr. Außerhalb des
  Kurvenbereichs wird auf den Randwert geklemmt (kein Extrapolieren).
- **Inflationierung:** Marktpreisstudien liefern reale Werte auf
  Preisbasis des Erscheinungsjahres; für die nominale Cashflow-Rechnung
  wird ab dem Basisjahr inflationiert. Der Inflationsfaktor basiert auf
  dem **tatsächlichen** Kalenderjahr, auch wenn der Realpreis am
  Kurvenrand geklemmt wurde – die Geldentwertung läuft unabhängig davon
  weiter. Der EAG-Zuschlag bleibt nominal fix (gesetzlich).
- **Verlustvortrag (§8 Abs. 4 Z 2 KStG):** zeitlich unbegrenzt, aber pro
  Gewinnjahr nur bis zur Verrechnungsgrenze (75 %) nutzbar. Deshalb ist
  `tax.py` bewusst **sequenziell** (der Vortragsbestand hängt vom
  Vorjahr ab), während alle anderen Module vektorisiert sind.
- **DSCR:** CFADS (Cashflow **vor** Zinsen) / Schuldendienst – Zinsen
  stehen im Nenner und dürfen nicht doppelt abgezogen werden.
- **XIRR statt IRR:** Diskontierung auf Tagesbasis (Act/365), wie Excels
  `=XIRR(...)` – relevant, sobald Projekte unterjährig in Betrieb gehen.
  Die Nullstellensuche erweitert ihr Intervall schrittweise
  (10 → 100 → 1000), statt bei exotischen Cashflows `None` zu liefern.
- **Konventionell-Abschlag** (−25 % auf den EAG-Zuschlag) ist eine
  benannte Konstante, kein Nutzerparameter – Geschäftsregel.

## UI-Schicht

- **`services.py` ist die einzige Brücke** zwischen UI und Engine. Sie
  cached Bewertungen auf Basis der Datei-mtimes (Projekt-YAML +
  Globale Annahmen): Die Portfolioseite rechnet ein Projekt nur dann
  neu, wenn sich tatsächlich etwas geändert hat – nicht bei jedem
  Streamlit-Rerun. Jede schreibende Operation invalidiert die Caches.
- **`components/charts.py`**: Alle Diagramme sind reine Funktionen
  (DataFrame → Figure) ohne Streamlit-Import – isoliert testbar, und
  die Views bleiben lesbar.
- **`theme.py`**: Design-Tokens (Farben), CSS und ein registriertes
  Plotly-Template. Das Template setzt u.a. `separators=",."` – dadurch
  sind auch Achsen und Hover deutsch formatiert. Kein anderes Modul
  enthält Hex-Codes.
- **`formatting.py`**: die einzige Stelle, die Zahlen in Strings
  verwandelt (Dezimalkomma, Tausenderpunkt). Bewusst ohne
  `locale.setlocale` (prozessglobal, auf Streamlit Cloud unzuverlässig).
- **Einheiten-Umschalter im Projektformular** (€/kWp ↔ €,
  €/kWp/Jahr ↔ €/ha/Jahr) liegen außerhalb von `st.form` und schreiben
  beim Umschalten den umgerechneten Wert in den Session-State, **bevor**
  das Widget instanziiert wird. Es gibt je Feld genau ein Widget mit
  stabilem Key – Widgets, die zwischen Runs erscheinen/verschwinden,
  sind ein bekanntes Streamlit-Risikomuster.

## Persistenz

YAML-Dateien unter `data/`, **bewusst kein Repository-Pattern und keine
Datenbank** – das kommt, wenn ein Wechsel tatsächlich ansteht.
`engine/io_yaml.py` ist der einzige Ort mit Datei-IO;
`engine/io_excel.py` liefert Excel nur als Austauschformat für
Down-/Upload (tabellarische Preiskurven sind in Excel bequemer zu
pflegen als in YAML).

Projekt-IDs entstehen per Slugify aus dem Namen (Umlaute
transliteriert, Kollisionen erhalten eine Laufnummer) – siehe
`services.make_project_id()`.

## Teststrategie

| Ebene | Dateien | Ansatz |
| --- | --- | --- |
| Einheit | `test_timeline_energy_opex.py`, `test_revenue.py`, `test_financing_tax.py` | Handgerechnete Erwartungswerte auf einem deterministischen Fixture-Projekt (flache 4-ct-Kurve, Inflation aus) |
| End-to-End | `test_pipeline_kpis_io.py` | Konsistenz der Cashflow-Kategorien, KPI-Plausibilität, Monotonie der NPV-Kurve und der Sensitivität, YAML-/Excel-Roundtrips |
| UI | `test_ui_smoke.py` | Streamlit `AppTest`: jede Seite rendert ohne Exception, Projekt-Dashboard öffnet |

Die Fixtures hängen **nicht** an den änderbaren Beispieldaten unter
`data/` – Nutzer können dort frei editieren, ohne Tests zu brechen.
