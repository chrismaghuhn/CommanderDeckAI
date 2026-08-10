# M5 — Matrix Factorization und DeepSets

## Ziel

Spezialisierte nicht-sprachbasierte Modelle, die Baselines messbar schlagen.

## Deliverables

- einheitliches `CardRanker`-Protokoll;
- weighted Matrix-Factorization-Baseline;
- DeepSets v1;
- Feature-Pipeline und OOV-Fallback;
- Training-/Modelmanifeste;
- Ablations- und Segmentreports;
- Batch-Inference.

## Exit-Kriterien

- messbare Verbesserung gegen B5/B6;
- keine unakzeptierte Coverage-/Long-Tail-Regression;
- Cold-Commander-Bericht;
- Modell ohne Netz/Source-Abhängigkeit ladbar;
- `uses_pretrained_language_model=false` verifiziert.
