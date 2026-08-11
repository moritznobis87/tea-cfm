% Mathematische Spezifikation der Projektbewertung und Gebotsanalyse

<!--
Einzige fachliche Quelle der Rechenweg-Dokumentation.

- Lesbar direkt im Repository; GitHub rendert die Markdown- und KaTeX-Formeln.
- `python docs/rechenmodell/build_pdf.py` erzeugt daraus
  `Rechenmodell.tex`, das Ablaufdiagramm `rechenweg.png` und das PDF
  `Rechenmodell.pdf` (alternativ: `make dokumentation`).
- Der PDF-Satz erfolgt mit Pandoc und XeLaTeX. Formeln bleiben dadurch
  Vektorgrafik und verwenden den vollständigen LaTeX-Mathematiksatz.
- Die Zahlen in Kapitel 13 erzeugt `docs/rechenmodell/beispiel.py`;
  `tests/test_dokumentation.py` hält sie mit der Engine synchron.

Formelsyntax: Verwendet wird die gemeinsame Teilmenge aus LaTeX und KaTeX.
Mehrzeilige Gleichungen dürfen `aligned` und Fallunterscheidungen `cases`
verwenden.
-->

# 1 Gegenstand, Geltungsbereich und Dokumentstruktur

## 1.1 Zielsetzung

Dieses Dokument enthält die **formale Spezifikation der im Cash-Flow-Model
implementierten Wirtschaftlichkeitsrechnung**. Sämtliche im Modell erzeugten
Größen werden durch ihre mathematische Definition, ihre Eingangsparameter und
ihre Stellung innerhalb der Berechnungsfolge beschrieben. Ziel ist eine
vollständige fachliche Nachvollziehbarkeit der Modellergebnisse unabhängig von
der konkreten Softwareimplementierung.

Die Darstellung ermöglicht insbesondere

- die Rekonstruktion des aufgelösten Parametersatzes aus projektbezogenen und
  globalen Eingaben (Kapitel 4),
- die unabhängige Reproduktion der Berechnungsschritte von der Periodisierung
  bis zu den Bewertungskennzahlen (Kapitel 5 bis 12),
- die numerische Plausibilisierung anhand eines vollständig spezifizierten
  Beispielprojekts (Kapitel 13),
- die methodische Einordnung der Sensitivitäts-, Risiko- und
  Break-even-Analysen (Kapitel 14),
- die Dokumentation des empirischen Modells der EAG-Ausschreibungen
  einschließlich Verteilungsannahmen, Parameterschätzung, Wettbewerbsmodell
  und Prognoseverfahren (Kapitel 15) sowie
- die Zuordnung der mathematischen Vorschriften zu Implementierung und Tests
  (Kapitel 18).

## 1.2 Sachliche Abgrenzung

Gegenstand des Dokuments ist ausschließlich die fachliche und mathematische
Rechenlogik. Die Softwarearchitektur wird in
[docs/ARCHITECTURE.md](../ARCHITECTURE.md), die Bedienung der Anwendung in der
[README](../../README.md) beschrieben. Steuer- und energierechtliche
Regelungen werden nur insoweit dargestellt, wie sie als explizite
Berechnungsvorschriften implementiert sind. Die Dokumentation stellt daher
keine rechtliche oder steuerliche Würdigung dar.

## 1.3 Aufbau und Darstellungskonventionen

Die Kapitel zu den einzelnen Rechenmodulen folgen einer einheitlichen
Struktur:

1. **Zielgröße** – Definition der im jeweiligen Modul ermittelten Größe.
2. **Eingangsgrößen** – erforderliche Parameter und Ergebnisse vorgelagerter
   Module.
3. **Berechnungsvorschrift** – mathematische Definition in der Reihenfolge der
   Implementierung.
4. **Methodische Erläuterung** – Begründung, Sonderfälle und Randbedingungen.
5. **Ausgangsgrößen** – erzeugte Variablen und Einheiten.
6. **Implementierungsreferenz** – zugehöriges Modul und zugehörige Funktion.

> Modellannahmen und bewusste Vereinfachungen werden an der jeweiligen
> Berechnungsstelle gekennzeichnet und in Kapitel 17 konsolidiert.

# 2 Mathematische Gesamtstruktur des Bewertungsmodells

## 2.1 Berechnungsarchitektur und Datenfluss

Die Projektbewertung ist als gerichteter Datenfluss organisiert. Jedes Modul
verwendet ausschließlich Eingangsparameter oder Ergebnisse vorgelagerter
Module. Algebraische Zirkelbezüge bestehen nicht. Eine zeitliche Rekursion
tritt lediglich bei zustandsabhängigen Größen auf, insbesondere beim
steuerlichen Verlustvortrag und beim Darlehensstand. Diese Rekursionen werden
periodenweise vorwärts ausgewertet und erfordern keine iterative
Gleichungslösung.

![Berechnungsarchitektur der Projektbewertung](rechenweg.png)

## 2.2 Bewertungsfunktion und hierarchisches Gleichungssystem

Die Bewertung erfolgt aus Sicht der Eigenkapitalgeber auf Grundlage der
periodischen Equity-Cashflows. Die mathematische Gesamtstruktur besteht aus
drei Ebenen:

1. dem Nettobarwert als expliziter Bewertungsfunktion,
2. dem internen Zinsfuß als implizit definierter Nullstelle dieser Funktion
   und
3. der periodenspezifischen Herleitung der zugrunde liegenden Cashflows.

Diese Hierarchie ist fachlich zweckmäßiger als eine vollständig ausmultiplizierte
Einzelformel: Eine solche Darstellung wäre zwar algebraisch möglich, würde
jedoch die Abhängigkeiten zwischen physischen, marktlichen, betrieblichen,
finanziellen und steuerlichen Größen verdecken.

### 2.2.1 Barwertfunktion als mathematischer Ausgangspunkt

Für einen vorgegebenen Diskontsatz $r$ ist der taggenaue Nettobarwert durch

$$
\operatorname{XNPV}(r)
  = \sum_{t=0}^{N}
    \frac{\mathrm{CF}_t}
         {(1+r)^{\Delta_t/365}},
\qquad
\Delta_t = \operatorname{Tage}(d_0,d_t)
$$

definiert. $d_0$ bezeichnet den Bewertungs- und Investitionszeitpunkt; $d_t$
ist das Zahlungsdatum des Cashflows der Periode $t$. Bei festgelegtem Diskontsatz stellt $\operatorname{XNPV}(r)$ die explizit
auswertbare Barwertgröße des Modells dar.

### 2.2.2 Interner Zinsfuß als implizite Renditekennzahl

Der auf datierten Zahlungszeitpunkten basierende interne Zinsfuß (XIRR) ist
nicht durch eine eigenständige Summenformel definiert. Er ergibt sich als eine Nullstelle der zuvor
definierten Barwertfunktion:

$$
r^{*} \in
\left\{r>-1\;\middle|\;\operatorname{XNPV}(r)=0\right\}.
$$

Damit beruhen Nettobarwert und interner Zinsfuß auf derselben
Cashflow-Zeitreihe. Der Nettobarwert bewertet diese Zeitreihe bei einem exogen
vorgegebenen Renditeanspruch; der interne Zinsfuß bestimmt demgegenüber den
endogenen Diskontsatz, bei dem ihr Barwert null beträgt.

### 2.2.3 Periodische Equity-Cashflows

Am Investitionszeitpunkt gilt mit Investitionsvolumen $I$, Fremdkapital $D$
und Eigenkapitalquote $e$:

$$
\mathrm{CF}_0 = -I + D = -eI,
\qquad
D=(1-e)I.
$$

Für die Betriebsperioden ergibt sich der Equity-Cashflow aus Erlösen,
Betriebskosten, Zinsen, Ertragsteuern und Tilgung:

$$
\mathrm{CF}_t
  = R_t-C_t-Z_t-S_t-T_t,
\qquad t\geq 1.
$$

Die Barwertfunktion kann damit zunächst in der folgenden aggregierten Form
geschrieben werden:

$$
\boxed{
\operatorname{XNPV}(r)
  = -eI
    + \sum_{t=1}^{N}
      \frac{R_t-C_t-Z_t-S_t-T_t}
           {(1+r)^{\Delta_t/365}}
}
$$

### 2.2.4 Substitution von Erlös und Energieertrag

Für die Behandlung negativer Strompreise wird der Einspeisefaktor $q_t$
definiert als

$$
q_t =
\begin{cases}
1, & \text{im Modus Marktwert},\\
1-\nu_t, & \text{im Modus Abregelung}.
\end{cases}
$$

Die wirksame Marktprämie je Kilowattstunde beträgt

$$
p_t
  = \mathbf{1}_{[t\leq F]}\,(z-m_t)^+.
$$

Der Gesamterlös folgt damit aus

$$
R_t
  = \frac{E_t}{100}
    \left[q_t m_t+(1-\nu_t)p_t\right],
$$

wobei Energieertrag und nominaler Marktwert durch

$$
\begin{aligned}
E_t
  &= P h(1-d)^{t-1}\pi_t(1-\sigma),\\
m_t
  &= m_t^{\mathrm{real}}(1+\iota)^{y_t-y_B},\\
y_t
  &= y_0+t-1
\end{aligned}
$$

bestimmt werden. Nach dieser Substitution lautet die Barwertfunktion

$$
\begin{aligned}
\operatorname{XNPV}(r)
={}&-eI+\sum_{t=1}^{N}\frac{1}{(1+r)^{\Delta_t/365}}
\Bigg[
\frac{P h(1-d)^{t-1}\pi_t(1-\sigma)}{100}\\
&\quad\cdot\left(
q_t m_t+(1-\nu_t)\mathbf{1}_{[t\leq F]}(z-m_t)^+
\right)
-C_t-Z_t-S_t-T_t
\Bigg].
\end{aligned}
$$

Aus der Gleichung ist die Wirkung der technischen und marktlichen Parameter
auf den Projektbarwert unmittelbar ableitbar. Die übrigen Terme werden im
Folgenden als eigenständige Teilmodelle spezifiziert.

### 2.2.5 Substitution der Betriebskosten

Die gesamten Betriebskosten setzen sich aus leistungsbezogenen
Standardpositionen, Gemeindeabgabe, Direktvermarktung und Pacht zusammen:

$$
\begin{aligned}
C_t
={}&\sum_j
\mathbf{1}_{[t\geq t_j^{\mathrm{start}}]}
 w_jP(1+g_j)^{(t-t_j^{\mathrm{idx}})^+}\\
&+E_t c_{\mathrm{gem}}\Theta_t
 +C_t^{\mathrm{dv}}
 +C_t^{\mathrm{pacht}},\\
\Theta_t
={}&(1+\kappa)^{(t-1)^+}.
\end{aligned}
$$

Je nach vertraglicher Parametrisierung können einzelne Kostenpositionen von
der installierten Leistung, der erzeugten Energiemenge, dem Marktwert oder
dem Umsatz abhängen. Die vollständigen Fallunterscheidungen werden in Kapitel
8 definiert.

### 2.2.6 Substitution von Finanzierung und Ertragsteuern

Zinsaufwand und Darlehensstand ergeben sich aus

$$
Z_t=B_t i f_t,
\qquad
B_{t+1}=(B_t-T_t)^+.
$$

Die Steuerzahlung ist eine Funktion des Ergebnisses nach Betriebskosten und
Zinsen, der Abschreibung, des Freibetrags und des nutzbaren
Verlustvortrags:

$$
\begin{aligned}
G_t
  &=R_t-C_t-Z_t-A_t-\Phi,\\
U_t
  &=\min(V_t,\gamma G_t)\,
    \mathbf{1}_{[G_t>0]},\\
S_t
  &=\tau(G_t-U_t)^+,\\
V_{t+1}
  &=V_t-U_t+(-G_t)^+.
\end{aligned}
$$

Damit ist die Bewertungsfunktion vollständig auf Eingabeparameter,
Szenariokurven und periodenabhängige Zustandsgrößen zurückgeführt. Die Kapitel
4 bis 10 spezifizieren die einzelnen Teilmodelle in der Reihenfolge ihrer
Implementierung; Kapitel 11 führt die Ergebnisse zum Equity-Cashflow zusammen,
Kapitel 12 wertet die Barwert- und Renditekennzahlen aus.

## 2.3 Reihenfolge und fachliche Abhängigkeiten

Die Reihenfolge der Rechenmodule folgt aus den fachlichen Abhängigkeiten der
jeweiligen Ausgangsgrößen:

| Schritt | Modul | Erforderliche Eingangsgrößen | Fachliche Abhängigkeit |
| --- | --- | --- | --- |
| 1 | `timeline` | Inbetriebnahmedatum, Betriebsdauer | Definition der Perioden und zeitanteiligen Faktoren |
| 2 | `energy` | Zeitachse | Wirkung von Degradation und unterjähriger Inbetriebnahme auf die Energiemenge |
| 3 | `revenue` | Energiemenge, Kalenderjahr | Verknüpfung der Produktion mit kalenderjahrbezogenen Marktpreiskurven |
| 4 | `opex` | Energiemenge, Marktwert, Erlös | Berücksichtigung mengen-, preis- und umsatzabhängiger Kostenpositionen |
| 5 | `financing` | Investitions- und Kreditparameter | Ermittlung des Schuldendienstes unabhängig vom operativen Ergebnis |
| 6 | `tax` | Erlös, Betriebskosten, Zinsen, Investition | Ableitung der steuerlichen Bemessungsgrundlage und Fortschreibung des Verlustvortrags |
| 7 | `cashflow` | sämtliche vorgelagerten Zeitreihen | Aggregation zum Equity-Cashflow und zum DSCR |
| 8 | `kpis` | datierte Cashflow-Zeitreihe | Berechnung der Barwert-, Rendite- und Amortisationskennzahlen |

Die Betriebskostenberechnung ist nach der Erlösberechnung angeordnet, da
Direktvermarktungskosten und Pacht in bestimmten Parametrisierungen vom
Marktwert beziehungsweise vom Umsatz abhängen. Eine umgekehrte Abhängigkeit
der Erlöse von den Betriebskosten ist nicht vorgesehen; algebraische
Zirkelbezüge werden dadurch ausgeschlossen.

## 2.4 Parametrisierungsebenen

Das Modell unterscheidet zwischen projektbezogenen und globalen Parametern:

- Die **Projektparameter** (`PVProject`) enthalten projektspezifische Größen,
  insbesondere Leistung, spezifischen Ertrag, Investitionskosten,
  Standortkosten, Finanzierungskonditionen und Zuschlagswert.
- Die **globalen Annahmen** (`GlobalAssumptions`) enthalten übergreifende
  Modellparameter, darunter Preiszeitreihen, Standardbetriebskosten,
  Förder- und Betriebsdauer, Steuerregeln, Degradation und Marktsystematik.

Die Funktion `resolve_assumptions()` führt beide Ebenen zum vollständig
spezifizierten Parametersatz `EffectiveAssumptions` zusammen. Sämtliche
nachgelagerten Rechenmodule verwenden ausschließlich diesen aufgelösten Satz.
Dadurch bleibt jede Ergebnisgröße eindeutig auf ihre Parametrisierung
zurückführbar.

## 2.5 Marktsystemabhängige Regelkonfiguration

Der Parameter `markt_system` konfiguriert mehrere länderspezifische Regeln als
konsistentes Ausgangspaket:

| Regel | Österreich (EAG) | Deutschland (EEG) |
| --- | --- | --- |
| Entfall der Prämie bei negativen Preisen | ab 6 zusammenhängenden Stunden | ab 1 Stunde |
| Ertragsbesteuerung | Körperschaftsteuer mit AfA, Freibetrag und Verlustvortrag | Gewerbesteuer mit Freibetrag, ohne Verlustvortrag im Referenzmodell |
| Zinsmethode im Anlaufjahr | taggenau Act/365 | kaufmännisch 30/360 |
| Herkunft des anzulegenden Wertes | empirisches Ausschreibungsmodell nach Kapitel 15 | manuelle Vorgabe des erwarteten Zuschlags |

