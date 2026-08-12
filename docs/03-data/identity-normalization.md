# Identität und Normalisierung

## Kartenidentität

- Trainings- und Decklogik verwendet `oracle_id`;
- konkretes Printing wird nur für Preis, Sammlung oder Export benötigt;
- Namen dienen Anzeige und Fallback-Matching, nie als primärer Schlüssel;
- Split-/Meld-/Transform-Karten behalten eine kanonische Card-ID und strukturierte Face-Daten.

## Deckidentität

`commander-structural-v1` ist ein SHA-256-Hash der kanonischen JSON-Darstellung
folgender Struktur:

```text
format family = commander
sorted command-zone (oracle_id, quantity)
sorted card-zone records (zone, oracle_id, quantity)
```

UUID-Texte werden vor der Hashbildung in die kleingeschriebene Schema-Darstellung
normalisiert. RulesetSnapshot-Version, Source-ID, Titel, Spieler, Event und
Evaluationsdaten fließen nicht ein. `canonical_deck_id` ist derselbe deterministische
Fingerprint; die aktuelle Algorithmusversion wird im CanonicalDeck gebunden.

## Command Zone

Nicht `commander_id`, sondern `command_zone: list[oracle_id]`. Der Validator entscheidet anhand des Rulesets, welche Kombinationen zulässig sind.

## Copy Limits

Copy Limits werden durch Ruleset + Kartenausnahmen bestimmt. Basic Lands und Kartentexte mit abweichender Kopienzahl dürfen nicht über eine simple globale Singleton-Abfrage modelliert werden.
