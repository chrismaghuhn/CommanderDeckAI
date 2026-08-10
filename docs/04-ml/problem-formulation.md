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
