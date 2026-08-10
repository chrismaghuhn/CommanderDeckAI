# M7 — cEDH Outcome Reranker

## Ziel

Turnier-/Pod-Evidenz als separaten, kalibrierten Zusatzscore nutzbar machen.

## Deliverables

- Event-/Pod-Temporal-Split;
- Bias-/Missingness-Audit;
- einfache Outcome-Baselines;
- Modell auf eingefrorenen Deckembeddings;
- Calibration-/Uncertainty-Report;
- Optimizer-Rerank-Integration hinter Feature Flag.

## Exit-Kriterien

- bessere Log Loss/Brier als Commander-Metashare-Baseline;
- Event-Leakage ausgeschlossen;
- Unsicherheit sichtbar;
- Casualprofil unverändert;
- Outcome-Score kann abgeschaltet werden.
