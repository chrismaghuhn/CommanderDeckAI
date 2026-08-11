# Learnability- und Pivot-Gate

## Zweck

Dieses Gate verhindert zwei symmetrische Fehler:

- komplexere Modelle auf eine nicht tragfähige Completion-Formulierung zu stapeln;
- einen grundsätzlich lernbaren Ansatz nach einer einzelnen schwachen Baseline zu früh zu verwerfen.

Die Entscheidung wird deshalb nicht an einen magischen absoluten NDCG-Wert gebunden. Stattdessen wird geprüft, ob zusätzliche Information und zusätzliche Modellkapazität auf demselben eingefrorenen Benchmark einen vorab definierten, reproduzierbaren Zusatznutzen liefern.

## Drei getrennte Fragen

```text
Daten bereit?
    ↓
M4 Benchmark Freeze
    ↓
Formulierung lernbar?
    ↓
M5 Modellkapazität gerechtfertigt?
```

Diese Fragen dürfen nicht vermischt werden.

- **Benchmark readiness** fragt, ob ein fairer, leakage-sicherer Benchmark gebaut werden kann.
- **Learnability** fragt, ob Commander- und sichtbarer Deckkontext Vorhersagesignal tragen.
- **Model capacity** fragt, ob komplexere Modelle zusätzliches Signal ausnutzen können.

## M4-Freeze-Trigger

M4 wird nicht aufgeschoben, bis sich die Data Foundation "vollständig" anfühlt. Vor dem Freeze wird eine versionierte Readiness-Policy festgelegt. Sobald deren Mindestzustand erfüllt ist, wird Benchmark v1 eingefroren.

Die Readiness-Policy bindet mindestens:

- minimale Zahl qualitätsgeprüfter Completion-Decks;
- minimale Commander-/Command-Zone-Diversität;
- Mindestgrößen für Train/Validation/Test und verpflichtende Segmente;
- zeitlichen Split und Cutoffs;
- erlaubte Unresolved-/Quarantine-Raten;
- Leakage-Suite und erforderlichen PASS-Status;
- Maskenpolicy und Masken-Hashes;
- Candidate-Pool-Policy und Hashes;
- Near-Duplicate-Policy und Version;
- Ruleset-/Card-Snapshot-Bindung.

Optional oder approval-gated Quellen sind **kein** automatischer Blocker für Benchmark v1. Wenn TopDeck, Spicerack oder eine andere geplante Quelle beim Erreichen des Mindestzustands nicht nutzbar ist, wird diese Missingness dokumentiert. Zusätzliche Daten erfordern später Benchmark v2 statt ein stilles Verschieben von v1.

## Decision Policy vor dem ersten Modellvergleich

Zusammen mit M4 wird eine versionierte `learnability_decision_policy` eingefroren. Sie enthält konkrete numerische Werte für:

- primäre Ranking-Metrik, standardmäßig eine versionierte NDCG@K-Definition;
- sekundäre Recall-/Coverage-Metriken;
- minimale materielle relative Verbesserung für jedes Gate;
- Confidence-/Resampling-Verfahren;
- maximal akzeptierte Regressionen auf verpflichtenden Segmenten;
- verpflichtende Maskierungsregime für einen Gate-PASS;
- Validation-Tuning-Budgets pro Baseline/Modellfamilie;
- maximales Diagnosebudget;
- Seed-Policy, wo Randomness verwendet wird.

Die Zahlen dürfen bis zum M4-Freeze anhand von Benchmarkgröße, Metrikvarianz und Candidate-Pool-Geometrie festgelegt werden. **Nach dem Freeze dürfen sie für Benchmark v1 nicht nach Ergebnislage verschoben werden.** Eine Änderung erzeugt eine neue Decision-Policy-/Benchmark-Version.

Damit wird die Entscheidungsregel jetzt festgelegt, ohne heute willkürliche absolute NDCG-Werte für einen noch nicht existierenden Benchmark zu erfinden.

## G0 — Pipeline- und Commander-Signal

Vergleich:

```text
B0 Random Legal
B1 Global Popularity
B2 Commander Popularity
```

Ziel: Belegen, dass der Benchmark überhaupt lernbares, formatrelevantes Signal enthält.

### PASS

`B2` schlägt `B0` und die in der Decision Policy definierte triviale/populäre Kontrolle um den vorregistrierten materiellen Mindestabstand; der Effekt ist unter dem festgelegten Confidence-Verfahren robust.

### FAIL

Wenn Commander-Popularity Random/Trivial-Baselines nicht zuverlässig schlägt, wird **keine zusätzliche Modellkomplexität** als nächster Schritt akzeptiert.

Zuerst werden geprüft:

- Candidate-Pool- und Label-Korrektheit;
- Split-/Leakage-Fehler;
- Maskierungsregime;
- Quarantine-/Resolution-Qualität;
- Benchmark-Metrik und Sample Counts.

Bleibt G0 nach dem begrenzten Diagnosebudget rot, gilt Benchmark/Formulierung v1 als nicht validiert und muss überarbeitet werden.

## G1 — Wert des sichtbaren Deckkontexts

Das ist das zentrale Formulierungs-Gate.

Vergleich:

```text
B2  P(card | command_zone)
vs.
B4  context-aware Card-Card Co-Occurrence
```

Der Architektur-Claim lautet nicht nur "Commander sagt Karten voraus", sondern:

```text
visible_deck adds predictive value
```

### GREEN

B4 schlägt B2 um den vorregistrierten materiellen Mindestabstand in der primären Metrik, der Effekt ist robust, und die Verbesserung erscheint in der von der Decision Policy verlangten Zahl unterschiedlicher Maskierungsregime/Segmente.

### YELLOW

B4 zeigt positives, aber zu kleines oder zu instabiles Context-Signal. Es folgt genau das eingefrorene, begrenzte Diagnosebudget. Typische Hypothesen:

- Maskierung ist zu leicht oder zu schwer;
- Precons/Revisionen dominieren;
- Archetype/Profile fehlt;
- Positive Labels sind stark multimodal;
- Co-Occurrence ist als Context-Baseline zu schwach.

### RED / Formulierungs-Pivot

Wenn nach dem erlaubten Diagnosezyklus kein vorregistrierter Context-Uplift nachweisbar ist, darf die Antwort nicht "größeres Netz" lauten.

Dann wird die aktuelle Formulierung `s(card | command_zone, visible_deck, ...)` in ihrer Trainings-/Labelkonstruktion überprüft oder ersetzt.

## G2 — Zusätzliche Modellkapazität

G2 beginnt erst nach einem positiven Context-Gate.

Die Reihenfolge bleibt:

```text
B4 Context Co-Occurrence
  ↓
B5 Hybrid Linear Ranker
  ↓
B6 Weighted Matrix Factorization
  ↓
DeepSets nur mit begründetem Gate
```

B5/B6 erhalten ein vorab begrenztes Validation-Tuning-Budget. Der Frozen Test bleibt unangetastet.

Wenn B5/B6 keinen materiellen Zusatznutzen liefern, ist Completion dadurch nicht automatisch widerlegt. Es bedeutet aber, dass **mehr Modellkapazität nicht automatisch gerechtfertigt ist**.

DeepSets darf dann nur gestartet werden, wenn entweder:

1. die vorherige Stufe den vorregistrierten Capacity-Uplift erreicht; oder
2. eine dokumentierte Fehleranalyse einen konkreten Set-/Interaktionsfehler identifiziert, den die einfachere Modellklasse nicht ausdrücken kann, und vor dem Training einen Erfolgsmargin für das DeepSets-Experiment festlegt.

"Neural ist größer" ist kein ausreichender Grund.

## G3 — Generalisierung statt Durchschnittswert

Ein Gesamt-Uplift allein reicht nicht. Die Decision Policy bindet verpflichtende Segmente, mindestens soweit Daten vorhanden sind:

- Standard temporal;
- `early_build`;
- `late_build` / near-complete;
- Cold Commander;
- Low-data Commander;
- New-card window;
- Long tail;
- Precon holdout.

Ein Modell darf einen Overall-Gewinn nicht durch eine vorab als unakzeptabel definierte Regression auf kritischen Segmenten erkaufen.

Segmentgrenzen, Mindest-Samplecounts und Regressionstoleranzen werden vor Auswertung eingefroren.

## Entscheidungszustände

### GREEN — Formulierung bestätigt

Mindestens:

- G0 PASS;
- G1 PASS;
- keine unakzeptierte G3-Regression.

Dann ist die Completion-Formulierung ausreichend validiert, um M5 kontrolliert fortzusetzen.

### YELLOW — begrenzte Diagnose

Signal existiert, aber ein Gate verfehlt den vorregistrierten materiellen/robusten Mindestabstand oder zeigt eine kritische Segmentregression.

YELLOW erlaubt **nur** das eingefrorene Diagnosebudget. Es erlaubt kein unbegrenztes Hyperparameter-Tuning und kein stilles Verschieben der Erfolgsschwelle.

### RED — Pivot

RED wird ausgelöst, wenn:

- G0 nach Pipeline-/Benchmark-Diagnose weiterhin scheitert; oder
- G1 nach dem erlaubten Diagnosebudget weiterhin keinen materiellen Context-Uplift zeigt; oder
- der scheinbare Gewinn nach Leakage-Korrektur verschwindet; oder
- die vorab definierten Generalisierungsanforderungen systematisch kollabieren.

Bei RED wird neue Modellkomplexität blockiert, bis eine neue Formulierung/Benchmark-Version reviewt ist.

Mögliche Pivots sind beispielsweise:

- archetype-conditioned completion;
- role-aware Multi-Task-Learning;
- explizite Replacement-/Slot-Aufgabe;
- pairwise preference ranking;
- deck-level contrastive objectives;
- getrennte Outcome-Supervision.

Ein Pivot bedeutet nicht, dass Card/Deck-Identität, Rulesets oder Data-Provenance verworfen werden. Diese Foundation bleibt wiederverwendbar.

## Begrenztes Experiment- und Diagnosebudget

Die exakten Trial-Zahlen werden in der eingefrorenen Decision Policy festgelegt. Der Vertrag ist aber hart:

- jede Modellfamilie besitzt ein maximales Validation-Budget;
- Testdaten werden nicht zur Modell-/Threshold-Auswahl verwendet;
- YELLOW besitzt eine begrenzte Zahl Diagnosezyklen;
- nach Budgetende folgt GREEN oder RED/Pivot, nicht "noch ein bisschen tunen";
- zusätzliches Budget erfordert eine explizite Policy-/Benchmark-Versionierung und Begründung.

## Testset-Disziplin

```text
TRAIN
  -> Fit

VALIDATION
  -> Hyperparameter, Gate-Diagnose, Modellwahl

FROZEN TEST
  -> finale Behauptung bestätigen
```

Wird nach Sichtung des Frozen-Test-Ergebnisses die Formulierung oder das Modell geändert, gehört die nächste Behauptung auf einen neuen Test-/Benchmark-Zyklus. Wiederholtes Tunen gegen denselben Test widerspricht M4.

## Rigor proportional zum Fehlerrisiko

Dieses Gate folgt derselben Engineering-Regel wie die Data Foundation:

- Identität, Legalität, Split-/Leakage-Regeln, Versionbindung und Testdisziplin sind **streng**, weil Fehler downstream unsichtbar und teuer sind.
- Effektgrößen, Near-Duplicate-Threshold-Werte und Modellhyperparameter sind **iterierbar**, aber ihre verwendete Version muss eingefroren und nachvollziehbar sein.
- Explorative Modell-/Feature-Experimente dürfen **pragmatisch** sein, solange sie keine frozen Evidence stillschweigend überschreiben.

Innerhalb eines Tasks kann deshalb das "Was" iterierbar sein, während das "welche Version wurde für diesen Benchmark verwendet" strikt bleibt.
