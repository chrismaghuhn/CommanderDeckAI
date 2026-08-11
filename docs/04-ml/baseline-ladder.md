# Baseline-Leiter

Jede Stufe wird auf demselben eingefrorenen Benchmark gemessen.

Die Leiter ist zugleich eine Learnability-Diagnose. Eine spätere Stufe darf eine fehlgeschlagene frühere Stufe nicht einfach durch mehr Modellkomplexität überdecken. Die Entscheidungsregeln stehen in `docs/06-evaluation/learnability-pivot-gate.md`.

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

B4 ist der erste zentrale Test des Architektur-Claims, dass der **sichtbare Deckkontext** gegenüber Commander-only Ranking zusätzlichen Predictive Value liefert.

## B5 — Hybrid Linear Ranker

Gewichtete Kombination aus B1–B4, Rollenfit, Kurve und Combo-Features. Gewichte auf Validation fitten.

B0–B5 bilden die nicht-neuronale M4-Learnability-Leiter. Ihre Daten, Masken, Candidate Pools, Metriken und Experimentbudgets werden durch den M4-Freeze gebunden.

## B6 — Weighted Matrix Factorization

Lernt latente Deck-/Karten- oder Context-/Kartenfaktoren.

B6 ist der erste verpflichtende Modellkapazitäts-Test in M5 und wird **vor DeepSets** gegen die stärkste zulässige B4/B5-Baseline gemessen.

## M1 — DeepSets

Erstes neuronales Hauptmodell. DeepSets wird nur gemäß Learnability-/Pivot-Gate gestartet. Ein fehlgeschlagenes oder schwaches B6 rechtfertigt nicht automatisch größere Netze; bei schwachem Context-Signal ist zuerst die Formulierung zu diagnostizieren.

Set Transformer wird erst nach dokumentierter DeepSets-Grenze geprüft.