Die Einzelparameter bleiben nach Auswahl des Marktsystems veränderbar. Der
Länderschalter stellt somit eine konsistente Vorbelegung dar, ohne die
Parametrisierung der Einzelregeln einzuschränken. Die grundlegende
Cashflow-Systematik bleibt in beiden Marktsystemen unverändert.

# 3 Notation, Einheiten und Konventionen

## 3.1 Zeitindex

Der Index $t$ bezeichnet das **Betriebsjahr**, gezählt ab der
Inbetriebnahme:

$$ t \in \{0, 1, 2, \dots, N\}, \qquad N = \text{Betriebsdauer in Jahren} $$

- $t = 0$ ist der **Investitionszeitpunkt**. In diesem Jahr gibt es keine
  Produktion, keine Erlöse und keine Kosten, sondern ausschließlich den
  Investitionsabfluss und die Kreditaufnahme.
- $t \geq 1$ sind die **Betriebsjahre**. Betriebsjahr $t$ endet stets am
  31. Dezember des Kalenderjahres $y_t$.

Das zugehörige **Kalenderjahr** ergibt sich aus dem Inbetriebnahmejahr
$y_0$:

$$ y_t = y_0 + t - 1 $$

Diese Unterscheidung ist zentral: Preiskurven sind nach Kalenderjahr
indiziert, Degradation und Kostenindexierung nach Betriebsjahr.

## 3.2 Symbolverzeichnis

| Symbol | Bedeutung | Einheit | Quelle |
| --- | --- | --- | --- |
| $P$ | Nennleistung (installiert, DC) | kWp | Projekt |
| $h$ | Spezifischer Ertrag (Vollbenutzungsstunden) | kWh/kWp | Projekt |
| $d$ | Degradation je Jahr | – | global |
| $\sigma$ | Sicherheitsabschlag auf die Menge | – | global |
| $\pi_t$ | Anteilsfaktor der Periode $t$ | – | Zeitachse |
| $E_t$ | Stromproduktion im Jahr $t$ | kWh | Schritt 2 |
| $m^{\mathrm{real}}_t$ | Marktwert Solar, real | ct/kWh | Szenariokurve |
| $m_t$ | Marktwert Solar, nominal | ct/kWh | Schritt 3 |
| $z$ | EAG-Zuschlagswert, effektiv | ct/kWh | Projekt + Regel |
| $F$ | Förderdauer | Jahre | global |
| $s_t$ | Vergütungssatz | ct/kWh | Schritt 3 |
| $\nu_t$ | Erzeugungsanteil in Stunden negativer Preise | – | Szenariokurve |
| $w$ | Gewichtung des Negativstunden-Effekts | – | global |
| $R_t$ | Erlös gesamt | € | Schritt 3 |
| $C_t$ | Betriebskosten gesamt | € | Schritt 4 |
| $\kappa$ | Allgemeine Kosteninflation | – | global |
| $\iota$ | Inflation der Marktpreiskurven | – | global |
| $y_B$ | Preisbasisjahr der Marktpreiskurven | – | global |
| $I$ | Investitionsvolumen (CAPEX) | € | Projekt |
| $e$ | Eigenkapitalquote | – | Projekt |
| $D$ | Kreditsumme (Fremdkapital) | € | Schritt 5 |
| $i$ | Fremdkapitalzins | – | Projekt |
| $n$ | Kreditlaufzeit (Anzahl Tilgungsraten) | Jahre | global |
| $Z_t$ | Zinsaufwand | € | Schritt 5 |
| $T_t$ | Tilgung | € | Schritt 5 |
| $B_t$ | Darlehensstand zu Jahresbeginn | € | Schritt 5 |
| $A_t$ | Abschreibung (AfA) | € | Schritt 6 |
| $V_t$ | Verlustvortragsbestand zu Jahresbeginn | € | Schritt 6 |
| $\gamma$ | Verrechnungsgrenze des Verlustvortrags | – | global |
| $\tau$ | Effektiver Ertragsteuersatz | – | global |
| $S_t$ | Steuerzahlung | € | Schritt 6 |
| $\mathrm{CF}_t$ | Equity-Cashflow gesamt | € | Schritt 7 |
| $r$ | Diskontsatz | – | Einstellung |
| $s_{\mathrm{trap}}$ | Cash-Trap-Schwelle des DSCR | – | global |
| $s_{\mathrm{eod}}$ | Event-of-Default-Schwelle des DSCR | – | global |
| $N_t$ | Erforderlicher Eigenkapitalnachschuss | € | Schritt 7 |

## 3.3 Einheiten und Umrechnungen

Das Modell rechnet **intern konsequent in kWh und ct/kWh** und wandelt an
den Rändern:

$$ \text{Erlös in €} = \frac{\text{Menge in kWh} \cdot \text{Satz in ct/kWh}}{100} $$

Eingaben, die üblicherweise je MWh erfasst werden (Gemeindeabgabe,
Direktvermarktungskosten), werden bereits bei der Parameterauflösung
umgerechnet:

$$ c^{\mathrm{kWh}} = \frac{c^{\mathrm{MWh}}}{1000} $$

Prozentangaben sind im Modell durchgängig **Brüche** in $[0,1]$
(0,02 = 2 %). Eine Ausnahme bildet der Gewerbesteuer-Hebesatz,
dessen natürlicher Wertebereich (200 bis 900) nicht in eine
0-bis-1-Konvention passt; er wird als Prozentzahl geführt und in der
Steuerformel durch 100 geteilt.

## 3.4 Vorzeichenkonvention

| Größe | Vorzeichen | Bemerkung |
| --- | --- | --- |
| Erlöse | positiv | |
| Betriebskosten, Zinsen, Steuern | positiv erfasst, negativ verrechnet | die Zeitreihe führt Beträge, die Cashflow-Formel zieht sie ab |
| Investition $\mathrm{CF}^{\mathrm{inv}}_0$ | negativ | Abfluss |
| Kreditaufnahme $\mathrm{CF}^{\mathrm{fin}}_0$ | positiv | Zufluss |
| Tilgung $\mathrm{CF}^{\mathrm{fin}}_t,\ t \geq 1$ | negativ | Abfluss |

## 3.5 Kappungen und Randwertbehandlung

Drei Operationen treten wiederholt auf und sind einheitlich definiert:

$$ \mathrm{clip}(x, a, b) = \min\left(\max(x, a),\, b\right) $$

$$ (x)^{+} = \max(x, 0) $$

$$ \mathbf{1}_{[\text{Bedingung}]} = 1, \text{ wenn die Bedingung gilt, sonst } 0 $$

Für Kurvenzugriffe außerhalb des definierten Bereichs gilt durchgängig
**Klemmen statt Extrapolieren** (Abschnitt 7.2).

# 4 Schritt 0 – Auflösung der Parameter

**Zweck.** Aus Projektmaske und globalen Annahmen entsteht ein
vollständiger, widerspruchsfreier Parametersatz.

**Codestelle.** `engine/pipeline.py`, `resolve_assumptions()`.

## 4.1 Übernahme, Umrechnung, Geschäftsregeln

Der Merge ist überwiegend eine 1:1-Übernahme. Vier Stellen enthalten
echte Rechenlogik:

**(a) Geschäftsregel Konventionell-Abschlag.** Konventionelle
Freiflächenanlagen erhalten gegenüber Agri-PV einen Abschlag von 25 % auf
den EAG-Zuschlagswert:

$$ z = z_{\mathrm{Gebot}} \cdot \left(1 - \delta_{\mathrm{konv}} \cdot \mathbf{1}_{[\text{Anlagentyp} = \text{konventionell}]}\right), \qquad \delta_{\mathrm{konv}} = 0{,}25 $$

Der Abschlag ist als benannte Konstante
(`KONVENTIONELL_ZUSCHLAG_ABSCHLAG_PCT`) implementiert und nicht als
Eingabeparameter veränderbar. Damit wird er als Geschäftsregel und nicht als
projektspezifische Annahme behandelt.

**(b) Einheitenumrechnung** der produktionsbasierten Sätze:

$$ c_{\mathrm{gem}} = \frac{c^{\mathrm{MWh}}_{\mathrm{gem}}}{1000}, \qquad c_{\mathrm{dv}} = \frac{c^{\mathrm{MWh}}_{\mathrm{dv}}}{1000} $$

**(c) Auswahl der Negativmengen-Kurve.** Jedes Marktpreisszenario führt
zwei Zeitreihen des Erzeugungsanteils in Stunden negativer Preise – eine
für die 6-Stunden-Regel, eine für die 1-Stunden-Regel. Die global
gewählte Regel entscheidet, welche in den Parametersatz übernommen wird.
Da die 1-Stunden-Regel einen größeren Stundenumfang erfasst, weist die
zugehörige Mengenkurve mindestens gleich hohe Werte auf.

**(d) Szenario-Rückfall.** Existiert das im Projekt hinterlegte Szenario
nicht mehr, wird das erste verfügbare Szenario verwendet; existiert gar
keines, ein leeres Szenario mit Marktwert 0. Dadurch bleibt die Bewertung auch nach Umbenennung oder Löschung eines
referenzierten Szenarios ausführbar. Der verwendete Rückfallwert ist im
aufgelösten Parametersatz transparent ausgewiesen.

## 4.2 Investitionsvolumen

Das Investitionsvolumen ist die Summe der neun festen Kostenkategorien der
Projektmaske und beliebig vieler frei benannter Zusatzpositionen:

$$ I = \sum_{c\, \in\, \mathcal{C}} I_c + \sum_{z\, \in\, \mathcal{Z}} I_z $$

$$ \mathcal{C} = \{\text{EPC},\ \text{Netzanschluss},\ \text{Trasse},\ \text{Widmung},\ \text{Genehmigung},\ \text{Sonstige externe},\ \text{AGM},\ \text{M+A},\ \text{Pönalepuffer}\} $$

$\mathcal{Z}$ ist die je Projekt frei definierbare Menge zusätzlicher
Investitionspositionen. Jede Position besteht aus einer Bezeichnung und
einem Betrag; die Bezeichnung muss nichtleer sein und darf keine der
reservierten Spaltenbezeichnungen der Cashflow-Zeitreihe tragen, damit die
Ausgabestrukturen eindeutig bleiben. Rechnerisch sind die Zusatzpositionen
den festen Kategorien gleichgestellt – sie erhöhen ausschließlich $I$ und
wirken damit über die Finanzierungs-, Abschreibungs- und Cashflow-Kette
identisch. Ist $\mathcal{Z}$ leer, reduziert sich die Formel auf die neun
Standardkategorien.

Alle Kategorien werden als **Gesamtbeträge in Euro** erfasst; die
Projektmaske erlaubt je Feld wahlweise die Eingabe als spezifischer Wert
(€/kWp), der intern unmittelbar mit $P$ multipliziert wird. Die spezifische
Größe $I/P$ wird nur zur Anzeige gebildet.

## 4.3 Vollständigkeitsprüfung

Zwei Konsistenzbedingungen werden bereits bei der Validierung erzwungen:

- Im Steuermodus mit AfA muss eine Nutzungsdauer gesetzt sein
  (sonst wäre $A_t$ undefiniert).
- Alle Anteilsgrößen liegen in $[0,1]$, Leistung und spezifischer Ertrag
  sind strikt positiv.

**Ausgang.** `EffectiveAssumptions` mit rund 40 Feldern als einheitliche
Eingangsstruktur sämtlicher nachgelagerter Rechenmodule.

# 5 Schritt 1 – Zeitachse

**Zweck.** Festlegen der Perioden und ihrer Anteilsfaktoren.

**Codestelle.** `engine/timeline.py`, `build_timeline()` und
`erstjahr_zins_pro_rata()`.

## 5.1 Perioden

Betriebsjahr $t$ läuft von $\mathrm{start}_t$ bis
$\mathrm{ende}_t$ mit

$$ \mathrm{ende}_t = 31.12.(y_0 + t - 1), \qquad \mathrm{start}_1 = \text{Inbetriebnahmedatum}, \qquad \mathrm{start}_{t+1} = 1.1.(y_0 + t) $$

Jede Periode außer der ersten ist damit ein volles Kalenderjahr. Die
erste Periode reicht vom Inbetriebnahmedatum bis zum Jahresende und ist
bei unterjähriger Inbetriebnahme kürzer.

## 5.2 Anteilsfaktor der Produktion

$$ \pi_t = \min\left(\frac{\mathrm{Tage}(\mathrm{start}_t,\ \mathrm{ende}_t) + 1}{365},\ 1\right) $$

Der Faktor ist für alle vollen Kalenderjahre gleich 1 (auch in
Schaltjahren, wegen der Kappung bei 1) und nur im Anlaufjahr kleiner. Er
skaliert die Produktionsmenge des ersten Jahres und damit indirekt alle
mengenabhängigen Erlöse und Kosten.

> **Annahme.** Betriebsperioden sind Kalenderjahre. Der Sonderfall
> „Vertragsende am Jahrestag der Inbetriebnahme statt am Jahresende“ ist
> nicht abgebildet (siehe Kapitel 17).

## 5.3 Anteilsfaktor der Zinsen

Für den Zinsaufwand des Anlaufjahres ist die Zinsmethode wählbar. Sie
wirkt sich ausschließlich bei unterjähriger Inbetriebnahme aus; bei
Inbetriebnahme am 1. Januar liefern beide Methoden exakt 1.

**Österreich, taggenau (act/365):** identisch zum Produktionsfaktor,

$$ f^{\mathrm{act/365}} = \min\left(\frac{\mathrm{Tage}(\text{IBN},\ 31.12.y_0) + 1}{365},\ 1\right) $$

**Deutsche kaufmännische Methode (30/360):** jeder Restmonat des
Anlaufjahres einschließlich des Inbetriebnahmemonats zählt pauschal mit
30 Tagen, das Jahr mit 360:

$$ f^{30/360} = \frac{(13 - M) \cdot 30}{360} = \frac{13 - M}{12}, \qquad M = \text{Inbetriebnahmemonat} $$

Beispiel: Inbetriebnahme im September ($M = 9$) ergibt
$f^{30/360} = 4/12 = 0{,}3\overline{3}$, während act/365 vom 1.9. bis
31.12. mit $122/365 = 0{,}334$ rechnet – nahe beieinander, aber nicht
identisch.

**Ausgang.** Zeitachse mit $t$, Periodengrenzen, $\pi_t$ und der Markierung
des letzten Jahres.

# 6 Schritt 2 – Energieertrag

**Zweck.** Die eingespeiste Strommenge je Betriebsjahr.

**Codestelle.** `engine/energy.py`, `calculate_energy_production()`.

## 6.1 Vorschrift

$$ E^{\mathrm{basis}} = P \cdot h $$

$$ \phi_t = (1 - d)^{\,t-1} $$

$$ E_t = E^{\mathrm{basis}} \cdot \phi_t \cdot \pi_t \cdot (1 - \sigma) $$

## 6.2 Erläuterung

- **Basisproduktion** $E^{\mathrm{basis}}$ ist der Ertrag eines vollen
  ersten Betriebsjahres ohne Degradation und ohne Abschlag; sie ist das
  Produkt aus installierter Leistung und spezifischem Ertrag.
- **Degradationsfaktor** $\phi_t$ ist geometrisch mit Exponent $t-1$: Das
  erste Betriebsjahr ist definitionsgemäß degradationsfrei
  ($\phi_1 = 1$), der Modulalterungseffekt wirkt ab dem zweiten Jahr.
  Bei $d = 0{,}25\,\%$ und $t = 30$ ergibt sich
  $\phi_{30} = 0{,}9975^{29} = 0{,}9298$, entsprechend einem
  Mengenrückgang von rund 7 % bis zum Ende der Betriebsdauer.
