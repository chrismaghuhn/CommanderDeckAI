# M5 — Matrix Factorization und DeepSets

## Ziel

Spezialisierte nicht-sprachbasierte Modelle, die Baselines messbar schlagen.

## Entry-Gate

M5 beginnt erst nach eingefrorenem M4-Benchmark und einem positiven Learnability-Gate für die Completion-Formulierung.

Mindestens müssen gelten:

- G0 Pipeline-/Commander-Signal PASS;
- G1 sichtbarer Deckkontext liefert den vorregistrierten materiellen Zusatznutzen oder ein begrenztes Diagnoseverfahren hat die Formulierung ausdrücklich freigegeben;
- keine unakzeptierte Generalisierungs-/Segmentregression gemäß M4-Decision-Policy.

Ein RED-Gate blockiert neue Modellkomplexität. Dann wird zuerst die Formulierung oder Benchmark-Version geändert.

Details: `docs/04-ml/learnability-pivot-gate.md`.

## Deliverables

- einheitliches `CardRanker`-Protokoll;
- weighted Matrix-Factorization-Baseline B6;
- dokumentiertes Capacity-/Fehleranalyse-Gate vor DeepSets;
- DeepSets v1, sofern das Gate es rechtfertigt;
- Feature-Pipeline und OOV-Fallback;
- Training-/Modelmanifeste;
- Ablations- und Segmentreports;
- Batch-Inference.

## Reihenfolge

```text
Frozen M4 + Learnability GREEN
  ↓
B6 Weighted Matrix Factorization
  ↓
Capacity-/Fehleranalyse
  ↓
DeepSets nur bei vorab definierter Hypothese und Erfolgsmargin
```

Wenn B6 einfachere Context-/Hybrid-Baselines nicht materiell verbessert, ist DeepSets **nicht automatisch** der nächste Schritt. Ein DeepSets-Experiment benötigt dann eine konkrete dokumentierte Fehlerhypothese, die die einfachere Modellklasse nicht ausdrücken kann, und eine vor Training festgelegte Erfolgsmargin.

Validation-Tuning bleibt innerhalb des eingefrorenen Budgets. Der Frozen Test wird nicht für Modell-/Hyperparameter-Auswahl verwendet.

## Exit-Kriterien

- messbare Verbesserung gegen die jeweils relevante eingefrorene B5/B6-Baseline gemäß Decision Policy;
- keine unakzeptierte Coverage-/Long-Tail-Regression;
- Cold-Commander-Bericht;
- Modell ohne Netz/Source-Abhängigkeit ladbar;
- `uses_pretrained_language_model=false` verifiziert;
- Trial-/Diagnosebudget und Gate-Entscheidung im Experimentreport dokumentiert.
