# Learnability- und Pivot-Gate

## Zweck

Dieses Gate verhindert zwei Fehlentscheidungen:

1. immer komplexere Modelle zu bauen, obwohl die aktuelle Completion-Formulierung kein belastbares zusätzliches Signal liefert;
2. M4 wegen immer weiterer Infrastruktur-, Quellen- oder Perfektionswünsche unbegrenzt aufzuschieben.

Das Gate bewertet **woher** zusätzlicher Predictive Value kommt. Ein einzelner absoluter NDCG-Wert entscheidet nicht über die gesamte Forschungsrichtung.

## Evidenzleiter

Die verpflichtende Reihenfolge ist:

```text
B0 Random Legal
  ↓
B1 Global Popularity
  ↓
B2 Commander Popularity / B3 Lift-PMI
  ↓
B4 Deck-Context Co-Occurrence
  ↓
B5 Hybrid Linear Ranker
  ↓
B6 Weighted Matrix Factorization
  ↓
DeepSets v1
```

Keine spätere Stufe darf eine fehlgeschlagene frühere Stufe durch bloß größeres Modellbudget verdecken.

## Primäre Entscheidungsmetrik

Für v1 ist `NDCG@25` die primäre Learnability-Metrik. Recall@25, MRR, Catalog Coverage, Long-Tail Recall und segmentierte Werte bleiben verpflichtende Sekundärmetriken.

Jeder Vergleich berichtet Samplecount und Bootstrap-Konfidenzintervall. Relative Uplifts werden gegen dieselben eingefrorenen Samples, Masken und Candidate Pools berechnet.

## G0 — Pipeline- und Grundsignal

G0 besteht aus zwei getrennten Kontrollen:

### G0a — Dataset-/Pipeline-Signal

B1 Global Popularity muss B0 Random Legal zuverlässig schlagen.

Mindestens muss die untere Grenze des vorab festgelegten Bootstrap-Konfidenzintervalls für `B1 - B0` über `0` liegen.

Wenn G0a nach validierter Metrik-/Pipeline-Implementation scheitert, lautet die Entscheidung **STOP MODELING**. Dataset, Labels, Candidate Pools, Maskierung und Metrikimplementation werden geprüft, bevor Matrix Factorization oder Deep Learning begonnen werden.

### G0b — Commander-spezifisches Signal

Die stärkste Commander-spezifische Baseline aus B2/B3 muss gegenüber B1 einen belastbaren Zusatznutzen zeigen. Auch hier muss für den entscheidenden Uplift die untere Grenze des preregistrierten Konfidenzintervalls über `0` liegen.

Scheitert G0b bei bestandenem G0a, ist das kein Pipeline-Totalausfall, aber mindestens `YELLOW`: Das Dataset enthält allgemeines Decksignal, aber die Command Zone liefert in der aktuellen Form nicht den erwarteten zusätzlichen Predictive Value. Eine bloße nachträgliche Erklärung ersetzt diesen Befund nicht.

## G1 — Wert des sichtbaren Deckkontexts

Der zentrale Architektur-Claim ist, dass `visible_deck` zusätzliche Information gegenüber Commander-only Ranking liefert.

Verglichen wird B4 gegen die stärkste eingefrorene Commander-only Baseline aus B2/B3.

Default-Gate für v1, sofern vor dem M4-Freeze kein begründeter anderer Wert committed wurde:

```text
relative NDCG@25 uplift >= 5 %
AND bootstrap CI lower bound > 0
AND positiver Effekt in late-build
AND positiver Effekt in mindestens einem weiteren Maskenregime
```

Die 5-%-Schwelle ist eine vorab registrierte Forschungsentscheidung, kein universelles Naturgesetz. Sie darf für Benchmark v1 nur **vor** dem ersten entscheidenden Validation-Lauf geändert werden. Danach benötigt eine geänderte Schwelle eine neue Benchmark-/Gate-Version.

Interpretation:

```text
PASS   >= preregistrierter Margin + CI > 0
WEAK   Signal > 0, aber Margin/Segmentkonsistenz nicht erreicht
FAIL   kein belastbarer zusätzlicher Context-Wert
```

## G2 — Zusätzliche Modellkapazität

B6 wird innerhalb von M5 **vor DeepSets** evaluiert. Verglichen wird gegen die stärkste zulässige nicht-neuronale Context-Baseline aus B4/B5.

Default-Gate für v1, sofern vor dem M4-Freeze kein begründeter anderer Wert committed wurde:

```text
relative NDCG@25 uplift >= 3 %
AND bootstrap CI lower bound > 0
AND keine preregistrierte geschützte Segmentgrenze verletzt
```

Ein Scheitern von B6 beweist nicht automatisch, dass DeepSets nutzlos ist. Es entscheidet aber, wie viel weitere Komplexität gerechtfertigt ist:

- starkes G1 + schwaches G2: ein begrenztes DeepSets-v1-Experiment darf als Test nichtlinearer Set-Interaktionen durchgeführt werden;
- schwaches G1 + schwaches G2: DeepSets ist blockiert, bis die Formulierung diagnostiziert oder geändert wurde;
- positives G1 + positives G2: DeepSets ist regulär gerechtfertigt.

Ein fehlgeschlagenes begrenztes DeepSets-v1-Experiment rechtfertigt **keine automatische Skalierung** zu größeren Netzen oder Set Transformern.

## Gate-Zustand über M4 und M5

M4 bewertet G0/G1 und erzeugt den ersten Gate-Zustand. G2 wird erst in M5 nach B6 ergänzt und kann den Zustand aktualisieren.

### GREEN — Formulierung trägt

M4-GREEN verlangt:

- G0a bestanden;
- G0b bestanden;
- G1 bestanden;
- keine unakzeptierte preregistrierte Temporal-/Cold-/Long-Tail-Regression.