- **Anteilsfaktor** $\pi_t$ kürzt das Anlaufjahr (Abschnitt 5.2).
- **Sicherheitsabschlag** $\sigma$ ist ein pauschaler Abschlag auf die
  Ertragsprognose (z. B. für P90-Betrachtungen). Er wirkt multiplikativ
  auf alle Jahre gleich.

> Der Sicherheitsabschlag wird **nach** Degradation und Anteilsfaktor
> angewendet. Da alle drei Faktoren multiplikativ sind, ist
> die Reihenfolge rechnerisch ohne Wirkung; die Trennung hält die
> Zeitreihe aber interpretierbar (der ausgewiesene Degradationsfaktor
> enthält keinen Risikoabschlag).

**Ausgang.** $\phi_t$ und $E_t$ (kWh) je Betriebsjahr.

# 7 Schritt 3 – Erlöse nach dem Marktprämienmodell

**Zweck.** Vergütungssatz und Erlös je Betriebsjahr, aufgeteilt in
Markterlös und Marktprämie.

**Codestelle.** `engine/revenue.py`, `calculate_revenue()`.

In diesem Modul werden die zentralen marktseitigen Berechnungsregeln
zusammengeführt. Die Berechnung gliedert sich in fünf Teilschritte: Kalenderjahr-Zuordnung, Kurvenzugriff,
Inflationierung, Vergütungssatz, Mengenwirkung negativer Preise.

## 7.1 Kalenderjahr-Zuordnung

$$ y_t = y_0 + t - 1 $$

Alle Preis- und Mengenkurven der Szenarien sind nach **echtem
Kalenderjahr** indiziert (typisch 2025 bis 2060), nicht nach
Betriebsjahr. Zwei Projekte mit unterschiedlichem Inbetriebnahmejahr
greifen im selben Betriebsjahr folglich auf unterschiedliche Kurvenpunkte
zu. Dies entspricht der kalenderzeitbezogenen Struktur einer
Marktpreisprognose.

## 7.2 Kurvenzugriff mit Klemmung

Für eine Kurve $g$, die auf den Stützjahren
$\{y_{\min}, \dots, y_{\max}\}$ definiert ist:

$$ g(y_t) = g\left(\mathrm{clip}(y_t,\ y_{\min},\ y_{\max})\right) $$

Liegt das Kalenderjahr außerhalb des Kurvenbereichs, wird der nächstgelegene
**Randwert** verwendet. Eine Extrapolation erfolgt nicht, da eine lineare Fortschreibung des
letzten Kurvensegments über den beobachteten Zeitraum hinaus nicht durch
die zugrunde liegende Marktpreisstudie abgesichert wäre. Ist gar keine Kurve hinterlegt, gilt
$g \equiv 0$.

## 7.3 Inflationierung des Marktwertes

Marktwert-Solar-Kurven aus Marktpreisstudien sind **reale** Werte auf der
Preisbasis des Erscheinungsjahres $y_B$. Für eine nominale
Cashflow-Rechnung werden sie inflationiert:

$$ m_t = m^{\mathrm{real}}_t \cdot (1 + \iota)^{\,y_t - y_B} $$

Für die Anwendung sind zwei Aspekte maßgeblich:

1. Der Exponent verwendet das **tatsächliche** Kalenderjahr $y_t$, nicht
   das eventuell geklemmte Nachschlagejahr. Wird jenseits des letzten
   Kurvenjahres mit dem letzten bekannten Realpreis fortgeschrieben, wird
   die allgemeine Preisniveauentwicklung weiterhin berücksichtigt.
2. Der **EAG-Zuschlagswert $z$ bleibt nominal fix**. Er wird während der
   Förderdauer gesetzlich nicht indexiert. Der Vergleich zwischen
   Marktwert und Zuschlagswert findet damit korrekt zwischen zwei
   nominalen Größen statt.

## 7.4 Vergütungssatz (gleitende Marktprämie)

Während der Förderdauer $F$ erhält der Betreiber den höheren der beiden
Werte, danach ausschließlich den Marktwert:

$$
\begin{aligned}
\widetilde{p}_t &= \left(z-m_t\right)^+,\\
p_t &= \mathbf{1}_{[t\leq F]}\,\widetilde{p}_t,\\
s_t &= m_t+p_t.
\end{aligned}
$$

Äquivalent und anschaulicher:

$$
s_t=
\begin{cases}
\max(m_t,z), & t\leq F,\\
m_t, & t>F.
\end{cases}
$$

$\widetilde{p}_t$ ist die rechnerische Differenz zwischen Zuschlagswert
und Marktwert; $p_t$ ist die **tatsächlich wirksame Marktprämie je kWh**.
Liegt der Marktwert unter dem Zuschlagswert, wird die Differenz während
der Förderdauer zugeschossen; liegt er darüber, ist die Prämie null. Nach
Ablauf der Förderdauer ist $p_t$ definitionsgemäß null.

## 7.5 Wirkung negativer Strompreise

In Stunden negativer Preise entfällt die Marktprämie. Modelliert wird das
über den Anteil $\nu^{\mathrm{roh}}_t$ der **Erzeugungsmenge**, die in
solche Stunden fällt (nicht über den Anteil der Stunden selbst – die
Menge ist die wirtschaftlich relevante Größe). Eine globale Gewichtung
erlaubt das Ein- und Ausblenden des Effekts für Vergleichsrechnungen:

$$ \nu_t = \nu^{\mathrm{roh}}_t \cdot w, \qquad w \in [0,1] $$

$w = 0$ blendet den Effekt vollständig aus (volle Vergütung auch in
Stunden negativer Preise), $w = 1$ entspricht der vollen gesetzlichen
Wirkung, wie sie in der Szenariokurve hinterlegt ist.

Für das Verhalten der Anlage in diesen Stunden gibt es zwei Modi. In
**beiden** entfällt die Prämie für den betroffenen Mengenanteil; sie
unterscheiden sich nur darin, ob der Markterlös erhalten bleibt.

**Modus „Marktwert“ (Anlage speist weiter ein):**

$$ R^{\mathrm{markt}}_t = \frac{E_t \cdot m_t}{100}, \qquad R^{\mathrm{pr\ddot{a}mie}}_t = \frac{E_t \cdot (1 - \nu_t) \cdot p_t}{100} $$

**Modus „Abregelung“ (Anlage wird abgeregelt):**

$$ R^{\mathrm{markt}}_t = \frac{E_t \cdot (1 - \nu_t) \cdot m_t}{100}, \qquad R^{\mathrm{pr\ddot{a}mie}}_t = \frac{E_t \cdot (1 - \nu_t) \cdot p_t}{100} $$

In beiden Fällen gilt

$$ R_t = R^{\mathrm{markt}}_t + R^{\mathrm{pr\ddot{a}mie}}_t $$

Nach Ablauf der Förderdauer ist $p_t = 0$; der Modus „Marktwert“ hat dann
keine Wirkung mehr, während „Abregelung“ die Menge weiterhin kürzt.

## 7.6 Interpretation der Aufteilung

Die Zerlegung in $R^{\mathrm{markt}}$ und $R^{\mathrm{prämie}}$ ermöglicht
eine ökonomische Zuordnung der Erlöse zu Markt und Förderung. Dadurch lässt
sich insbesondere die Abhängigkeit des Projektwerts von der Förderdauer
quantifizieren. In der grafischen Darstellung entspricht die Differenz
zwischen Vergütungssatz und Marktwert der Marktprämie.

**Ausgang.** $y_t$, $m^{\mathrm{real}}_t$, $m_t$, $s_t$, $R_t$,
$R^{\mathrm{markt}}_t$, $R^{\text{Prämie}}_t$.

# 8 Schritt 4 – Betriebskosten

**Zweck.** Alle laufenden Kosten je Betriebsjahr, sowohl als Summe als
auch aufgeschlüsselt nach Einzelposition.

**Codestelle.** `engine/opex.py`, `calculate_opex()`.

Die Betriebskosten setzen sich aus vier Gruppen zusammen, die
unterschiedlichen Bemessungsgrundlagen folgen:

| Gruppe | Bemessung | Indexierung |
| --- | --- | --- |
| Standardpositionen | €/kWp/Jahr | eigene, je Position sichtbare Indexierung |
| Gemeindeabgabe | €/kWh | allgemeine Kosteninflation |
| Direktvermarktung | €/kWh oder % vom Marktwert | Kosteninflation bzw. implizit über den Marktwert |
| Pacht | €/kWp/Jahr oder % vom Umsatz mit Mindestpacht | Kosteninflation |

## 8.1 Allgemeiner Inflationsfaktor

Für alle Positionen ohne eigene Preislogik gilt ein gemeinsamer
Kosteninflationsfaktor. Eingaben verstehen sich als Preisstand bei
Inbetriebnahme, die Eskalation beginnt daher im zweiten Betriebsjahr:

$$ \Theta_t = (1 + \kappa)^{\,(t-1)^{+}} $$

## 8.2 Betriebskostenpositionen

Die Positionsliste eines Projekts entsteht aus zwei Quellen: den in den
Globalen Annahmen gepflegten Standardpositionen und den frei benannten
Zusatzpositionen des Projekts. Beide werden in `resolve_assumptions()` zu
einer Liste verkettet – Standardpositionen zuerst, danach die
Zusatzpositionen. Die Reihenfolge bestimmt zugleich die Stapelreihenfolge
in der Kostendarstellung. Für die Rechnung selbst besteht kein Unterschied:
Jede Position durchläuft dieselbe Vorschrift.

Jede Position $j$ trägt einen spezifischen Basiswert $w_j$ (€/kWp/Jahr),
ein Startjahr $t^{\mathrm{start}}_j$, eine eigene Indexrate $g_j$ und ein
Jahr, ab dem indexiert wird, $t^{\mathrm{idx}}_j$:

$$ C^{(j)}_t = \mathbf{1}_{[\,t\, \geq\, t^{\mathrm{start}}_j\,]} \cdot w_j \cdot P \cdot (1 + g_j)^{\left(t - t^{\mathrm{idx}}_j\right)^{+}} $$

Der Exponent ist bei $0$ gekappt: Vor dem Indexierungsstartjahr gilt der
unveränderte Basiswert, es findet keine „Rückwärtsindexierung“ statt. Der
Startzeitpunkt ist von der Indexierung getrennt, damit Positionen
abgebildet werden können, die erst später einsetzen (z. B. eine Rücklage
ab Jahr 11), ihren Preisstand aber ab Jahr 1 fortschreiben.

Positionen mit identischer Bezeichnung werden aggregiert. Dadurch bleibt
jede Bezeichnung in der Kostenaufschlüsselung eindeutig. Für die
Bezeichnung gilt dieselbe Einschränkung wie bei den Investitionspositionen:
Sie muss nichtleer sein und darf keine der reservierten Spaltenbezeichnungen
der Cashflow-Zeitreihe (etwa `opex_gesamt_eur` oder `erloes_eur`) tragen, da jede
Position als eigene Spalte in die Zeitreihe geschrieben wird.

## 8.3 Produktionsbasierte Positionen

**Gemeindeabgabe** (je erzeugter kWh an die Standortgemeinde):

$$ C^{\mathrm{gem}}_t = E_t \cdot c_{\mathrm{gem}} \cdot \Theta_t $$

**Direktvermarktungskosten** (Bilanzkreis, Prognose, Marktzugang) in zwei
Modi:

Modus **absolut** – fester Satz je kWh:

$$ C^{\mathrm{dv}}_t = E_t \cdot c_{\mathrm{dv}} \cdot \Theta_t $$

Modus **relativ zum Marktwert** – Anteil $\varphi$ am nominalen
Jahresmarktwert der erzeugten Menge:

$$ C^{\mathrm{dv}}_t = E_t \cdot \frac{m_t}{100} \cdot \varphi $$

Im relativen Modus verändern sich die Kosten proportional zum Preisniveau.
Eine zusätzliche Kostenindexierung erfolgt nicht, da die Preisentwicklung
bereits im nominalen Marktwert enthalten ist und andernfalls doppelt
berücksichtigt würde.

## 8.4 Pacht

Die Pacht wird als eigenständige Kostenposition geführt, da sie abhängig von
Vertragsmodell unterschiedlich bemessen wird.

**Modus fix** – fester Betrag je installierter kWp und Jahr:

$$ C^{\mathrm{pacht}}_t = p_{\mathrm{kWp}} \cdot P \cdot \Theta_t $$

**Modus Umsatzbeteiligung** – Anteil $\beta$ am Jahresumsatz, mindestens
aber eine indexierte Mindestpacht je Hektar:

$$ C^{\mathrm{pacht}}_t = \max\left(\beta \cdot R_t,\ \ p_{\mathrm{ha}} \cdot A_{\mathrm{ha}} \cdot \Theta_t\right) $$

Marktüblich sind $\beta \approx 5{,}5\,\%$. Die Maximumbildung ist
wirtschaftlich relevant: In frühen Jahren dominiert typischerweise die
Umsatzbeteiligung, in späten Jahren die stetig steigende Mindestpacht –
insbesondere nach Auslaufen der Förderung und mit fortschreitender
Degradation. Ist keine Projektfläche gesetzt, wirkt die Mindestpacht wie
null, und es bleibt die reine Umsatzbeteiligung.

> Die Umsatzbeteiligung verwendet $R_t$ aus Schritt 3. Diese Abhängigkeit
> begründet die Anordnung des Erlösmoduls vor dem Betriebskostenmodul.

## 8.5 Summe

$$ C_t = \sum_j C^{(j)}_t + C^{\mathrm{gem}}_t + C^{\mathrm{dv}}_t + C^{\mathrm{pacht}}_t $$

**Ausgang.** $C_t$ sowie jede Einzelposition als eigene Spalte – die
Grundlage der aufgeschlüsselten Kostendarstellung in Oberfläche, Excel-
Export und PDF-Bericht.

# 9 Schritt 5 – Finanzierung

**Zweck.** Zins, Tilgung und Restschuld über die Kreditlaufzeit.

**Codestelle.** `engine/financing.py`, `calculate_financing()`.

## 9.1 Kapitalstruktur

$$ D = I \cdot (1 - e), \qquad EK = I \cdot e $$

Die Kreditsumme ergibt sich residual aus Investitionsvolumen und
Eigenkapitalquote. Das Modell enthält keine gesonderte Zwischenfinanzierung,
keine Bauzeitzinsen und keine Disagio- oder Gebührenposition; entsprechende
Kosten sind
gegebenenfalls im CAPEX zu erfassen.

## 9.2 Konventionen

- Zinsen eines Jahres fallen auf den **Jahresanfangsstand** $B_t$ an.
- Tilgung fließt **nachschüssig** am Jahresende.
- Der Schuldendienst endet nach $n$ Tilgungsraten (bei tilgungsfreiem
  Anlaufjahr entsprechend ein Jahr später).

$$ B_1 = D, \qquad B_{t+1} = \left(B_t - T_t\right)^{+} $$

## 9.3 Zinsaufwand

$$ Z_t = B_t \cdot i \cdot \left(f \cdot \mathbf{1}_{[t=1]} + \mathbf{1}_{[t>1]}\right) \quad \text{für } t \leq t^{\mathrm{ende}}, \qquad Z_t = 0 \text{ sonst} $$

Dabei ist $f$ der Zins-Anteilsfaktor des Anlaufjahres aus Abschnitt 5.3
(act/365 oder 30/360) und

$$ t^{\mathrm{ende}} = n + \mathbf{1}_{[\text{tilgungsfreies Anlaufjahr}]} $$

## 9.4 Tilgung

**Annuitätentilgung.** Die konstante Rate folgt der Standard-Annuität
(identisch zu `PMT` in Tabellenkalkulationen):

