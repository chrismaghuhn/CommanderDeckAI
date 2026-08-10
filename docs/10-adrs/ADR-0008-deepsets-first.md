# ADR-0008-deepsets-first — DeepSets vor Set Transformer

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Erstes neuronales Modell ist DeepSets. Attention folgt nur nach belegter Grenze.

## Begründung

Permutation-Invarianz bei geringer Komplexität, leichter Debug, faire Baseline.

## Folgen

Set-Transformer-Arbeit benötigt Gate-Dokument und Ablation.