M5 darf regulär fortfahren. B6 wird vor DeepSets ausgeführt.

### YELLOW — Signal vorhanden, Diagnose erforderlich

Beispiele:

- G0a besteht, G0b ist schwach;
- Commander-Signal ist vorhanden, aber B4 liefert nur schwachen zusätzlichen Deckkontext-Nutzen;
- der Gesamtwert steigt, aber Cold-/Long-Tail-Segmente regressieren;
- G1 ist stark, B6 liefert in M5 aber kaum weiteren Gewinn.

YELLOW erlaubt nur ein **begrenztes, vorab dokumentiertes Diagnosebudget**. Es darf nicht in eine offene Hyperparameter- oder Infrastrukturphase übergehen.

### RED — Formulierung oder Benchmark pivoten

RED wird ausgelöst, wenn nach validierter Pipeline und ausgeschöpftem Diagnosebudget mindestens eines gilt:

- G0a scheitert weiterhin;
- Commander-/Deckkontext liefert keinen belastbaren Zusatznutzen und B5/B6 können das nicht erklären oder beheben;
- scheinbare Gewinne verschwinden nach Leakage-/Duplicate-Kontrolle;
- Gewinne entstehen praktisch nur durch Popularity Memorization, während preregistrierte Generalisierungssegmente kollabieren.

RED bedeutet nicht „DeepSets war schlecht“, sondern: Die aktuelle supervised Completion-Formulierung liefert nicht ausreichend das Signal, auf dem die geplante Architektur basiert.

Mögliche Pivot-Richtungen werden dann separat geprüft, zum Beispiel Archetype-conditioning, Role-aware Multi-Task Learning, Pairwise/Preference Ranking, Replacement-Tasks oder spätere Outcome-Supervision. Ein Pivot ist eine neue Forschungsentscheidung und kein stilles Tuning des alten Benchmarks.

## Begrenztes Experimentbudget

Das exakte Validation-Budget wird im M4-Benchmarkmanifest vor dem ersten Search-Lauf eingefroren.

Wenn kein begründeter anderer Wert preregistriert wurde, gelten für v1 diese Obergrenzen:

- B0–B4: deterministische/fest definierte Baselines; keine offene Search-Schleife;
- B5: maximal 20 Validation-Konfigurationen;
- B6: maximal 20 Konfigurationen, jeweils höchstens 3 Seeds;
- ein ausdrücklich genehmigtes DeepSets-v1-Diagnoseexperiment: maximal 12 Konfigurationen, jeweils höchstens 3 Seeds.

Zusätzliche Versuche nach Sichtung der Ergebnisse benötigen eine dokumentierte neue Hypothese und dürfen das eingefrorene Testset nicht als Tuning-Signal verwenden.

## Train / Validation / Test

```text
TRAIN
  Modellparameter fitten

VALIDATION
  Baselines vergleichen
  Hyperparameter wählen
  GREEN/YELLOW/RED diagnostizieren

FROZEN TEST
  finalen vorab gewählten Claim einmal bestätigen
```

Das Testset wird nicht nach jedem schlechten Ergebnis erneut konsultiert. Eine wesentliche Änderung von Aufgabe, Labels, Masken, Candidate-Pool-Semantik oder Splitlogik erzeugt einen neuen Benchmark statt Testset-Tuning durch die Hintertür.

## Minimum-Viable-Benchmark-Freeze

Vor dem Exit von M3 muss ein versioniertes M4-Freeze-Profil committed sein. Es definiert **vor Betrachtung der entscheidenden M4-Ergebnisse** mindestens:

- minimale Anzahl qualitätsgeprüfter Decks;
- minimale Commander-/Command-Zone-Abdeckung;
- Temporal-Cutoffs und minimale Split-/Segment-Samplecounts;
- Maskenregime und Candidate-Pool-Policy;
- primäre/sekundäre Metriken;
- G0/G1/G2-Margins und geschützte Segmentgrenzen;
- Bootstrap-/Unsicherheitsmethode;
- Experimentbudgets.

Sobald diese Mindestbedingungen erfüllt sind, wird Benchmark v1 eingefroren. M4 darf dann nicht verzögert werden, nur weil eine zusätzliche Quelle, mehr historische Abdeckung oder „noch sauberere“ Infrastruktur wünschenswert wäre.

Insbesondere sind TopDeck/Spicerack **keine Voraussetzung** für den Completion-Benchmark, wenn dessen preregistrierte Mindestbedingungen ohne sie erfüllt sind. Später verfügbare Daten können Benchmark v2 speisen; Benchmark v1 bleibt unverändert.

Falls die Mindestbedingungen nicht erfüllt sind, ist weitere Data-Foundation-Arbeit nur insoweit M4-blockierend, wie sie eine konkret verfehlte Mindestbedingung adressiert.

## Rigor innerhalb eines Tasks

Rigor wird nach Fehlerkosten und Reversibilität angewandt, nicht pauschal nach Verzeichnis oder Milestone.

**Sehr streng / invariant:**

- Card-/Deck-Identität;
- Split- und Leakage-Semantik;
- eingefrorene Masken/Candidate Pools;
- Metric-Definitionen;
- Benchmark-/Gate-Versionen;
- Provenienz der Trainings-/Evaluationsinputs.

**Iterierbar bis zum Freeze:**

- konkrete Near-Duplicate-Threshold-Werte;
- Smoothing-/Baseline-Hyperparameter;
- numerische Gate-Margins;
- Reporting- oder Cache-Details.

Sobald ein iterierbarer Wert Bestandteil eines eingefrorenen Benchmarklaufs ist, wird er für diese Benchmarkversion reproduzierbare Contract-Evidenz und darf nicht still verändert werden.
