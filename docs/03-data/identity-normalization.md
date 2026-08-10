# Identität und Normalisierung

## Kartenidentität

- Trainings- und Decklogik verwendet `oracle_id`;
- konkretes Printing wird nur für Preis, Sammlung oder Export benötigt;
- Namen dienen Anzeige und Fallback-Matching, nie als primärer Schlüssel;
- Split-/Meld-/Transform-Karten behalten eine kanonische Card-ID und strukturierte Face-Daten.

## Deckidentität

`deck_fingerprint_v1` ist ein Hash über:

```text
ruleset family
sorted command-zone oracle IDs
sorted (zone, oracle_id, quantity)
```

Source-ID und Titel fließen nicht ein.

## Command Zone

Nicht `commander_id`, sondern `command_zone: list[oracle_id]`. Der Validator entscheidet anhand des Rulesets, welche Kombinationen zulässig sind.

## Copy Limits

Copy Limits werden durch Ruleset + Kartenausnahmen bestimmt. Basic Lands und Kartentexte mit abweichender Kopienzahl dürfen nicht über eine simple globale Singleton-Abfrage modelliert werden.
