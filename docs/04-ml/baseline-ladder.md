# Baseline-Leiter

Jede Stufe wird auf demselben eingefrorenen Benchmark gemessen.

## B0 — Random Legal

Zufällige Reihenfolge aller legalen Kandidaten. Prüft Pipeline und Metriken.

## B1 — Global Popularity

Häufigkeit einer Karte im Trainingssplit, optional nach Modus/Farbidentität.

## B2 — Commander Popularity

`P(card | command_zone)` mit Glättung.

## B3 — Lift/PMI

Bestraft globale Staples und belohnt überproportionale Commander-Zuordnung:

```text
log P(card | commander) - log P(card)
```

## B4 — Card-Card Co-Occurrence

Aggregiert Ähnlichkeit zwischen Kandidat und sichtbarem Teildeck. Nur Trainingsdaten verwenden.

## B5 — Hybrid Linear Ranker

Gewichtete Kombination aus B1–B4, Rollenfit, Kurve und Combo-Features. Gewichte auf Validation fitten.

## B6 — Weighted Matrix Factorization

Lernt latente Deck-/Karten- oder Context-/Kartenfaktoren. B6 gehört in M5 und wird vor DeepSets ausgewertet.

## M1 — DeepSets

Erstes neuronales Hauptmodell. Set Transformer wird erst nach dokumentierter DeepSets-Grenze geprüft.

## Welche Frage beantwortet welche Stufe?

```text
B0 -> B1/B2
Gibt es überhaupt lernbares Commander-Signal?

B2 -> B4
Liefert der sichtbare Deckkontext zusätzlichen Predictive Value?

B4 -> B5/B6
Liefert zusätzliche Feature-/Modellkapazität weiteren Nutzen?

B6 -> DeepSets
Ist ein nichtlineares Set-Modell durch Messung oder konkrete Fehleranalyse gerechtfertigt?
```

Die Leiter ist deshalb nicht nur ein Leaderboard. Sie ist eine Kette von Hypothesentests für die Problemformulierung.

## Entscheidungs-Gate

Vor Auswertung werden im M4-Benchmark eine versionierte `learnability_decision_policy`, materielle Mindestabstände, Segmentregressionen und Tuning-Budgets eingefroren.

Insbesondere ist `B2 -> B4` das zentrale Context-Gate: Wenn der sichtbare Deckkontext nach begrenzter Diagnose keinen vorregistrierten Zusatznutzen liefert, darf die Antwort nicht automatisch ein größeres Modell sein.

B5/B6 und DeepSets erhalten begrenzte Validation-Budgets. Der Frozen Test wird nicht für Hyperparameter- oder Threshold-Auswahl verwendet.

Details: `docs/04-ml/learnability-pivot-gate.md`.