$$ \mathrm{Ann} = D \cdot \frac{i}{1 - (1+i)^{-n}} $$

$$ T_t = \mathrm{Ann} - Z_t $$

**Lineare Tilgung.** Konstante Tilgungsrate, fallender Schuldendienst:

$$ T_t = \frac{D}{n} $$

**Tilgungsfreies Anlaufjahr.** Ist es aktiviert, gilt $T_1 = 0$; die
Tilgung beginnt in Jahr 2. Die **Anzahl** der Raten bleibt $n$; der Schuldendienstzeitraum verlängert
sich dadurch um ein Jahr. Da im ersten Jahr keine Tilgung erfolgt, wird der
Zins auch im zweiten Jahr auf die vollständige Kreditsumme berechnet.

$$ T_t = 0 \quad \text{für } t < t^{\mathrm{tilg}}, \qquad t^{\mathrm{tilg}} = 1 + \mathbf{1}_{[\text{tilgungsfreies Anlaufjahr}]} $$

**Schuldendienst.**

$$ \mathrm{DS}_t = Z_t + T_t $$

## 9.5 Wechselwirkung mit dem unterjährigen Anlaufjahr

Der Anteilsfaktor $f$ reduziert **ausschließlich die Zinslast** des
ersten Jahres. Die Tilgung folgt unverändert der Annuitäts- bzw.
Linearformel. Bei Annuitätentilgung bedeutet das: Weil von der fixen Rate
im ersten Jahr weniger Zins abgeht, wird entsprechend mehr getilgt; das
Darlehen kann dadurch geringfügig vor Ablauf der nominellen Laufzeit
vollständig getilgt sein. Dieser Effekt ergibt sich systematisch aus einem unterjährigen ersten
Zinszeitraum und stellt keine numerische Approximation dar.

Die Kappung $B_{t+1} = (B_t - T_t)^{+}$ verhindert in jedem Fall einen
negativen Darlehensstand.

**Ausgang.** $Z_t$, $T_t$, $\mathrm{DS}_t$, $B_t$ (Jahresanfang) und
$B_{t+1}$ (Jahresende).

# 10 Schritt 6 – Ertragsteuern

**Zweck.** Steuerliche Bemessungsgrundlage und Steuerzahlung je Jahr.

**Codestelle.** `engine/tax.py`, `calculate_tax()`.

Dieses Modul weist als einziges Teilmodell eine periodenübergreifende
Zustandsfortschreibung auf: Der Verlustvortragsbestand einer Periode hängt vom
Bestand der Vorperiode ab. Die Berechnung erfolgt daher sequenziell über die
Zeitachse.

## 10.1 Ergebnis vor Abschreibung

$$ \mathrm{EBT}^{\mathrm{vA}}_t = R_t - C_t - Z_t $$

Die Bemessungsgrundlage setzt **nach** Zinsen an (Zinsen sind
Betriebsausgaben), aber **vor** Abschreibung – diese wird im nächsten
Schritt modusabhängig abgezogen. Die Tilgung ist erfolgsneutral und geht
korrekterweise nicht ein.

## 10.2 Abschreibung

$$ A_t = \frac{I}{n_{\mathrm{AfA}}} \cdot \mathbf{1}_{[\,t\, \leq\, n_{\mathrm{AfA}}\,]} $$

Lineare Abschreibung des gesamten Investitionsvolumens über die
steuerliche Nutzungsdauer. Nach Ablauf der Nutzungsdauer ist das
Wirtschaftsgut voll abgeschrieben; eine weitere Abschreibung wäre
unzulässig und ist ausgeschlossen. Im Pauschalmodus gilt $A_t = 0$.

## 10.3 Modusabhängige Parameter

| Modus | $A_t$ | Freibetrag $\Phi$ | Satz $\tau$ | Grenze $\gamma$ |
| --- | --- | --- | --- | --- |
| Pauschal auf EBT | 0 | 0 | Eingabewert | Eingabewert |
| Körperschaftsteuer (AT) | linear über $n_{\mathrm{AfA}}$ | Eingabewert | Eingabewert | Eingabewert (gesetzlich 0,75) |
| Gewerbesteuer (DE) | linear über $n_{\mathrm{AfA}}$ | 24.500 € | $0{,}035 \cdot H/100$ | 0 |

Der effektive Gewerbesteuersatz folgt der gesetzlichen Systematik aus
Steuermesszahl und gemeindlichem Hebesatz $H$:

$$ \tau_{\mathrm{GewSt}} = 0{,}035 \cdot \frac{H}{100} $$

Bei einem Hebesatz von 400 % ergibt das $\tau = 14{,}0\,\%$.

## 10.4 Steuerliches Ergebnis vor Verlustvortrag

$$ G_t = \mathrm{EBT}^{\mathrm{vA}}_t - A_t - \Phi $$

## 10.5 Verlustvortrag

Nach österreichischem Recht (§ 8 Abs. 4 Z 2 KStG) sind Verluste zeitlich
**unbegrenzt** vortragbar, in einem Gewinnjahr aber nur bis zur
Verrechnungsgrenze $\gamma$ (gesetzlich 75 %) des steuerlichen
Ergebnisses verrechenbar. Der Rest ist in jedem Fall zu versteuern.

Mit dem Vortragsbestand $V_t$ zu Jahresbeginn ($V_1 = 0$):

$$ U_t = \min\left(V_t,\ \gamma \cdot G_t\right) \cdot \mathbf{1}_{[\,G_t\, >\, 0\,]} $$

$$ G^{\mathrm{st}}_t = \left(G_t - U_t\right)^{+} $$

$$ S_t = G^{\mathrm{st}}_t \cdot \tau $$

$$ V_{t+1} = V_t - U_t + \left(-G_t\right)^{+} $$

Dabei ist $U_t$ der genutzte Vortrag, $G^{\mathrm{st}}_t$ das
tatsächlich versteuerte Ergebnis und $(-G_t)^{+}$ der im Jahr $t$ neu
entstandene Verlust.

Ein optionaler Deaktivierungsschalter für den Verlustvortrag ist nicht
vorgesehen, da dessen Berücksichtigung im österreichischen Steuermodus
Bestandteil der implementierten Rechtslogik ist. Steuerung erfolgt ausschließlich über die
Verrechnungsgrenze $\gamma$; mit $\gamma = 0$ ist der Vortrag faktisch
deaktiviert (so wird die deutsche Gewerbesteuer abgebildet).

> **Annahme (Gewerbesteuer).** Der gewerbesteuerliche Verlustvortrag nach
> § 10a GewStG wird nicht abgebildet: Das als Referenz validierte
> Modell (Abgleich mit einer realen Projekt-Excel) berücksichtigt ihn
> ebenfalls nicht. Jedes Jahr wird unabhängig betrachtet.

## 10.6 Ausweis der steuerlichen Zwischengrößen

Neben $S_t$ werden $A_t$, $V_t$, $G_t$, $U_t$, $V_{t+1}$ und
$G^{\mathrm{st}}_t$ ausgegeben. Der vollständige Ausweis dieser
Zwischengrößen ermöglicht die periodenbezogene Prüfung der Überleitung vom
Ergebnis vor Steuern zur tatsächlichen Steuerzahlung.

**Ausgang.** $A_t$, $V_t$, $G_t$, $U_t$, $V_{t+1}$, $G^{\mathrm{st}}_t$,
$S_t$.

# 11 Schritt 7 – Cashflow-Rechnung

**Zweck.** Zusammenführung aller Zeitreihen zum Equity-Cashflow.

**Codestelle.** `engine/cashflow.py`, `calculate_cashflow()`.

Dieses Modul führt die zuvor berechneten Zeitreihen ohne zusätzliche
fachliche Annahmen zusammen. Die Trennung von Berechnung und Aggregation
ermöglicht eine eindeutige Zuordnung etwaiger Abweichungen zum jeweils
verantwortlichen Teilmodell.

## 11.1 Investitionszeitpunkt $t = 0$

$$ \mathrm{CF}^{\mathrm{op}}_0 = 0, \qquad \mathrm{CF}^{\mathrm{inv}}_0 = -I, \qquad \mathrm{CF}^{\mathrm{fin}}_0 = D $$

$$ \mathrm{CF}_0 = -I + D = -I \cdot e = -EK $$

Der Nettozahlungsmittelabfluss zum Zeitpunkt $t=0$ entspricht damit dem **Eigenkapitaleinsatz**.
Die Zeile trägt als Datum das Inbetriebnahmedatum – sie ist der
Bezugspunkt aller Diskontierungen.

## 11.2 Betriebsjahre $t \geq 1$

$$ \mathrm{CF}^{\mathrm{op}}_t = R_t - C_t - Z_t - S_t $$

$$ \mathrm{CF}^{\mathrm{inv}}_t = 0, \qquad \mathrm{CF}^{\mathrm{fin}}_t = -T_t $$

$$ \mathrm{CF}_t = \mathrm{CF}^{\mathrm{op}}_t + \mathrm{CF}^{\mathrm{inv}}_t + \mathrm{CF}^{\mathrm{fin}}_t $$

$$ \mathrm{CF}^{\mathrm{kum}}_t = \sum_{k=0}^{t} \mathrm{CF}_k $$

Der operative Cashflow ist bereits nach Zinsen und Steuern definiert; die
Tilgung erscheint separat im Finanzierungs-Cashflow. $\mathrm{CF}_t$ ist
damit durchgängig als **Cashflow aus Sicht der Eigenkapitalgeber** definiert. Er bildet
die gemeinsame Datengrundlage für XNPV, XIRR und Amortisationszeit.

## 11.3 Schuldendienstdeckungsgrad (DSCR)

$$ \mathrm{CFADS}_t = R_t - C_t - S_t $$

$$ \mathrm{DSCR}_t = \frac{\mathrm{CFADS}_t}{\mathrm{DS}_t} \quad \text{für } \mathrm{DS}_t > 0, \qquad \text{sonst undefiniert} $$

CFADS (*Cash Flow Available for Debt Service*) ist der Cashflow **vor**
Zinsen. Da die Zinsen bereits als Bestandteil des Schuldendienstes im Nenner
enthalten sind, werden sie im Zähler nicht erneut abgezogen. Für Perioden ohne Schuldendienst ist der DSCR nicht definiert. Diese Perioden
werden bei der Ermittlung des Minimums und bei Verlaufsanalysen nicht
berücksichtigt.

## 11.4 Ergebnisstruktur

Die Cashflow-Zeitreihe führt neben den Aggregaten alle Erklärgrößen mit:
Produktion, Marktwert real und nominal, Vergütungssatz, Erlösaufteilung,
Betriebskosten je Einzelposition, Zinsen, Tilgung, sämtliche
Steuergrößen. Das Spaltenschema wird beim Erzeugen erzwungen – fehlt eine
Spalte, bricht die Rechnung ab, statt eine unvollständige Tabelle
weiterzureichen.

**Ausgang.** Vollständige Cashflow-Tabelle, Zeilen $t = 0 \dots N$.

## 11.5 DSCR-Kovenanten: Ausschüttungssperre und Nachschusspflicht

**Codestelle.** `engine/covenants.py`, `analysiere_kovenanten()`.

Kreditverträge belegen den Schuldendienstdeckungsgrad mit zwei Schwellen.
Beide wirken **nicht** auf die Cashflow-Rechnung zurück; sie werden auf
der fertigen Zeitreihe ausgewertet.

$$ s_{\mathrm{trap}} = \text{Cash-Trap-Schwelle (Vorbelegung } 1{,}10\text{)}, \qquad s_{\mathrm{eod}} = \text{Event-of-Default-Schwelle (Vorbelegung } 1{,}05\text{)} $$

**Ereignisse.** Für alle Perioden mit $\mathrm{DS}_t > 0$:

$$ \text{Cash Trap}_t \iff \mathrm{DSCR}_t < s_{\mathrm{trap}}, \qquad \text{Event of Default}_t \iff \mathrm{DSCR}_t < s_{\mathrm{eod}} $$

**Nachschussbetrag.** Bei einem Event of Default wird der Verstoß
üblicherweise durch eine Eigenkapitaleinlage geheilt (*Equity Cure*), und
zwar in der Höhe, die den Deckungsgrad gerade wieder auf die Schwelle
hebt. Zusätzlich ist eine reine Zahlungslücke stets zu decken – auch
dann, wenn die Schwelle so niedrig gesetzt ist, dass sie formal nicht
greift:

$$ N_t = \max\left( \mathbf{1}_{[\mathrm{DSCR}_t\, <\, s_{\mathrm{eod}}]} \left(s_{\mathrm{eod}} \mathrm{DS}_t - \mathrm{CFADS}_t\right)^{+},\ \left(-\mathrm{CF}_t\right)^{+} \right) $$

**Ausschüttung und Reserve.** Der Cash Trap sperrt die Ausschüttung; der
freie Cashflow verbleibt dann als Reserve in der Gesellschaft:

$$ \text{Ausschüttung } G_t^{\mathrm{aus}} = \left(\mathrm{CF}_t\right)^{+} \cdot \mathbf{1}_{[\mathrm{DSCR}_t\, \geq\, s_{\mathrm{trap}}]}, \qquad \text{Reservezugang } \left(\mathrm{CF}_t\right)^{+} \cdot \mathbf{1}_{[\mathrm{DSCR}_t\, <\, s_{\mathrm{trap}}]} $$

**Deckungswasserfall.** Der Nachschuss wird in fester Reihenfolge aus drei
Quellen gedeckt. Mit dem Reservebestand $Q_t$ und dem Bestand bereits
ausgeschütteter, rückführbarer Mittel $A_t$:

$$ n^{\mathrm{res}}_t = \min(N_t,\ Q_t), \qquad n^{\mathrm{aus}}_t = \min\left(N_t - n^{\mathrm{res}}_t,\ A_t\right), \qquad n^{\mathrm{ext}}_t = N_t - n^{\mathrm{res}}_t - n^{\mathrm{aus}}_t $$

$$ Q_{t+1} = Q_t - n^{\mathrm{res}}_t + \left(\mathrm{CF}_t\right)^{+}\mathbf{1}_{[\mathrm{DSCR}_t\, <\, s_{\mathrm{trap}}]}, \qquad A_{t+1} = A_t - n^{\mathrm{aus}}_t + G_t^{\mathrm{aus}} $$

Die ersten beiden Quellen sind Mittel, die das Projekt zuvor **selbst
erwirtschaftet** hat: einbehaltener Cashflow und bereits an die
Gesellschafter ausgekehrtes Kapital. Nur der Rest erfordert
**zusätzliches externes Kapital**:

$$ N^{\mathrm{ext}} = \sum_{t=1}^{N} n^{\mathrm{ext}}_t > 0 \quad \Longleftrightarrow \quad \text{externe Kapitalzuführung erforderlich} $$

Diese Unterscheidung ist die eigentliche Aussage der Prüfung: Ein
Nachschussbedarf, der aus eigener Kraft gedeckt werden kann, ist ein
Liquiditäts-, kein Finanzierungsproblem.

> **Annahme.** Der Deckungswasserfall unterstellt, dass ausgeschüttete
> Mittel bei Bedarf in voller Höhe zurückgeführt werden können. Er
> beziffert damit die Obergrenze der aus eigener Kraft möglichen
> Deckung; ob die Gesellschafter tatsächlich zurückführen, ist eine
> Frage des Gesellschaftsvertrags und nicht Gegenstand des Modells.

# 12 Schritt 8 – Bewertungskennzahlen

**Zweck.** Ableitung der entscheidungsrelevanten Barwert-, Rendite-,
Amortisations- und Finanzierungskennzahlen aus der datierten
Cashflow-Zeitreihe.

**Codestelle.** `engine/kpis.py` und `engine/analytics.py`
(`calculate_lcoe`).

## 12.1 Nettobarwert bei taggenauer Diskontierung (XNPV)

