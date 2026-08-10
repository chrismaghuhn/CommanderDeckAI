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

Lernt latente Deck-/Karten- oder Context-/Kartenfaktoren.

## M1 — DeepSets

Erstes neuronales Hauptmodell. Set Transformer wird erst nach dokumentierter DeepSets-Grenze geprüft.
