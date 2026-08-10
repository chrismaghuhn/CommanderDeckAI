# Weiche Ziele

Ein Optimizerprofil gewichtet getrennte Komponenten:

```text
card_rank_score
pair_synergy_score
role_coverage_score
mana_curve_fit
color_pip_support
combo_completeness
theme_alignment
novelty
budget_preference
staple_penalty
uncertainty_penalty
```

## Grundregeln

- jede Komponente wird separat im Ergebnis ausgewiesen;
- Gewichte sind versionierte Config, nicht im Code versteckt;
- Scores werden vor Kombination skaliert/kalibriert;
- Casual und cEDH verwenden getrennte Profile;
- keine einzige Komponente darf Legalität überschreiben;
- Popularität ist Signal und Bias zugleich.

## Pairwise Synergy

Nur Top-K positive/negative Kanten werden in CP-SAT aufgenommen. Für jede relevante Paarung kann eine Hilfsvariable `z_ij = x_i AND x_j` verwendet werden. Vollständiges O(N²) wird vermieden.