Die in Abschnitt 2.2 eingeführte Barwertfunktion wird auf Act/365-Basis
taggenau ausgewertet. Sie entspricht damit der Berechnungslogik der
Tabellenkalkulationsfunktion `XNPV`:

$$ \operatorname{XNPV}(r) = \sum_{t=0}^{N} \frac{\mathrm{CF}_t}{(1+r)^{\frac{\Delta_t}{365}}}, \qquad \Delta_t = \text{Tage}(d_0,\ d_t) $$

Dabei ist $d_0$ das Investitionsdatum (Inbetriebnahmedatum) und $d_t$ das
Ende des Betriebsjahres $t$. Die jahresbasierte Vereinfachung $(1+r)^{-t}$ wird nicht verwendet, da sie
bei unterjähriger Inbetriebnahme systematisch von der taggenauen
Diskontierung abweicht.

Der ausgewiesene Nettobarwert entspricht $\operatorname{XNPV}(r)$ bei
einem frei wählbaren Diskontsatz (Vorbelegung 8 %). Die zugehörige
Barwertkurve wertet dieselbe Funktion an 21 Stützstellen zwischen 0 % und
10 % in Schritten von 0,5 Prozentpunkten aus. Ein Nulldurchgang dieser
Funktion entspricht einem internen Zinsfuß.

## 12.2 Interner Zinsfuß bei unregelmäßigen Zahlungszeitpunkten (XIRR)

Der Equity-IRR ist gemäß Abschnitt 2.2.2 als Nullstelle der
XNPV-Funktion definiert:

$$ \operatorname{XNPV}(r^{*}) = 0 $$

Gelöst wird mit dem Verfahren von Brent (`brentq`), einer Kombination aus
Bisektion, Sekantenverfahren und inverser quadratischer Interpolation.
Das Verfahren benötigt ein Intervall mit Vorzeichenwechsel. Um auch
extreme Projekte abzudecken, wird das Suchintervall schrittweise
erweitert:

$$ \left[-0{,}9999,\ 10\right] \ \rightarrow\ \left[-0{,}9999,\ 100\right] \ \rightarrow\ \left[-0{,}9999,\ 1000\right] $$

Vorab wird geprüft, ob der Cashflow überhaupt einen Vorzeichenwechsel
enthält. Fehlt ein Vorzeichenwechsel, ist der interne Zinsfuß für die vorliegende
Cashflow-Folge nicht bestimmbar. In diesem Fall wird kein numerischer
Ersatzwert ausgewiesen.

> Die Mehrdeutigkeit des IRR bei mehrfachem Vorzeichenwechsel ist eine
> bekannte Eigenschaft der Kennzahl. Bei der hier vorliegenden
> Cashflow-Struktur (ein Abfluss zu Beginn, danach überwiegend Zuflüsse)
> tritt sie praktisch nicht auf; ausgewiesen wird die vom Verfahren
> gefundene Nullstelle im Suchintervall.

## 12.3 Amortisationszeit

$$ t^{\mathrm{PB}} = \min\left\{\,t \ :\ \mathrm{CF}^{\mathrm{kum}}_t \geq 0\,\right\} $$

Die Amortisation ist **undiskontiert** definiert (einfache Payback-
Periode) und wird in vollen Betriebsjahren ausgewiesen. Erreicht der
kumulierte Cashflow innerhalb der Betrachtungsdauer nie null, wird kein
Wert ausgewiesen.

## 12.4 Weitere Kennzahlen

$$ EK = -\mathrm{CF}_0, \qquad I = -\mathrm{CF}^{\mathrm{inv}}_0 $$

$$ \mathrm{DSCR}^{\min} = \min_{t\,:\,\mathrm{DS}_t > 0} \mathrm{DSCR}_t $$

$$ \text{Spezifisches Invest} = \frac{I}{P} \quad \left[\text{€/kWp}\right] $$

**Equity Value.** Der Nettobarwert enthält den Eigenkapitaleinsatz des
Jahres 0 als Abfluss. Rechnet man ihn wieder hinzu, verbleibt der Barwert
der künftigen Eigenkapital-Cashflows – der Wert des Eigenkapitals zum
Bewertungsstichtag:

$$ V^{\mathrm{EK}}(r) = \operatorname{XNPV}(r) + EK = \sum_{t=1}^{N} \frac{\mathrm{CF}_t}{(1+r)^{\Delta_t/365}} $$

**Enterprise Value.** Zuzüglich des zum Stichtag aufgenommenen
Fremdkapitals ergibt sich der Gesamtunternehmenswert:

$$ V^{\mathrm{GK}}(r) = V^{\mathrm{EK}}(r) + D, \qquad D = I - EK $$

## 12.5 Stromgestehungskosten (LCOE)

$$ v_t = (1 + r)^{-\frac{\Delta_t}{365}} $$

$$ \mathrm{LCOE} = \frac{\sum_{t=0}^{N} \left(-\mathrm{CF}^{\mathrm{inv}}_t + C_t\right) \cdot v_t}{\sum_{t=0}^{N} E_t \cdot v_t} \cdot 100 \quad \left[\text{ct/kWh}\right] $$

Zähler sind die diskontierten Vollkosten (Investition plus
Betriebskosten), Nenner die diskontierte Strommenge; der Faktor 100
wandelt €/kWh in ct/kWh. Die Diskontierung ist dieselbe taggenaue
Act/365-Systematik wie beim XNPV.

Bewusst **nicht** enthalten sind Zinsen und Steuern: Die
Finanzierungskosten stecken definitionsgemäß im Diskontsatz $r$; sie
zusätzlich im Zähler zu führen, würde sie doppelt zählen. Der LCOE ist
damit die Kostenseite des Projekts unabhängig von der konkreten
Finanzierungsstruktur und direkt mit Marktpreisen und Zuschlagswerten
vergleichbar.

**Ausgang.** Equity-IRR, NPV, Payback, Investitionsvolumen,
Eigenkapitaleinsatz, minimaler DSCR, LCOE.

# 13 Numerisches Anwendungsbeispiel

Dieses Kapitel dokumentiert die numerische Reproduktion eines vollständig
spezifizierten Beispielprojekts. Grundlage
ist das mitgelieferte Beispielprojekt `data/projects/template-agri.yaml`
mit den globalen Annahmen aus `data/global_assumptions.yaml`. Alle
Tabellen dieses Kapitels erzeugt `python docs/rechenmodell/beispiel.py`;
`tests/test_dokumentation.py` prüft, dass die abgedruckten Zahlen
weiterhin dem Rechenergebnis entsprechen.

## 13.1 Eingangsgrößen

| Größe | Wert |
| --- | --- |
| Nennleistung $P$ | 3.800 kWp |
| Spezifischer Ertrag $h$ | 1.400 kWh/kWp |
| Inbetriebnahme | 01/2027 |
| Investitionsvolumen $I$ | 2.915.100 € |
| Eigenkapitalquote $e$ | 20,0 % |
| Fremdkapitalzins $i$ | 4,20 % |
| Kreditlaufzeit $n$ / Tilgungsart | 20 Jahre / Annuität |
| EAG-Zuschlagswert $z$ (Agri-PV, ohne Abschlag) | 6,50 ct/kWh |
| Förderdauer $F$ / Betriebsdauer $N$ | 20 / 30 Jahre |
| Degradation $d$ / Sicherheitsabschlag $\sigma$ | 0,25 %/a / 0 % |
| Marktpreisszenario | Aurora 10/25 |
| Marktpreisinflation $\iota$ / Basisjahr $y_B$ | 2,0 % / 2025 |
| Kosteninflation $\kappa$ | 2,0 % |
| Steuermodus | Körperschaftsteuer, $\tau = 23\,\%$, $n_{\mathrm{AfA}} = 20$ |
| Negativstunden | 6-Stunden-Regel, Modus „Marktwert“, Gewichtung 100 % |

Standard-Betriebskosten (global, je kWp und Jahr, je 2 % indexiert ab
Jahr 1): technische Betriebsführung 3,00 €, Wartung/Rücklage
Wechselrichter 1,00 €, Versicherungen 1,00 €, kaufmännische
Betriebsführung 3,00 €, Sonstiges 1,00 € – zusammen 9,00 €/kWp/Jahr.
Projektspezifisch: Pacht 5,263158 €/kWp/Jahr (fix), Gemeindeabgabe
2,00 €/MWh, Direktvermarktung 1,00 €/MWh.

## 13.2 Betriebsjahr 1 Schritt für Schritt

**Schritt 1 – Zeitachse.** Inbetriebnahme am 1. Januar 2027, also
$\pi_1 = 1$ und $f = 1$; Kalenderjahr $y_1 = 2027$.

**Schritt 2 – Menge.**

$$ E_1 = 3800 \cdot 1400 \cdot (1-0{,}0025)^0 \cdot 1 \cdot 1 = 5.320.000\ \mathrm{kWh} $$

**Schritt 3 – Erlös.** Kurvenwert des Szenarios für 2027:
$m^{\mathrm{real}}_1 = 4{,}133$ ct/kWh; Negativmengenanteil
$\nu_1 = 0{,}222$.

$$ m_1 = 4{,}133 \cdot 1{,}02^{\,2027-2025} = 4{,}133 \cdot 1{,}0404 = 4{,}300\ \text{ct/kWh} $$

$$ p_1 = (6{,}50 - 4{,}300)^{+} = 2{,}200\ \text{ct/kWh}, \qquad s_1 = 4{,}300 + 2{,}200 = 6{,}500\ \text{ct/kWh} $$

Modus „Marktwert“: Der Markterlös bleibt für die gesamte Menge erhalten,
nur die Prämie entfällt für den Anteil $\nu_1$.

$$ R^{\mathrm{markt}}_1 = \frac{5.320.000 \cdot 4{,}300}{100} = 228.759\ \text{€} $$

$$ R^{\text{Prämie}}_1 = \frac{5.320.000 \cdot (1 - 0{,}222) \cdot 2{,}200}{100} = 91.058\ \text{€} $$

$$ R_1 = 319.817\ \text{€} $$

**Schritt 4 – Betriebskosten.** Im ersten Jahr ist
$\Theta_1 = 1{,}02^0 = 1$, alle Indexexponenten sind null:

| Position | Rechnung | Betrag |
| --- | --- | --- |
| Standardpositionen | $9{,}00 \cdot 3800$ | 34.200 € |
| Pacht (fix) | $5{,}263158 \cdot 3800$ | 20.000 € |
| Gemeindeabgabe | $5.320.000 \cdot 0{,}002$ | 10.640 € |
| Direktvermarktung | $5.320.000 \cdot 0{,}001$ | 5.320 € |
| **Summe $C_1$** | | **70.160 €** |

**Schritt 5 – Finanzierung.**

$$ D = 2.915.100 \cdot 0{,}8 = 2.332.080\ \text{€} $$

$$ Z_1 = 2.332.080 \cdot 0{,}042 \cdot 1 = 97.947\ \text{€} $$

$$ \mathrm{Ann} = 2.332.080 \cdot \frac{0{,}042}{1 - 1{,}042^{-20}} = \frac{97.947}{0{,}56083} = 174.651\ \text{€} $$

$$ T_1 = 174.651 - 97.947 = 76.704\ \text{€} $$

**Schritt 6 – Steuern.**

$$ \mathrm{EBT}^{\mathrm{vA}}_1 = 319.817 - 70.160 - 97.947 = 151.710\ \text{€} $$

$$ A_1 = \frac{2.915.100}{20} = 145.755\ \text{€} $$

$$ G_1 = 151.710 - 145.755 - 0 = 5.955\ \text{€} $$

Kein Vortragsbestand ($V_1 = 0$), also $U_1 = 0$ und
$G^{\mathrm{st}}_1 = 5.955$ €:

$$ S_1 = 5.955 \cdot 0{,}23 = 1.370\ \text{€} $$

**Schritt 7 – Cashflow.**

$$ \mathrm{CF}^{\mathrm{op}}_1 = 319.817 - 70.160 - 97.947 - 1.370 = 150.340\ \text{€} $$

$$ \mathrm{CF}_1 = 150.340 - 76.704 = 73.636\ \text{€} $$

$$ \mathrm{CFADS}_1 = 319.817 - 70.160 - 1.370 = 248.287\ \text{€}, \qquad \mathrm{DSCR}_1 = \frac{248.287}{174.651} = 1{,}42 $$

**Jahr 0.**

$$ \mathrm{CF}_0 = -2.915.100 + 2.332.080 = -583.020\ \text{€} $$

## 13.3 Ergebniszeitreihe (ausgewählte Jahre)

| Jahr | Ertrag (kWh) | Marktwert (ct/kWh) | Vergütung (ct/kWh) | Erlös (€) | OPEX (€) | Zinsen (€) | Tilgung (€) | Steuer (€) | Equity-CF (€) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 5.320.000 | 4,300 | 6,500 | 319.817 | 70.160 | 97.947 | 76.704 | 1.370 | 73.636 |
| 2 | 5.306.700 | 4,470 | 6,500 | 322.311 | 71.523 | 94.726 | 79.925 | 2.371 | 73.766 |
| 3 | 5.293.433 | 4,749 | 6,500 | 329.055 | 72.912 | 91.369 | 83.282 | 4.374 | 77.117 |
| 20 | 5.072.906 | 7,304 | 7,304 | 370.525 | 101.130 | 7.040 | 167.612 | 26.818 | 67.926 |
| 21 | 5.060.224 | 7,447 | 7,447 | 376.834 | 103.096 | 0 | 0 | 62.960 | 210.778 |
| 30 | 4.947.501 | 8,142 | 8,142 | 402.842 | 122.609 | 0 | 0 | 64.454 | 215.779 |

Drei Muster lassen sich daran ablesen:

- **Bis Jahr 20** liegt der nominale Marktwert unter dem Zuschlagswert
  von 6,50 ct/kWh; der Vergütungssatz ist konstant 6,50, die Differenz
  wird als Marktprämie gezahlt. Ab Jahr 20 hat die Inflationierung den
  Marktwert über den Zuschlagswert gehoben – die Prämie ist von selbst
  auf null gelaufen, noch bevor die Förderdauer endet.
- **Ab Jahr 21** entfallen Zins und Tilgung (Kreditlaufzeit 20 Jahre).
  Der Equity-Cashflow springt von rund 68.000 € auf rund 211.000 €,
  gleichzeitig steigt die Steuerlast deutlich, weil die AfA (ebenfalls
  20 Jahre) ausgelaufen ist.
- **Die Steuerlast der ersten Jahre ist klein**, weil AfA (145.755 €/a)
  und Zinsen den Großteil des Ergebnisses aufzehren.

## 13.4 Kennzahlen

| Kennzahl | Wert |
| --- | --- |
| Investitionsvolumen $I$ | 2.915.100 € |
| Eigenkapitaleinsatz $EK$ (Jahr 0) | 583.020 € |
| EK-Rendite (XIRR) | 13,80 % |
| NPV bei 8 % | 442.171 € |
| Minimaler DSCR | 1,37 |
| Payback (kumulierter Equity-CF $\geq 0$) | Jahr 8 |
| Summe Erlöse über 30 Jahre | 10.725.258 € |

# 14 Sensitivität, Risiko und Gebotsuntergrenze


**Codestelle.** `engine/sensitivity.py` und `engine/analytics.py`.

Alle Auswertungen dieses Kapitels arbeiten ausschließlich über den
aufgelösten Parametersatz: Sie mutieren `EffectiveAssumptions` und rufen
die vollständige Bewertungskette erneut auf. Sie kennen die internen
Rechenmodule nicht und bleiben deshalb bei Änderungen an der Engine
automatisch konsistent.

## 14.1 Treibermutationen

Ein Treiber $\theta$ wird multiplikativ um den Faktor $\lambda$ variiert:

