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
Learnability Gate: G0/G1/G3
  ├── GREEN ──→ M5 Matrix Factorization + gated DeepSets
  ├── YELLOW ─→ bounded diagnosis ─→ GREEN or RED
  └── RED ────→ reformulate / Benchmark v2
                  
M5 GREEN path
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

Ein späterer Milestone darf nicht die Exit-Kriterien eines früheren Milestones umgehen. Besonders M5 beginnt erst nach eingefrorenem M4-Benchmark und positivem Learnability-Gate, und M8 beginnt nicht als Ersatz für fehlende Offline-Qualität.

M4 besitzt einen versionierten Minimum-Viable-Benchmark-Trigger. Sobald der definierte Mindestzustand erfüllt ist, wird Benchmark v1 eingefroren; optionale oder approval-gated Quellen dürfen den Freeze nicht unbegrenzt aufschieben. Zusätzliche Daten landen in einer späteren Benchmark-Version.

Vor Ergebnisinterpretation werden materielle Erfolgsmargins, Segmenttoleranzen, Tuning-Budgets und Diagnosebudget eingefroren. YELLOW erlaubt nur begrenzte Diagnose; RED blockiert zusätzliche Modellkomplexität bis zu einer reviewten Neuformulierung/Benchmark-Version.

Details: `docs/04-ml/learnability-pivot-gate.md`.

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
- M4 liefert einen publizierbaren Benchmark plus vorregistrierte Learnability-/Pivot-Regeln;
- M5 testet Modellkapazität nur nach positivem Context-Signal;
- M6 liefert vollständige legale Decks;
- M7/M8 ergänzen Performance-Evidenz;
- M9 macht Casual-Ziele produktreif, ohne sie in cEDH-Winrate zu pressen.
