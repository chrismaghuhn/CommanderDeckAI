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

## Doppelzählung und Ablation

Der Ranker kann Synergie bereits implizit aus Co-Occurrence und Deckkontext lernen. Pair-Synergy, Combo-Boni und Rollenfeatures können dieselbe Evidenz erneut ausdrücken. Mehrere positive Komponenten dürfen deshalb nicht ungeprüft als unabhängige Qualitätssignale behandelt werden.

Vor einer Default-Gewichtung werden mindestens folgende Varianten auf demselben eingefrorenen Benchmark verglichen:

```text
ranker
ranker + roles
ranker + pair
ranker + combo
ranker + pair + combo + roles
```

Die Ablation berichtet nicht nur den Gesamt-Objective-Wert, sondern auch Recommendation-Metriken, Constraint-Erfüllung, Rollenredundanz, Combo-/Pair-Komponenten, Deckdiversität und Laufzeit. Eine höhere interne Optimizer-Summe allein gilt nicht als Beweis für bessere Deckqualität.

Ein späteres iteratives Contextual Re-Score/Repair ist ebenfalls nur ein experimenteller Zusatz und muss gegen den one-shot Pfad abliert werden; siehe `joint-deck-consistency.md`.
