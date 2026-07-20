# Sprachdateien (locales/)

Alle sichtbaren Texte der Anwendung liegen hier als YAML, aufgeteilt
nach Textgattung – nicht in einer einzigen riesigen Datei, damit
verschiedene Änderungen sich nicht in die Quere kommen (z. B. jemand
tippt UI-Buttons um, während jemand anders am PDF-Berichtstext
schreibt) und damit die Dateien überschaubar bleiben. Vier Sprachen
sind vollständig gepflegt: **Deutsch (de), Englisch (en), Französisch
(fr), Spanisch (es)** – umschaltbar über das Dropdown oben rechts in
der App.

| Datei              | Inhalt                                                              | Konsumiert von            |
|--------------------|----------------------------------------------------------------------|----------------------------|
| `oberflaeche.yaml` | Navigation, Buttons, Badges, Abschnittstitel, Hinweistexte der Views | `app/` (Streamlit-Views)   |
| `diagramme.yaml`   | Diagrammtitel, Achsenbeschriftungen, Legendennamen, Annotationen     | `app/components/charts.py` |
| `bericht.yaml`     | Kapitel-/Abschnittsüberschriften des PDF-Berichts                    | `app/report.py`            |
| `excel.yaml`       | Blatt-/Spalten-/Diagrammbeschriftungen des Pipeline-Excel-Exports    | `engine/io_ergebnis_excel.py` |

## Verwendung im Code

```python
from texte import txt

st.button(txt("oberflaeche.btn_loeschen"))
txt("oberflaeche.portfolio_toggle_inaktive", anzahl=3)  # Platzhalter {anzahl}
```

In der Engine-Schicht (kein Streamlit, kein Import aus `app/`) gibt es
den schlanken Wrapper `excel_texte()` bzw. das `_t(...)`-Hilfsfunktion
in `engine/io_ergebnis_excel.py`.

## Sprachumschaltung in der App

Oben rechts in der Kopfzeile öffnet ein Symbol (Weltkugel-Icon) ein
Popover mit den vier Sprachen – jede Zeile zeigt die echte
Flaggen-Grafik (`assets/flags/*.png`) neben dem Sprachnamen. Bewusst
kein `st.selectbox` mit Emoji-Flaggen: Emoji-Länderflaggen werden auf
etlichen Systemen (u. a. verbreitet unter Windows) und in manchen
Browsern gar nicht dargestellt, und `st.selectbox` kann ohnehin keine
Bilder in seinen Optionen zeigen, nur Text. Ein Klick auf eine Sprache
landet in `st.session_state["tea_sprache"]` (`texte.SESSION_KEY`) und
wirkt ab dem nächsten Rerun in der **gesamten** App: Navigation,
Sidebar (Sichern/Wiederherstellen), sämtliche Formulare, das komplette
Projekt-Dashboard, die Ausschreibungsseite, Globale Annahmen,
Diagramme sowie neu erzeugte PDF- und Excel-Exporte. Alle vier
Sprachen sind vollständig gepflegt – 696 Schlüssel je Sprache (382 UI-
Texte, 72 Diagrammtexte, 175 Berichtstexte inkl. der kompletten
PDF-Fließtexte aller Kapitel, 67 Excel-Beschriftungen), mit exakt
identischen Schlüsseln und Platzhaltern über alle vier Sprachen (per
Test bei jedem Lauf abgesichert, siehe `tests/test_texte.py`).

Außerhalb der laufenden App (Tests, Skripte, direkte Engine-Aufrufe
ohne Streamlit-Session) greift stattdessen die Umgebungsvariable
`NOBIS_SPRACHE` (Standard `de`).

## Eine weitere Sprache ergänzen

1. Ordner kopieren: `locales/de` → z. B. `locales/it`.
2. Werte in allen vier YAML-Dateien übersetzen (Schlüssel und
   `{platzhalter}` unverändert lassen).
3. Sprachcode in `texte.py` in der `SPRACHEN`-Registry ergänzen (Code,
   Anzeigename, Flaggen-Dateiname) und eine passende Flaggengrafik
   unter `assets/flags/<dateiname>.png` ablegen – erscheint danach
   automatisch im Popover.

Eine Übersetzung muss nicht sofort vollständig sein: Fehlt ein
Schlüssel in der Zielsprache, greift automatisch der deutsche Text;
fehlt er auch dort (Tippfehler o. Ä.), wird der Schlüsselname selbst
angezeigt statt eines Absturzes.

## Texte ändern/erweitern

Einfach den Wert in der passenden YAML-Datei bearbeiten – kein
Code-Deployment nötig, kein Python-Wissen erforderlich. Neue Texte
brauchen einen neuen, sprechenden Schlüssel (Konvention:
`bereich_beschreibung`, z. B. `btn_pdf_bericht`) und werden im Code per
`txt("<datei>.<schluessel>")` abgerufen. Texte mit eingesetzten
Kennzahlen (z. B. Bildunterschriften im PDF-Bericht) verwenden
`{platzhalter}` in der YAML-Datei und werden per
`txt("<schluessel>", platzhalter=wert)` aufgerufen – siehe
`bericht.yaml` (Kapitel 8) für ein durchgängiges Beispiel mit mehreren
Absätzen und dynamischen Werten (Rundenanzahl, Daten, Kennzahlen).

Damit sind sämtliche sichtbaren Texte der Anwendung ausgelagert – UI,
Diagramme, PDF-Bericht (inklusive der mehrsätzigen Fließtext-Absätze
in Kapitel 8) und der Excel-Ergebnisexport.
