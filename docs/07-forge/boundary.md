# Forge-Grenze

Forge wird nicht in die Python-ML-Pipeline eingebettet. Commander Deck AI und Forge bleiben getrennte Systeme mit einem versionierten Austauschformat.

## Commander Deck AI liefert

- vollständige kanonische Decklisten;
- Ruleset- und Karten-Snapshot;
- gewünschte Pod-Konfiguration;
- Agent-/Policy-IDs;
- Seeds, Sitzrotationen und Evaluationsparameter.

## Forge liefert

- Annahme/Ablehnung der Anfrage;
- Forge-Commit und Rules-Engine-Version;
- normalisierte Spielergebnisse;
- Abbruch-/Fehlergründe;
- optionale aggregierte Telemetrie;
- Hashes der tatsächlich geladenen Decks.

## Autorität

Python validiert Deckbau-Constraints. Forge bleibt Autorität für die Ausführung einer Partie. Abweichungen werden als Contract-/Ruleset-Mismatch behandelt, nicht still korrigiert.
