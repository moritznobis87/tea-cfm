# Architektur

Dieses Dokument beschreibt den **Aufbau** der Software (Schichten,
Datenmodell, bewusste Designentscheidungen). Die **Rechenvorschrift**
selbst – jede Formel der Bewertungskette, das Auktionsmodell und ein
durchgerechnetes Beispiel – steht in
[rechenmodell/rechenmodell.md](rechenmodell/rechenmodell.md) bzw. als
gesetztes PDF in [rechenmodell/Rechenmodell.pdf](rechenmodell/Rechenmodell.pdf).

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
- **Zeitauflösung:** Der Cashflow ist immer jährlich. Die Monatsebene
  (`GlobalAssumptions.zeitaufloesung = MONAT`) ist ausschließlich eine
  Unterebene der Erlösrechnung: `energy.calculate_energy_production_monatlich()`
  verteilt die Jahresmenge über die Einspeisekurve, `revenue.py` rechnet
  je Monatsscheibe und verdichtet danach auf Jahre – Beträge summiert,
  Preise **mengengewichtet** gemittelt. Voreingestellt bleibt die
  Jahresauflösung; fehlen einem Kalenderjahr Monatswerte, gilt sein
  Jahreswert für alle zwölf Monate. Beides zusammen heißt: Die
  Umschaltung verändert kein Projekt, für das keine Monatsdaten
  vorliegen.
- **Prämienmodell:** `PraemienModell` trennt die Vertragsform von der
  Rechnung – einseitiger CfD (Voreinstellung, bisheriges Verhalten),
  zweiseitiger CfD und das österreichische Toleranzband nach § 10 EAG
  (Rückzahlung von 66 % oberhalb von 140 % des anzulegenden Werts, ab
  5 MW; alle drei Größen einstellbar). Prämie und Rückzahlung stehen in
  getrennten Spalten: zwei Zahlungsrichtungen, und nur getrennt ist
  sichtbar, welcher Teil des Ergebnisses aus einer Abschöpfung stammt.
- **Hybride Vermarktung:** Der PPA-Anteil teilt die vermarktete *Menge*
  auf (`erloes_ppa_eur` / `erloes_merchant_eur`); die Förderung bemisst
  sich unverändert am Referenzmarktwert und nicht am erzielten Preis.
  Ein PPA verschiebt deshalb die Erlösverteilung, nicht den
  Förderanspruch – das ist die Konstruktion der gleitenden Marktprämie,
  keine Vereinfachung.

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

