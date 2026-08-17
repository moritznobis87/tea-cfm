# Changelog

## v5.9 – Szenarien aufgeräumt: Jahrgänge statt Kurzszenarien (2026-08)

- **Drei Kurzszenarien entfallen** („Aurora 6/26", „Aurora 04/26",
  „Aurora 10/25"). Sie trugen weder Großhandelspreis noch Bauform; die
  Jahrgangsszenarien aus der Arbeitsmappe ersetzen sie vollständig.
  **Alle Projekte rechnen jetzt mit „Aurora Q3/26 · Pult · Central"** –
  dem aktuellen Jahrgang.
- **Einheitliche Schreibweise der Jahrgänge**: Aurora benannte seine
  Ausgaben früher nach Monat, heute nach Quartal. Im Tool zählt eine
  Schreibweise, sonst stünden „Oct 25" und „Q4/25" als zwei Jahrgänge
  nebeneinander. Aus Jan 25 wird **Q1/25**, aus Apr 25 **Q2/25**, aus
  Oct 25 **Q4/25** – auch für künftige Importe alter Mappen.
- **Kein Marktgebiet mehr im Namen**: „GER" trug nichts bei, solange
  alle Mappen dasselbe Gebiet betreffen, und ließ die Legende
  überlaufen.
- **Legende nennt nur den Unterschied**: Bauform und Preisszenario
  stehen dort nur noch, wenn sie sich zwischen den gezeigten Kurven
  unterscheiden. In der Übersicht bleibt damit „Q3/26", „Q2/26" …
  stehen statt dreimal derselbe Zusatz.
- **Ein Reiter je Jahrgang** statt je Kurve: Bauform und Preisszenario
  werden im Reiter gewählt, wo sie hingehören. Aus siebzehn Reitern
  werden sieben, und der Vergleich Pult/Tracker ist ein Klick statt
  eines Reiterwechsels.

## v5.8 – Übersicht auf die Leitszenarien beschränkt (2026-08)

- Aus jeder Aurora-Arbeitsmappe entstehen bis zu sechs Szenarien je
  Jahrgang; nebeneinander gezeichnet waren das zwanzig Linien. Die
  **Übersichtsdiagramme zeigen jetzt je Familie eine Kurve** – Pult und
  Central. Low und High sind ohnehin die Spanne um Central, und die
  Tracker-Kurve läuft dicht neben der Pult-Kurve.
- Ein Schalter **„Alle Szenarien zeigen"** holt die übrigen zurück – für
  die Preisspanne eines einzelnen Jahrgangs ist die volle Ansicht genau
  richtig.
- Szenarien ohne Bauform oder Preisszenario im Namen (von Hand
  gepflegte Bestände) bleiben immer sichtbar; in den Reitern darunter
  und in der Projektauswahl ändert sich nichts.

## v5.7 – Einspeisekurven je Bauform, Prämienmodell je Markt (2026-08)

- **Zwei hinterlegte Einspeisekurven**: „Pult" und „Tracker", abgeleitet
  aus PVGIS-Monatserträgen einer 1-kWp-Anlage (1.148 bzw.
  1.429 kWh/kWp, also 24,5 % Nachführgewinn) und auf 100 % normiert. Sie
  ersetzen die bisherige geschätzte Standardkurve. In den globalen
  Annahmen wird zwischen beiden umgeschaltet; wer die Werte von Hand
  ändert, landet bei „Eigene Kurve".
  Der Nachführgewinn ist im Juli größer als im Dezember (28,6 % gegen
  22,0 %), die Tracker-Kurve deshalb sommerlastiger – für die
  Monatsrechnung wesentlich, weil die Sommermonate die niedrigeren
  Marktwerte tragen.
  Die Rohwerte stehen als `PVGIS_MONATSERTRAG_KWH_KWP` im Modell und
  bleiben damit gegen eine wiederholte PVGIS-Abfrage prüfbar.
- **Großhandelspreis sichtbar**: Er wurde seit v5.6 aus der
  Aurora-Arbeitsmappe importiert und trägt die Direktvermarktungskosten
  im Modus „Anteil am Großhandelspreis" – in den globalen Annahmen war er
  aber nirgends zu sehen. Jetzt steht er als eigenes Szenariendiagramm
  neben dem Marktwert Solar (der Abstand der beiden Kurven ist die
  Kannibalisierung) und als Spalte in der Zahlentabelle, dort auch
  editierbar. Fehlt er einem Szenario, sagt das ein Hinweis statt eines
  leeren Diagramms.
- **Fehler behoben**: Beim Speichern der globalen Annahmen gingen die
  Großhandelspreis-Kurven eines Szenarios verloren, sobald dessen Zahlen
  aufgeklappt waren – das Szenario wurde aus der Tabelle neu gebaut, die
  Baseload-Reihen kannte die Tabelle aber nicht.
- **Sechs Aurora-Q3/26-Szenarien ausgeliefert**: Central, Low und High,
  je einmal für Pult und Tracker, mit Marktwerten, Abregelungsquoten und
  Großhandelspreisen – jährlich und monatlich, 2027 bis 2060. Damit steht
  die Preisspanne als Sensitivität bereit, ohne dass jeder Anwender die
  Arbeitsmappe selbst importieren muss. Die bisherigen Szenarien bleiben
  unverändert bestehen, damit vorhandene Projekte weiter rechnen.
- **Fünf ältere Aurora-Jahrgänge** (Jan 25, Apr 25, Oct 25, Q1/26,
  Q2/26) stehen als Central-Szenario je Bauform bereit – für die Frage,
  wie sich die Prognose über die Ausgaben verschoben hat. Ihre realen
  Preise sind dabei auf die globale Preisbasis 2025 umgerechnet (die
  Mappen rechnen in Preisen von 2023 bzw. 2024); ohne diese Umrechnung
  zeigte der Vergleich Inflation statt Prognoseänderung. Der Marktwert
  Solar 2035 fällt über die Jahrgänge von 6,03 auf 4,31 ct/kWh.
- **Legende der Szenariendiagramme** kürzt die gemeinsame Herkunft weg:
  Aus „Aurora Q3/26 GER · Pult · Central" wird „Pult · Central", wenn
  alle gezeigten Kurven denselben Stamm tragen. Der Tooltip nennt
  weiterhin den vollen Namen, und die Bildhöhe wächst mit der Zahl der
  Legendenzeilen.
- **Projektdaten aktualisiert**: Die ausgelieferte Projektsammlung
  entspricht jetzt dem Stand der Arbeitsmappe `projekte_24.xlsx` –
  vierzehn Projekte an neun Standorten (85,7 MWp Leitvarianten) plus die
  beiden Vorlagen.
- **Fehler behoben**: Das Projektformular reichte die Leitfall-Markierung
  nicht durch. Ein frisch geöffneter Leitfall meldete deshalb „1
  ungespeicherte Änderung", und ein Speichern aus der Parameterspalte
  hätte die Markierung stillschweigend gelöscht – der Standort wäre
  danach mit seiner ersten Variante statt der gewählten ins Portfolio
  eingegangen.
- **Prämienmodell folgt dem Länderschalter**: Österreich rechnet mit dem
  zweiseitigen CfD mit Toleranzband (§ 10 EAG), Deutschland mit dem
  einseitigen CfD des EEG. Beides bleibt danach frei wählbar. Die
  ausgelieferten globalen Annahmen (Marktsystem Österreich) stehen damit
  auf dem Toleranzband – **das ändert Ergebnisse bestehender Projekte**,
  sobald Marktwerte über dem anzulegenden Wert liegen und die Anlage die
  5-MW-Schwelle erreicht.

## v5.6 – Aurora-Arbeitsmappe, Großhandelspreis, Bauform (2026-08)

Der Aurora-Import liest jetzt die Arbeitsmappe, die Aurora ohnehin
ausliefert – statt vier CSV-Exporten eine Datei.

- **Import aus der Arbeitsmappe „Market Forecast Data"**: alle
  Preisszenarien (Central, Low, High, teils Net Zero) auf einmal. Je
  gewähltem Preisszenario entsteht ein Marktpreisszenario
  „Stamm · Bauform · Preisszenario", zum Beispiel „Aurora Q3/26 GER ·
  Pult · Central". Damit sind sie im Projekt einzeln wählbar **und**
  stehen gemeinsam im Szenarienvergleich der Risikosicht – die
  Preisspanne ist dort ein Bild statt einer Reihe von Handrechnungen.
- **Bauform wählbar**: Aurora unterscheidet „Fixed solar PV" und
  „Tracking solar PV"; im Tool heißen sie **Pult** (Voreinstellung) und
  **Tracker**. Ihre Marktwerte unterscheiden sich deutlich – der Tracker
  trifft die preisschwachen Mittagsstunden weniger stark.
- **Großhandelspreis (Baseload)** wird mitimportiert und je Szenario
  gespeichert – jährlich und monatlich.
- **Direktvermarktungskosten in drei Modi**: fester Betrag je MWh,
  **Anteil am Großhandelspreis** (marktüblich rund 10 % – so rechnen
  Direktvermarkter ab) oder Anteil am Marktwert Solar. Da der Marktwert
  einer PV-Anlage unter dem Baseload liegt, sind die beiden relativen
  Modi bei gleichem Prozentsatz spürbar verschieden.
- **Alles dynamisch gesucht**: Aurora verschiebt zwischen den Ausgaben
  Kopfzeilen, benennt Blätter um, fügt deutsche Zweitspalten hinzu und
  nennt die monatliche Abregelungsquote mal „below zero", mal „1 hour
  rule". Der Import findet Kopfzeile, Datenspalten, Szenariospalte und
  Beschriftungen an ihrem Inhalt. Geprüft an sechs Ausgaben von Jan 25
  bis Q3 26.
- **Abregelung**: Das Monatsblatt führt nur eine Quote, das Jahresblatt
  mehrere Regeln. Welche Regel die Monatsreihe meint, verrät ihre
  Beschriftung oder die Fußnote; sonst wird sie durch Vergleich mit den
  Jahresreihen bestimmt. Die Monatsreihe trägt dann das Profil, die
  Jahresreihe der Zielregel (1h/6h) das Niveau.
- **Szenarienvergleich korrigiert**: Er tauschte bisher nur die
  Jahreskurven – in der Monatsauflösung zeigte er deshalb für alle
  Szenarien dasselbe Ergebnis.
- **Vergütungsdiagramm** zeigt den Großhandelspreis als gepunktete
  Linie: Der Abstand zum Marktwert Solar ist die Kannibalisierung.
- Excel-Rundlauf um die Baseload-Spalten erweitert (Jahres- und
  Monatsblatt); ältere Dateien bleiben lesbar.
- 15 neue Tests; Suite: 425.

## v5.5 – Aurora-Import (2026-08)

Marktpreisszenarien entstehen nicht mehr per Hand, sondern aus den
Aurora-Exporten. Vier Dateien liefert Aurora je Szenario (System- und
Technologiedaten, jeweils jährlich und monatlich); der Import liest sie
und baut daraus ein vollständiges Szenario.

- **Marktwert Solar** aus dem **Capture Price** der gewählten
  Technologie (EUR/MWh → ct/kWh) – der Preis, den genau diese
  Technologie erlöst, nicht der Baseload-Preis. Voreingestellt ist der
  *ungekürzte* Capture Price: Die Wirkung negativer Preise bringt das
  Modell selbst über die Abregelungsquote ein, mit dem bereits
  gekürzten Preis zählte sie doppelt.
- **Beide Negativstunden-Zeitreihen** aus den Abregelungsquoten der
  1h- und der 6h-Regel – genau die zwei Kurven, zwischen denen die
  Globalen Annahmen umschalten.
- **Einspeisekurve** aus der monatlichen Erzeugung derselben
  Technologie: Der Ertragsverlauf steckt in den Daten und muss nicht
  mehr geschätzt werden.
- **Jahreswerte als erzeugungsgewichtetes Mittel** der Monatswerte –
  dieselbe Vorschrift, mit der die Engine verdichtet. Ein einfacher
  Mittelwert wäre für PV systematisch zu hoch.
- **Inflation** (Basisjahr und mittlere Rate) aus dem Index der
  Systemdatei.
- **Monatsdaten sind Pflicht.** Zweiseitiger CfD und Abschöpfung
  entscheiden sich in einzelnen Monaten und sind aus einem Jahresmittel
  nicht rekonstruierbar. Wer die Jahresdatei lädt, bekommt deshalb keine
  halbe Rechnung, sondern eine Fehlermeldung; unvollständige Monatsreihen
  werden übergangen und benannt.
- **Gegenprobe** gegen die Technologie-Jahresdatei: Weicht das
  gewichtete Monatsmittel um mehr als 2 % vom ausgewiesenen Jahreswert
  ab, erscheint eine Warnung – ein Zeichen für die falsche Technologie
  oder den falschen Capture Price.
- Robust gegen die Unterschiede echter Exporte: Spaltenerkennung über
  Teilbegriffe, Monat als Zahl, Name oder Datum, Quoten als Anteil oder
  Prozent, CSV mit Komma oder Semikolon, Excel ebenso.
- 26 neue Tests; Suite: 410.

## v5.4.1 – Szenarien als Bild (2026-08)

- **Die Globalen Annahmen zeigen die Marktpreisszenarien als Diagramm**:
  je eine Linie für den Marktwert Solar und für die Erzeugungsmenge in
  Stunden negativer Preise (nach der oben gewählten 6h/1h-Regel). Der
  Vergleich ist die Frage, die man an eine Szenariosammlung hat – vier
  Tabellen mit je 36 Zeilen beantworten sie nicht.
- **Die Zahlen stehen dahinter**: Je Szenario blendet der Schalter
  „Zahlen bearbeiten" die Jahreswerte als Tabelle ein; darüber steht,
  wie viele Kalenderjahre hinterlegt sind und wie viele davon
  Monatswerte tragen.
- 4 neue Tests; Suite: 384.

## v5.4 – Monatsauflösung, Prämienmodelle, hybride PPA (2026-08)

Die Erlösrechnung ist methodisch geöffnet: Sie kann jetzt in Monaten
rechnen, kennt drei Vertragsformen der Förderung und teilt die Menge
zwischen PPA und Spotmarkt auf. **Alle drei Erweiterungen sind
voreingestellt aus** – ein bestehendes Projekt rechnet unverändert.

- **Monatliche Marktwerte und Negativstunden-Quoten.** Ein
  Marktpreisszenario trägt neben den Jahreskurven optionale Monatsreihen
  (zwölf Werte je Kalenderjahr). Fehlt für ein Jahr die Monatsreihe,
  gilt sein Jahreswert für alle zwölf Monate; die Umschaltung bleibt
  damit auch mit unvollständigen Daten rechenbar.
- **Einspeisekurve** in den Globalen Annahmen: zwölf Prozentwerte, die
  festlegen, welcher Anteil der Jahreserzeugung in welchem Monat
  anfällt. Sie wird beim Rechnen auf 100 % normiert – gerundete Eingaben
  verändern die Jahresmenge nicht.
- **Zeitauflösung Jahr/Monat** als globaler Schalter. Im Monatsmodus
  trifft die Sommermenge auf den Sommerpreis, und das Anlaufjahr folgt
  der Erzeugung statt dem Kalender: Eine im Juli in Betrieb gehende
  Anlage liefert rund 60 % der Jahresmenge, nicht die Hälfte. Cashflow,
  Finanzierung, Steuer und DSCR bleiben jährlich.
- **Drei Marktprämienmodelle**: einseitiger CfD (bisheriges Verhalten),
  zweiseitiger CfD (Vergütung = anzulegender Wert) und der
  österreichische Weg mit **Toleranzband nach § 10 EAG** – 66 % des
  Betrags oberhalb von 140 % des anzulegenden Werts gehen zurück, für
  Photovoltaik ab 5 MW Engpassleistung. Schwelle, Band und Anteil sind
  einstellbar, weil sie Gegenstand laufender Novellen sind.
- **Hybride Vermarktung (PPA + Merchant)**: Anteil, Preis, Startjahr,
  Laufzeit und Indexierung je Projekt. Die Förderung bemisst sich
  weiterhin am Referenzmarktwert, nicht am erzielten Preis – ein PPA
  verschiebt die Erlösverteilung, nicht den Förderanspruch.
- **Erlösdiagramm** zeigt die Herkunft: Merchant, PPA, Marktprämie, und
  die Rückzahlung als Balken unter der Nulllinie. PPA und Rückzahlung
  erscheinen nur, wenn es sie gibt.
- **Excel-Rundlauf** um zwei Blätter erweitert („Preiskurven Monate",
  „Einspeisekurve") sowie um die PPA-Spalten der Projektliste. Ältere
  Dateien ohne diese Blätter/Spalten bleiben lesbar.
- **Rechenmodell-Dokumentation** um die Abschnitte 6.3 (Monatsaufteilung),
  7.7 (Prämienmodelle), 7.8 (hybride Vermarktung) und 7.9
  (Monatsauflösung samt Konvexitätseffekt) erweitert, PDF neu gebaut.
- Die mitgelieferten Monatsreihen und die Einspeisekurve sind
  **Platzhalter** mit plausibler Form (Winter teuer, Sommer billig;
  negative Stunden im Frühjahr) – sie werden durch echte Daten ersetzt.
- 21 neue Tests; Suite: 380.

## v5.3.1 – Zweite Achse für die Landkarte, Leitfall im Projekt (2026-08)

Nachträge aus der Benutzung; die Rechenregeln sind unverändert.

- **Die x-Achse der Rendite-Risiko-Landkarte ist umschaltbar**: neben dem
  spezifischen Invest (€/kWp) jetzt auch der **Deckungsbeitrag (NPV)**.
  Beide Sichten ordnen dieselbe Pipeline unterschiedlich – das
  spezifische Invest misst die Effizienz unabhängig von der Größe, der
  Deckungsbeitrag den absoluten Wertbeitrag, und dort liegt ein großes
  mittelmäßiges Projekt vor einem kleinen exzellenten. Eine gestrichelte
  Nulllinie markiert die Schwelle, ab der ein Projekt seine
  Kapitalkosten verdient. Voreingestellt ist der Deckungsbeitrag: Die
  erste Frage an eine Pipeline ist, welches Projekt wie viel Wert
  schafft.
- **Der Leitfall lässt sich im Projektfenster setzen.** Ein Stern
  markiert in der Variantenreihe die Rechnung, die in die
  Portfolio-Kennzahlen eingeht; der Knopf „★ Als Leitfall" macht die
  geöffnete Variante dazu. Bisher gab es die Wahl nur in der
  Vergleichssicht – dort sucht sie niemand.
- **Beschriftungen der Landkarte überlappen nicht mehr.** Die
  Platzsuche berücksichtigt jetzt die tatsächliche Blasengröße: Plotly
  setzt den Text an den Rand des Markers, mit einer Einheitsblase
  gerechnet landete das Label einer großen Blase genau dort, wo das der
  kleinen Nachbarin lag. Bleibt kein freier Platz, wird der am wenigsten
  verdeckte gewählt; findet sich gar keiner, entfällt der Name (er steht
  im Tooltip).
- **Sicht „Alle Varianten" aus der Portfolioübersicht entfernt**: Sie
  summierte über alle Rechnungen, ein Standort mit drei Sensitivitäten
  zählte dreifach. Die einzelnen Rechnungen stehen im Reiter
  „Varianten".
- **Reiter „Varianten" erklärt sich**: neuer Hilfetext mit den beiden
  Schwellen im Klartext, und die Spalte „Ziel" heißt jetzt „Ziel
  erfüllt" (angehakt, wenn Zielrendite *und* Cash-Trap-Schwelle
  eingehalten sind).
- 10 neue Tests (x-Achsenwahl samt Rückfall, Nulllinie, Platzsuche der
  Beschriftungen, Leitfall in der Variantenreihe); Suite: 359.

## v5.3 – Standort als Kurzbezeichnung, Landkarte entlastet (2026-08)

Mit zwölf Rechnungen war die Rendite-Risiko-Landkarte am Limit: sechs
Variantenpfade kreuzten einander, und die vollständigen Projektnamen
überlagerten sich. Beides wächst mit der Pipeline. Die Rechenregeln sind
unverändert.

- **Projektkennung und Standort sind jetzt zwei Felder.** Die Kennung
  („OÖ_St.Georgen_Spitzwieser") identifiziert und steht in der
  Seitenleiste; der **Standort** („St. Georgen") ist die
  Kurzbezeichnung und beschriftet die Diagramme. Er steht als zweites
  Feld in der Parameterspalte.
- **Mehrere Projekte an einem Ort werden durchnummeriert**
  („St. Georgen I", „St. Georgen II") – sonst trüge die Karte zwei
  gleich beschriftete Punkte. Sensitivitäten desselben Projekts zählen
  dabei nicht mit; sie sind ein Feld. Ohne Kurzbezeichnung bleibt die
  Kennung stehen, ein nie gepflegter Bestand verliert also nichts.
- **Excel-Sicherung**: neue optionale Spalte `standort` hinter `name`.
- **Die Landkarte zeigt je Projekt nur noch die Leitvariante.** Aus zwölf
  Blasen mit sechs Pfaden werden sechs Blasen ohne Pfad; die übrigen
  Rechnungen stehen mit ihrer Rendite im Tooltip.
- **Ein Klick auf eine Blase klappt ihr Projekt auf**: nur dieser eine
  Standort zeigt dann alle Rechnungen samt Pfad und Variantennamen, alle
  übrigen treten zurück. Das bleibt lesbar, ob sechs oder sechzig
  Projekte im Hintergrund liegen. Ein Knopf hebt den Fokus wieder auf.
- **Neuer Reiter „Rangliste"** ersetzt das bisherige Ranking: eine Zeile
  je Projekt, nach Rendite der Leitvariante sortiert, Varianten als
  offene Punkte auf derselben Zeile, Spanne als Balken, Zielmarke als
  senkrechte Linie. Die Namen stehen in der Achse und können sich
  strukturell nicht überlagern – die Ansicht, die auch bei vierzig
  Projekten trägt.
- 12 neue Tests (Nummerierung, Excel-Spalte samt Abwärtskompatibilität,
  Landkarte mit und ohne Fokus, Sortierung der Rangliste); Suite: 355.

## v5.2 – Blick über alle Varianten (2026-08)

### v5.2.2 – Pacht als Treiber der Tornado-Analyse

- **Achter Treiber „Pacht".** Sie wird in `engine/opex.py` getrennt von
  den Standardpositionen geführt (die Berechnung hängt vom Pachtmodus
  ab) und steckte deshalb in keinem der bisherigen Balken — der Treiber
  „Betriebskosten" enthält sie nicht, die beiden überschneiden sich
  nicht.
- Bei Umsatzbeteiligung werden Beteiligungssatz und Mindestpacht
  gemeinsam skaliert: Die Zahlung ist ihr Maximum, eine Variation nur
  eines Terms bliebe wirkungslos, sobald der andere führt.
- Die Höhe des Tornado-Bildes im PDF-Bericht wächst mit der Zahl der
  Treiber — bei fester Höhe rückten die Beschriftungen zusammen.
- Nachgezogen: Abschnitt 14.1 und 14.3 der Rechenmodell-Dokumentation
  samt neu gebautem PDF. 3 neue Tests; Suite: 343.

### v5.2.1 – Variantenpfade auch in der Sicht „Standorte"

- **Die Rendite-Risiko-Landkarte zeigt jetzt immer alle Rechnungen.**
  Bisher folgte sie der Sichtwahl und zeigte unter „Standorte" nur die
  Leitvarianten — damit fehlten genau die Variantenpfade, für die die
  Darstellung gedacht ist. Die Leitvarianten sind ausgeschrieben und
  voll deckend, die übrigen treten zurück und sind über die Linie mit
  ihrem Leitfall verbunden. Ranking und Vergleichstabelle bleiben bei
  der gewählten Sicht: Sie sind Listen und müssen zur
  Kennzahlenleiste passen.
- Beschriftet werden nur die hervorgehobenen Punkte — zwölf
  ausgeschriebene Namen überlagern einander; der Rest steht im Hover.
- 3 neue Tests (Pfade, Hervorhebung, Gleichrangigkeit ohne Auswahl);
  Suite: 340.



Sensitivitäten ließen sich anlegen und ansteuern, aber nicht vergleichen:
Wer wissen wollte, welche Rechnung gewinnt und woran das liegt, musste
zwischen den Reitern hin- und herspringen und sich die Zahlen merken. Die
Rechenregeln sind unverändert.

- **Leitvariante je Standort.** Eine Rechnung trägt die Entscheidung; nur
  sie geht in die Portfolio-Kennzahlen und die Pipeline ein. Damit ist
  eine falsche Zahl behoben: Bisher zählte jede Sensitivität mit, ein
  Standort mit drei Varianten also dreifach — Portfolio-Leistung,
  Investitionsvolumen und Eigenkapital waren entsprechend zu hoch (im
  Beispielbestand 30,3 MWp statt 15,3 MWp). Ist keine Variante markiert,
  gilt die erste; ein nie angefasster Bestand ist damit sofort richtig.
- **Neue Sicht „Vergleich"** als fünfter Reiter der Projektseite, dazu
  ein Chip am Ende der Variantenreihe. Vier Blöcke, von der Entscheidung
  zur Begründung:
  - **Entscheidungstabelle** — je Variante Equity IRR mit Zielbalken, Δ
    zur wählbaren Referenz, NPV, Equity Value, Min. DSCR mit
    Kovenantenmarkierung, CAPEX und Payback. Die beste Rendite ist
    hervorgehoben.
  - **„Was unterscheidet die Varianten"** — nur die Felder, die
    tatsächlich abweichen, aus den Projektdaten abgeleitet. Die Frage
    „was hatte ich hier eigentlich geändert?" beantwortet damit das
    Programm statt der Erinnerung.
  - **DSCR je Betriebsjahr** als Linienvergleich mit beiden
    Kovenantenschwellen — der Minimalwert allein verrät nicht, ob eine
    Unterdeckung Ausreißer oder Dauerzustand ist.
  - **Kumulierter Cashflow** je Variante; die Nulllinie ist der Payback.
  - Die Parameterspalte entfällt in dieser Sicht: Sie bearbeitet eine
    Variante, der Vergleich zeigt alle. Der Vergleich bekommt die volle
    Breite.
- **Portfolio mit Sichtwahl „Standorte | Alle Varianten".** Standorte
  zeigt je Feld eine Karte mit der Spanne der Varianten („3 Varianten ·
  6,46 % – 13,50 %") und dem Leitfall; alle Kennzahlen beziehen sich dann
  auf die Leitvarianten. Alle Varianten zeigt jede Rechnung einzeln, und
  in der Rendite-Risiko-Landkarte verbindet eine Linie die Rechnungen
  desselben Standorts.
- **Neuer Analytik-Reiter „Varianten"**: alle Rechnungen der Pipeline,
  nach Standort gruppiert, mit Leitfall-Marke und einer Ampel, die
  Zielrendite und Kovenanten gemeinsam prüft.
- **Excel-Sicherung**: neue optionale Spalte `leitvariante` hinter
  `variante`; ältere Dateien bleiben lesbar.
- 13 neue Tests (Leitvariante inkl. Exklusivität und Excel-Rundlauf,
  Unterschiedsableitung, Vergleichssicht); Suite: 337.

## v5.1 – Standort und Variante (2026-08)

### v5.1.2 – Engere Stufen der EAG-Zuschlag-Sensitivität

- **Die Zuschlagswert-Varianten liegen jetzt bei ±2,5 % und ±5 %** statt
  bei ±5 % und ±10 %. In einer Ausschreibungsrunde bewegt sich der
  Zuschlagswert um wenige Zehntel Cent je Kilowattstunde; eine Variation
  um 10 % beschrieb keine Entscheidung mehr, die tatsächlich zur Wahl
  stand. Die weiteren Spannen bleiben Tornado-Analyse und Heatmap
  vorbehalten, die davon unberührt sind.
- Die Beschriftung führt eine Nachkommastelle nur, wo sie etwas
  beiträgt: „+5 %" neben „+2,5 %".
- Nachgezogen: Diagrammtitel und Bildunterschrift in allen vier
  Sprachen, Abschnitt 14.2 der Rechenmodell-Dokumentation samt neu
  gebautem PDF.

### v5.1.1 – Löschabfrage sichtbar, Wertkacheln untereinander

- **Die Rückfrage vor dem Löschen stand am Seitenende.** Sie wurde erst
  nach dem Aufbau der Arbeitsfläche erzeugt und landete deshalb unter
  Kennzahlen, Diagrammen und Parameterspalte – wer im Überlaufmenü
  „Löschen" wählte, sah oben nichts geschehen und hielt das Löschen für
  kaputt. Sie steht jetzt direkt unter der Kopfzeile, dort, wo auch der
  auslösende Knopf sitzt.
- **Nach dem Löschen einer Variante bleibt man am Standort**, solange
  dort noch eine Rechnung steht; der Sprung ins Portfolio war ein
  Ortswechsel, den niemand verlangt hat.
- **CAPEX und Enterprise Value getauscht**: Die begleitenden Kacheln
  stehen zweispaltig und werden zeilenweise gefüllt – damit liegen
  Equity Value und Enterprise Value jetzt übereinander statt über Eck.
- 2 neue Tests (Rückfrage entsteht vor der Arbeitsfläche; Variante
  anlegen und wieder löschen); Suite: 323.


Sensitivitäten waren bisher Kopien mit eigenem Namen („… (Kopie)",
„… (Netz high)"). Technisch waren sie eigenständige Projekte, und die
Projektliste wuchs mit jeder Rechnung, ohne dass ihr anzusehen war,
welche Einträge denselben Standort meinen. Die Rechenregeln sind
unverändert – die Variante ist ein reines Ordnungsmerkmal.

- **Ein Projekt trägt zwei Namen**: `name` ist der Standort, `variante`
  die Sensitivität an diesem Standort. Die Variante darf leer bleiben;
  das ist der Grundfall, die Oberfläche nennt ihn „Basis". Beide Felder
  stehen oben in der Parameterspalte.
- **Keine Ableitung aus Namensmustern.** Ob „Lödersdorf Agri" und
  „Lödersdorf konventionell" zwei Sensitivitäten eines Standorts oder
  zwei Anlagen sind, kann kein Parser entscheiden – die Zuordnung wird
  eingegeben.
- **Die Seitenleiste führt Standorte**, nicht Varianten: Ein Eintrag je
  Standort, die Zahl der Varianten steht dahinter. Aus zwölf
  gleichrangigen Einträgen werden damit vier.
- **Variantenreihe im Projektfenster.** Direkt unter dem Titel stehen die
  Sensitivitäten des Standorts als flache Reiterreihe; ein Klick wechselt
  die Rechnung, während Standort, Sicht und Parameterspalte stehen
  bleiben. „+ Variante" legt eine weitere an.
- **Duplizieren erzeugt eine Variante**, keinen zweiten Standort mehr:
  Die Kopie behält den Standortnamen und bekommt einen freien
  Variantennamen („Variante", „Variante 2", …).
- **Excel-Sicherung**: neue Spalte `variante` direkt hinter `name`. Sie
  ist optional – jede früher gesicherte Datei bleibt lesbar, ihre Zeilen
  gelten als Grundfall ihres Standorts.
- Titel und Dateinamen von PDF-Bericht, Cashflow-Export,
  Pipeline-Ergebnisbericht, Portfoliotabelle und Auktionsmodul nennen den
  Anzeigenamen („Standort · Variante"), sonst wären zwei Sensitivitäten
  in der Ausgabe nicht auseinanderzuhalten.
- Nebenbei behoben: Speichern aus der Parameterspalte setzte ein
  stillgelegtes Projekt wieder auf „aktiv" – der Aktiv-Schalter liegt im
  Überlaufmenü und war im Formular nicht abgebildet.
- 19 neue Tests (Modell, Excel-Rundlauf und Abwärtskompatibilität,
  Gruppierung, Duplizieren, Seitenleiste und Variantenreihe); Suite: 321.

## v5.0 – Neue Seitenstruktur (2026-08)

Umbau der Oberfläche in fünf Schritten. Die Rechenregeln sind unverändert;
alle Änderungen betreffen Navigation, Anordnung und Darstellung.

- **Jede Seite hat eine eigene Adresse** (`?seite=projekt&id=…&tab=…`,
  neu: `app/router.py`). Neuladen, Lesezeichen, verschickte Links und der
  Zurück-Knopf des Browsers funktionieren dadurch. Bis hierher lag die
  geöffnete Ansicht allein im Session-State, und die Projektansicht hing
  unten an der Portfolioseite – erreichbar erst nach rund drei
  Bildschirmhöhen.
- **Navigation statt Formularauswahl.** Das Radio-Feld der Seitenleiste ist
  hervorgehobenen Einträgen gewichen; das geöffnete Projekt wird genauso
  markiert wie die aktive Seite. Neu sind eine Projektliste mit direktem
  Wechsel, ein „+ Neues Projekt"-Knopf und die Gruppe **Sichern** mit
  *Projekte sichern*, *Annahmen sichern* und *Wiederherstellen* als
  direkte Einträge.
- **Eingabe neben dem Ergebnis.** Die Projektmaske steht als Parameterspalte
  rechts neben den Auswertungen und arbeitet auf einem Entwurf: Jede
  Änderung rechnet sofort durch, gespeichert wird auf Knopfdruck. Die
  Fußzeile zählt die offenen Änderungen und bietet *Verwerfen* an. Damit
  lässt sich gefahrlos ausprobieren – bisher waren Absenden und Speichern
  derselbe Schritt.
  - Nicht live rechnen Tornado, Heatmap, Monte Carlo, Szenarien und
    Break-even: Sie führen je Aufruf Dutzende bis Tausende
    Bewertungsläufe aus und beziehen sich weiter auf den gespeicherten
    Stand. Die Sicht „Risiko" weist darauf hin, solange ein abweichender
    Entwurf offen ist.
- **Eine Regel für Tabs und Klappfelder**: Tabs sind gleichrangige Sichten
  auf denselben Gegenstand, Klappfelder optionales Detail innerhalb einer
  Sicht – und nie ineinander. Aus sieben Projekt-Tabs werden vier
  (**Ergebnis** = Cashflow + Erlöse, **Finanzierung**, **Risiko** =
  Sensitivität + Monte Carlo + Szenarien, **Annahmen**); die
  Portfolio-Analytik verliert ihr umschließendes Klappfeld.
- **Leitkennzahl statt fünf gleichrangiger Kacheln.** Equity IRR groß, mit
  Zielmarke und – bei offenen Änderungen – der Abweichung zum
  gespeicherten Stand; NPV, Equity Value, Enterprise Value und CAPEX
  begleiten kompakt daneben. Auf der Portfolioseite entsprechend der
  mittlere Equity IRR.
- **Beträge werden gerundet dargestellt** („9,34 Mio €" statt
  „9.338.144 €", genauer Wert im Tooltip). Damit passen alle Werte bei
  fester Schriftgröße: Das bisherige Mess-Skript mit Resize- und
  MutationObserver entfällt ersatzlos – rund 100 Zeilen JavaScript und
  die Ursache der im Safari gemeldeten abgeschnittenen Werte.
- **Kontextzeile** unter dem Projekttitel: Marktsystem, Preisszenario,
  Diskontsatz, Leistung, Inbetriebnahme, Anlagentyp und Zuschlagswert.
  Der Diskontsatz gilt app-weit und ist dort einstellbar, statt als
  kleines Zahlenfeld mitten auf der Seite zu stehen.
- **Aktionen nach Gewicht sortiert**: PDF-Bericht hervorgehoben, Excel
  daneben, Duplizieren/Inaktiv/Löschen im Überlaufmenü. Löschen hat nicht
  mehr die Prominenz eines Exports.
- **Auktionsmodul als Analysewerkzeug gekennzeichnet**: eigene Gruppe
  *Werkzeuge* in der Navigation, Hinweis auf der Seite, und die Übernahme
  des Vorschlagswerts führt direkt auf die Projektseite.
- Investkosten in €/kWp werden mit zwei statt einer Nachkommastelle
  geführt – mit nur einer verlor der Rückweg bei kleinen Positionen
  mehrere hundert Euro.
- 18 neue Tests (Wegsteuerung, Parameterspalte mit Entwurf und Verwerfen,
  vier Sichten, Kennzahlenleiste, Zahlenformat); Suite: 294.

### v5.0.6 – Projektkacheln fluchten

- **Je Reihe ein eigener Spaltensatz.** Bisher gab es einen Satz und die
  Karten wurden per Modulo verteilt – Streamlit stapelt sie dann
  spaltenweise, und eine hohe Karte verschiebt alles darunter in ihrer
  Spalte. Nichts richtete sich mehr aneinander aus.
- **Feste Kartenhöhe**, damit auch die „Öffnen"-Knöpfe einer Reihe auf
  einer Linie stehen. Lange Projektnamen werden auf eine Zeile gekürzt;
  der vollständige Name steht im Tooltip der Karte.
- Name und Anlagentyp-Kennzeichen stehen in einer Kopfzeile, der Rest
  darunter – die Karte hat damit eine feste Struktur statt einer Kette
  aus Zeilenumbrüchen.
- Die letzte Reihe wird nicht gestreckt: Die Karten behalten ihre Breite,
  die Übersicht bleibt ein Raster.

### v5.0.5 – Projektname wieder auffindbar

- **Der Projektname steht an erster Stelle der Parameterspalte.** Er war
  weiterhin vorhanden, stand aber zwischen Investkosten und Pacht – in
  einer scrollenden Spalte praktisch unauffindbar, sodass ein Projekt
  (etwa eine Kopie) nicht mehr umbenannt werden konnte.
- Das Feld liegt bewusst außerhalb des Formularrahmens: In der
  Parameterspalte gibt es keinen Absenden-Knopf, der Wert muss sofort in
  den Entwurf laufen.

### v5.0.4 – Cashflow-Diagramme in der Markenfamilie

- **Wertbrücke, Gesamt-Cashflow und operativer Cashflow** folgen jetzt
  ebenfalls dem Blau-Türkis: Zufluss türkis, Abfluss navy – in der
  Oberfläche wie im PDF-Bericht. Die Richtung steht bereits in der Lage
  des Balkens zur Nulllinie; die Farbe muss sie nicht ein zweites Mal
  behaupten.
- Grün und Rot bleiben damit den Fällen vorbehalten, in denen wirklich
  etwas nicht stimmt: der Unterdeckung im DSCR-Verlauf und der
  Zielverfehlung in der IRR-Heatmap.
- Bildunterschriften, die Farben benennen (Tornado, Gebotsdichte,
  Verteilungsverlauf), in allen vier Sprachen nachgezogen.

### v5.0.3 – Alphabetische Projektliste

- 4 neue Tests (Sortierschlüssel, Reihenfolge nach Projektnamen, gleiche
  Reihenfolge in Leiste und Kacheln); Suite: 299.
- **Projekte stehen alphabetisch** – in der Seitenleiste wie in der
  Kachelübersicht. Sortiert wird nach dem angezeigten Namen; bisher nach
  Dateinamen, und der folgt der Projekt-ID, die bei einer Umbenennung
  bewusst stehen bleibt. Umlaute werden aufgelöst und Groß-/Kleinschreibung
  ignoriert, damit „Ötscher" nicht hinter „Zwentendorf" landet.

### v5.0.2 – Farbschema und zwei Beschriftungen

- **Diagramme in der Blau-Türkis-Familie.** Die gestapelten
  Betriebskosten liefen bisher in Warmtönen (Rot/Orange) – neben Navy und
  Türkis las sich das wie eine Warnung, obwohl Betriebskosten nichts
  Kritisches sind. Ebenfalls umgestellt: Tornado (Navy für die
  Abwärts-, Türkis für die Aufwärtsvariante), Monte-Carlo-Verteilung mit
  Quantilen in Abstufungen derselben Familie, Szenarienvergleich,
  Erlösaufteilung und die Anlagentypen im Portfolio.
- Bewusst **außerhalb** der Familie bleibt, was eine Aussage trifft:
  Grün/Rot für Zu- und Abflüsse, die DSCR-Ampel und die IRR-Heatmap.
- „Cashflow als Excel" heißt jetzt schlicht **Excel**.
- Statuszeile der Parameterspalte über statt neben den Knöpfen – in der
  schmalen Spalte brachen „Speichern" und „Verwerfen" sonst um.
- Gesperrte Primärknöpfe werden wieder gedämpft dargestellt; die
  Markenfarbe war mit `!important` gesetzt und galt auch für sie.

### v5.0.1 – Darstellung nachgezogen

- **Auswahl durchgängig in Markenfarbe**: aktiver Navigationseintrag und
  aktive Sicht türkis hinterlegt, mit dunklerem Strich links bzw.
  darunter. Die Aufhellung wird aus der Markenfarbe berechnet
  (`Colors.SELECT`), damit der verdeckte Markenschalter sie mitnimmt.
- **Parameterspalte als eigene Fläche** mit Markenrand und türkis
  hinterlegtem Kopf; die Speicherleiste steht innerhalb des Rahmens.
- **Seitenleiste bei echten Projektnamen brauchbar**: Beschriftungen
  linksbündig, eine Zeile je Eintrag mit Auslassungspunkten statt
  Umbruch mitten im Wort, vollständiger Name im Tooltip. Inaktive
  Projekte werden blasser dargestellt statt mit einem angehängten Zeichen.
- Ursache der zuvor zentrierten und umbrechenden Beschriftungen: Knöpfe
  mit Hilfetext hängen bei Streamlit unter einem Tooltip-Träger und sind
  dann kein direktes Kind von `.stButton` mehr – die Auswahl kommt jetzt
  ohne Kindkombinator aus.

## v4.29 – Excel-Import älterer Dateien, Zusatzblöcke einklappbar (2026-08)

- **Gespeicherte Projekte lassen sich wieder einlesen.** Die
  Vollständigkeitsprüfung des Projekt-Imports blockierte Dateien, denen
  eine nachträglich hinzugekommene Spalte fehlte – und zwar bevor die
  dafür vorgesehene Vorbelegung greifen konnte. Betroffen waren
  `capex_zusatzpositionen_json` und `zusatz_opex_json` (seit v4.28) sowie,
  bereits zuvor, `capex_widmung_eur` und `capex_genehmigung_eur`.
  Die optionalen Spalten stehen jetzt als `OPTIONALE_PROJEKT_SPALTEN`
  neben der Spaltenliste, damit beides gemeinsam gepflegt wird. Eine
  echte Pflichtspalte meldet weiterhin einen klaren Fehler.
- Leere Zellen in optionalen Zahlenspalten werden als 0 gelesen. Zuvor
  hätte ein `wert or 0` das NaN durchgereicht (NaN ist wahrheitswertig
  wahr) und die Investitionssumme unbrauchbar gemacht.
- **„Weitere Investkosten" und „Weitere Betriebskosten" sind eingeklappt**
  und lassen sich je über einen Schalter vor der Überschrift einblenden.
  Standard ist zugeklappt; bei einem Projekt mit bereits hinterlegten
  Positionen startet der Block aufgeklappt. Ausblenden verändert die
  gespeicherten Positionen nicht.
- 7 neue Tests (Import ohne einzelne und ohne alle optionalen Spalten,
  leere Zelle, weiterhin gemeldete Pflichtspalte, Schalterzustände);
  Suite: 281.

## v4.28 – Frei benannte Zusatzpositionen (2026-08)

- **Zusätzliche Investkosten- und Betriebskostenpositionen mit frei
  gewählter Bezeichnung.** Das Projektformular enthält dafür je eine
  dynamische Tabelle (`st.data_editor`, `num_rows="dynamic"`); Zeilen ohne
  Bezeichnung werden verworfen, ein leerer Betrag zählt als 0.
- Die Positionen wirken durchgängig:
  - Investpositionen erhöhen `CapexBreakdown.summe_eur` und damit
    Finanzierung, Abschreibung und Cashflow – rechnerisch identisch zu
    einer Erhöhung einer Standardkategorie.
  - Betriebskostenpositionen werden in `resolve_assumptions()` hinter die
    globalen Standardpositionen gehängt und durchlaufen dieselbe
    Indexierungsvorschrift; jede erhält eine eigene Spalte der
    Cashflow-Zeitreihe.
  - Kostendiagramm, Legende, CAPEX-Ring und der PDF-Bericht (Annex A,
    Positionsliste der Betriebskosten) folgen der Liste dynamisch.
- **Namensvalidierung**: Bezeichnungen müssen nichtleer sein und dürfen
  keine reservierte Spaltenbezeichnung der Cashflow-Zeitreihe tragen
  (`RESERVIERTE_POSITIONSNAMEN`), da jede Position als Spalte geschrieben
  wird.
- Persistenz erweitert: YAML unverändert schemagetrieben, Excel um die
  Spalten `capex_zusatzpositionen_json` und `zusatz_opex_json` – Projekte
  ohne Zusatzpositionen bleiben unverändert lesbar.
- Rechenmodell-Dokumentation aktualisiert (Kapitel 4.2 Investitionsvolumen,
  8.2 Betriebskostenpositionen) und PDF neu gebaut.
- Unzulässige Bezeichnungen werden beim Absenden als Hinweis am Formular
  gemeldet statt als Fehlerseite.
- 21 neue Tests (Namensvalidierung, Äquivalenz zur Standardposition,
  eigene Zeitreihenspalte, YAML-/Excel-Roundtrip, Sichtbarkeit im
  Bericht, Formulartabellen); Suite: 275.

## v4.27 – Investkosten je Feld umschaltbar (2026-08)

- **Jedes Investkosten-Feld hat einen eigenen Umschalter** zwischen
  spezifischer Eingabe (€/kWp, Vorbelegung) und Gesamtbetrag (€) – der
  gemeinsame Radio-Umschalter für alle Felder entfällt. Beim Umschalten
  wird der bereits eingegebene Wert umgerechnet, statt die Vorbelegung
  neu zu setzen.
- Der Investkosten-Block liegt dafür jetzt außerhalb von `st.form`:
  Widgets innerhalb eines Formulars lösen erst beim Absenden einen Rerun
  aus, die Umschalter müssen aber sofort wirken (dieselbe Begründung wie
  bei den übrigen Einheiten-Umschaltern, siehe Modulkopf).
- Sidebar-Hinweise zum Sichern/Wiederherstellen nutzerorientiert
  formuliert – ohne Verweise auf Tabellenblätter, YAML-Dateien und
  Repository-Commits.
- 3 neue UI-Tests (ein Schalter je Feld, Umrechnung beim Umschalten,
  Unabhängigkeit der Felder); Suite: 252.

## v4.26 – Projektbericht: Kovenanten statt Modellherleitung (2026-08)

- **Event-of-Default-DSCR jetzt 1,05x vorbelegt** (zuvor 1,00x) – in
  Modell, Excel-Roundtrip, Hilfetexten und Dokumentation.
- **Projektbericht (PDF) bildet die Kovenantenprüfung ab**, analog zu den
  Statusmeldungen der Anwendung:
  - DSCR-Diagramm zeigt beide Schwellen als Linien; Balken folgen der
    Ampel (rot unter Event of Default, gedämpft unter Cash Trap).
  - Neuer Abschnitt in Kapitel 4 mit Schwellentabelle, betroffenen
    Betriebsjahren, Aufteilung der Nachschussdeckung (Reserve /
    bereits ausgeschüttet / extern) und Klartext-Bewertung.
  - Management Summary nennt einen Nachschussbedarf und weist aus, ob
    externes Kapital erforderlich ist.
- **Mathematische Modellherleitung des Auktionsmodells aus dem
  Projektbericht entfernt** (Abschnitt 8.3 samt Formelsatz). Der Bericht
  zeigt Datenlage, Anpassung und Prognose; die Herleitung steht
  ausschließlich in der Rechenmodell-Dokumentation (Kapitel 15), auf die
  das Kapitel jetzt verweist. Tote Formel-Hilfsfunktion und acht nicht
  mehr benötigte Textbausteine entfernt.
- **Begriffe harmonisiert** – Portfolio-Kacheln: „Investitionsvolumen
  gesamt" → **Capex Gesamt**, „Eigenkapital gesamt" → **Equity Gesamt**,
  „Ø EK-Rendite" → **Ø Equity IRR**; Projektkarten entsprechend.
- Alle Änderungen in allen vier Sprachen gepflegt; Suite: 249 grün.

## v4.25 – Bewertungskacheln und DSCR-Kovenanten (2026-07)

- **KPI-Kacheln neu belegt** (Projekt-Dashboard und PDF-Bericht):
  Equity IRR · NPV bei x % · **Equity Value** (bisher „Verkaufspreis") ·
  **Enterprise Value** (neu: Equity Value + aufgenommenes Fremdkapital) ·
  CAPEX. Die DSCR-Kachel entfällt – ein einzelner Minimalwert sagt nicht,
  ob er eine Ausschüttungssperre oder eine Nachschusspflicht auslöst.
- **Zwei DSCR-Kovenanten in den Globalen Annahmen** (Block Förderung/
  Finanzierung), mit Excel-Roundtrip und marktüblichen Vorbelegungen:
  - *Cash-Trap-DSCR* (1,10x): Darunter keine Ausschüttung; der freie
    Cashflow bleibt als Reserve in der Gesellschaft.
  - *Event-of-Default-DSCR* (1,00x): Darunter ist ein
    Eigenkapitalnachschuss nötig (Equity Cure) – in Höhe des Betrags,
    der den DSCR gerade wieder auf die Schwelle hebt.
- **Neue Kovenantenprüfung** `engine/covenants.py`: wertet beide
  Schwellen Jahr für Jahr aus und verfolgt dabei einen
  Deckungswasserfall – einbehaltene Reserve, danach bereits
  ausgeschüttetes (selbst erwirtschaftetes) Kapital, erst dann externes
  Kapital. Die Cashflow-Rechnung selbst bleibt unberührt.
- **Statusaussage im Projekt-Dashboard** unter den Kacheln: betroffene
  Jahre je Schwelle sowie die Kernfrage, ob ein Nachschuss aus eigener
  Kraft gedeckt ist oder ob die Gesellschaft innerhalb der Laufzeit
  zusätzliches externes Kapital benötigt.
- Dokumentation ergänzt: neues Kapitel 11.5 (Ereignisse,
  Nachschussbetrag, Deckungswasserfall), Equity und Enterprise Value in
  Kapitel 12.4, Symbolverzeichnis, Annahmenkatalog und Zuordnungstabelle;
  PDF neu gesetzt (48 Seiten).
- 12 neue Tests (10 Kovenanten gegen handgerechnete Erwartungswerte auf
  einer synthetischen Zeitreihe, 2 UI); Suite: 249.

## v4.24 – Vollständige Dokumentation des Rechenweges (2026-07)

- **Neue Rechenmodell-Dokumentation** unter `docs/rechenmodell/`: der
  komplette Rechenweg mit allen mathematischen Formeln, in genau der
  Reihenfolge, in der die Engine sie rechnet – Parameterauflösung,
  Zeitachse, Energieertrag, Erlöse (Marktprämie, Inflationierung,
  negative Stunden), Betriebskosten, Finanzierung, Steuern
  (inkl. Verlustvortrag), Cashflow, Kennzahlen (XNPV/XIRR/LCOE),
  Sensitivitäten und Monte Carlo sowie das vollständige Auktionsmodell
  (Verteilungsfamilien, Fit, Wettbewerbs-Link, Differenzen-
  extrapolation, Gebotsempfehlung).
- **Ein durchgerechnetes Beispielprojekt** (Kapitel 13): Betriebsjahr 1
  Schritt für Schritt von Hand nachgerechnet, Ergebniszeitreihe und
  Kennzahlen – erzeugt aus der Engine, nicht abgeschrieben.
- **Symbolverzeichnis, Annahmenkatalog (A1–A27) und Zuordnungstabelle**
  Formel → Codestelle → Test; zusätzlich die Zuordnung jedes Symbols zum
  Spaltennamen in Cashflow-Tabelle und Excel-Export.
- **Einzige Quelle:** `docs/rechenmodell/rechenmodell.md` (auf GitHub
  direkt lesbar). `docs/rechenmodell/build_pdf.py` setzt daraus das
  42-seitige PDF `Rechenmodell.pdf` – mit Deckblatt, Inhaltsverzeichnis,
  PDF-Lesezeichen und Kolumnentiteln, ausschließlich mit `reportlab`
  und `matplotlib` (mathtext), ohne TeX- oder Pandoc-Installation.
  Neuer Make-Zielbefehl: `make dokumentation`.
- `matplotlib` und `reportlab` sind jetzt auch in `pyproject.toml`
  Laufzeitabhängigkeiten (bisher nur in `requirements.txt`, obwohl
  `app/report.py` sie importiert) – damit funktionieren PDF-Bericht und
  Dokumentationsbau auch nach `make install`.
- 3 neue Tests (`tests/test_dokumentation.py`): sie lesen die Zahlen des
  Beispielkapitels aus der Markdown-Quelle und vergleichen sie mit einer
  frisch gerechneten Bewertung – die Dokumentation kann der Rechnung
  nicht mehr unbemerkt davonlaufen. Suite: 234.

## v4.23 – Wasserfalldiagramm: Hover zeigt Balkenhöhe statt Achsenwert (2026-07)

- **Bugfix (vom Nutzer gemeldet):** Beim Überfahren der Balken im
  Equity-Wasserfall (Projektdetail) wurde der kumulierte
  Y-Achsenwert des Balkenendes angezeigt statt der Höhe des Balkens –
  bei Plotly-Waterfall-Traces liefert die Hover-Variable `%{y}` die
  kumulierte Endposition, nicht das Delta. Umgestellt auf `%{delta}`
  (vorzeichenbehaftete Balkenhöhe in €); bei Total-Balken entspricht
  delta dem Endwert, die Vorlage passt damit für beide Balkentypen.
- 2 neue Regressionstests (Hovertemplate nutzt delta statt y;
  Balkenhöhen fachlich unverändert); Suite: 231.

## v4.22 – Marktsystem-Schalter Österreich (EAG) / Deutschland (EEG) (2026-07)

- **Neuer Länderschalter** direkt unter der Überschrift der Seite
  „Globale Annahmen“: zwei Flaggen-Buttons (Österreich/Deutschland,
  gleiche Bild-Icon-Technik wie der Sprachumschalter, neue Flaggendatei
  `assets/flags/de.png`). Ein Klick stellt die gesamte Marktsystematik
  als Paket um und speichert sofort:
  - **Österreich (EAG):** 6-Stunden-Regel für den Prämienentfall,
    Steuermodus „Körperschaftsteuer mit AfA“, Zinsmethodik act/365,
    Untertitel „… EAG-Marktprämienmodell, Österreich“, empirisches
    Ausschreibungsmodell aktiv (unverändert wie bisher).
  - **Deutschland (EEG):** 1-Stunden-Regel, Steuermodus „Deutsche
    Gewerbesteuer“, Zinsmethodik 30/360, Untertitel
    „… EEG-Marktprämienmodell, Deutschland“; auf der Marktprämienseite
    wird die empirische Methodik (Historie, Kurven-Fitting, Prognose)
    ausgegraut und stattdessen der erwartete Marktprämienzuschlag
    manuell eingetragen (global gespeichert, Übergabe an Projekte wie
    bisher).
  Die einzelnen Einstellungen bleiben nach dem Wechsel weiterhin
  manuell änderbar.
- **Rubrik umbenannt:** „Ausschreibung“ heißt jetzt „Marktprämie“
  (alle vier Sprachen).
- Engine: neues Enum `MarktSystem` und Felder
  `GlobalAssumptions.markt_system` sowie
  `GlobalAssumptions.de_marktpraemie_erwartet_ct_kwh` (rückwärts-
  kompatibel, Bestandsdateien laden mit Standard Österreich).
- 12 neue Tests (Modell/Serialisierung, Flaggen-Buttons und
  Paket-Umstellung, marktabhängiger Untertitel, deutsche
  Marktprämienseite inkl. Speicherung und Übergabe des manuellen
  Werts); Suite: 229.

## v4.21 – Excel-Projektimport: echte Rückwärtskompatibilität (2026-07)

- **Bugfix (vom Nutzer gemeldet):** Projekt-Excel-Dumps, die vor der
  Umsatzbeteiligungs-Pacht (v4.19) exportiert wurden, ließen sich
  nicht mehr importieren (`ValueError: Spalten fehlen`). Ursache: die
  drei neuen Spalten (`pacht_modus`, `pacht_umsatzbeteiligung_pct`,
  `pacht_mindestpacht_eur_ha_jahr`) hatten zwar bereits eine passende
  Fallback-Logik pro Feld, wurden aber von einer davor geschalteten,
  strikten Spaltenprüfung blockiert, bevor diese Logik je zum Einsatz
  kam – ein Fehler, der bei der Einführung dieser drei Spalten
  entstanden ist.
- Die drei Spalten sind jetzt korrekt als optional markiert (wie
  bereits `aktiv` seit v4.5) – ältere Exportdateien laden mit
  sinnvollen Vorgabewerten (Pachtmodus „fix“, Umsatzbeteiligung 5,5 %,
  Mindestpacht 0 €/ha).
- 1 neuer Regressionstest, der genau dieses Szenario nachbildet
  (Export, drei Spalten künstlich entfernen, erneut importieren);
  Suite: 217, zweifach hintereinander stabil gelaufen.

## v4.20 – Deutsche Gewerbesteuer als dritte Steuerlogik (2026-07)

- Klarstellung zur letzten Version: v4.18 hatte die **Zinsberechnungs­methodik**
  (Tageszählweise 30/360 vs. act/365) umgesetzt, wörtlich wie damals
  angefragt – das ist aber etwas anderes als die **Steuerlogik**, die
  eigentlich gemeint war. Diese Version holt das nach.
- Neuer dritter Steuermodus neben Pauschal und österreichischer
  AfA-Körperschaftsteuer: **Deutsche Gewerbesteuer**, global umschaltbar
  in Globale Annahmen → Steuern (wie Tilgungsart/Zinsmethode, gilt für
  alle Projekte).
  `Steuer = MAX(EBT − AfA − Freibetrag, 0) × 3,5 % × Hebesatz`
  (Hebesatz einstellbar, Standard 400 %; Freibetrag einstellbar, Standard
  24.500 €/Jahr – gesetzlicher Wert für Personengesellschaften wie
  GmbH & Co. KG). Live-Anzeige des daraus berechneten effektiven Satzes
  in der Oberfläche.
- Bewusst **ohne Verlustvortrag** modelliert (jedes Jahr unabhängig
  betrachtet) – echte deutsche Gewerbesteuer kennt zwar einen
  Verlustvortrag (§10a GewStG), das als Referenz validierte Modell
  (Abgleich mit einer realen Projekt-Excel in einer früheren Sitzung)
  bildete ihn aber ebenfalls nicht ab; diese Vereinfachung ist im Code
  klar dokumentiert.
- UI zeigt je nach gewähltem Modus automatisch die passenden Felder
  (deutsch: Hebesatz + Freibetrag; österreichisch/pauschal: Steuersatz
  + Verlustvortrag-Verrechnungsgrenze) statt aller Felder gleichzeitig.
- Vollständig durchverdrahtet: Datenmodell, Engine, Excel-Import/
  -Export (inkl. Rückwärtskompatibilität für ältere Exportdateien),
  PDF-Bericht (Annex A zeigt modusabhängig den korrekten effektiven
  Satz statt des dort sonst irrelevanten generischen Feldes), alle
  vier Sprachdateien.
- 9 neue Tests (Formelkorrektheit, unterschiedliche Hebesätze,
  Freibetrag-Wirkung, AfA-Berücksichtigung, kein Verlustvortrag im
  Gegensatz zum österreichischen Modus, End-to-End-Unterscheidung
  zwischen beiden Ländern, YAML-/Excel-Rundlauf, Rückwärts­kompatibilität);
  Suite: 216, zweifach hintereinander stabil gelaufen.

## v4.19 – Pacht: Umsatzbeteiligung mit Mindestpacht (2026-07)

- Neuer Pachtmodus zusätzlich zur bisherigen fixen Pacht (€/kWp oder
  €/ha): **Umsatzbeteiligung mit Mindestpacht**. Der Verpächter erhält
  einen Anteil am Jahresumsatz (Vorschlagswert 5,5 %, projektspezifisch
  einstellbar) – mindestens aber eine fixe Mindestpacht je Hektar, die
  mit der allgemeinen Kosteninflation indexiert wird.
  `Pacht = MAX(Umsatz × Prozentsatz, Mindestpacht/ha × Fläche × Inflation)`.
- Genau der vom Nutzer beschriebene Effekt ist nachgebildet und per
  Test abgesichert: In frühen Jahren (hoher, EAG-gestützter Umsatz)
  dominiert die Umsatzbeteiligung; nach Ende der EAG-Förderung (Umsatz
  bricht ein) übersteigt die stetig weiter mit der Inflation
  wachsende Mindestpacht die Umsatzbeteiligung.
- Neue Auswahl im Projektformular (Pachtmodus-Umschalter direkt über
  dem bisherigen Pacht-Eingabefeld) sowie ein neuer
  Umsatzbeteiligungs-Vorschlagswert in den Globalen Annahmen (analog
  zum bereits bestehenden Muster bei Gemeindeabgabe/
  Direktvermarktungskosten).
- Architektur: Pacht wird nicht mehr als generische, projektbezogene
  OPEX-Position behandelt (dafür bräuchte es den Jahresumsatz, den die
  generische Position nicht kennt), sondern als eigene, produktions-
  UND umsatzabhängige Berechnung analog zu Gemeindeabgabe/
  Direktvermarktungskosten – bleibt aber weiterhin ein normaler,
  benannter Balken im gestapelten Betriebskosten-Diagramm.
- Vollständig durchverdrahtet: Datenmodell, Engine, Excel-Import/
  -Export (inkl. Rückwärtskompatibilität für ältere Exportdateien),
  PDF-Bericht (Annex A zeigt den gewählten Modus korrekt), alle vier
  Sprachdateien.
- Dabei einen Namenskollisions-Bug im Vorbeigehen gefunden und
  behoben: Sollte eine globale Standard-Betriebskostenposition
  zufällig ebenfalls „Pacht“ heißen, führte die erste Fassung dieser
  Änderung zu einer doppelten Spalte und einem Pandas-Fehler beim
  Rendern der Detailtabelle.
- 7 neue Tests (beide Regime einzeln, Übergang zwischen den Regimen
  über die volle Pipeline, Fläche fehlt, Namenskollision,
  unveränderte Rückwärtskompatibilität des bisherigen Fix-Modus);
  Suite: 207, zweifach hintereinander stabil gelaufen.

## v4.18 – Steuer-Diagramm, Verkaufspreis-KPI, deutsche/österreichische Zinsmethodik (2026-07)

### Steuerzahlungen jetzt als eigenes Diagramm
- Neues Balkendiagramm direkt unter der Betriebskosten-Grafik im
  Projekt-Dashboard (`charts.tax_chart()`) – Steuer war bisher in
  keinem Diagramm sichtbar, nur in der Detailtabelle.

### Verkaufspreis ersetzt LCOE
- Projekt-KPI-Zeile neu geordnet: EK-Rendite, NPV, **Verkaufspreis**,
  CAPEX, DSCR (vorher: …, DSCR, CAPEX, LCOE).
  `Verkaufspreis = NPV + Eigenkapital`.
- Konsistent auch im PDF-Bericht (Management-Summary-Kacheln)
  nachgezogen; alte LCOE-Sprachschlüssel durch die neuen ersetzt statt
  sie tot liegen zu lassen.

### Robustheit: Portfolio-Landkarte bei leerem Portfolio
- Beim Testen dieser Version aufgefallen: `portfolio_bubble_chart()`
  stürzte mit `KeyError: 'typ'` ab, wenn (z.B. über den Inaktiv-Filter)
  null aktive Projekte übrig blieben - der DataFrame war dann leer und
  hatte keine Spalten. Zeigt jetzt stattdessen eine leere Grafik.

### Deutsche vs. österreichische Zinsberechnungsmethodik
- Neue Auswahl in Globale Annahmen → Förderung, Finanzierung, direkt
  neben der Tilgungsart: **Österreichisch** (act/365, taggenau – nach
  österreichischer Rechtsprechung/OGH für Unternehmen üblich) oder
  **Deutsch** (30/360, kaufmännische Zinsmethode). Wirkt sich nur aus,
  wenn die Inbetriebnahme nicht am 1. Januar erfolgt.
- **Dabei gefundener Bestandsfehler:** Das Modell berechnete für das
  erste Betriebsjahr bislang *immer* volle 12 Monate Zinsen,
  unabhängig vom Inbetriebnahme-Monat – bei einem Testprojekt mit
  Inbetriebnahme im Juni waren das 40.521 € zu viel Zinsen im ersten
  Jahr (fast das Doppelte des korrekten Werts). Betrifft rückwirkend
  jedes bestehende Projekt mit Inbetriebnahme ungleich Januar, nicht
  nur die neue Auswahlmöglichkeit.
- Neue Funktion `engine.timeline.erstjahr_zins_pro_rata()`: berechnet
  den anteiligen Zinsfaktor für beide Konventionen; die
  österreichische Variante nutzt exakt dieselbe taggenaue Zeitachse
  wie die bereits bestehende Produktions-Anteilsrechnung.
  `engine.financing.calculate_financing()` wendet den Faktor gezielt
  nur auf die Zinsen des ersten Jahres an, die Tilgung folgt
  unverändert der Annuitäten-/Linear-Formel.
- Vollständig durchverdrahtet: `GlobalAssumptions`/
  `EffectiveAssumptions`, YAML-I/O (automatisch über Pydantic),
  Excel-I/O (inkl. Rückwärtskompatibilität für ältere Exportdateien
  ohne die neue Spalte), alle vier Sprachdateien.
- 15 neue Tests (Formelkorrektheit beider Konventionen, Konsistenz mit
  der Produktions-Zeitachse, End-to-End über die volle Pipeline,
  YAML-/Excel-Rundlauf, Rückwärtskompatibilität); Suite: 200 (inkl. 1 Regressionstest für die Portfolio-Landkarten-Robustheit).

## v4.17 – Verdeckter Marken-Schalter: Trianel-Layout vs. Nobis Analytics (2026-07)

- Neuer verdeckter Schalter zwischen der aktuellen Nobis-Analytics-
  Gestaltung (Standard) und der vorherigen Trianel-Gestaltung.
  Aktivierung ausschließlich über den URL-Parameter `?marke=trianel`
  – nirgends in der Oberfläche verlinkt oder dokumentiert, daher
  "verdeckt". Zurück zu Nobis Analytics: `?marke=nobis` oder Parameter
  entfernen und neu laden.
- **Original-Assets wiederhergestellt**, nicht nachgebaut: Das exakte
  Trianel-Logo und -Favicon wurden aus einem alten, vom Nutzer
  hochgeladenen Archivstand (`pv_platform_v2_2.zip`) extrahiert und
  unter `assets/trianel/` abgelegt – die Originaldatei war beim
  Rebrand (v4.15) unwiederbringlich gelöscht worden.
- Neues Modul `app/branding.py`: zentrale Registry beider
  Markenkonfigurationen (Farben, Logo, Favicon, Kopfzeilentexte).
  `app/theme.py` (`wende_farben_an()`) und `app/report.py` (eigene
  gespiegelte Konstanten, identische Funktion) machen die Farbpalette
  zur Laufzeit umschaltbar; PDF-Bericht und Excel-Pipeline-Export
  übernehmen Logo, Farben und Signatur-Text ebenfalls (kein
  `{marken_name}`-Platzhalter mehr hart codiert).
- Zwei echte Bugs beim Umbau gefunden und behoben, bevor sie live
  gegangen wären: (1) `HEAT_SCALE` (IRR-Heatmap-Farbskala) rutschte
  beim Einfügen der neuen Funktion versehentlich aus der `Colors`-
  Klasse heraus und hätte die Heatmap mit `AttributeError` abstürzen
  lassen; (2) das Plotly-Template wurde bisher nur einmal registriert
  und cachte nach einem Markenwechsel die alte Farbpalette weiter.
- Bekannte, bewusst in Kauf genommene Einschränkung (dokumentiert in
  `app/branding.py`): Die Farbpalette ist prozessweiter, nicht
  sitzungsspezifischer Zustand – bei echtem gleichzeitigem
  Mehrnutzerbetrieb auf demselben Streamlit-Worker könnte sich in
  seltenen, timing-abhängigen Fällen die Farbwahl zweier Sessions kurz
  überschneiden (rein optisch, kein Datenrisiko). Für eine selten
  genutzte, verdeckte Vergleichsansicht ein akzeptabler Kompromiss.
- 8 neue Tests (Registry-Vollständigkeit, Original-Assets vorhanden,
  App/PDF/Excel-Export folgen dem Schalter, Rückfall auf Nobis bei
  unbekanntem Parameter, Zustand bleibt zwischen Tests nicht hängen);
  Suite: 184, zweifach hintereinander stabil gelaufen.

## v4.16 – Kopfzeile: abgeschnittenes Logo/Sprach-Popover behoben (2026-07)

- **Ursache 1 (Layout):** Bei breitem Fenster ohne Zeilenumbruch im
  Titeltext fiel die Zeilenhöhe der Kopfzeile knapp auf die Texthöhe -
  das etwas höhere Logo und der Sprach-Popover-Button wurden dadurch
  oben abgeschnitten. Bei schmalem Fenster (Titeltext bricht um) wuchs
  die Zeile automatisch mit, das Problem trat nicht auf - genau das vom
  Nutzer beschriebene Muster. Behoben durch einen eigenen,
  adressierbaren Kopfzeilen-Container (`st.container(key="app_header")`)
  mit garantierter Mindesthöhe (80px) und explizit sichtbarem Overflow
  in der zugehörigen CSS-Regel.
- **Ursache 2 (echter Bug, beim Beheben von Ursache 1 selbst
  eingebaut und noch in derselben Antwort gefunden):** Ein
  Einrückungsfehler beim Umbau ließ `st.rerun()` im
  Sprachauswahl-Popover auf Schleifenebene statt innerhalb des
  Klick-`if` stehen - dadurch feuerte bei **jeder** der vier
  Schleifeniterationen ein unbedingter Rerun, unabhängig davon, ob
  ein Sprach-Button überhaupt angeklickt wurde. Ergebnis: ein
  Rerun-Endlosloop, der die App nie fertig rendern ließ (und damit
  vermutlich der eigentliche/verstärkende Grund für das
  "Abschneiden" war, da Logo und Popover nie einen abgeschlossenen
  Render-Zyklus erreichten). Fund per zeitgestopptem Testlauf: erste
  Fassung des Fixes ließ den initialen Render über 170 Sekunden
  hängen statt der üblichen ~3 Sekunden.
- 2 neue Regressionstests: einer prüft, dass der initiale Render
  unter 15 Sekunden bleibt (fängt künftige Rerun-Loops jeder Art ab),
  einer prüft statisch, dass `st.rerun()` exakt auf derselben
  Einrückungsebene wie die zugehörige Session-State-Zuweisung steht.
  Suite: 176.

## v4.15 – Farbschema: Trianel-Rot durch Nobis-Türkis/Navy ersetzt (2026-07)

- Komplette Markenfarben-Palette aus dem Nobis-Analytics-Logo abgeleitet
  (Türkis- und Navy-Ton direkt aus dem Farbverlauf gemessen), statt nur
  Logo/Favicon auszutauschen und die alte Trianel-Farbgebung
  weiterlaufen zu lassen:
  - `BRAND` (Akzent, Buttons, Auswahl, Kopfzeilen-Linie):
    `#BE172B` (Trianel-Rot) → **`#167B88`** (Nobis-Türkis)
  - `INK` (Überschriften, Haupttext): `#143530` (Tannengrün) →
    **`#14304F`** (Navy)
  - `INK_SOFT`, `MUTED`, `NEUTRAL`, `LINE`, `WASH` rechnerisch aus dem
    neuen Navy-Farbton hergeleitet (gleiche Helligkeits-/Sättigungs-
    Verhältnisse wie zuvor), damit die gesamte Palette aus einer
    Familie stammt statt einzelner geschätzter Werte. Alle neuen Töne
    WCAG-AA-konform gegen Weiß geprüft (`BRAND` 4,97:1, `INK` 13,4:1).
  - `POSITIVE`/`NEGATIVE`/`OPEX_SCALE`/`HEAT_SCALE` bewusst
    unverändert: rot=negativ/grün=positiv ist eine semantische
    Finanz-Konvention, keine Marken-Dekoration.
- Betrifft `app/theme.py` (App-UI, Plotly-Diagramme) und `app/report.py`
  (PDF-Bericht, eigene gespiegelte Konstanten) identisch – inklusive
  bislang direkt eingebetteter Werte, die nicht über die zentrale
  `Colors`-Klasse liefen: der Button-Hover-Zustand
  (`#A31425` → `#12646E`) sowie sechs `rgba(20, 53, 48, …)`- und drei
  `rgba(138, 166, 160, …)`-Flächenfüllungen in den Plotly-Charts.
- 4 neue Tests, davon einer mit Pixel-Analyse des gerenderten PDFs
  (`pdftoppm`): bestätigt 0 Trianel-Rot-Pixel und >100 Nobis-Türkis-
  Pixel auf dem Deckblatt; Suite: 174.

## v4.14 – Rebrand: Nobis Analytics (2026-07)

- Vollständiger Markenwechsel weg von Trianel/„TEA PV-Projektbewertung“
  hin zu **Nobis Analytics**, dem neuen Eigenprodukt.
- Neues Logo (`assets/nobis_logo.png`, auf den Bildinhalt zugeschnitten,
  Seitenverhältnis 3,35:1) ersetzt das alte Trianel-Logo im App-Header
  (Anzeigebreite entsprechend angepasst) und auf dem PDF-Deckblatt
  (Höhe wird dort ohnehin dynamisch aus dem Seitenverhältnis berechnet,
  keine Codeänderung nötig). Neues Favicon (`assets/favicon.png`,
  automatisch auf den quadratischen Bildinhalt zugeschnitten) für den
  Browser-Tab.
- App-Titel im Header auf „PV-Projektbewertung“ verkürzt (funktionale
  Beschreibung) statt Firmennamen zu wiederholen, da das neue Logo den
  Schriftzug „NOBIS ANALYTICS“ bereits enthält – Browser-Tab-Titel,
  PDF-Fußzeile/Autor-Metadaten und Excel-Berichtstitel zeigen
  weiterhin „Nobis Analytics“ als Signatur.
- Sämtliche „TEA“-Vorkommen im Programmcode, allen vier Sprachdateien
  und der Dokumentation entfernt; die interne Umgebungsvariable
  `TEA_SPRACHE` in `NOBIS_SPRACHE` umbenannt. Historische
  Changelog-Einträge bewusst unverändert belassen (Protokoll des
  jeweiligen Entwicklungsstands).
- 5 neue Regressionstests (Konfiguration, Sprachdateien, App-Header,
  PDF-Bericht, Excel-Export – jeweils frei von „TEA“, neue Marke
  vorhanden); Suite: 170.

## v4.13 – Sprachumschalter: echte Flaggen-Icons statt Emoji (2026-07)

- Emoji-Länderflaggen (🇦🇹 🇬🇧 🇫🇷 🇪🇸) werden auf etlichen Systemen und
  in manchen Browsern nicht dargestellt (u. a. verbreitet unter
  Windows, das keine regionalen Indikatorsymbole in vielen
  System-Schriftarten unterstützt) – zusätzlich kann `st.selectbox`
  ohnehin keine Bilder in seinen Optionen zeigen, nur Text. Der
  Sprachumschalter wurde deshalb von `st.selectbox` auf ein
  `st.popover` mit **echten PNG-Flaggen-Icons** umgebaut
  (`assets/flags/{at,gb,fr,es}.png`, lokal generiert, keine externe
  Netzwerkabhängigkeit im Betrieb).
- Trigger-Button zeigt das aktuelle Länderkürzel mit Streamlits
  eingebautem Material-Icon (`:material/language:`) statt eines
  Emojis – ebenfalls unabhängig von der System-Schriftart zuverlässig
  darstellbar. Popover-Inhalt: eine Zeile Flagge + Sprachname je
  Sprache, aktuell aktive Sprache farblich hervorgehoben.
- Funktional unverändert: Ein Klick setzt weiterhin
  `st.session_state["tea_sprache"]` und wirkt sofort auf die gesamte
  App. 2 neue Tests (Flaggendateien vorhanden und gültige PNGs,
  Popover bettet 4 Bilder + Umschaltung funktioniert); bestehende
  Dropdown-Tests auf Button-Klicks umgestellt; Suite: 165.

## v4.12 – Vollständige Übersetzung: alle verbliebenen Texte erfasst (2026-07)

- Gründliche Neuvermessung der gesamten App ergab 226 weitere
  unübersetzte deutsche Textstellen, die frühere Extraktionsrunden
  übersehen hatten – darunter **komplett unangetastete Dateien** wie
  `app/components/sidebar.py` (Projekte/Globale Annahmen sichern &
  wiederherstellen, wie vom Nutzer gemeldet) sowie große Teile von
  `assumptions.py`, `auktion.py`, `project_detail.py`, `project_form.py`
  und `report.py` (PDF-Kapitel 1–7 und Annex A/B, zuvor nur Kapitel 8
  vollständig ausgelagert).
- Alle 226 Fundstellen extrahiert und verdrahtet: Sidebar-Expander,
  Datei-Upload-Labels, sämtliche Eingabefeld-Labels und Hilfetexte in
  den Globalen Annahmen (Marktpreisszenarien, Negativstunden-Regeln,
  Steuerlogik), die komplette Ausschreibungsseite (inkl. der
  LaTeX-eingebetteten Prognosemethodik-Texte), das gesamte
  Projekt-Dashboard (KPI-Labels, Tab-Namen, alle Diagrammbeschriftungen
  und -captions, Break-even-Assistent, Monte-Carlo-Steuerung,
  Szenarienvergleich, Annahmen-Zusammenfassung) sowie der PDF-Bericht
  bis auf die letzte Tabellenüberschrift.
- Editor-Spaltenüberschriften (Marktpreiskurven, Standardbetriebskosten)
  über `st.column_config` übersetzt, ohne die internen
  DataFrame-Spaltennamen zu ändern, die an anderer Stelle als
  Dictionary-Schlüssel gelesen werden – vermeidet Bruch der
  Speicherlogik.
- Monatsnamen (`MONATE`/`MONATE_KURZ` in `app/config.py`) von
  statischen deutschen Konstanten auf sprachabhängige Funktionen
  (`monate()`/`monate_kurz()`) umgestellt, die zur Laufzeit die
  aktuell gewählte Sprache widerspiegeln.
- Alle neuen Schlüssel vollständig in Englisch, Französisch und
  Spanisch übersetzt. **Endstand: 696 Schlüssel je Sprache** (382
  `oberflaeche.yaml`, 72 `diagramme.yaml`, 175 `bericht.yaml`, 67
  `excel.yaml`) – exakt identische Schlüssel und Platzhalter über alle
  vier Sprachen, automatisiert geprüft. Ein vollständiger Scan der
  gesamten `app/`-Schicht bestätigt: keine verbleibenden
  unübersetzten deutschen Literalstrings.
- 6 neue Tests (Seiten-Übersetzung von Formular/Ausschreibung/
  Annahmen/Sidebar in mehreren Sprachen); Suite: 163.

## v4.11 – Sprach-Dropdown: kompaktes Flagge+Kürzel-Format (2026-07)

- Das Sprach-Dropdown zeigt jetzt Flagge + Länderkürzel statt des vollen
  Sprachnamens: 🇦🇹 DE · 🇬🇧 EN · 🇫🇷 FR · 🇪🇸 ES (vorher: 🇦🇹 Deutsch,
  🇬🇧 English, 🇫🇷 Français, 🇪🇸 Español). Kompakter in der Kopfzeile,
  funktional unverändert – Umschaltverhalten und Fallback-Mechanismus
  sind unberührt.

## v4.10 – Drei gemeldete Fehler behoben (2026-07)

- **Gemeindeabgabe im Betriebskosten-Chart nicht sichtbar:** Ursache war
  kein Datenfehler (der Balken war immer da, mit korrektem Wert), sondern
  fehlender Farbkontrast – die feste Farbe `#7B241C` lag optisch fast
  identisch neben den benachbarten `OPEX_SCALE`-Warmtönen (Pacht
  `#873600`, Sonstiges `#A04000`) und "verschwand" dadurch im Stack.
  Gemeindeabgabe und Direktvermarktung erhalten jetzt Farben aus der
  Ink-Grün-Familie (`Colors.INK` / `Colors.INK_SOFT`) statt der
  Warmton-Skala – klar unterscheidbar unabhängig davon, wie viele
  Standard-OPEX-Positionen konfiguriert sind. Beide Serien zusätzlich
  über die Sprachdatei übersetzt (`diagramme.serie_gemeindeabgabe`/
  `serie_direktvermarktung`).
- **Projektanzahl-KPI ignorierte den Inaktiv-Filter:** Die "Projekte"-
  Kachel zählte immer `len(zeilen)` (alle Projekte) statt der gefilterten
  `kpi_basis`, während alle anderen Portfolio-KPIs (Leistung, CAPEX, EK,
  Ø-Rendite) korrekt auf aktive Projekte reduzierten. Jetzt konsistent.
- **KPI-Schriftgrößen passten "manchmal" nicht:** Das bestehende
  JS-Anpassungsskript maß Textbreiten nur beim initialen Laden (fixe
  Timeouts + Resize-Event). Spätere Layoutverschiebungen ohne
  `window.resize`-Event – Sidebar auf-/zuklappen, Tab- oder
  Expander-Wechsel, ein Rerun mit anderen Werten – ließen die einmal
  gesetzte Schriftgröße veralten. Ein `ResizeObserver` auf der KPI-Zeile
  und ein `MutationObserver` auf dem Dokument stoßen jetzt bei jeder
  relevanten Änderung einen entprellten Re-Fit an. Zusätzliches
  CSS-Sicherheitsnetz: `text-overflow: ellipsis` auf `.kpi-value`, falls
  eine Anpassung doch einmal minimal zu spät kommt – sauberes Abschneiden
  statt hartem, unleserlichem Clip.
- 6 neue Regressionstests (Farbkontrast, Datenintegrität, Projektanzahl-
  Filter inkl. Testisolation mit Cleanup, CSS- und JS-Vorhandensein);
  Suite: 158, zweifach hintereinander lauffähig ohne Seiteneffekte auf
  die Projektdateien.

## v4.9 – Mehrsprachigkeit: DE/EN/FR/ES mit Live-Umschaltung (2026-07)

### Sprachumschaltung
- Neues Dropdown oben rechts in der Kopfzeile mit Flagge + Sprachname
  (🇦🇹 Deutsch · 🇬🇧 English · 🇫🇷 Français · 🇪🇸 Español). Die Auswahl
  landet in `st.session_state["tea_sprache"]` und wirkt sofort nach
  einem Rerun auf Navigation, alle Buttons/Abschnittstitel, Diagramme
  sowie neu erzeugte PDF- und Excel-Exporte – geprüft per
  End-to-End-Test inkl. eines vollständig auf Englisch generierten
  PDF-Berichts (Kapitelüberschriften und Kapitel-8-Fließtext).
- `texte.py`: neue `SPRACHEN`-Registry (Code → Anzeigename + Flagge),
  `aktive_sprache()` liest zuerst die Streamlit-Session (Dropdown),
  außerhalb einer laufenden App weiterhin die Umgebungsvariable
  `TEA_SPRACHE`. Der Streamlit-Import bleibt lazy/optional, damit
  Engine-Schicht und Tests unverändert ohne Streamlit funktionieren.
- Navigation auf stabile interne Codes umgestellt (`portfolio`, `neu`,
  `auktion`, `annahmen` statt übersetzter Label-Strings als
  Radio-Wert): Die Auswahl bleibt beim Sprachwechsel gültig, unabhängig
  von der aktuell anzeigten Übersetzung.

### Vollständige Übersetzung
- Englisch, Französisch und Spanisch vollständig für alle vier
  Sprachdateien ergänzt: 95 Schlüssel `oberflaeche.yaml`, 58
  `diagramme.yaml`, 43 `bericht.yaml` (inkl. der kompletten
  Fließtext-Absätze aus PDF-Kapitel 8), 67 `excel.yaml` – macht 263
  Texte je Sprache, für alle vier Sprachen mit exakt identischen
  Schlüsseln UND identischen `{platzhalter}` (per Test abgesichert).
- Dabei zusätzlich 60 bislang unausgelagerte deutsche Literalstrings
  gefunden und mit extrahiert: alle Abschnittstitel des
  Projekt-Dashboards (Wertbrücke, DSCR, Tornado, IRR-Landkarte,
  Gebotsassistent, Monte-Carlo-Sektionen etc.), der Ausschreibungsseite,
  Erfolgs-/Fehler-/Hinweismeldungen (Projekt speichern/löschen/anlegen,
  Excel-Import, Szenario-Verwaltung) sowie Portfolio-KPI-Labels, die in
  einer früheren Extraktionsrunde in der Sprachdatei angelegt, aber nie
  mit dem Code verdrahtet worden waren.
- 9 neue Tests (Sprachregistrierung, Fallback-Mechanismus über ein
  isoliertes synthetisches Locale-Verzeichnis, Schlüssel-/
  Platzhalter-Vollständigkeit aller vier Sprachen, Dropdown-E2E je
  Sprache, PDF-Export-Sprache); Suite: 153.

## v4.8 – PDF-Kapitel 8: letzte Fließtexte ausgelagert (2026-07)

- Die zuvor als bekannte Lücke dokumentierten Fließtext-Absätze in
  PDF-Kapitel 8 (Historie der Ausschreibungen, Fitting-Erklärung,
  Modellbeschreibung, Bildunterschriften Abb. 14–17, Tabellenkopf/
  -unterschrift Tab. 3) sind jetzt vollständig nach `bericht.yaml`
  ausgelagert – 18 neue Schlüssel mit `{platzhalter}` für alle zuvor
  im Code eingesetzten Kennzahlen (Rundenanzahl, Daten, Grenzzuschlag,
  Wettbewerbsquote, Projektwert, Zuschlagswahrscheinlichkeit,
  Formel-Zeile). `app/report.py` enthält für Kapitel 8 keine
  literalen deutschen Fließtexte mehr, nur noch `txt(...)`-Aufrufe.
- Damit sind sämtliche sichtbaren Texte der Anwendung ausgelagert:
  UI, Diagramme, kompletter PDF-Bericht und Excel-Ergebnisexport.
  `locales/README.md` aktualisiert (Platzhalter-Beispiel, bekannte
  Lücke entfernt).
- 4 neue Tests (Schlüsselvollständigkeit, Platzhalter-Einsetzung,
  End-to-End-Regeneration des PDF-Berichts mit den ausgelagerten
  Texten); Suite: 147. PDF-Ausgabe inhaltlich unverändert
  (byte-identische Textinhalte, gleiche Dateigröße).

## v4.7 – Sprachdateien: alle Texte ausgelagert (2026-07)

- Neuer zentraler Text-Loader `texte.py` (Projekt-Wurzel, bewusst
  außerhalb von `engine/` und `app/`, damit beide Schichten ihn ohne
  Schichtverletzung nutzen können): liest `locales/<sprache>/*.yaml`,
  merged nach `<datei>.<schlüssel>`, mit Fallback-Kette Zielsprache →
  Deutsch → Schlüsselname (fail-soft, kein Absturz bei Lücken).
  Sprachwahl über Umgebungsvariable `TEA_SPRACHE` (Standard `de`).
  Platzhalter als `{name}` via `str.format`.
- **Vier Sprachdateien nach Textgattung** (`locales/de/`):
  `oberflaeche.yaml` (Navigation, Buttons, Badges, Abschnittstitel,
  Hinweistexte), `diagramme.yaml` (Diagrammtitel, Achsen, Legenden,
  Annotationen), `bericht.yaml` (PDF-Kapitel-/Abschnittsüberschriften),
  `excel.yaml` (Pipeline-Export-Beschriftungen) – siehe
  `locales/README.md` für Architektur und Anleitung zum Übersetzen.
- Durchgängig verdrahtet: komplette Navigation und Kopfzeile
  (`streamlit_app.py`), alle Projekt-/Portfolio-Buttons und
  Statusbadges (`overview.py`, `project_detail.py`), 35 Diagrammtexte
  (`charts.py`), 25 PDF-Kapitel-/Abschnittstitel (`report.py`), 81
  Beschriftungen des Excel-Ergebnisexports über den schichtfreien
  `_t(...)`-Helfer (`io_ergebnis_excel.py`, ohne Streamlit-Abhängigkeit
  in der Engine).
- Demo-Übersetzung `locales/en/oberflaeche.yaml` (bewusst
  unvollständig) belegt den Fallback auf Deutsch für fehlende
  Schlüssel. 11 neue Tests für Loader/Fallback/Platzhalter; Suite: 143.
- Bekannte Lücke (dokumentiert in `locales/README.md`): die
  mehrsätzigen Fließtext-Absätze in PDF-Kapitel 8 sind noch nicht
  ausgelagert.

## v4.6 – Excel-Ergebnisbericht für die gesamte Pipeline (2026-07)

- Neuer Export auf der Portfolio-Seite ("Excel-Ergebnisbericht
  erstellen"): eine Arbeitsmappe mit Blatt **Übersicht** (Kennzahlen
  aller Projekte inkl. Aktiv-Kennzeichnung, IRR-Diagramm) plus **je
  Projekt ein eigener Reiter**.
- Alle Auswertungen als **native, editierbare Excel-Diagramme** (keine
  Bilder), jeweils mit dem Datengerüst als Tabelle daneben: Vergütung/
  Marktwert, Erlösstruktur (gestapelt), Gesamt-Cashflow (Balken +
  kumulierte Linie), Betriebskosten (gestapelt), Kapitaldienst +
  DSCR-Verlauf, NPV-Kurve, Sensitivitäts-Tornado (±10 %),
  EAG-Zuschlagswert-Sensitivität, Monte-Carlo-Histogramm (300 Läufe,
  inkl. P10/Median/P90) und Szenarienvergleich – 11 Diagramme je
  Projektblatt.
- KPI-Kopf je Reiter (Leistung, Zuschlagswert, CAPEX, EK, IRR, NPV,
  DSCR min, Amortisation); inaktive Projekte enthalten und im Titel/
  in der Übersicht markiert; eindeutige Blattnamen bei
  Namenskollisionen. Engine-Funktion `pipeline_ergebnis_excel` separat
  testbar; 4 neue Tests; Suite: 132.

## v4.5 – PDF-Kapitel 8 wissenschaftlich & Projekte inaktiv schaltbar (2026-07)

### PDF-Bericht: Kapitel 8 neu strukturiert
- Ausführliche Beschreibung der Ausschreibungshistorie (Mechanismus,
  beide Regime, Zahlenverlauf, Literaturbezug), danach Abb. 14
  (historische Werte).
- Neuer Abschnitt "Anpassung der Verteilungsfunktionen": textliche
  Erklärung der Kalibrierung aus den Aggregaten (inkl. latenter
  Wettbewerbsquote) plus Abb. 15 mit den geschätzten Verteilungen
  aller 15 Runden (Farbverlauf alt→neu, unterzeichnete gestrichelt).
- Modellbeschreibung mit allen mathematischen Formeln in
  LaTeX-Schreibweise (Matplotlib-Mathtext, sauber gesetzt):
  gespiegelte Inverse-Gamma-Dichte, Kalibrierbedingungen und latentes
  r, Differenzenextrapolation (Rekursion), trunkierte
  Grenzzuschlag-Verteilung, P(Zuschlag | Gebot), b(z) sowie die
  Dichte der Zuschlagswerte.
- Beide Prognose-Plots wie im Tool: Abb. 16 (Verteilung der
  Zuschlagswerte mit P10–P90-Band und Projektwert) und Abb. 17
  (Wert ↔ Zuschlagswahrscheinlichkeit mit Einordnung des
  Projektwerts), danach die Empfehlungstabelle.

### Projekte: löschen & inaktiv schalten
- Löschen (mit Bestätigungsdialog) existiert im Projekt-Dashboard
  neben Duplizieren.
- Neu: Projekte lassen sich **inaktiv schalten** (Button im Dashboard,
  jederzeit reaktivierbar, YAML-persistiert). Inaktive Projekte
  erscheinen als **grau hinterlegte Karten** mit "Inaktiv"-Badge,
  werden aus Rendite-Risiko-Landkarte, Ranking und Vergleichstabelle
  ausgeblendet und sind standardmäßig aus den kumulierten
  Portfolio-KPIs herausgerechnet (Schalter "in Portfolio-KPIs
  berücksichtigen" holt sie optional zurück) – Pipeline-Bereinigung
  ohne Löschen.
- Excel-Export/-Import um die Spalte "aktiv" erweitert (optional,
  ältere Dateien bleiben importierbar). 2 neue Tests; Suite: 128.

## v4.4 – Kosteninflation auf alle Kostenpositionen (2026-07)

- Behoben: Die Inflation wirkte bisher nur auf die Marktwerte und drei
  OPEX-Positionen (dort erst ab Jahr 10). NICHT indexiert waren Pacht,
  Gemeindeabgabe, Direktvermarktungskosten (absoluter Modus) sowie
  zwei OPEX-Positionen.
- Neuer globaler Parameter **Kosteninflation (%/Jahr)**, Standard 2,0 %
  (Globale Annahmen, neben der Marktwert-Inflation): eskaliert Pacht,
  Gemeindeabgabe und Direktvermarktungskosten (absolut) ab dem
  2. Betriebsjahr – Eingaben verstehen sich als Preisstand bei
  Inbetriebnahme (Betriebsjahr 1 = Basis, konsistent zur bestehenden
  OPEX-Indexierung). Direktvermarktung im Relativ-Modus folgt weiterhin
  dem nominalen Marktwert (keine Doppelzählung, per Test gesichert).
- Standard-OPEX-Positionen vereinheitlicht: alle fünf Positionen jetzt
  2 %/Jahr ab Jahr 1 (vorher drei ab Jahr 10, zwei ohne Index). Die
  Indexierung bleibt je Position im Editor einstellbar.
- Wirkung: Template Agri IRR 14,84 % → 13,80 %. Excel-Export/-Import
  um den Parameter erweitert (ältere Dateien laden mit 2 %-Default);
  PDF-Annex A weist die Kosteninflation aus. 5 neue Tests; Suite: 126.

## v4.3 – Prognosemethodik: rekursive Differenzenextrapolation (2026-07)

- Die Momentum-Formel ist vollständig durch die allgemeine
  Mehrfach-Differenzenextrapolation ersetzt: Rekursive Differenzen
  Δ⁽ᵏ⁾, höchste Ordnung bleibt konstant, niedrigere werden rekursiv um
  λₖ-gedämpfte höhere Ordnungen ergänzt, x̂(t+1) = x(t) + Δ̂⁽¹⁾. Das
  Verfahren berücksichtigt damit Trend UND Trendänderung: Halbiert
  sich der Rückgang je Runde (−40 → −20 → −10), erwartet es mit
  λ = 0,5 den nächsten Schritt bei −5 statt −10.
- Parametrierbar auf der Seite: maximale Differenzenordnung (1–3,
  Standard 2; effektiv durch verfügbare Wettbewerbsrunden begrenzt)
  und alle Dämpfungsparameter λₖ ∈ [0, 1] (Standard 1; λ = 0
  entspricht der jeweils niedrigeren Ordnung – per Test und E2E
  verifiziert).
- Anwendung getrennt auf Grenzzuschlag und Ø-Zuschlag; das Minimum
  wird unverändert fortgeschrieben (keine stabile Dynamik in der
  Historie). Anschließend Projektion auf Minimum ≤ Ø ≤ Grenzzuschlag <
  Preisobergrenze. Standardwerte auf den aktuellen Daten (Ordnung 2,
  λ = 1): Grenzzuschlag 6,96 ct, Ø 6,91 ct (projiziert).
- Backtest je Runde mit ausgewiesener effektiver Ordnung; Ø-Prognose
  06/2026: 6,43 vs. Ist 6,40 ct. PDF-Kapitel 8 und alle Hilfetexte auf
  die neue Methodik umgestellt. Suite: 121 Tests.

## v4.2 – Zwei Zuschlagswert-Modi, Momentum-Prognose & PDF-Kapitel (2026-07)

### Zwei Modi (Seite "Ausschreibung" und Monte-Carlo-Tab)
- **Letzte Ausschreibung (gesetzt):** Die gefittete Zuschlagswert-
  Verteilung der letzten Runde gilt unverändert; die Risikoneigung
  (50–95 %) wählt das Quantil der Zuschlagswerte (hohe
  Wahrscheinlichkeit = konservativ niedriger Wert).
- **Prognosemodell (nächste Ausschreibung):** Momentum-Punktprognose je
  Stützstelle: x(t+1) = x(t) + Δt·(Δt − Δt−1) für Grenzzuschlag
  (6,69 → 6,65 ct) und Ø-Zuschlag (6,40 → 6,44 ct) über die
  Wettbewerbsrunden; daraus wird die neue Verteilung gebaut
  (Ø-Bedingung stark gewichtet, letztes Minimum als weicher
  Tail-Anker, Abschneiden am prognostizierten Grenzzuschlag). Die
  Wettbewerbsquote ist impliziert (r = 1/F(max)) und wird ausgewiesen;
  Grenzzuschlag-Unsicherheit als an der Obergrenze trunkierte
  Normalverteilung (± einstellbar, Vorbelegung = Streuung der
  historischen Rundenänderungen). Formel samt eingesetzten
  Stützstellen im Expander dokumentiert.
- **Harte Überschreibung:** Auf der Seite lässt sich der Zuschlagswert
  jederzeit manuell setzen – der überschriebene Wert speist Session-
  Vorbelegung, Übernehmen-Button und KPI-Zeile. Im Monte-Carlo-Tab ist
  der feste Projektwert (Schalter aus) die harte Überschreibung; bei
  aktivierter Ziehung ist die Grundlage wählbar (letzte Runde /
  Prognosemodell).
- Backtest auf die Momentum-Formel umgestellt (nur 06/2026 mit drei
  Stützstellen prüfbar: Prognose 6,46 vs. Ist 6,69; Methode je Zeile
  ausgewiesen).

### PDF-Bericht
- Neues Kapitel 8 "EAG-Ausschreibungsmodell": Historie aller Runden
  (Min/Ø/Max, Preisobergrenze, markierte Wettbewerbsphase),
  prognostizierte Zuschlagswert-Verteilung mit P10–P90-Band und
  Einordnung des angesetzten Projektwerts (inkl. dessen
  Zuschlagswahrscheinlichkeit), Momentum-Formel mit eingesetzten
  Stützstellen sowie Empfehlungstabelle je Zielwahrscheinlichkeit.
- Suite: 120 Tests.

## v4.1 – Ausschreibungsmodul: Verankerung an der letzten Runde & korrigierte Dichteform (2026-07)

### Prognose grundlegend überarbeitet
- Die Prognose ist jetzt an der LETZTEN Ausschreibung verankert (lokales
  Random-Walk-Modell): Die zentrale Prognosewelt entspricht exakt der
  Verteilung der letzten Runde, nur um Wettbewerbsquote und
  Preisobergrenze angepasst; die Unsicherheit stammt aus den
  beobachteten Änderungen zwischen den Wettbewerbsrunden. Die frühere
  Level-Regression über alle 15 Runden war vom alten, unterzeichneten
  Regime dominiert und schätzte den nächsten Grenzzuschlag unplausibel
  hoch.
- Bei erwarteter Überzeichnung (r > 1) werden Unterzeichnungs-Welten
  ausgeschlossen (links trunkierte Lognormal-Ziehung von r): Der
  prognostizierte Grenzzuschlag fällt nie mit der Preisobergrenze
  zusammen (P = 0 %; vorher fälschlich spürbare Cap-Masse).
- Median-Grenzzuschlag jetzt ≈ letzter Ist-Wert (6,78 vs. 6,69 ct);
  Ein-Schritt-Backtest schlägt die naive Fortschreibung (RMSE 0,60 vs.
  0,69 ct; im stabilen Regime ab 2026: 0,23 vs. 0,36 ct).

### Verteilungsform
- Neue Familie "Gespiegelte Inverse Gamma" (an der Y-Achse gespiegelte,
  an die Obergrenze verschobene Inverse-Gamma-Verteilung) als
  Standardfamilie: beste Anpassung an die Wettbewerbsrunden (Fit-RMSE
  0,15 vs. 0,21 Beta) und strukturell exakt die erwartete Form – Dichte
  an der Obergrenze null, steiler rechter Abfall, langsam auslaufender
  linker Rand.
- Angezeigt wird die Dichte der ZUSCHLAGSWERTE (erfolgreiche Gebote, am
  Grenzzuschlag der zentralen Welt abgeschnitten – das ist die
  Verteilung, die die OeMAG-Aggregate beschreiben) plus gestrichelt die
  Verteilung aller Gebote und das P10–P90-Band des Grenzzuschlags.
- Neue Sektion mit den GESCHÄTZTEN VERTEILUNGEN ALLER HISTORISCHEN
  RUNDEN (Dichte- und Verteilungsfunktions-Tab, Farbverlauf alt→neu):
  sichtbarer Regimewechsel von Cap-Klumpung zu linksverschobenen,
  verdichteten Verteilungen.
- 4 neue Tests (Verankerung, keine Cap-Masse, Dichteform,
  Backtest-Überlegenheit im stabilen Regime); Suite: 119 Tests.

## v4.0 – EAG-Ausschreibungsmodul: Gebotsverteilung & Zuschlagswahrscheinlichkeit (2026-07)

### Neues Modul (Price-Taker-Modell)
- Neue Seite **"Ausschreibung"**: Analyse aller 15 historischen
  EAG-Marktprämienausschreibungen PV (2022–2026, `data/ausschreibungen.yaml`
  aus EAG.xlsx), Prognose der Gebotsverteilung der nächsten Runde und
  Ableitung des empfohlenen Gebots je gewünschter
  Zuschlagswahrscheinlichkeit (50–95 %).
- Statistischer Kern (`engine/auktion.py`): Je Runde wird eine auf
  [0, Preisobergrenze] beschränkte **Beta-Verteilung** über zwei
  Bedingungen kalibriert (mengengewichteter Ø-Zuschlag; Minimum als
  2 %-Quantil). Modellvergleich gegen Kumaraswamy und trunkierte
  Normalverteilung; Leave-one-out-Validierung über die vier
  Wettbewerbsrunden inkl. naiver Basislinie.
- Wettbewerbs-Link datengetrieben: logit(Lage) und ln(Konzentration)
  linear auf ln(Wettbewerbsquote r) regressiert; für überzeichnete
  Runden ist r latent (Gebotsvolumen wird von der OeMAG nicht
  veröffentlicht) und wird aus dem Abstand Grenzzuschlag ↔ Obergrenze
  rückgeschätzt.
- Prognose: 4.000 Auktionswelten (r ~ Lognormal, Residuen-Bootstrap)
  liefern die prädiktive Verteilung des Grenzzuschlags;
  P(Zuschlag | Gebot) = P(Grenzzuschlag > Gebot); Empfehlung =
  (1−Ziel)-Quantil.

### Integration ins Cashflow-Modell
- Der empfohlene Gebotswert wird neuen Projekten automatisch als
  EAG-Zuschlagswert vorbelegt (manuell überschreibbar) und kann per
  Button in ein bestehendes Projekt übernommen werden.
- Monte-Carlo-Tab: neuer Schalter "EAG-Zuschlagswert aus dem
  Ausschreibungsmodell ziehen" – je Lauf wird ein zufälliges
  erfolgreiches Gebot der prognostizierten Auktion gezogen
  (`run_monte_carlo(..., gebot_ziehungen=...)`); der
  Konventionell-Abschlag bleibt erhalten. Alle übrigen Funktionen des
  Cashflow-Modells sind unverändert.
- 17 neue Tests (Regime, Kalibrierbedingungen, Verteilungs-
  eigenschaften, Link-Richtungen, Monotonie, Reproduzierbarkeit,
  MC-Integration); Suite: 115 Tests.

## v3.9 – Bugfix: Download-Dateiname nach Umbenennen (2026-07)

- Behoben: Nach Duplizieren und Umbenennen eines Projekts zeigte der
  PDF- und Excel-Download-Dateiname weiterhin den ursprünglichen Namen
  (z.B. "template-agri_bericht.pdf"), obwohl Berichtstitel und
  Projektname im Dashboard bereits korrekt aktualisiert waren.
- Ursache: Die interne Projekt-ID (Dateiname der YAML-Datei) wird bei
  Anlage/Duplizierung einmalig aus dem Namen abgeleitet und bleibt
  danach bewusst stabil, damit Umbenennen nicht versehentlich die Datei
  wechselt. Die Download-Dateinamen folgten fälschlich dieser
  eingefrorenen ID statt dem aktuellen Namen.
- Fix: PDF- und Excel-Download-Dateinamen werden jetzt bei jedem
  Download frisch aus dem aktuellen Projektnamen abgeleitet
  (`services.slugify()`); die interne ID/Dateiidentität bleibt
  unverändert stabil. 2 neue Tests; Suite: 98 Tests.

## v3.8 – PDF-Ergebnisbericht (2026-07)

- Neuer Button "PDF-Bericht erstellen" im Projekt-Dashboard: erzeugt
  einen herunterladbaren Ergebnisbericht im Gutachtenstil (A4,
  Trianel-Branding, Kopf-/Fußzeilen mit Seitenzahlen, ca. 15 Seiten).
- Aufbau: Deckblatt mit Logo, Projektsteckbrief und Disclaimer ·
  Inhaltsverzeichnis · Management Summary mit KPI-Kacheln und
  Kernaussagen · Ergebnisrechnung (Wertbrücke, Cashflow-Tabelle) ·
  Erlöse & Förderung (Vergütungssatz/Marktwert, Markterlös vs. Prämie) ·
  Finanzierung (DSCR, Schuldenprofil, Kapital-/Investitionsstruktur,
  NPV-Kurve) · Sensitivität (Tornado, EAG-Varianten, Break-even-Gebot) ·
  Risikoanalyse (Monte Carlo, 400 Läufe mit dokumentierten
  Standardparametern) · Szenarienvergleich · Annex A (vollständig
  aufgelöste Annahmen, OPEX- und CAPEX-Positionen) · Annex B (alle
  verwendeten Zeitreihen: Marktwerte real/nominal, Erzeugungsmengen
  6h/1h, Marktwertübersicht aller Szenarien).
- NPV, LCOE und MC-NPV im Bericht folgen dem im Dashboard gewählten
  Diskontsatz; Zielrendite für Break-even und Erfolgswahrscheinlichkeit:
  8,0 %. Diagramme als hochauflösende Grafiken im Markenstil
  (druckfähig); Bericht wird beim Bearbeiten des Projekts automatisch
  invalidiert.
- Technik: reiner Generator ohne Streamlit-Abhängigkeit
  (app/report.py, ReportLab + Matplotlib – neue Abhängigkeiten in
  requirements.txt); 3 neue Tests (Struktur, Kapitel, Metadaten);
  Suite: 96 Tests.

## v3.7 – Investkosten: Widmung & Genehmigung (2026-07)

- Zwei neue Positionen in den Investkosten (Details), direkt nach der
  Trasse: **Widmung** (Vorbelegung 1 €/kWp bzw. 10.000 € im
  Absolut-Modus) und **Genehmigung** (8 €/kWp bzw. 80.000 €). Die
  Vorbelegung folgt damit erstmals der gewählten Eingabe-Einheit statt
  aus dem Absolutwert abgeleitet zu werden.
- Beide Positionen fließen in CAPEX-Summe, Finanzierung, KPI-Kachel und
  den Investitionsstruktur-Donut ein und sind Teil des
  Excel-Roundtrips (ältere Projekt-Exporte ohne die Spalten laden mit
  0 €).
- Bestehende Projekte bleiben unverändert (beide Positionen 0 €).

## v3.6 – Szenario-Reihenfolge & EAG-Default (2026-07)

- Szenario-Reihenfolge: alle Aurora-Szenarien zuerst (Aurora 6/26 bleibt
  Standard-Vorauswahl), Enervis 2025 ans Ende – gilt für Szenario-Tabs,
  Projektauswahl und Excel-Export.
- EAG-Zuschlagswert: Vorbelegung für neue Projekte jetzt 6,5 ct/kWh
  (vorher 7,2); die beiden Template-Projekte wurden ebenfalls auf
  6,5 ct/kWh gesetzt. Bestehende eigene Projekte bleiben unverändert.

## v3.5 – Negativmengen je Regel (6h/1h) & Aurora 6/26 (2026-07)

### Fachlich
- Die Größe heißt jetzt korrekt **"Erzeugungsmenge neg. Stunden"**: der
  Anteil der PV-Jahreserzeugung, der in Zeiten negativer Preise anfällt
  (nicht der Stundenanteil).
- Jedes Marktpreisszenario führt zwei getrennte Zeitreihen: **6h-Regel**
  (Prämienentfall erst ab mindestens 6 Stunden am Stück negativer
  Preise; Standard Österreich/EAG) und **1h-Regel** (bereits ab 1 Stunde
  am Stück; Regelung Deutschland). Global wählbar unter Globale
  Annahmen → Marktpreisszenarien; Standard: 6h.
- Neues Standardszenario **Aurora 6/26** (Marktwerte und getrennte
  6h/1h-Negativmengen 2027–2060 aus der Marktpreisstudie; 2025/2026 mit
  den 2027-Werten aufgefüllt). Es steht an erster Stelle und ist damit
  die Vorauswahl für neue Projekte; bestehende Projekte behalten ihr
  zugewiesenes Szenario.
- Bestehende Szenarien: die bisherige (einzelne) Zeitreihe wurde in
  beide Regel-Spalten übernommen.

### Kompatibilität
- Ältere YAML-Datenstände und Excel-Importe mit nur einer
  Negativ-Spalte ("Anteil neg. Stunden (%)") laden weiter: der Wert
  wird automatisch für beide Regeln übernommen.
- Excel-Export der Globalen Annahmen enthält jetzt beide Spalten sowie
  die gewählte Regel; der aufgelöste Parametersatz im Annahmen-Tab
  weist die Regel aus.
- 7 neue Tests (Regelwirkung auf Erlöse/IRR, exakte Kurvenwahl,
  Legacy-Migration, Excel-Roundtrip, Aurora-6/26-Stützwerte); Suite:
  90 Tests.

## v3.4 – Kompaktere Übersicht (2026-07)

- KPI-Kachel "Investitionsvolumen" heißt jetzt "CAPEX"; die Leiste zeigt
  damit exakt: EK-Rendite, NPV, Min. DSCR, CAPEX, LCOE.
- Portfolio-Analytik (Rendite-Risiko-Landkarte, Ranking,
  Vergleichstabelle) liegt jetzt in einem zuklappbaren Bereich
  (Standard: eingeklappt) – die Pipelineübersicht startet kompakt.
- Hinweis: Cashflow-Sparkline und Payback waren bereits seit v3.2 aus
  den Projektkarten entfernt.

## v3.3 – Trianel-Rot erzwingen (2026-07)

- Ursache des hellen Streamlit-Rots (#FF4B4B): .streamlit/config.toml
  wird von Streamlit nur gelesen, wenn die App aus dem Projektordner
  gestartet wird. Die Theme-Optionen (primaryColor #BE172B, Inter als
  Fließ- und Überschriftenschrift) werden jetzt zusätzlich zur Laufzeit
  im Einstiegspunkt gesetzt und gelten damit unabhängig vom
  Startverzeichnis.
- CSS-Fallback für die sichtbarsten Akzentflächen (Primary-Buttons,
  Button-Hover/-Fokus, Tab-Akzentlinie, Slider-Griff und -Wertlabel,
  Links), damit auch der allererste Seitenaufbau nie im Standard-Rot
  erscheint.

## v3.2 – Aufgeräumte Kennzahlen & Direktvermarktungs-Modus (2026-07)

### Direktvermarktungskosten: absolut oder relativ zum Marktwert
- Neuer globaler Modus (Globale Annahmen → Betriebskosten): **Absoluter
  Betrag** (wie bisher, projektspezifisch in €/MWh, z.B. 1 €/MWh) oder
  **Relativ zum Marktwert** (globaler Prozentsatz, z.B. 10 % vom
  nominalen Jahresmarktwert je erzeugter kWh – die Kosten atmen mit dem
  Preisniveau).
- Im Relativ-Modus blendet das Projektformular die €/MWh-Eingabe aus und
  zeigt stattdessen den wirksamen Prozentsatz; der gespeicherte
  Projektwert bleibt für einen späteren Moduswechsel erhalten.
- Modus und Prozentsatz sind Teil des YAML- und Excel-Roundtrips
  (bestehende Dateien laden unverändert mit Modus "absolut").
- Fünf neue Tests (exakte Jahresformel, Unverändertheit des
  Absolut-Modus, IRR-Wirkung, YAML- und Excel-Roundtrip).

### Aufgeräumte Kennzahlen
- Projekt-Dashboard: eine KPI-Leiste mit EK-Rendite, NPV, min. DSCR,
  Investitionsvolumen und LCOE; entfernt: Payback, Eigenkapitaleinsatz,
  spezifisches Invest, Erzeugung Jahr 1, Erlöse gesamt.
- Projektkarten im Portfolio: ohne Cashflow-Sparkline und ohne Payback
  (Name, Typ-Badge, Leistung, IBN, EK-Rendite, EK-Einsatz).
- Letztes verbliebenes Icon im Projektformular entfernt.

## v3.1 – Design-Korrekturen (2026-07)

- Zurück zu Trianel-Rot als einzigem Markenakzent: Kopfzeilen-Band und
  KPI-Kachel-Akzent wieder in Rot statt Farbverlauf; Bernstein-Töne aus
  allen Diagrammen entfernt (Erlös-Split grün/neutral, Monte-Carlo-Fächer
  in Ink-Tönung, Heatmap rot/neutral/grün).
- Schriftart durchgängig Inter (fixiert über .streamlit/config.toml,
  primaryColor #BE172B); Space Grotesk entfernt.
- Tabs wieder im Streamlit-Standard (Akzentlinie in primaryColor) statt
  dunkel hinterlegter Pills.
- Abschnittstitel ohne Marker; sämtliche Icons/Emojis aus Navigation,
  Tabs, Buttons und Hinweistexten entfernt (Trianel-Logo/-Favicon bleibt).
- Standard-Zielrendite in Heatmap, Gebotsassistent und Monte-Carlo-
  Erfolgswahrscheinlichkeit: 8,0 %.

## v3.0 – Analyse-Studio & Sonnenband-Design (2026-07)

### Neue Fachfunktionen (engine/analytics.py)
- **Monte-Carlo-Simulation**: gleichzeitige Variation von Ertrag,
  Marktwert-Niveau, CAPEX und OPEX (Normalverteilung, einstellbare
  Sigmas, fester Seed, 200–1000 Läufe). Ergebnisse: IRR-Verteilung
  (P10/P50/P90), NPV-Verteilung, Erfolgswahrscheinlichkeit gegen eine
  Ziel-Rendite, P10–P90-Fächer des kumulierten Equity-Cashflows.
- **Tornado-Analyse**: Einzelvariation von sieben Werttreibern (±10 %)
  mit Wirkung auf die EK-Rendite, sortiert nach Spannweite.
- **IRR-Heatmap**: EK-Rendite über ein 7×7-Raster zweier frei wählbarer
  Treiber, divergierende Farbskala um die Ziel-IRR.
- **Gebotsassistent**: Break-even-EAG-Zuschlagswert (anzulegender Wert)
  für eine Ziel-EK-Rendite – Untergrenze für ein Auktionsgebot
  (Nullstellensuche per brentq, defensiv bei nicht berechenbarer IRR).
- **LCOE**: Stromgestehungskosten (diskontierte Vollkosten je
  diskontierter kWh, Act/365 analog XNPV).
- **Szenarienvergleich**: identisches Projekt über alle hinterlegten
  Marktpreisszenarien (IRR, NPV, kumulierte Cashflows).
- Erlös-Zeitreihe zusätzlich exakt aufgeteilt in **Markterlös** und
  **Marktprämie** (beide Negativstunden-Modi); `produktion_kwh` ist
  jetzt Teil der Cashflow-Zeitreihe (auch im Excel-Export).
- `run_valuation_from_assumptions()`: Bewertung direkt aus einem (ggf.
  mutierten) EffectiveAssumptions-Satz, optional ohne NPV-Kurve –
  Grundlage für die vielen Bewertungsläufe der Analytik.

### Neue UI
- **Projekt-Dashboard mit 7 Tabs**: Cashflow (inkl. Wertbrücke/
  Waterfall), Erlöse (Vergütungssatz vs. Marktwert, Markterlös vs.
  Prämie), Finanzierung (DSCR, Schuldenprofil, Kapital-/CAPEX-Donuts,
  NPV-Kurve), Sensitivität (Tornado, Heatmap, Gebotsassistent,
  EAG-Varianten), Monte Carlo (mit explizitem Start-Button, da Tabs
  eager rendern), Szenarien, Annahmen.
- **Zweite KPI-Leiste**: Payback, LCOE, spezifisches Invest,
  Erzeugung Jahr 1, Erlöse gesamt.
- **Portfolio-Analytik**: Rendite-Risiko-Landkarte (Bubble-Chart),
  Projekt-Ranking, Vergleichstabelle als Tabs; Projektkarten mit
  Cashflow-**Sparkline** (inline SVG), Typ-Badge und
  Auswahl-Hervorhebung.

### Design ("Sonnenband")
- Neue Dreiklang-Palette: Trianel-Rot (Interaktion), Solar-Bernstein
  (Erzeugung/Erlöse), Tannengrün-Ink (Finanzen/Struktur); Signatur-
  Verlaufband in Kopfzeile und KPI-Kacheln.
- Display-Schrift Space Grotesk (Überschriften, KPI-Werte, tabellarische
  Ziffern), Pill-Tabs, Hover-Mikrointeraktionen (mit
  prefers-reduced-motion-Fallback), Hero-Kopfzeile mit Untertitel.
- Plotly-Template v2: einheitliche Serienfarben, x-unified-Hover in
  Zeitreihen, divergierende Heatmap-Skala.

### Qualität
- 18 neue Tests (Analytik-Engine, Erlös-Split, Reproduzierbarkeit der
  Monte-Carlo-Simulation, Break-even-Zielerreichung, LCOE-Monotonie);
  Suite: 78 Tests, ruff clean.
- Analytik-Ergebnisse werden wie Bewertungen auf Datei-mtimes und
  Parameter gecacht und bei jedem Speichern/Löschen invalidiert.


## 2.2.0 – Neue Standards und Branding

- **Negativstunden-Modus**: „Rückfall auf Jahresmarktwert" ist jetzt der
  Standard und steht in der Auswahl an erster Stelle; „Abregelung"
  bleibt als Option erhalten. Die Engine-Einheitstests rechnen weiterhin
  explizit mit Abregelung (härteste Annahme, handgerechnete Werte).
- **Standard-Diskontsatz 8 %**: gilt konsistent für die NPV-KPI-Kachel
  (Voreinstellung des Eingabefelds), die KPI-Berechnung der Engine, die
  Portfoliotabelle („NPV bei 8 %") und den Excel-Export.
- **Logo/Favicon**: neues Trianel-Logo im Kopfbereich; für den
  Browser-Tab wird eine automatisch beschnittene, quadratische
  Logovariante erzeugt (assets/favicon.png), damit das Logo im Tab
  nicht in Leerfläche verschwindet.
- `st.components.v1.html` durch `st.iframe` ersetzt (Streamlit-
  Deprecation ab 06/2026); ausgelieferte global_assumptions.yaml
  enthält die neuen Felder jetzt explizit.

## 2.1.0 – Konfigurierbare Modelloptionen, KPI-Auto-Fit, NPV-Diskontsatz

Validiert gegen das Referenz-Excel „Tool_TEA_Buchkirchen.xlsm" (Blatt
Silber): Mit aktiviertem tilgungsfreiem Anlaufjahr und Marktwert-Modus
reproduziert die Engine dessen Zinsreihe auf den Cent und die Equity-IRR
bis auf 0,14 Prozentpunkte (Rest: dokumentierte Konventionsunterschiede).

### Engine
- **Negativstunden-Modus** (Globale Annahmen, umschaltbar):
  „Abregelung" – Erlöse entfallen für den Anteil negativer Stunden
  vollständig (bisheriges Verhalten, Standard) – oder „Rückfall auf
  Jahresmarktwert" – die Anlage speist weiter ein, nur die Marktprämie
  entfällt. Nach der Förderdauer wirkt nur noch der Abregelungs-Modus.
- **Tilgungsfreies Anlaufjahr** (On/Off in den Kreditoptionen): Jahr 1
  nur Zinsen, Tilgung ab Jahr 2 bei unveränderter Ratenzahl; dadurch
  fällt auch im zweiten Jahr der Zins noch auf die volle Kreditsumme an.
- Neuer Helfer `engine.kpis.npv_at()`: exakter XNPV für beliebige
  Diskontsätze (keine Interpolation zwischen Kurvenpunkten nötig).
- Gemeindeabgabe: Regressionstest ergänzt, der absichert, dass die
  Abgabe (z.B. 2 €/MWh) in **jedem** Jahr der gesamten Betriebsdauer auf
  die Produktion gezahlt wird – das war bereits das Verhalten der Engine.
- Beide neuen Optionen in YAML- und Excel-IO (Blatt „Einstellungen":
  `negative_stunden_modus`, `tilgungsfreies_anlaufjahr` als JA/NEIN).

### Oberfläche
- **KPI-Kacheln mit dynamischer Schriftgröße**: Lange Werte werden nicht
  mehr abgeschnitten. Ein Skript misst die Wertbreiten und verkleinert
  die Schrift – pro Kachelgruppe (5 Projekt-KPIs bzw. Portfolio-Zeile)
  mit EINEM gemeinsamen Faktor, damit alle Kacheln identisch aussehen.
  Die bisherige Größe ist als Maximum fixiert; Reaktion auf
  Fenstergröße und Font-Laden inklusive.
- **NPV-Diskontsatz einstellbar** (0–10 %, Eingabefeld direkt über der
  KPI-Leiste): Die NPV-Kachel rechnet exakt zum eingegebenen Satz
  (XNPV) statt zu interpolieren; die Einstellung gilt app-weit, damit
  Projekte zum selben Satz verglichen werden.
- Neue Schalter in den Globalen Annahmen (Negativstunden-Modus als
  Auswahl mit Erklärtexten, tilgungsfreies Anlaufjahr als Toggle);
  beide erscheinen auch im „Annahmen"-Tab jedes Projekt-Dashboards.
- `.streamlit/config.toml`: Inter als App-Schriftart (Theme-Konfiguration).

### Tests
- 14 neue Tests (60 gesamt): Gemeindeabgabe-Regression, tilgungsfreies
  Anlaufjahr (Zinsstruktur, vollständige Tilgung, IRR-Wirkung),
  Negativstunden-Modi inkl. Äquivalenz zur Spread-Formel des
  Referenz-Excels, `npv_at`-Konsistenz mit KPI und NPV-Kurve,
  IO-Roundtrips der neuen Felder, aktualisierte UI-Smoke-Tests
  (KPI-Kacheln, NPV-Eingabe wirkt auf die Kachelbeschriftung).

## 2.0.0 – Restrukturierung zu einer Programm-Bibliothek

Fachlich identische Ergebnisse (alle Berechnungen numerisch unverändert),
aber vollständig neue Struktur, Qualitätssicherung und Oberfläche.

### Architektur
- Der 1.200-Zeilen-Monolith `streamlit_app.py` wurde in eine
  UI-Schicht (`app/`) mit Views, Komponenten, Services, Theme und
  Formatierung zerlegt; der Entry-Point enthält nur noch Konfiguration
  und Navigation.
- Neue Service-Schicht (`app/services.py`) als einzige Brücke zwischen
  UI und Engine – inkl. Bewertungs-Cache auf Datei-mtimes: Die
  Portfolioseite rechnet Projekte nur noch bei tatsächlichen Änderungen
  neu statt bei jedem Streamlit-Rerun.
- `engine/__init__.py` definiert jetzt die vollständige öffentliche API
  (inkl. `MarktpreisSzenario`, `CashflowTimeseries`).

### Qualitätssicherung (neu)
- 46 Tests: Engine-Einheitstests mit handgerechneten Erwartungswerten
  (EAG-Prämienlogik, Verlustvortrag-Verrechnungsgrenze, Annuität/linear,
  Indexierung, Clamping), End-to-End-Pipeline, YAML-/Excel-Roundtrips,
  Formatierung/Slugs sowie UI-Smoke-Tests (Streamlit AppTest).
- `pyproject.toml` mit Projektmetadaten, Ruff- und Pytest-Konfiguration;
  GitHub-Actions-CI (Lint + Tests auf Python 3.11/3.12); Makefile.
- Ruff-sauber (u.a. `zip(..., strict=...)` durchgängig).

### Engine
- Robustere XIRR-Suche: Das Suchintervall wird schrittweise erweitert
  (10 → 100 → 1000), statt bei extremen Cashflows `None` zu liefern.
- Neue Kennzahl `eigenkapital_eur` (EK-Einsatz im Jahr 0) in `KPIs`.

### Usability
- Projekte können jetzt **dupliziert** und (mit Bestätigung)
  **gelöscht** werden; Projekt-IDs entstehen per Slugify mit
  Umlaut-Transliteration und Kollisions-Laufnummern statt naivem
  `lower().replace(" ", "-")`.
- **Cashflow-Export als Excel** direkt aus dem Projekt-Dashboard
  (Blätter „Cashflow" + „KPIs").
- Portfolioseite mit aggregierten Kennzahlen (Leistung,
  Investitionsvolumen, Ø EK-Rendite) und sortierbarer
  Vergleichstabelle inkl. spezifischer Investkosten (€/kWp).
- Neuer Dashboard-Tab **„Annahmen"**: der vollständig aufgelöste
  Parametersatz jeder Berechnung (Transparenz/Nachvollziehbarkeit).
- Cashflow-Übersichtstabelle mit sprechenden deutschen Spaltentiteln.

### Oberfläche
- Design-Token-System (`app/theme.py`): eine Farbquelle für CSS und
  Diagramme, Trianel-Rot als Akzent, KPI-Kacheln mit Markenkante,
  Karten-Hover, Header-Linie.
- Zentrales Plotly-Template: einheitliche Typografie, Legenden, Margins
  und **deutsche Zahlenformate auch in Achsen und Hovern**
  (`separators=",."`).
- Durchgängig deutsche Zahlenformatierung in der gesamten App
  (`app/formatting.py`): `7,43 %`, `1.234.567 €`, `1,25x` – statt
  gemischter US-/DE-Formate und `str.replace`-Hacks.

### Entfernt/ersetzt
- Direkte YAML-/Pfad-Zugriffe aus der UI (jetzt ausschließlich über
  Services), globales `st.cache_data.clear()` (jetzt gezielte
  Cache-Invalidierung).
