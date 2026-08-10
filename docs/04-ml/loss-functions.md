# Loss-Funktionen

## Start: Sampled Binary Cross Entropy

Positive und negative Kandidaten werden gemeinsam gescored. Vorteile: einfach, stabil, gut debuggbar.

## Alternative: Pairwise BPR

Optimiert direkt, dass ein positives Label über einem Negativ liegt. Als kontrolliertes Experiment nach BCE.

## Optionaler Multi-Task-Loss

- Rollen-Multilabel;
- Mana-Value-Bucket;
- Commander-/Archetyp-Kontrastivziel.

Zusatzaufgaben dürfen den Hauptbenchmark nicht verschlechtern und benötigen eigene Ablation.

## Gewichtung

- inverse Clustergröße;
- Popularitätskorrektur;
- Source-/Qualitätsgewicht;
- keine Outcome-Gewichte im allgemeinen Completion-Modell, bevor Bias-Analyse existiert.

## Kalibrierung

Ranking-Metriken benötigen keine perfekte Wahrscheinlichkeit. Falls Scores als Wahrscheinlichkeit angezeigt oder im Optimizer sourceübergreifend kombiniert werden, erfolgt eine separate Validation-Kalibrierung.
