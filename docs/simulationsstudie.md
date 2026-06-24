# Simulationsstudie: Methodik und Versuchsdesign

*Teil der Dokumentation des abgeschlossenen ASAG-Simulationsprojekts.*

Dieses Dokument beschreibt die Methodik, die Modellbildung und das Versuchsdesign der ereignisdiskreten Simulationsstudie zur hybriden technischen Wagenbehandlung. Es ergänzt die System- und Modulsicht in [architecture.md](../architecture.md) und das Anwendungs-Setup im [README](../README.md) um die wissenschaftliche Methodik. Die Befunde der Studie sind in [ergebnisse.md](ergebnisse.md) dokumentiert.

---

## 1. Kurzkontext

Gegenstand der Studie ist die **technische Wagenbehandlung (TWb)** von Güterzügen im Einzelwagenbetrieb: Züge treffen in einem Rangierbahnhof ein, werden auf Abstellgleise disponiert und vor der Ausfahrt auf Verkehrstauglichkeit begutachtet. Untersucht wird ein **hybrider Inspektionsprozess**, in dem ein KI-gestütztes optisches **PreScreening** (Labeling/Detektion von Schäden) der menschlichen Begutachtung durch einen **Wagenmeister** vorgelagert ist. Der Mensch kann die KI-Vorlabels akzeptieren, umklassifizieren oder neue Schäden annotieren und verantwortet die Schlussentscheidung.

Der Prozess wird als **ereignisdiskrete Simulation (DES, *discrete-event simulation*)** mit **SimPy** abgebildet. Die Simulation springt von Ereignis zu Ereignis (Zugankunft, Prüfinitiierung, Befund, Dokumentation, Pausen) und bildet Ressourcenbeschränkungen (Wagenmeister, Abstellgleise), Warteschlangen und stochastische Prozesszeiten ab. Zwei Betriebsmodi werden gegenübergestellt:

- **Human-only (Baseline):** ausschließlich menschliche Inspektion, vollständige Detektion und Klassifikation durch den Wagenmeister.
- **Hybrid:** KI-gestütztes visuelles PreScreening vor der menschlichen Begutachtung; der Mensch bestätigt, korrigiert oder ergänzt die KI-Vorlabels.

Ziel ist eine Entscheidungsunterstützung (Decision-Support) für Disposition, Personal- und Prozessplanung: Unter welchen Güte- und Vertrauensbedingungen liefert die hybride Konfiguration einen Mehrwert gegenüber der Baseline, und wo entstehen Engpässe?

---

## 2. Datengrundlage und PVG-Analyse (R-Modul)

Die stochastischen Randbedingungen der Simulation sind empirisch fundiert. Grundlage sind historische Auszüge aus dem **PVG-System** über jeweils ein Betriebsjahr für vier Standorte (codiert als **BSS**, **MN**, **SEE**, **TK**). Die Auswertung übernimmt ein eigenständiges Softwaremodul mit Schnittstelle zu **R** ([`r_code/PVG_analysis.Rmd`](../r_code/PVG_analysis.Rmd)), das die Rohdaten iterativ verarbeitet, Wagen-Einträge zu Zügen zusammenfasst, irrelevante Datensätze filtert und Berichte in Markdown- und HTML-Format generiert.

