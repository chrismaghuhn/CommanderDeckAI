# Datenqualitätsregeln

## Blockierend

- unbekannte Kartenidentität;
- fehlende Command Zone;
- nicht parsebare Mengen;
- unmögliche Zonenanzahl;
- Source-Snapshot unvollständig;
- Schema-/Ruleset-Version unbekannt;
- Ergebnis verweist auf nicht vorhandenes Deck/Event.

## Quarantäne statt Löschen

Illegale oder unvollständige Decks werden mit Finding-Codes in Quarantäne geschrieben. Sie können für spezielle Analysen erhalten bleiben, dürfen aber nicht automatisch in den Completion-Trainingssatz gelangen.

## Warnungen

- ungewöhnliche Deckgröße;
- sehr alter Ruleset-Snapshot;
- übermäßige Basic-Land-Mengen;
- wahrscheinlich kopiertes Precon;
- fehlende Update-Zeit;
- unbekannte Resultatsemantik.

Jede Dataset-Erzeugung veröffentlicht Counts pro Finding-Code.