**Aurora-Import** (`engine/io_aurora.py`): baut aus den Aurora-Daten
`MarktpreisSzenario`-Objekte – auf zwei Wegen. Die **Arbeitsmappe**
(„Market Forecast Data", `lies_arbeitsmappe` / `importiere_arbeitsmappe`)
liefert in einer Datei alle Preisszenarien (Central/Low/High/Net Zero)
und beide Bauformen (Aurora „Fixed"/„Tracking solar PV", im Tool „Pult"
und „Tracker"); je gewähltem Preisszenario entsteht ein eigenes Szenario
`Stamm · Bauform · Preisszenario`. Nichts wird über feste Zeilen- oder
Spaltennummern gefunden: Kopfzeile ist die Zeile mit „Calendar year"/
„Month", Datenspalten sind die mit Zahlen darunter, die Szenariospalte
wird an ihren Werten erkannt, und gesucht wird im zusammengesetzten Text
aller Beschriftungsspalten (das erfasst auch die deutschen
Zweitspalten). Die monatliche Abregelungsquote bezieht sich je nach
Jahrgang auf eine andere Regel; welche es ist, verrät die Beschriftung
oder die Fußnote des Abschnitts – sonst wird sie durch Vergleich mit den
Jahresreihen bestimmt. Die Monatsreihe trägt dann das Profil, die
Jahresreihe der Zielregel das Niveau. Der zweite Weg sind die vier
**CSV-Exporte** aus EOS; sie tragen zusätzlich die monatliche Erzeugung
und damit die Einspeisekurve. Quelle der Kurven ist die **Technologiedatei
in Monatsauflösung** – Capture Price (EUR/MWh → ct/kWh), die beiden
Abregelungsquoten (1h/6h) und die monatliche Erzeugung, aus der die
Einspeisekurve abgeleitet wird; die Jahreswerte entstehen als
erzeugungsgewichtetes Mittel der Monatswerte, also mit derselben
Vorschrift, die auch die Engine beim Verdichten anwendet. Die
Systemdatei liefert nur Basisjahr und Rate der Inflation, die
Technologie-Jahresdatei nur eine Gegenprobe. **Monatsdaten sind
Pflicht**: Zweiseitiger CfD und Abschöpfung sind abgeschnittene
Funktionen des Marktwerts, aus einem Jahresmittel nicht rekonstruierbar
– fehlen sie, bricht der Import mit `AuroraImportFehler` ab, statt
stillschweigend eine entwertete Rechnung zu liefern. Die
Spaltenerkennung arbeitet über Teilbegriffe statt exakter Namen, weil
sich Aurora-Exporte zwischen Marktgebieten in Kleinigkeiten
unterscheiden.

**Einspeisekurven je Bauform**: Die zwölf Monatsanteile stammen aus
PVGIS-Monatserträgen einer 1-kWp-Anlage – je eine Reihe für Pult und
Tracker. Die Rohwerte stehen als `PVGIS_MONATSERTRAG_KWH_KWP` in
`engine/models.py` und werden dort beim Laden auf 1 normiert
(`EINSPEISEKURVEN_JE_BAUFORM`); sie bleiben in ihrer Rohform stehen,
damit eine wiederholte PVGIS-Abfrage Zahl für Zahl vergleichbar ist.
`tests/test_einspeisekurve.py` prüft Rohwerte, Normierung und den
Umschalter. In den globalen Annahmen wird nur zwischen den Bauformen
umgeschaltet oder von Hand nachgebessert.

**Szenarionamen** folgen dem Schema `Stamm · Bauform ·
Preisszenario` (`Aurora Q3/26 · Pult · Central`).
`io_aurora.zerlege_szenarioname()` zerlegt sie wieder – erkannt wird an
den Werten, nicht an der Position. Darauf bauen drei Dinge auf: die
Reiter der globalen Annahmen (einer je Stamm, Bauform und
Preisszenario werden darin gewählt), die Legende der
Szenariendiagramme (nennt nur, was sich unterscheidet) und die
Übersichtsauswahl. Ausgabestände werden beim Import auf Quartale
normiert (`Oct25` → `Q4/25`), damit derselbe Jahrgang nicht in zwei
Schreibweisen nebeneinandersteht.

**Übersicht und Auswahl:** Aus einer Arbeitsmappe entstehen bis zu sechs
Szenarien je Jahrgang. Die Szenariendiagramme der globalen Annahmen
zeigen deshalb je Familie eine Kurve – `io_aurora.ist_leitszenario()`
erkennt an den Namensteilen die Bauform und das Preisszenario und lässt
nur `Pult · Central` durch; Namen ohne diese Teile (von Hand gepflegte
Bestände) bleiben immer sichtbar. Ein Schalter holt die übrigen zurück.
Gerechnet wird davon nichts: Reiter, Zahlentabellen und Projektauswahl
führen unverändert alle Szenarien.

**Standort und Variante:** Ein `PVProject` trägt zwei Namen – `name`
(Standort) und `variante` (Sensitivität, leer = Grundfall). Mehrere
Varianten desselben Standorts sind weiterhin eigenständige Projekte mit
eigener Datei und eigener Adresse; gruppiert werden sie ausschließlich
über den gleichen `name` (`services.gruppiere_nach_standort()`). Die
Zuordnung wird **nicht** aus Namensmustern abgeleitet – „Lödersdorf
Agri" und „Lödersdorf konventionell" sind zwei Anlagentypen, keine
Sensitivitäten; das kann nur die eingebende Person entscheiden. Die
Seitenleiste führt Standorte, die Variantenreihe im Projektfenster
wechselt zwischen ihnen. In der Excel-Sicherung ist `variante` eine
optionale Spalte, ältere Dateien bleiben lesbar.

**Projektkennung und Standort:** `name` ist die Kennung
(„OÖ_St.Georgen_Spitzwieser") – sie identifiziert das Projekt, gruppiert
seine Varianten und steht in der Seitenleiste. `standort` ist die
Kurzbezeichnung („St. Georgen") und beschriftet Diagramme; teilen sich
mehrere Projekte einen Ort, nummeriert `services.standort_labels()`
durch (I, II, III …). Varianten desselben Projekts lösen keine
Nummerierung aus. Ohne `standort` wird die Kennung auch als
Beschriftung verwendet.

**Leitvariante:** Je Standort trägt genau eine Variante das Flag
`leitvariante`. Nur sie geht in die Portfolio-Kennzahlen und die
Pipeline ein (`services.leitvarianten()`) – ohne diese Auswahl zählte
ein Standort mit drei Sensitivitäten dreifach. Ist keine gesetzt, gilt
die erste Variante (`services.leitvariante_von`); ein nie angefasster
Bestand ist damit ohne Migration korrekt. `services.setze_leitvariante`
schreibt die übrigen Varianten des Standorts mit – zwei Leitfälle
ergäben zwei mögliche Portfoliozahlen. Gesetzt wird sie in der
Variantenreihe des Projektfensters (Stern am Reiter, Knopf „Als
Leitfall"); die Vergleichssicht bietet dieselbe Wahl zusätzlich an.

**Rendite-Risiko-Landkarte:** Die y-Achse ist immer die EK-Rendite, die
x-Achse ist umschaltbar (`charts.LANDKARTE_ACHSEN`): spezifisches Invest
(€/kWp) misst die Effizienz unabhängig von der Projektgröße, der
Deckungsbeitrag (NPV) den absoluten Wertbeitrag – dort liegt ein großes
mittelmäßiges Projekt vor einem kleinen exzellenten. Voreingestellt ist
der Deckungsbeitrag (`charts.LANDKARTE_X_STANDARD`). Die Beschriftungen
platziert `charts.beschriftungsplaetze()`: Plotly kennt nur neun starre
Textpositionen je Punkt und kein Ausweichen, deshalb wird für jeden
Namen der erste kollisionsfreie Platz gesucht (Blasengrößen gehen dabei
ein, weil Plotly den Text an den Markerrand setzt) und der Name notfalls
weggelassen – er steht im Tooltip.

**Variantenvergleich:** `app/components/varianten.py` leitet die
Unterschiede zwischen Varianten aus den Projektmodellen ab (kein
gepflegter Änderungsverlauf). `geprueft_alle_felder()` ist der
Regressionsschutz dafür: Ein neu hinzugekommenes Projektfeld fällt im
Test auf, statt still aus der Unterschiedstabelle zu verschwinden.

## Teststrategie

| Ebene | Dateien | Ansatz |
| --- | --- | --- |
| Einheit | `test_timeline_energy_opex.py`, `test_revenue.py`, `test_financing_tax.py` | Handgerechnete Erwartungswerte auf einem deterministischen Fixture-Projekt (flache 4-ct-Kurve, Inflation aus) |
| End-to-End | `test_pipeline_kpis_io.py` | Konsistenz der Cashflow-Kategorien, KPI-Plausibilität, Monotonie der NPV-Kurve und der Sensitivität, YAML-/Excel-Roundtrips |
| UI | `test_ui_smoke.py` | Streamlit `AppTest`: jede Seite rendert ohne Exception, Projekt-Dashboard öffnet |

Die Fixtures hängen **nicht** an den änderbaren Beispieldaten unter
`data/` – Nutzer können dort frei editieren, ohne Tests zu brechen.
