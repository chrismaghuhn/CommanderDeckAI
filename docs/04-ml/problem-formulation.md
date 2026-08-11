# Problemformulierung

## Primäre Aufgabe: Candidate Ranking

Gegeben:

- Command-Zone-Set `C`;
- sichtbares Teildeck `D_visible`;
- Zielprofil `P`;
- Ruleset `R`;
- legaler Kandidatenpool `K`.

Lerne einen Score:

```text
s(card | C, D_visible, P, R)
```

Der Score sortiert Kandidaten. Das Modell muss **kein Deck sequenziell generieren**.

## Supervised Target

Aus einem realen Deck `D` werden Karten maskiert:

```text
positive = D_masked
context  = C + D_visible
negative = legale Karten, die nicht in D liegen
```

Das Modell lernt, positive Karten über negative zu ranken.

## Semantische Grenze

Masked Completion lernt primär die Verteilung plausibler Karten in beobachteten Decks. Der Ranker ist deshalb zunächst ein Recommendation-Modell, kein direkter Beweis für Deckstärke.

```text
Recommendation quality
!= Construction quality
!= Gameplay strength
```

Eine Verbesserung von Recall/NDCG darf nicht als proportionale Verbesserung von Winrate, objektiver Deckqualität oder Casual-Präferenz beschrieben werden. M6 fügt constraint-konforme Konstruktion hinzu; M7/M8 liefern separat Outcome- beziehungsweise Gameplay-Evidenz.

Wenn der one-shot Ranker+Optimizer-Pfad später messbare Kontextdrift zeigt, darf ein experimentelles Re-Score/Repair-Verfahren evaluiert werden. Es ist kein impliziter Bestandteil des Ranker-Targets; siehe `docs/05-optimizer/joint-deck-consistency.md`.

## Sekundäre Aufgaben

- Deck-/Commander-Embedding lernen;
- Rollen-/Themen-Multilabels vorhersagen;
- cEDH-Pod-Outcome als separater Reranker;
- Unsicherheit für Low-Data-Commander schätzen.

## Nicht als Target verwenden

- bloße Kartenpopularität als „Qualität“;
- Casual-Winrate als alleinige Wahrheit;
- aktuelle Aggregatfeatures für historische Samples;
- illegalen Kandidatenpool.
