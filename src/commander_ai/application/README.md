# Application

Use Cases und Ports. Orchestriert Domainobjekte, besitzt aber keine konkrete Infrastruktur. Die Source-Policy prüft typisierte Registry-/Current-use-Entscheidungen; die Configuration-Port referenziert bereits aufgelöste Konfigurationen, ohne YAML, HTTP oder DuckDB zu importieren.

## Unterteilung

- `ports/`: Protocols für Catalog, Repository, Ranker, Optimizer, Registry und Forge;
- `use_cases/`: ein Modul pro klarer Operation wie `build_dataset`, `rank_cards`, `optimize_deck`.

Keine HTTP-/DuckDB-/PyTorch-Klassen importieren.
