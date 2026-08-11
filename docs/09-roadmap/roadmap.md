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
  ↓
[optional experiment gate: Joint Deck Consistency / Repair]
  ↓
M7 cEDH Outcome Reranker
  ↓
M8 Forge Evaluation Bridge
  ↓
M9 Casual Evaluation/Product Layer
```

## Grundregel

Ein späterer Milestone darf nicht die Exit-Kriterien eines früheren Milestones umgehen. Besonders M5 beginnt erst nach eingefrorenem M4-Benchmark, und M8 beginnt nicht als Ersatz für fehlende Offline-Qualität.

Der optionale Joint-Consistency-/Repair-Gate nach M6 ist kein eigener Pflicht-Milestone. Er wird nur aktiviert, wenn der one-shot Ranker+CP-SAT-Pfad einen messbaren Kontextfehler zeigt und ein iteratives Verfahren diesen auf eingefrorenen Benchmarks besser löst. Zusätzliche Komplexität muss sich durch Ablation, Stabilität und Laufzeitmessung verdienen.

## Semantische Evidenzstufen

- M2–M5: Recommendation-/Completion-Evidenz;
- M6: constraint-konforme Deckkonstruktion;
- M7: kompetitive Outcome-Evidenz;
- M8: Gameplay-Evidenz;
- M9: Casual-Präferenz-/Produkt-Evidenz.

Diese Stufen sind nicht austauschbar. Insbesondere ist eine bessere Completion-NDCG kein direkter Beweis für proportional bessere Deckstärke.

## Nutzbarer Wert entlang der Roadmap

- M2 liefert bereits einen echten, nicht-LLM-basierten Recommendation-Baseline;
- M4 liefert einen publizierbaren Benchmark;
- M6 liefert vollständige legale Decks;
- M7/M8 ergänzen Performance-Evidenz;
- M9 macht Casual-Ziele produktreif, ohne sie in cEDH-Winrate zu pressen.
