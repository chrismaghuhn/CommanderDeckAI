# Produktvertrag

## Minimale Anfrage

```json
{
  "command_zone": ["oracle-id"],
  "partial_deck": ["oracle-id"],
  "mode": "casual",
  "top_k": 50,
  "ruleset_version": "commander-2026-02-09"
}
```

## Zusätzliche Constraints

- Must-Include/Must-Exclude;
- Budget und Preis-Snapshot;
- Rollen-Minima/Maxima;
- Landbereich;
- erlaubte/verbotene Themen;
- gewünschtes Bracket-/Intent-Profil;
- verfügbare Sammlung;
- maximale Staple-Abhängigkeit.

## Antwort

Jede Kandidatenkarte enthält mindestens:

- finalen Score;
- Ranker-Score;
- Commander- und Deck-Co-Occurrence;
- Rollenbeitrag;
- Combo-/Synergiebezug;
- Popularitäts-/Staple-Penalty;
- Unsicherheit;
- Legalitätsstatus;
- Modell-, Dataset- und Ruleset-Version.
