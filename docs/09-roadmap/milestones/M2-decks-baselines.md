# M2 — Deckimporte und statistische Baselines

## Ziel

Erster vertikaler Completion-Benchmark ohne neuronales Modell.

## Deliverables

- manueller Decklistenimport;
- offizielle Precon-Imports über freigegebene Daten;
- Decknormalisierung/Deduplikation;
- Completion-Sample-Builder;
- Random-, Popularitäts-, Commander-Lift- und Co-Occurrence-Ranker;
- CLI `rank` und Benchmarkreport.

## Exit-Kriterien

- Tiny und reale lokale Datasets laufen end-to-end;
- Splits gruppieren Revisionen/Duplikate;
- Baselinewerte reproduzierbar;
- Qualitäts-/Leakagereport vorhanden;
- Recommendation-Ausgabe enthält Score-Komponenten.