| Treiber | Mutation |
| --- | --- |
| EAG-Zuschlagswert | $z \rightarrow z \cdot \lambda$ |
| Marktwert-Niveau | $m^{\mathrm{real}}_y \rightarrow m^{\mathrm{real}}_y \cdot \lambda$ für alle Stützjahre $y$ |
| Spezifischer Ertrag | $h \rightarrow h \cdot \lambda$ |
| Investitionskosten | $I \rightarrow I \cdot \lambda$ |
| Betriebskosten | $w_j \rightarrow w_j \cdot \lambda$ für alle Standardpositionen |
| Pacht | $p \rightarrow p \cdot \lambda$; bei Umsatzbeteiligung werden Beteiligungssatz und Mindestpacht gemeinsam skaliert |
| Fremdkapitalzins | $i \rightarrow i \cdot \lambda$ |
| Negativmengen | $\nu^{\mathrm{roh}}_y \rightarrow \nu^{\mathrm{roh}}_y \cdot \lambda$ |

Die Pacht wird in `engine/opex.py` getrennt von den Standardpositionen
geführt (die Berechnung hängt vom Pachtmodus ab); der Treiber
„Betriebskosten" enthält sie deshalb nicht, die beiden Treiber
überschneiden sich nicht. Bei Umsatzbeteiligung ist die Zahlung das
Maximum aus Beteiligung und Mindestpacht – beide Terme werden gemeinsam
skaliert, da eine Variation nur eines Terms wirkungslos bliebe, sobald
der andere führt.

Die Parametervariation setzt auf Ebene der **Eingangskurve** und nicht auf
Ebene des bereits berechneten Ergebnisses an:
Eine Skalierung des Marktwert-Niveaus verändert dadurch auch die
Prämienhöhe, den Zeitpunkt, an dem der Marktwert den Zuschlagswert
übersteigt, und im relativen Modus die Direktvermarktungskosten. Damit wird der
vollständige fachliche Wirkungszusammenhang berücksichtigt.

## 14.2 EAG-Zuschlag-Sensitivität

Fünf Varianten des gebotenen Zuschlagswertes:

$$ z_k = z_{\mathrm{Gebot}} \cdot (1 + \Delta_k), \qquad \Delta_k \in \{+5\,\%,\ +2{,}5\,\%,\ 0,\ -2{,}5\,\%,\ -5\,\%\} $$

Für jede Variante wird die vollständige Bewertung neu gerechnet und
IRR und NPV ausgewiesen. Der Konventionell-Abschlag wirkt weiterhin, da
die Variante am gebotenen Wert ansetzt.

Die Stufen sind bewusst eng gefasst: In einer Ausschreibungsrunde
bewegt sich der Zuschlagswert um wenige Zehntel Cent je Kilowattstunde.
Eine Variation um 10 % beschreibt keine Entscheidung mehr, die
tatsächlich zur Wahl steht; die weiteren Spannen bleiben der
Tornado-Analyse (Abschnitt 14.3) und der Heatmap (Abschnitt 14.4)
vorbehalten.

## 14.3 Tornado-Analyse

Für jeden der acht Treiber wird die EK-Rendite bei $\lambda = 1 - \delta$
und $\lambda = 1 + \delta$ berechnet (Vorbelegung $\delta = 10\,\%$):

$$ \mathrm{Spanne}(\theta) = \left|\,\mathrm{IRR}(\theta \cdot (1+\delta)) - \mathrm{IRR}(\theta \cdot (1-\delta))\,\right| $$

Die Darstellung wird aufsteigend nach der Ergebnisbandbreite sortiert. Das
Tornado-Bild der Projektfinanzierung. Es beantwortet die Frage, welcher
Parameter die Rendite am stärksten bewegt, und damit, wo Genauigkeit in
der Datenbeschaffung am meisten wert ist.

## 14.4 IRR-Heatmap

Zwei frei wählbare Treiber werden über ein Raster kombiniert. Für jede
Achse ist eine treiberspezifische Spanne hinterlegt (z. B. ±20 % beim
Zuschlagswert, ±10 % beim Ertrag, ±30 % beim Zins):

$$ \lambda^{x}_a = 1 - \Delta_x + \frac{2\Delta_x (a-1)}{S-1}, \qquad a = 1 \dots S $$

Analog für die $y$-Achse; $S$ ist die Stufenzahl (Vorbelegung 7). Für
jede Rasterzelle $(a,b)$ wird die Bewertung vollständig neu gerechnet:

$$ \mathrm{IRR}_{a,b} = \mathrm{IRR}\left(\text{Mutation}(\lambda^{x}_a) \circ \text{Mutation}(\lambda^{y}_b)\right) $$

Das sind $S^2$ vollständige Bewertungen (Vorbelegung 49).

## 14.5 Monte-Carlo-Simulation

Je Lauf $k = 1 \dots K$ werden für die aktiven Treiber unabhängige
multiplikative Faktoren gezogen:

$$ \lambda^{(k)}_\theta = \max\left(\,\xi,\ 0{,}4\,\right), \qquad \xi \sim \mathcal{N}\left(1,\ \sigma_\theta^2\right) $$

Vorbelegte Standardabweichungen: Ertrag 5 %, Marktwert-Niveau 10 %,
CAPEX 5 %, OPEX 5 %. Die Untergrenze 0,4 verhindert unphysikalische
Ausreißer (negative Erträge oder negative Investitionskosten) bei großen
Streuungen.

Gesammelt werden je Lauf IRR, NPV zum gewählten Diskontsatz und der
gesamte Pfad des kumulierten Equity-Cashflows. Daraus entstehen:

$$ \mathrm{P}q_t = \text{empirisches } q\text{-Quantil von } \left\{\mathrm{CF}^{\mathrm{kum},(k)}_t\right\}_{k=1}^{K}, \qquad q \in \{10, 25, 50, 75, 90\} $$

$$ \Pr\left[\mathrm{IRR} \geq \mathrm{Ziel}\right] = \frac{\left|\left\{k \ :\ \mathrm{IRR}^{(k)} \geq \mathrm{Ziel}\right\}\right|}{K} $$

Zwei Festlegungen sind wichtig für die Belastbarkeit:

- Der Zufallsgenerator ist mit einem **festen Startwert** initialisiert.
  Dieselben Eingaben liefern damit exakt dieselbe Verteilung –
  Voraussetzung für Caching und für die Nachvollziehbarkeit in
  Gremienunterlagen.
- Läufe ohne berechenbaren IRR gehen in den Nenner, aber nicht in den
  Zähler der Erfolgswahrscheinlichkeit ein und werden damit konservativ als
  **Zielverfehlung** klassifiziert.

Optional kann der EAG-Zuschlagswert je Lauf aus der Gebotsverteilung des
Auktionsmodells gezogen werden (Kapitel 15.8). Dann enthält die
IRR-Verteilung zusätzlich die Auktionsunsicherheit:

$$ z^{(k)} = b^{(k)} \cdot \frac{z}{z_{\mathrm{Gebot}}} $$

Der zweite Faktor erhält den Konventionell-Abschlag des Projekts.

## 14.6 Break-even-Zuschlagswert (Gebotsassistent)

Gesucht ist der kleinste anzulegende Wert, mit dem eine Ziel-EK-Rendite
gerade noch erreicht wird – die **wirtschaftliche Untergrenze** für ein
Auktionsgebot:

$$ \text{Finde } b^{*} \text{ mit } \mathrm{IRR}\left(b^{*}\right) = \mathrm{IRR}^{\mathrm{Ziel}}, \qquad b^{*} \in [0{,}5,\ 15]\ \text{ct/kWh} $$

Gelöst wird wieder mit `brentq` auf der monoton steigenden Funktion
$b \mapsto \mathrm{IRR}(b) - \mathrm{IRR}^{\mathrm{Ziel}}$. Zwei Randfälle
werden ausdrücklich behandelt:

- Ist das Ziel bereits am unteren Rand erreicht, trägt der Marktwert das
  Projekt praktisch allein; ausgewiesen wird die untere Suchgrenze.
- Ist das Ziel am oberen Rand nicht erreichbar, wird **kein** Wert
  ausgewiesen (das Ziel ist mit diesem Projekt nicht erreichbar).

Nicht berechenbare IRR-Werte werden in der Nullstellensuche konservativ
als −100 % behandelt, damit die Suche nicht an einem undefinierten Wert
abbricht.

## 14.7 Szenarienvergleich

Dasselbe Projekt wird über alle hinterlegten Marktpreisszenarien
gerechnet. Ausgetauscht werden je Szenario ausschließlich die
Marktwertkurve und die Negativmengenkurve; alle übrigen Parameter bleiben
identisch. Verglichen werden IRR, NPV und Gesamterlös sowie die
kumulierten Equity-Cashflow-Pfade.

# 15 Empirisches Modell der EAG-Ausschreibungen

**Zweck.** Aus den veröffentlichten Aggregaten vergangener
Ausschreibungsrunden eine Verteilung der Zuschlagswerte schätzen, daraus
die Zuschlagswahrscheinlichkeit eines Gebots ableiten und ein Gebot zur
gewünschten Risikoneigung empfehlen.

**Codestelle.** `engine/auktion.py`, Daten in `data/ausschreibungen.yaml`.

## 15.1 Fachlicher Rahmen

Die österreichischen EAG-Marktprämienausschreibungen für Photovoltaik
funktionieren nach **Pay-as-Bid mit Gebotspreisreihung**: Gebote werden
aufsteigend gereiht und bis zur ausgeschriebenen Menge bezuschlagt; jeder
Gewinner erhält seinen **eigenen** Gebotswert als anzulegenden Wert. Eine
Preisobergrenze wird per Verordnung festgelegt; Gebote darüber sind
ungültig.

Das Modell nimmt konsequent die **Price-Taker-Sicht** ein: Ein einzelner
Bieter beeinflusst den Grenzzuschlagswert nicht messbar. Aus dieser Perspektive ist die Zuschlagsentscheidung von einer exogenen
Zufallsvariable abhängig, dem Grenzzuschlagswert $p_m$ der nächsten Runde.

Die Auktionsliteratur beschreibt für Pay-as-Bid-Verfahren ein Muster, das
auch in den vorliegenden Aggregatdaten erkennbar ist: Bieter setzen ihr Gebot knapp unter den
erwarteten Grenzzuschlag („bid shading“). Bei schwachem Wettbewerb liegen
die Gebote nahe der Preisobergrenze; mit steigendem Wettbewerb sinken sie
und verdichten sich.

## 15.2 Datenlage und ihre Konsequenzen

Veröffentlicht werden je Runde nur **Aggregate** der bezuschlagten
Gebote: Minimum, mengengewichteter Mittelwert, Maximum sowie
ausgeschriebene und bezuschlagte Menge und die Preisobergrenze.
Einzelgebote werden nicht veröffentlicht.

Daraus folgt unmittelbar die Methodenwahl: Verfahren auf Rohgeboten
(Kerndichteschätzung, Mischverteilungen) scheiden aus. Es bleibt die
Anpassung **parametrischer, auf $[0, c]$ beschränkter Verteilungs-
familien** über Momenten- und Quantilbedingungen, wobei $c$ die
Preisobergrenze ist.

**Regimeerkennung.** Entscheidend ist, ob eine Runde unterzeichnet oder
überzeichnet war:

$$ \text{Runde } j \text{ gilt als unterzeichnet} \quad \Leftrightarrow \quad \max_j \geq c_j - 0{,}02\ \text{ct/kWh} $$

- **Unterzeichnet**: Der Höchstzuschlag liegt (bis auf Rundung) an der
  Obergrenze. Das Gebotsvolumen hat nicht ausgereicht, um die Grenze zu
  drücken; alle gültigen Gebote wurden bezuschlagt. Die veröffentlichten
  Aggregate beschreiben damit die **volle** Gebotsverteilung, und die
  Wettbewerbsquote ist direkt beobachtbar:

$$ r_j = \frac{\text{bezuschlagte Menge}_j}{\text{ausgeschriebene Menge}_j} $$

- **Überzeichnet**: Der Höchstzuschlag liegt unter der Obergrenze; die
  ausgeschriebene Menge ist nahezu vollständig ausgeschöpft. Die Aggregate beschreiben nur den
  **unteren, bezuschlagten Teil** der Gebotsverteilung. Das eingereichte
  Gebotsvolumen wird nicht veröffentlicht – die Wettbewerbsquote ist
  **latent** und muss geschätzt werden (Abschnitt 15.5).

## 15.3 Verteilungsfamilien auf $[0, c]$

Alle Familien werden einheitlich über zwei Parameter beschrieben, damit
sie unmittelbar vergleichbar sind und der Wettbewerbs-Link
familienunabhängig formuliert werden kann:

$$ \mu_{\mathrm{rel}} = \frac{\mathbb{E}[b]}{c} \in (0,1) \quad \text{(Lage)}, \qquad \kappa > 0 \quad \text{(Konzentration)} $$

**Beta (Vorbelegung).** Skalierte Beta-Verteilung auf $[0,c]$:

$$ \frac{b}{c} \sim \mathrm{Beta}(\alpha, \beta), \qquad \alpha = \mu_{\mathrm{rel}} \kappa, \quad \beta = (1-\mu_{\mathrm{rel}})\kappa $$

$$ \mathbb{E}\left[\frac{b}{c}\right] = \frac{\alpha}{\alpha+\beta} = \mu_{\mathrm{rel}}, \qquad \mathrm{Var}\left[\frac{b}{c}\right] = \frac{\mu_{\mathrm{rel}}(1-\mu_{\mathrm{rel}})}{\kappa+1} $$

Die Verteilung ist aufgrund ihres Trägers auf $[0,c]$ beschränkt und kann
unterschiedliche Schiefegrade abbilden. Für
$\mu_{\mathrm{rel}}$ nahe 1 bei moderatem $\kappa$ ergibt sich eine Verteilungsform mit hoher Wahrscheinlichkeitsmasse nahe
der Obergrenze und einem ausgeprägten linken Ausläufer.

**Kumaraswamy.** Der Beta sehr ähnlich, aber mit analytischer
Quantilfunktion:

$$ F(x) = 1 - \left(1 - \left(\frac{x}{c}\right)^{a}\right)^{\beta}, \qquad Q(q) = c\left(1 - (1-q)^{1/\beta}\right)^{1/a} $$

Die Formparameter heißen hier $a$ und $\beta$ (nicht $a, b$ wie in der
Literatur – $b$ ist in diesem Kapitel das Gebot). Ihre Umrechnung aus
$(\mu_{\mathrm{rel}}, \kappa)$ erfolgt numerisch:
$a = \max(\kappa \mu_{\mathrm{rel}},\ 0{,}05)$, und $\beta$ wird so bestimmt,
dass die Momentbedingung erfüllt ist:

$$ \mathbb{E}\left[\frac{b}{c}\right] = \beta \cdot B\left(1 + \frac{1}{a},\ \beta\right) = \mu_{\mathrm{rel}} $$

Gelöst wird über $\ln \beta$ mit `brentq` im Intervall $[-8, 10]$.

**Trunkierte Normalverteilung.** Bewusst als symmetrische
Vergleichsbasis:

$$ b \sim \mathcal{N}\left(\mu_{\mathrm{rel}} c,\ \left(\frac{c}{\kappa}\right)^2\right) \text{ trunkiert auf } [0, c] $$

Sie kann die harte Obergrenze abbilden, aber keinen langen linken
Ausläufer bei gleichzeitig hoher Konzentration rechts ; diese Einschränkung zeigt sich in der Validierung.

**Gespiegelte inverse Gamma.** Modelliert den Abstand zur Obergrenze:

$$ b = c - Y, \qquad Y \sim \mathrm{InvGamma}\left(a,\ \text{scale}\right), \quad a = \max(\kappa,\ 1{,}1) $$

