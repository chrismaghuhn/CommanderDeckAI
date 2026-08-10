# Komponenten- und Portgrenzen

## Zentrale Ports

- `CardCatalog`: liest kanonische Karten und Ruleset-Snapshots.
- `DeckRepository`: streamt normalisierte Decks.
- `SourceAdapter`: erzeugt unveränderliche Raw Snapshots und Provenienz.
- `DatasetRepository`: liest/schreibt Datasetmanifeste und Parquet-Dateien.
- `CardRanker`: bewertet Kandidaten unabhängig vom Optimizer.
- `DeckOptimizer`: konsumiert einen eingefrorenen Score-Snapshot.
- `ModelRegistry`: speichert/lädt Modellartefakte über Manifeste.
- `ForgeGateway`: schreibt Requests und liest Results.

## Wichtige Trennung

Der Optimizer erhält **keinen direkten PyTorch-Modellzugriff**. Er erhält eine Liste von Kandidaten und Scores. Dadurch sind Solver-Runs reproduzierbar und Modell-/Solver-Fehler getrennt testbar.

Der Ranker kennt keine API-Clients. Er verarbeitet bereits kanonische Features.

Source-spezifische Felder verlassen den jeweiligen Mapper nicht; unbekannte Rohfelder können im Raw Snapshot erhalten bleiben, werden aber nicht unkontrolliert in die Domain geschoben.
