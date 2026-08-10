# Inference

## Schritte

1. Anfrage und Ruleset validieren;
2. legalen Kandidatenpool erzeugen;
3. Must-Excludes und Collection-/Budgetfilter anwenden;
4. Features aus exakt dem Modell-kompatiblen Snapshot bilden;
5. Kandidaten in Batches scoren;
6. Score-Komponenten und Unsicherheit persistieren;
7. `RankResponse` oder Score-Snapshot erzeugen.

## Reproduzierbarkeit

Der Score-Snapshot enthält alle Kandidaten, nicht nur Top-K, soweit Speicherbudget dies zulässt. Mindestens müssen alle an den Optimizer übergebenen Kandidaten mit unveränderten Komponenten gespeichert werden.

## Caching

Cache-Key:

```text
model_id + feature_snapshot + ruleset + command_zone
+ partial_deck_fingerprint + profile_hash + candidate_pool_hash
```

Cache ist eine Optimierung und darf Ergebnisse nicht semantisch verändern.