$$ \text{scale} = c\left(1 - \mu_{\mathrm{rel}}\right)(a-1) \ \Longrightarrow\ \mathbb{E}[Y] = c(1-\mu_{\mathrm{rel}}) \ \Longrightarrow\ \mathbb{E}[b] = \mu_{\mathrm{rel}} c $$

Die Dichte fällt zur Obergrenze hin stark gegen null und weist nach links
einen langsam abklingenden Ausläufer auf. Damit lässt sich die für wettbewerbliche Pay-as-Bid-Verfahren
plausible Konzentration der Dichte knapp unterhalb des erwarteten
Grenzzuschlags abbilden. Ihre
prinzipielle Grenze: Masse **direkt an** der Obergrenze (wie in
unterzeichneten Runden beobachtet) kann sie nicht abbilden.

## 15.4 Trunkierter Erwartungswert

Für überzeichnete Runden ist der bedingte Erwartungswert unterhalb des
Grenzzuschlags erforderlich. Er wird für alle Familien einheitlich über die
Quantilfunktion berechnet – numerisch stabil auch dort, wo keine
geschlossene Form existiert:

$$ \mathbb{E}\left[b \ \middle|\ b \leq u\right] = \frac{1}{F(u)} \int_{0}^{F(u)} Q(v)\, dv \ \approx\ \frac{1}{n}\sum_{k=1}^{n} Q(v_k), \quad v_k \text{ gleichverteilt in } (0, F(u)) $$

mit $n = 400$ Stützstellen.

## 15.5 Anpassung je Runde

Je Runde $j$ werden zwei robuste Bedingungen an die Verteilung gestellt:

**(a) Mittelwertbedingung.**

$$ \text{unterzeichnet:} \quad \mathbb{E}[b] = \overline{b}_j $$

$$ \text{überzeichnet:} \quad \mathbb{E}\left[b \ \middle|\ b \leq \max_j\right] = \overline{b}_j $$

**(b) Minimumbedingung.** Das veröffentlichte Minimum der Zuschlagswerte
wird als niedriges Quantil **aller** Gebote interpretiert – das
günstigste Gebot gewinnt immer:

$$ Q(\varepsilon_{\min}) = \min_j, \qquad \varepsilon_{\min} = 0{,}02 $$

> **Annahme.** $\varepsilon_{\min} = 2\,\%$ entspricht der Größenordnung
> von 40 bis 80 Geboten je Runde. Die Ergebnisse reagieren auf diese
> Annahme nur schwach, weil sie den linken Ausläufer betrifft, während
> die Gebotsentscheidung am rechten Rand fällt.

Geschätzt wird über transformierte Parameter, damit die Suche
unbeschränkt laufen kann:

$$ \theta_1 = \mathrm{logit}\left(\mu_{\mathrm{rel}}\right) = \ln\frac{\mu_{\mathrm{rel}}}{1-\mu_{\mathrm{rel}}}, \qquad \theta_2 = \ln \kappa $$

$$ \hat{\theta} = \arg\min_{\theta} \left[ \left(\mathbb{E}_\theta - \overline{b}_j\right)^2 + \left(Q_\theta(\varepsilon_{\min}) - \min_j\right)^2 \right] $$

Verfahren: Trust-Region-Reflective-Kleinstquadrate mit den Schranken
$\theta_1 \in [-8, 8]$ und $\kappa \in [1{,}05,\ 800]$, Startwert
$\mu_{\mathrm{rel}} = 0{,}85$, $\kappa = 8$.

**Wettbewerbsquote.** Bei überzeichneten Runden wird sie aus dem Fit
zurückgerechnet. Alle Gebote bis $p_m$ erhalten einen Zuschlag; ihr
Anteil an allen Geboten ist $F(p_m)$, und dieser Anteil entspricht dem
Kehrwert der Überzeichnung:

$$ r_j = \frac{1}{F\left(\max_j\right)} $$

Ein Fit-Residuum (Wurzel des mittleren quadratischen Restfehlers beider
Bedingungen) wird je Runde mitgeführt und dient dem Familienvergleich.

## 15.6 Wettbewerbs-Link

Über alle Runden hinweg wird der Zusammenhang zwischen Wettbewerbsintensität
und Verteilungsform linear in den transformierten Größen geschätzt
(gewöhnliche Kleinstquadrate):

$$ \mathrm{logit}\left(\mu_{\mathrm{rel},j}\right) = a_L + b_L \ln r_j + \epsilon_j $$

$$ \ln \kappa_j = a_K + b_K \ln r_j + \eta_j $$

Umgekehrt liefert der Link zu einer gegebenen Wettbewerbsquote die
Verteilungsparameter:

$$ \mu_{\mathrm{rel}}(r) = \frac{1}{1 + e^{-\left(a_L + b_L \ln r\right)}}, \qquad \kappa(r) = \max\left(e^{\,a_K + b_K \ln r},\ 1{,}05\right) $$

Die Residuen $\epsilon_j, \eta_j$ sind das Maß der Prognoseunsicherheit
dieses Zusammenhangs.

**Lokales Trendmodell.** Für die Rundenprognose werden zusätzlich die
Änderungen der transformierten Parameter zwischen aufeinanderfolgenden
**Wettbewerbsrunden** ausgewertet:

$$ \Delta_j = \mathrm{logit}\left(\mu_{\mathrm{rel},j}\right) - \mathrm{logit}\left(\mu_{\mathrm{rel},j-1}\right) $$

$$ \mathrm{Drift} = 0, \qquad \mathrm{sd} = \mathrm{clip}\left(\mathrm{StdAbw}\left(\Delta\right),\ 0{,}15,\ 0{,}8\right) $$

> **Annahme (Random Walk).** Bei bisher nur drei beobachteten
> Rundenänderungen – davon eine Regimeänderung – ist die sparsamste
> belastbare Annahme ein Drift von null: Die zentrale Prognosewelt
> entspricht der letzten Runde, angepasst um Wettbewerbsquote und
> Obergrenze. Die **Streuung** der beobachteten Änderungen geht als
> Prognoseunsicherheit ein; sie ist nach oben begrenzt, weil die
> Rundenschwankung der Fit-Parameter auch Kalibrierrauschen enthält
> (aus Aggregaten ist $\kappa$ nur grob identifiziert).

## 15.7 Familienvergleich und Validierung

Die Auswahl der Verteilungsfamilie erfolgt anhand von drei
Validierungskriterien:

**(1) Massentreue an der Obergrenze.** In unterzeichneten Runden liegt
der Höchstzuschlag an der Obergrenze. Eine Familie muss dort noch
spürbare Masse tragen:

$$ 1 - F\left(0{,}99\,c\right) \geq \frac{1}{50} $$

Ausgewiesen wird der Anteil verletzter Runden.

**(2) Leave-one-out-Prognose des Grenzzuschlags.** Für jede überzeichnete
Runde wird das Modell **ohne** diese Runde kalibriert und der
Grenzzuschlag bei gegebener (aus der Runde geschätzter) Wettbewerbsquote
prognostiziert:

$$ \hat{p}_m = Q_{\mu_{\mathrm{rel}}(r),\ \kappa(r)}\left(\min\left(1,\ \frac{1}{r}\right)\right), \qquad \mathrm{RMSE} = \sqrt{\frac{1}{J}\sum_j \left(\hat{p}_{m,j} - p_{m,j}\right)^2} $$

**(3) Mittleres Fit-Residuum** der beiden Kalibrierbedingungen über alle
Runden.

Zusätzlich wird jede Leave-one-out-Prognose gegen eine **naive
Basislinie** gestellt – die Fortschreibung des zuletzt beobachteten
Höchstzuschlags. Diese Referenz bildet den Vergleichsmaßstab für die Beurteilung, ob das
Modell gegenüber einer einfachen Fortschreibung einen geringeren
Prognosefehler erzielt.

## 15.8 Prognose und Gebotsempfehlung

Zwei Modi stehen zur Verfügung.

### 15.8.1 Modus „letzte Runde gesetzt“

Die zuletzt beobachtete Ausschreibung gilt als maßgeblich. Verwendet
werden ihre gefittete Verteilung, ihr Grenzzuschlag und ihre
Wettbewerbsquote. Mit dem Zuschlagsanteil

$$ q_c = \min\left(1,\ \frac{1}{r}\right) $$

gilt für ein Gebot $b$:

$$ \Pr\left[\text{Zuschlag}\right] = \mathrm{clip}\left(\frac{q_c - F(b)}{q_c},\ 0,\ 1\right) $$

Dieser Ausdruck entspricht dem Anteil der Zuschlagswerte der betrachteten
Runde, die oberhalb des eigenen Gebots liegen, und damit dessen Quantilslage
innerhalb der Verteilung. Zur Zielwahrscheinlichkeit $z$ folgt das empfohlene
Gebot:

$$ b^{*}(z) = Q\left((1-z)\, q_c\right) $$

### 15.8.2 Modus „Prognose der nächsten Runde“

**Schritt 1: Punktprognosen per Differenzenextrapolation.** Für
Grenzzuschlag und mengengewichteten Mittelwert wird die Zeitreihe der
Wettbewerbsrunden fortgeschrieben. Mit den rekursiven Differenzen

$$ \Delta^{(k)}_t = \Delta^{(k-1)}_t - \Delta^{(k-1)}_{t-1}, \qquad \Delta^{(0)}_t = x_t $$

lautet die Extrapolation der Ordnung $m$:

$$ D^{(m)} = \Delta^{(m)}_t $$

$$ D^{(k)} = \Delta^{(k)}_t + \lambda_k \cdot D^{(k+1)}, \qquad k = m-1, \dots, 1 $$

$$ \hat{x}_{t+1} = x_t + D^{(1)} $$

Die Dämpfungsparameter $\lambda_k \in [0,1]$ steuern, wie stark höhere
Ableitungen eingehen: $\lambda = 1$ übernimmt Trend **und** Beschleunigung
voll, $\lambda \rightarrow 0$ nähert sich der linearen Fortschreibung. Die
effektive Ordnung ist durch die Anzahl der Stützstellen begrenzt; eine
Ordnung $m$ erfordert $m+1$ Beobachtungen. Bei nur einer Stützstelle wird
der zuletzt beobachtete Wert fortgeschrieben (Random Walk).

**Schritt 2: Projektion auf den zulässigen Bereich.**

$$ \hat{p}_m = \mathrm{clip}\left(\hat{x}^{\max}_{t+1},\ 0{,}5,\ c - 0{,}02\right), \qquad \hat{\overline{b}} = \mathrm{clip}\left(\hat{x}^{\,\overline{b}}_{t+1},\ 0{,}3,\ \hat{p}_m - 0{,}05\right) $$

Das Minimum wird aufgrund der fehlenden stabilen Dynamik unverändert
fortgeschrieben (Random Walk) und auf einen Wert unterhalb des
prognostizierten Mittelwerts begrenzt.

**Schritt 3: Verteilung aus den Punktprognosen.** Methodisch identisch
zum Fit der historischen Runden, mit dem Unterschied, dass die
Mittelwertbedingung stark gewichtet wird (Faktor 8) – sie ist die vom
Verfahren vorgegebene Größe, während das Minimum als schwächer gewichtete Nebenbedingung für den linken
Ausläufer eingeht:

$$ \hat{\theta} = \arg\min_{\theta}\left[ 64 \left(\mathbb{E}_\theta\left[b \mid b \leq \hat{p}_m\right] - \hat{\overline{b}}\right)^2 + \left(Q_\theta(\varepsilon_{\min}) - \min\right)^2 \right] $$

Die Wettbewerbsquote ist in diesem Modus **impliziert** und wird
ausgewiesen:

$$ \hat{r} = \frac{1}{F\left(\hat{p}_m\right)} $$

**Schritt 4: Unsicherheit des Grenzzuschlags.** Um die Punktprognose wird
eine an der Obergrenze und bei 0,5 ct/kWh trunkierte Normalverteilung
gelegt:

$$ p_m \sim \mathcal{N}\left(\hat{p}_m,\ \sigma_{p_m}^2\right) \text{ trunkiert auf } \left[0{,}5,\ c\right] $$

$$ \sigma_{p_m} = \mathrm{clip}\left(\mathrm{StdAbw}\left(\text{Rundenänderungen des Höchstzuschlags}\right),\ 0{,}15,\ 0{,}8\right) $$

Die Trunkierung beschränkt den Grenzzuschlag auf den zulässigen Wertebereich.
Für die numerische Auswertung werden 4.000 Szenarien simuliert.

**Schritt 5: Entscheidungsgrößen.** Als Price-Taker gilt: Ein Gebot $b$
erhält genau dann einen Zuschlag, wenn der Grenzzuschlag darüber liegt.

$$ \Pr\left[\text{Zuschlag}(b)\right] = \Pr\left[p_m > b\right] \approx \frac{1}{n}\left|\left\{k : p_m^{(k)} > b\right\}\right| $$

$$ b^{*}(z) = \text{empirisches } (1-z)\text{-Quantil von } \left\{p_m^{(k)}\right\} $$

Aus der Quantildefinition folgt, dass mit zunehmender angestrebter
Zuschlagswahrscheinlichkeit ein niedrigeres Gebot erforderlich ist.

**Schritt 6: Ziehungen für die Monte-Carlo-Kopplung.** Für die Simulation
werden stochastische Realisationen erfolgreicher Zuschlagswerte erzeugt:

$$ u \sim \mathcal{U}(0,\ q_c), \qquad b^{\mathrm{basis}} = Q(u) $$

$$ b^{(k)} = \mathrm{clip}\left(b^{\mathrm{basis}} + \left(p_m^{(k)} - \hat{p}_m\right),\ 0,\ c\right) $$

Die zentrale Verteilung wird in jeder Simulationswelt parallel zum gezogenen
Grenzzuschlag verschoben. Die **Form** bleibt erhalten; ausschließlich die Lage
folgt der Unsicherheit. Im Modus „letzte Runde“ entfällt die
Verschiebung.

## 15.9 Deutschland: manuelle Vorgabe

Im deutschen EEG-Marktsystem entfällt das empirische Modell: Der erwartete
Marktprämienzuschlag (anzulegender Wert) wird direkt als Zahl
eingetragen. Die Historie der österreichischen OeMAG-Ausschreibungen ist
für die deutschen Ausschreibungen nicht aussagekräftig. Eine unmittelbare
Übertragung wäre aufgrund der abweichenden Auktionssystematik methodisch
nicht belastbar. Alles Weitere – Cashflow,
Steuern, Kennzahlen – ist identisch; nur die Herkunft von $z$
unterscheidet sich.

# 16 Portfolio- und Vergleichsrechnungen

Über die Einzelprojektbewertung hinaus aggregiert die Anwendung über alle
**aktiven** Projekte. Inaktive Projekte bleiben im Datenbestand erhalten, werden jedoch bei der
Berechnung der Portfoliokennzahlen nicht berücksichtigt.

$$ P^{\mathrm{ges}} = \sum_{v} P_v, \qquad I^{\mathrm{ges}} = \sum_{v} I_v, \qquad EK^{\mathrm{ges}} = \sum_{v} EK_v $$

$$ \overline{\mathrm{IRR}} = \frac{1}{\left|\mathcal{V}\right|}\sum_{v \in \mathcal{V}} \mathrm{IRR}_v, \qquad \mathcal{V} = \left\{v : \mathrm{IRR}_v \text{ berechenbar}\right\} $$

> Die Portfolio-Rendite ist ein **ungewichtetes arithmetisches Mittel**
> der Projekt-IRR, keine kapitalgewichtete Portfolio-IRR. Sie beantwortet
> die Frage „wie rentabel sind die Projekte im Schnitt“, nicht „welche
> Rendite erzielt das eingesetzte Kapital insgesamt“. Für die zweite
> Frage müssten die Cashflows aller Projekte zunächst datumsgenau
> zusammengeführt und daraus ein gemeinsamer XIRR bestimmt werden.

