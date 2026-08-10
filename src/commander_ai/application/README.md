# Application

Use Cases und Ports. Orchestriert Domainobjekte, besitzt aber keine konkrete Infrastruktur.

## Unterteilung

- `ports/`: Protocols für Catalog, Repository, Ranker, Optimizer, Registry und Forge;
- `use_cases/`: ein Modul pro klarer Operation wie `build_dataset`, `rank_cards`, `optimize_deck`.

Keine HTTP-/DuckDB-/PyTorch-Klassen importieren.
