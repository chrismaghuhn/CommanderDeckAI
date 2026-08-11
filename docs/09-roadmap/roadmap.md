# Roadmap

```text
M0 Foundation
  ↓
M1 Card Catalog + Ruleset
  ↓
M2 Deck Imports + Statistical Baselines
  ↓
M3 Approved Commander/Tournament Sources
  ↓
M4 Frozen Completion Benchmark
  ↓
M5 Matrix Factorization + DeepSets Ranker
  ↓
M6 Deterministic Deck Optimizer
  ├── primary roadmap ──→ M7 cEDH Outcome Reranker
  │                       ↓
  │                     M8 Forge Evaluation Bridge
  │                       ↓
  │                     M9 Casual Evaluation/Product Layer
  │
  └── optional experiment:
      Joint Deck Consistency / Repair
```

## Grundregel

Ein späterer Milestone darf nicht die Exit-Kriterien eines früheren Milestones umgehen. Besonders M5 beginnt erst nach eingefrorenem M4-Benchmark, und M8 beginnt nicht als Ersatz für fehlende Offline-Qualität.

M4 wird durch ein vor M4 preregistriertes Minimum-Viable-Freeze-Profil ausgelöst. Seine numerischen Mindestwerte werden ausschließlich aus outcome-blinden deskriptiven Bestands-/Coverage-Statistiken nach reproduzierbarer Ableitungsregel bestimmt und müssen in der Git-Ancestry des ersten entscheidenden Validation-Runs liegen. Zusätzliche Quellen oder Plattformpolish dürfen den Freeze danach nicht verzögern.

M4 bewertet G0/G1 des Learnability-/Pivot-Gates. Matrix Factorization (`B6`) wird anschließend in M5 vor DeepSets gegen dieselbe preregistrierte Benchmarkversion bewertet. Eine fehlgeschlagene frühere Gate-Stufe darf nicht durch bloß mehr Modellkomplexität übersprungen werden.

Der optionale Joint-Consistency-/Repair-Gate nach M6 ist kein eigener Pflicht-Milestone und blockiert M7 nicht. Er wird nur aktiviert, wenn der one-shot Ranker+CP-SAT-Pfad einen messbaren Kontextfehler zeigt und ein iteratives Verfahren diesen auf eingefrorenen Benchmarks besser löst. Zusätzliche Komplexität muss sich durch Ablation, Stabilität und Laufzeitmessung verdienen.

## Semantische Evidenzstufen

- M2–M5: Recommendation-/Completion-Evidenz;
- M6: constraint-konforme Deckkonstruktion;
- M7: kompetitive Outcome-Evidenz;
- M8: Gameplay-Evidenz;
- M9: Casual-Präferenz-/Produkt-Evidenz.

Diese Stufen sind nicht austauschbar. Insbesondere ist eine bessere Completion-NDCG kein direkter Beweis für proportional bessere Deckstärke.

## Nutzbarer Wert entlang der Roadmap

- M2 liefert bereits einen echten, nicht-LLM-basierten Recommendation-Baseline;
- M4 liefert einen publizierbaren Benchmark und eine explizite GREEN/YELLOW/RED-Entscheidung zur Completion-Formulierung;
- M5 darf Modellkomplexität nur entsprechend des Learnability-Gates erhöhen;
- M6 liefert vollständige legale Decks;
- M7/M8 ergänzen Performance-Evidenz;
- M9 macht Casual-Ziele produktreif, ohne sie in cEDH-Winrate zu pressen.