Für die Rendite-Risiko-Landkarte wird je Projekt das spezifische Invest
gebildet:

$$ \text{Invest}_v = \frac{I_v}{P_v} \quad \left[\text{€/kWp}\right] $$

**Wertbrücke.** Die Brücke über die Gesamtlaufzeit summiert jede
Cashflow-Komponente über alle Jahre und stellt sie als Wasserfall dar:

$$ \sum_t R_t \ -\ \sum_t C_t \ -\ \sum_t Z_t \ -\ \sum_t S_t \ =\ \sum_t \mathrm{CF}^{\mathrm{op}}_t $$

$$ \sum_t \mathrm{CF}^{\mathrm{op}}_t \ -\ I \ +\ D \ -\ \sum_t T_t \ =\ \mathrm{CF}^{\mathrm{kum}}_N $$

Beide Identitäten gelten exakt – sie sind die Probe darauf, dass die
Cashflow-Aggregation vollständig ist.

# 17 Modellannahmen, Vereinfachungen und Geltungsgrenzen

Dieses Kapitel sammelt alle Stellen, an denen das Modell eine Entscheidung
trifft, die über die reine Rechenvorschrift hinausgeht. Wer Ergebnisse
interpretiert, sollte diese Liste kennen.

## 17.1 Zeit und Perioden

| Nr. | Annahme | Wirkung |
| --- | --- | --- |
| A1 | Betriebsperioden sind Kalenderjahre; nur das Anlaufjahr ist anteilig | Der Sonderfall „Vertragsende am Jahrestag der Inbetriebnahme“ ist nicht abgebildet |
| A2 | Anteilsfaktor bei 1 gekappt | Schaltjahre erzeugen keinen 366/365-Effekt |
| A3 | Alle Zahlungen eines Jahres wirken zum Jahresende | Unterjährige Zahlungsströme werden nicht abgebildet; die Diskontierung ist dennoch taggenau |

## 17.2 Erlöse

| Nr. | Annahme | Wirkung |
| --- | --- | --- |
| A4 | Kurvenwerte außerhalb des Stützbereichs werden geklemmt | Konservativ gegenüber Extrapolation, unterschätzt aber langfristige Preistrends |
| A5 | Inflationierung mit dem tatsächlichen Kalenderjahr, auch bei geklemmtem Realwert | Nominale Fortschreibung des letzten bekannten Realpreises |
| A6 | Der EAG-Zuschlagswert ist nominal fix | Entspricht der gesetzlichen Regelung, keine Vereinfachung |
| A7 | Negative Preise wirken über einen jährlichen Mengenanteil, nicht stundenscharf | Innerjährliche Korrelation von Erzeugung und Preis wird nicht modelliert |
| A8 | Kein Eigenverbrauch, keine Speicher, keine Regelenergie- oder PPA-Erlöse | Reines Marktprämien-/Marktverkaufsmodell |

## 17.3 Kosten und Finanzierung

| Nr. | Annahme | Wirkung |
| --- | --- | --- |
| A9 | Keine Bauzeitzinsen, keine Zwischenfinanzierung, kein Disagio | Solche Kosten müssen im CAPEX erfasst werden |
| A10 | Ein Kredit, feste Kondition über die gesamte Laufzeit | Keine Zinsbindungsfristen, keine Anschlussfinanzierung |
| A11 | Der Anteilsfaktor des Anlaufjahres reduziert nur den Zins, nicht die Tilgung | Bei Annuität wird im Anlaufjahr modellgemäß ein höherer Tilgungsanteil angesetzt |
| A12 | Keine Liquiditätsreserve, kein Schuldendienstreservekonto | DSCR wird ausgewiesen, aber nicht als Nebenbedingung erzwungen |
| A13 | Kein Restwert und keine Rückbaukosten am Ende der Betriebsdauer | Beides ist gegebenenfalls über CAPEX bzw. eine OPEX-Position abzubilden |
| A13a | DSCR-Kovenanten wirken nicht auf die Cashflow-Rechnung zurück | Cash Trap und Equity Cure werden als Prüfung ausgewertet, nicht als Zahlungsstrom gebucht |
| A13b | Ausgeschüttete Mittel gelten als in voller Höhe rückführbar | Der Deckungswasserfall beziffert die Obergrenze der Deckung aus eigener Kraft |

## 17.4 Steuern

| Nr. | Annahme | Wirkung |
| --- | --- | --- |
| A14 | Lineare AfA über die gesamte Investitionssumme | Keine Komponentenaufteilung, keine degressive Abschreibung, kein Investitionsfreibetrag |
| A15 | Verlustvortrag zeitlich unbegrenzt, Verrechnungsgrenze je Gewinnjahr | Entspricht § 8 Abs. 4 Z 2 KStG |
| A16 | Deutsche Gewerbesteuer ohne Verlustvortrag nach § 10a GewStG | Bewusst, zur Deckungsgleichheit mit dem Referenzmodell |
| A17 | Keine Umsatzsteuer, keine Grundsteuer, keine Kapitalertragsteuer auf Ausschüttungen | Betrachtung endet auf Ebene der Projektgesellschaft |

## 17.5 Kennzahlen und Auswertungen

| Nr. | Annahme | Wirkung |
| --- | --- | --- |
| A18 | IRR nur bei Vorzeichenwechsel im Cashflow; sonst kein Wert | Kein Ersatzwert, der als Rendite fehlgelesen werden könnte |
| A19 | Payback undiskontiert, in vollen Jahren | Keine unterjährige Interpolation |
| A20 | Monte-Carlo-Treiber sind unabhängig normalverteilt | Korrelationen (z. B. Marktwert-Niveau mit negativen Stunden) sind nicht abgebildet |
| A21 | Fester Startwert des Zufallsgenerators | Reproduzierbar, aber keine Stichprobenvariation über Läufe hinweg |
| A22 | Portfolio-IRR als ungewichtetes Mittel | Keine kapitalgewichtete Portfoliorendite |

## 17.6 Auktionsmodell

| Nr. | Annahme | Wirkung |
| --- | --- | --- |
| A23 | Price-Taker-Sicht | Das eigene Gebot beeinflusst den Grenzzuschlag nicht |
| A24 | $\varepsilon_{\min} = 2\,\%$ für die Minimumbedingung | Schwacher Einfluss, betrifft nur den linken Ausläufer |
| A25 | Random Walk statt geschätztem Drift | Zentrale Prognose entspricht der letzten Runde |
| A26 | Wettbewerbsquote überzeichneter Runden aus dem Fit rückgeschätzt | Das eingereichte Gebotsvolumen wird nicht veröffentlicht |
| A27 | Verteilungsfamilie ist eine Modellwahl | Wird über Massentreue, Leave-one-out und Fit-Residuum geprüft, nicht gesetzt |

## 17.7 Daten

Die mitgelieferten Preiskurven sind plausible Platzhalter beziehungsweise
Studienauszüge, keine für den Einzelfall validierten Marktprognosen. Vor
einer Investitionsentscheidung sind sie durch aktuelle, lizenzierte
Marktwert-Solar-Kurven zu ersetzen. Das Modell selbst ist davon
unberührt – es rechnet mit der Kurve, die hinterlegt ist.

# 18 Nachvollziehbarkeit und Verifikation

## 18.1 Zuordnung Rechenschritt zu Code und Test

| Kapitel | Rechenschritt | Codestelle | Test |
| --- | --- | --- | --- |
| 4 | Parameterauflösung | `engine/pipeline.py: resolve_assumptions` | `tests/test_pipeline_kpis_io.py` |
| 5 | Zeitachse, Anteilsfaktoren | `engine/timeline.py` | `tests/test_timeline_energy_opex.py` |
| 6 | Energieertrag | `engine/energy.py` | `tests/test_timeline_energy_opex.py` |
| 7 | Erlöse, Marktprämie | `engine/revenue.py` | `tests/test_revenue.py` |
| 8 | Betriebskosten | `engine/opex.py` | `tests/test_timeline_energy_opex.py`, `tests/test_model_optionen.py` |
| 9 | Finanzierung | `engine/financing.py` | `tests/test_financing_tax.py` |
| 10 | Steuern | `engine/tax.py` | `tests/test_financing_tax.py`, `tests/test_markt_system.py` |
| 11 | Cashflow | `engine/cashflow.py` | `tests/test_pipeline_kpis_io.py` |
| 11.5 | DSCR-Kovenanten | `engine/covenants.py` | `tests/test_covenants.py` |
| 12 | Kennzahlen, LCOE | `engine/kpis.py`, `engine/analytics.py` | `tests/test_pipeline_kpis_io.py`, `tests/test_analytics.py` |
| 13 | Beispielrechnung | `docs/rechenmodell/beispiel.py` | `tests/test_dokumentation.py` |
| 14 | Sensitivität, Monte Carlo | `engine/sensitivity.py`, `engine/analytics.py` | `tests/test_analytics.py` |
| 15 | Auktionsmodell | `engine/auktion.py` | `tests/test_auktion.py` |
| 16 | Portfolio, Wertbrücke | `app/views/overview.py`, `app/components/charts.py` | `tests/test_ui_smoke.py` |
| – | Seitensteuerung, Projektseite | `app/router.py`, `app/views/project_page.py` | `tests/test_navigation.py` |

## 18.2 Teststrategie

Die Einheitstests rechnen gegen **handgerechnete Erwartungswerte** auf
einem bewusst vereinfachten Fixture-Projekt: flache Marktwertkurve von
4 ct/kWh, Inflation aus, keine negativen Stunden, keine Kosteninflation.
Damit ist jeder Erwartungswert im Test selbst nachrechenbar, und ein
Fehler in der Engine kann sich nicht in den Erwartungswerten verstecken.

Die End-to-End-Tests prüfen zusätzlich strukturelle Eigenschaften, die
unabhängig von konkreten Zahlen gelten müssen: Konsistenz der
Cashflow-Kategorien, Monotonie der NPV-Kurve im Diskontsatz, Monotonie
der Sensitivität im Zuschlagswert, verlustfreie Roundtrips über YAML und
Excel.

Die Fixtures hängen ausdrücklich **nicht** an den änderbaren
Beispieldaten unter `data/` – Nutzer können dort frei editieren, ohne
Tests zu brechen. Die einzige Ausnahme ist
`tests/test_dokumentation.py`, der explizit prüft, ob die in Kapitel 13
abgedruckten Zahlen noch zum Beispielprojekt passen.

## 18.3 Symbol, Spaltenname, Export

Die folgende Tabelle verbindet die Notation dieses Dokuments mit den
Spaltennamen in Cashflow-Tabelle, Excel-Export und Oberfläche.

| Symbol | Spalte in der Cashflow-Tabelle | Einheit |
| --- | --- | --- |
| $E_t$ | `produktion_kwh` | kWh |
| $m^{\mathrm{real}}_t$ | `marktwert_real_ct_kwh` | ct/kWh |
| $m_t$ | `marktwert_nominal_ct_kwh` | ct/kWh |
| $s_t$ | `verguetungssatz_ct_kwh` | ct/kWh |
| $R_t$ | `erloes_eur` | € |
| $R^{\mathrm{markt}}_t$ | `erloes_markt_eur` | € |
| $R^{\text{Prämie}}_t$ | `erloes_praemie_eur` | € |
| $C_t$ | `opex_gesamt_eur` | € |
| $C^{\mathrm{gem}}_t$ | `gemeindeabgabe_eur` | € |
| $C^{\mathrm{dv}}_t$ | `direktvermarktungskosten_eur` | € |
| $C^{(j)}_t$ | eine Spalte je Positionsname (z. B. `Pacht`) | € |
| $Z_t$ | `zinsen_eur` | € |
| $T_t$ | `tilgung_eur` | € |
| $A_t$ | `afa_eur` | € |
| $G_t$ | `steuerliches_ergebnis_vor_verlustvortrag_eur` | € |
| $U_t$ | `verlustvortrag_genutzt_eur` | € |
| $V_{t+1}$ | `verlustvortrag_bestand_eur` | € |
| $G^{\mathrm{st}}_t$ | `steuerliches_ergebnis_eur` | € |
| $S_t$ | `steuer_eur` | € |
| $\mathrm{CF}^{\mathrm{op}}_t$ | `cf_operativ_eur` | € |
| $\mathrm{CF}^{\mathrm{inv}}_t$ | `cf_invest_eur` | € |
| $\mathrm{CF}^{\mathrm{fin}}_t$ | `cf_finanzierung_eur` | € |
| $\mathrm{CF}_t$ | `cf_gesamt_eur` | € |
| $\mathrm{CF}^{\mathrm{kum}}_t$ | `cf_kumuliert_eur` | € |
| $\mathrm{DSCR}_t$ | `dscr` | – |

## 18.4 Plausibilisierungsfolge für eine unabhängige Nachrechnung

Für eine unabhängige Reproduktion in einer Tabellenkalkulation empfiehlt
sich die folgende Prüfsequenz:

1. $E_1 = P \cdot h$ – bei Inbetriebnahme im Januar exakt, ohne Faktoren.
2. $m_1$ – Kurvenwert des Inbetriebnahmejahres mal Inflationsfaktor.
3. $C_1$ – Summe der spezifischen Positionen mal Leistung plus
   produktionsbasierte Sätze, alle ohne Indexierung.
4. $Z_1 = D \cdot i$ und $T_1 = \mathrm{Ann} - Z_1$.
5. $G_1 = R_1 - C_1 - Z_1 - A_1$ und daraus $S_1$.
6. $\mathrm{CF}_1 = R_1 - C_1 - Z_1 - S_1 - T_1$.

Bei Übereinstimmung dieser sechs Größen sind die wesentlichen
Berechnungsbeziehungen des ersten Betriebsjahres verifiziert. Die
Folgeperioden unterscheiden sich durch die in den Kapiteln 5 bis 10
definierten zeitabhängigen Faktoren. Kapitel 13 dokumentiert diese
Prüfung anhand des Beispielparametersatzes.

# 19 Reproduzierbarer Dokumentationsaufbau

## 19.1 Generierung

```
python docs/rechenmodell/build_pdf.py     # erzeugt Rechenmodell.pdf
python docs/rechenmodell/beispiel.py      # erzeugt die Zahlen zu Kapitel 13
make dokumentation                        # beides in einem Schritt
```

Die fachliche Quelle ist `docs/rechenmodell/rechenmodell.md`. Der
Build-Prozess erzeugt daraus zunächst eine LaTeX-Datei und anschließend das
PDF. Erforderlich sind Pandoc, Graphviz, XeLaTeX und `latexmk`. Sämtliche
mathematischen Ausdrücke werden im PDF als Vektorsatz ausgegeben.

## 19.2 Pflege der fachlichen Quelle

Inhaltliche Änderungen werden ausschließlich in der Markdown-Quelle
vorgenommen. Die verwendete Formelsyntax muss sowohl von KaTeX für die
Darstellung im Repository als auch von XeLaTeX für den PDF-Satz unterstützt
werden. Mehrzeilige Gleichungen können mit `aligned`, Fallunterscheidungen mit
`cases` gesetzt werden. Nicht unterstützte Ausdrücke führen zu einem
reproduzierbaren Build-Fehler.

## 19.3 Konsistenz mit der Implementierung

Wird eine Rechenvorschrift in der Engine geändert, sind vier Stellen
nachzuziehen:

1. die betroffene Formel in diesem Dokument,
2. gegebenenfalls die Annahmenliste in Kapitel 17,
3. die Zahlen in Kapitel 13 (über `beispiel.py` neu erzeugen),
4. das gebaute PDF.

Der Test `tests/test_dokumentation.py` vergleicht die in Kapitel 13
dokumentierten Zahlen mit den aktuellen Ergebnissen der Engine. Abweichungen
zwischen Dokumentation und Implementierung werden dadurch im Testlauf
sichtbar.
