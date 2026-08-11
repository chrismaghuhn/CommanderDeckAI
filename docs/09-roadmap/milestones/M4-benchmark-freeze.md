# M4 — Completion Benchmark Freeze

## Ziel

Ein stabiler Benchmark, gegen den Modelle fair verglichen werden können.

## Deliverables

- zeitlicher Standardholdout;
- Cold-Commander-, New-Card- und Precon-Segmente;
- eingefrorene Masken und Candidate Pools;
- Leakage-Suite;
- Baseline-Report;
- Benchmarkmanifest und Checksums;
- versionierte Benchmark-Readiness-Policy;
- versionierte `learnability_decision_policy` mit Erfolgsmargins, Segmenttoleranzen und Experimentbudgets.

## Minimum-Viable-Benchmark-Trigger

M4 wird nicht aufgeschoben, bis sich die Data Foundation subjektiv "vollständig" anfühlt.

Vor dem Freeze werden konkrete Mindestwerte für Benchmark v1 committed, mindestens für:

- Zahl qualitätsgeprüfter Decks;
- Commander-/Command-Zone-Diversität;
- Train-/Validation-/Test-Samplecounts;
- verpflichtende Segmentgrößen;
- zulässige Unresolved-/Quarantine-Raten;
- temporale Cutoffs;
- Leakage-Prüfungen;
- Masken- und Candidate-Pool-Policies.

Sobald dieser versionierte Mindestzustand erfüllt ist, wird Benchmark v1 eingefroren.

Nicht verfügbare approval-/credential-gated Quellen wie TopDeck oder Spicerack blockieren den Freeze **nicht automatisch**, wenn der definierte Mindestzustand ohne sie erfüllt ist. Ihre Missingness wird dokumentiert; später hinzugefügte Daten gehören in Benchmark v2 statt still in v1.

## Decision Policy Freeze

Vor dem ersten entscheidungsrelevanten Modellvergleich werden für Benchmark v1 festgeschrieben:

- primäre/sekundäre Metriken;
- materielle relative Mindestverbesserungen für Learnability-Gates;
- Confidence-/Resampling-Verfahren;
- verpflichtende Masken-/Generaliserungssegmente;
- maximal akzeptierte Segmentregressionen;
- Tuning-Budgets pro Modellfamilie;
- maximales Diagnosebudget;
- Seed-Policy.

Diese Werte dürfen nach Sichtung der Benchmark-Ergebnisse nicht verschoben werden. Eine Änderung verlangt eine neue Decision-Policy-/Benchmark-Version.

Details: `docs/04-ml/learnability-pivot-gate.md`.

## Exit-Kriterien

- keine Splitüberschneidung;
- jede Metrik mit Samplecounts;
- Baselines auf identischen Pools;
- Testset nicht für Tuning verwendet;
- Readiness-Trigger erfüllt und versioniert;
- Learnability-Decision-Policy vor Ergebnisinterpretation eingefroren;
- Dokumentation ausreichend für unabhängige Reproduktion.