> **Datenschutz:** Die PVG-Rohdaten (CSV/Parquet) sind nicht Bestandteil des Repositories und werden über lokale Pfade eingelesen. Hier werden ausschließlich aggregierte Verteilungsparameter dokumentiert (siehe [README](../README.md#datenschutz-reale-auftraggeber-daten)).

### 2.1 Filterprozess (am Beispiel SEE)

Der Filterprozess ist exemplarisch für den Standort SEE dokumentiert:

| Schritt | Filter-/Aggregationskriterium | Verbleibende Einträge |
|---|---|---|
| Ausgangsdatensatz | — | **53.986** Einträge |
| Erste Filterung | nur ein Wagenmeister zuständig (`anzWeitereMitarbeiter == 0`), Mindestzuglänge (`abfahrtZugLaenge > 0`), reguläre Bearbeitung (`bemerkung != 'Abbruch'`) | **52.191** Einträge |
| Dubletten-Bereinigung | Eliminierung von PVG-Dubletten | **24.338** Wageneinträge |
| Zusammenfassung zu Zügen | Aggregation der Wagen-Einträge zu Zügen | **17.208** Züge |
| Finale Filterung | Mindestzuglänge ≥ 10 Wagen (`abfahrtZugFahrzeuge > 9`) und Begutachtungszeit > 20 min (`begutachtungMinuten > 20`) | **15.624** Züge |

Die finale Filterung reduzierte den Bestand um weitere 1.584 Züge.

### 2.2 Gewonnene Verteilungen

Aus den gefilterten Daten wurden die folgenden empirischen Verteilungen geschätzt; sie dienen als Randparameter und Kalibrierungsgrundlage der Simulation:

| Größe | Verteilung / Kennwerte |
|---|---|
| Begutachtungszeit pro Achse | Normalverteilung, *M* = 0,36 min/Achse, *SD* = 0,10 min/Achse |
| Zuglänge (Anzahl Güterwagen) | Normalverteilung *M* = 26,66, *SD* = 8,49; alternativ Beta-Verteilung mit α = 2,02, β = 1,29 |
| Tagesfrequenz der Zugankünfte | bimodale Verteilung als gewichtete Überlagerung zweier Normalverteilungen (Normalmischung je Wochentag) |
| Schadwahrscheinlichkeit | Weibull-Verteilung (Form- und Skalenparameter geschätzt) |
| Begutachtungsdauer ohne Schaden | *M* = 69,54 min, *SD* = 21,82 min |
| Begutachtungsdauer mit Schaden | *M* = 76,06 min, *SD* = 21,47 min |

Zwischen Schadhäufigkeit und Begutachtungsdauer besteht kein signifikanter Zusammenhang. Das R-Modul liefert darüber hinaus deskriptive Statistiken, Gegenüberstellungen von Roh- und gefilterten Daten, Häufigkeits- und Frequenzanalysen (Achsen, Längen, Zugnummern) sowie Tagesverteilungen je Standort. Es bildet damit die empirische Grundlage für die Validierung des Gesamtmodells und die Ableitung der Simulationsparameter.

---

## 3. Modellbildung (OOP/SimPy)

Die Simulationsumgebung ist objektorientiert aufgebaut. Zentrale Entitäten und ihre Interaktionen:

| Entität | Umsetzung | Verhalten |
|---|---|---|
| **InspectorPool** | SimPy `Store` mit Kapazität `NUM_INSPECTORS` | Zuteilung und Verfügbarkeitssteuerung der Wagenmeister, Pausenkoordination, Lastverteilung |
| **Inspector** | Klasse mit summierten, positiv trunkiert normalverteilten Prozesszeiten | Wegezeiten, Screening, Inspektion pro Achse, vertiefte Begutachtung, PVG-Prüfung, Formalitäten; Entscheidungslogik mit/ohne KI (binomiale Entscheidungsstruktur, moduliert durch `TRUST_AI_PROB`); integrierter Pausenmanager |
| **Inspector_AI** | KI-basiertes Screening | False Positives ~ Poisson(`FALSE_POSITIVE`) je Wagen; False Negatives ~ Binomial pro tatsächlichem Schaden(`FALSE_NEGATIVE`); generiert Vorlabels zu Position und Schadtyp |
| **Train** | physische Zugstruktur | Länge `NUM_WAGONS`; Achszahl je Wagen gezogen aus `POSSIBLE_AXES` mit `PROBABILITIES_AXES`; Anzahl Schäden ~ Poisson(`MEAN_NUM_DAMAGES`); Schadwahrscheinlichkeiten/-schweregrade ~ Weibull; orchestriert über die `twb()`-Methode Ressourcenanforderung, Prozesszeiten und Entscheidungslogik |

Die Zugerzeugung erfolgt über eine Generatorfunktion, die wochentagsabhängige Parameter (`PARAMS_WEEK`) berücksichtigt, um realistische Verkehrsprofile abzubilden.

### 3.1 Vereinfachter Ereignisfluss

1. **Zugankunft & Disposition:** Zuginstanz (Länge, Achsen, Schadprofil) wird erzeugt; ggf. Wartezeit auf ein freies Abstellgleis (`ABSTELLGLEISE`).
2. **(optional, nur Hybridmodus) KI-PreScreening:** `Inspector_AI` erzeugt Vorlabels unter FP-/FN-Raten; Screening-Zeit pro Wagen wird gezogen.
3. **Zuteilung Wagenmeister:** Anforderung an den `InspectorPool`; Wegezeit (`WALKING_DURATION`).
4. **Menschliche Begutachtung:** Inspektionszeit als Summe über Wagen/Achsen (positiv trunkierte Normalverteilung); bei Label-Inkonsistenzen/Unsicherheit vertiefter Blick (`INSP_CLOSER_LOOK`).
5. **Entscheidung:** *Ohne KI* vollständige Detektion/Klassifikation durch den Menschen; *mit KI* Bestätigung/Umklassifizierung/Neuannotation über Binomial-Regeln, deren Erfolgswahrscheinlichkeiten durch `TRUST_AI_PROB` moduliert werden.
6. **Dokumentation & Formalitäten:** PVG-Zeit (`TIME_PVG`) plus Formalitäten (`FORMALITIES_BASELINE`, Anzahl Akte ~ Poisson(`MEAN_NUM_FORMAL_ACTS`), Dauer pro Akt ~ Normal(`MEAN_TIME_FORMALS`)).
7. **Pausensteuerung:** Kurz- bzw. reguläre Pausen gemäß `REGULAR_PAUSE`, `SHORT_PAUSE_[MIN,MAX]` und Schicht-Staffelung über `NUM_SHIFTS`.
8. **Freigabe:** Inspector und Abstellgleis werden freigegeben; der Zug verlässt das System.

Eine detailliertere Beschreibung der Klassen, Datenflüsse und Modul-Kopplung findet sich in [architecture.md](../architecture.md).

---

## 4. Parameterisierung

Die Parameter teilen sich in deterministische/strukturelle Randparameter (über die Laufzeit konstant), stochastische Prozessparameter (Zeitverteilungen) und stochastische Entscheidungsparameter (Wahrscheinlichkeiten). Zeitverteilungen werden positiv trunkiert normalverteilt modelliert; die Schadlast zweistufig (Anzahl Poisson-, Schadwahrscheinlichkeiten Weibull-verteilt); KI-Fehler über Poisson (False Positives) bzw. Binomial (False Negatives). Die Setzung erfolgte auf Basis der PVG-Analyse, ergänzt durch Expertenbefragungen und Literatur.

### 4.1 Deterministische/strukturelle Randparameter

| Gruppe | Parameter |
|---|---|
| Zeit und Kontext | `SIM_TIME`, `WORKING_DAY`, `WOCHENTAG`, `PARAMS_WEEK` (wöchentliche Unterschiede, z. B. reduzierte Besetzung am Wochenende) |
| Ressourcen | `ABSTELLGLEISE` (Abstellkapazität als SimPy-Ressource), `NUM_INSPECTORS` (Wagenmeister im `InspectorPool` als Store), `NUM_SHIFTS` (Schichtgruppen zur Pausen-Staffelung) |
| Infrastrukturzeiten | `WALKING_DURATION` (Wegezeiten), `DRIVING_DURATION` (Zugbewegungen/Disposition) |
| Zug-/Wagenstruktur | `NUM_WAGONS`, `NUM_POSSIBLE_AXES`, `POSSIBLE_AXES`, `PROBABILITIES_AXES` |

### 4.2 Stochastische Prozessparameter (Zeiten)

| Gruppe | Parameter |
|---|---|
| Inspektionszeiten | `INSP_TIME_PER_AXES`, `SD_INSP_TIME_PER_AXES`; `INSP_TIME_SCREEN_PER_WAGON`, `SD_INSP_TIME_SCREEN_PER_WAGON`; `INSP_CLOSER_LOOK`, `SD_INSP_CLOSER_LOOK` |
| Dokumentation/Formalitäten | `TIME_PVG`, `SD_TIME_PVG`; `FORMALITIES_BASELINE`, `MEAN_NUM_FORMAL_ACTS`, `MEAN_TIME_FORMALS`, `SD_TIME_FORMALS` |
| Pausenmodell | `SHORT_PAUSE_MIN`, `SHORT_PAUSE_MAX` (random); `REGULAR_PAUSE` (nach Arbeitsintervallen); Schicht-Staffelung über `NUM_SHIFTS` |

### 4.3 Stochastische Entscheidungsparameter (Wahrscheinlichkeiten)

| Gruppe | Parameter |
|---|---|
| Prozesspfade | `HUMAN_INSP_PROB` (Anteil/Güte menschlicher Inspektionen im Hybridmodus), `TRUST_AI_PROB` (Akzeptanz/Vertrauen in KI-Labels), `PROB_INCON_HANDLING` (Sonderfälle/Inkonsistenzen) |
| Detektionsqualität (KI) | `FALSE_POSITIVE`, `FALSE_NEGATIVE` |
| Schadlast | `MEAN_NUM_DAMAGES` |

Die Kalibrierung dieser Größen erfolgte über Maximum-Likelihood-Schätzung, Bootstrapping und metaheuristische Optimierung (Simulated Annealing); die Verteilungsannahmen (Normal, Poisson, Weibull, Binomial) wurden über Goodness-of-Fit-Tests und Informationskriterien validiert (s. Abschnitt 7).

---

## 5. Versuchsplan (vollfaktoriell, Monte-Carlo)

Die Hauptstudie wurde als **vollständiges faktorielles Design** ausgeführt: Es wurden **alle** Faktorstufenkombinationen simuliert. Variiert wurden vier Faktoren — die KI-Güte (False-positive- versus False-negative-rate), die menschliche Entscheidungsgüte, das Vertrauen in die KI und die digitale Begutachtungszeit am Bildschirm. Die Faktorstufen orientieren sich an der einschlägigen Literatur:

| Faktor | Parameter | Stufen | Werte |
|---|---|---|---|
| Trust in AI | `TRUST_AI_PROB` | high / med / low | 0,9 / 0,7 / 0,5 |
| Human decision probability | `HUMAN_INSP_PROB` | high / good / bad / very bad | 0,99 / 0,9 / 0,8 / 0,7 |
| KI-Güte (AI) — False-negative-rate | `FALSE_NEGATIVE` | near_perfect / good / med / bad | 0,001 / 0,02 / 0,15 / 0,25 |
| KI-Güte (AI) — False-positive-rate | `FALSE_POSITIVE` | near_perfect / good / med / bad | 0,001 / 0,05 / 0,1 / 0,2 |
| Inspection_time_screen | `INSP_TIME_SCREEN_PER_WAGON` | med / slow | 1 / 2 |

Die KI-Güte ist ein zusammengesetzter Faktor: False-negative- und False-positive-rate werden gemeinsam über die vier Güte-Stufen (near_perfect, good, med, bad) variiert.

Daraus ergibt sich:

$$3 \times 4 \times 4 \times 2 = \textbf{96 Faktorstufenkombinationen}$$

Je Kombination wurden **1000 unabhängige Replikationen** gerechnet:

$$96 \times 1000 = \textbf{96.000 Simulationsiterationen.}$$

**Monte-Carlo-Charakter.** Jede Zelle des Versuchsplans wird über 1000 unabhängige Replikationen (Zufallspfade) bewertet. Die Auswertung erfolgt pro Zelle über **Mittelwerte** und **95-%-Konfidenzintervalle** (auf Basis der t-Verteilung), sodass Haupteffekte und Interaktionen statistisch abgesichert verglichen werden können. Der vollständige Versuchsplan ist in `Versuchsplan.xlsx` hinterlegt (als Rohdaten-Artefakt nicht im Repository enthalten; hier als Tabelle dokumentiert).

---

## 6. Zweite Studie — Ressourcenknappheit

In einer zweiten, fokussierten Studie wurde das System unter **Ressourcenknappheit** untersucht. Variiert wurden bei *guter* menschlicher Begutachtungsgüte:

| Faktor | Stufen |
|---|---|
| Trust in AI (`TRUST_AI_PROB`) | high vs. low |
| KI-Güte (AI) | near_perfect / good / bad |

Daraus ergeben sich 2 × 3 = 6 Kombinationen, je **N = 1000** Replikationen:

$$6 \times 1000 = \textbf{6.000 Iterationen.}$$

Die Ressourcenknappheit wurde gezielt induziert durch:

1. Erhöhung der **Zugfrequenzierung** um ca. **30 %**,
2. **Verdopplung der Gleisentfernungen** (Erhöhung der infrastrukturellen Last).

Zur Vergleichbarkeit wurden die übrigen Parameter konstant gehalten. Diese Reihe erlaubt es, prozessimmanente Effekte (KI-Güte × Vertrauen) von systemischen Störeinflüssen (Infrastrukturlast) zu trennen.

---

## 7. Validierung

Die Validierung des Modells erfolgt mehrstufig auf Basis der historischen PVG-Auszüge:

- **Parameterschätzung:** Maximum-Likelihood-Estimation (MLE), Bootstrapping und metaheuristische Optimierung (Simulated Annealing).
- **Modellgüte und -auswahl:** Goodness-of-Fit-Tests, Akaike-Informationskriterium (AIC) und Bayes'sches Informationskriterium (BIC), ergänzt durch Residuenanalysen.
- **Kalibrierung:** Abgleich mit beobachteten Kennzahlen, u. a. mittlere Begutachtungszeit pro Achse und die typischerweise bimodale tageszeitliche Frequenz.
- **Face Validity:** Prüfung von Prozesslogik und Ressourcenverbrauch durch Domänenexperten.
- **Sensitivitäts- und Szenarioanalyse:** Variation zentraler Parameter — `FALSE_POSITIVE`, `FALSE_NEGATIVE`, `TRUST_AI_PROB`, `NUM_INSPECTORS` und Anzahl der Abstellgleise — zur Prüfung der Robustheit gegenüber strukturellen und stochastischen Veränderungen.

Ein objektrelationales Datenbankmanagementsystem (**PostgreSQL**) ist Bestandteil der Architektur und dient der Zwischenspeicherung von Ein- und Ausgabedaten in Form von SQL-Tabellen. Dies gewährleistet eine konsistente Datenhaltung und schnelle Zugriffszeiten über die einzelnen Module hinweg.

---

## 8. Performanz

Die Berechnungszeit pro Simulation wurde neben den inhaltlichen KPIs als Performanzparameter erfasst. Die Läufe wurden lokal auf einem Laptop mit hoher Rechenleistung (Mehrkernprozessor, SSD, **32 GB RAM**) ausgeführt. Die durchschnittliche Laufzeit pro Instanz lag im Bereich **weniger Sekunden**. Dadurch ließen sich auch umfangreiche Kampagnen — bis hin zu den **96.000 Läufen** des vollfaktoriellen Versuchsplans (96 Kombinationen × 1000 Replikationen) — praktikabel und in vertretbarer Zeit verarbeiten.

---

## Weiterführend

- Methodische und architektonische Details: [architecture.md](../architecture.md)
- Anwendung, Setup und Datenschutz: [README](../README.md)
- **Befunde und Auswertung der Studie: [ergebnisse.md](ergebnisse.md)**
