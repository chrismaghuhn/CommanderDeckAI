# Baseline-Vergleichsprotokoll

## Fairness

- gleiche Candidate Pools;
- gleiche Splits und Masken;
- gleiche verfügbaren Features zum Beobachtungszeitpunkt;
- identische Ausschlüsse und Rulesets;
- Hyperparameter nur auf Validation;
- Test genau einmal pro Releasekandidat.

## Mindestbericht

| Modell | NDCG@25 | Recall@25 | Coverage | Long-Tail Recall | Parameter | Dataset |
|---|---:|---:|---:|---:|---:|---|

Zusätzlich segmentieren nach Datenmenge des Commanders, Farbidentität, Deckmodus, Maskenart und Zeitfenster.

Ein komplexes Modell wird nicht akzeptiert, wenn der globale Gewinn allein von beliebten Commanders stammt und Low-Data-Segmente schlechter werden.
