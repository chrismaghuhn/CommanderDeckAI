# System Context

```mermaid
flowchart LR
    User[CLI / spätere UI] --> CDA[Commander Deck AI]
    Sources[freigegebene Datenquellen] --> CDA
    CDA --> Local[(Parquet / DuckDB)]
    CDA --> Artifacts[(Dataset- und Modellartefakte)]
    CDA --> ForgeBridge[Forge File Bridge]
    ForgeBridge --> Forge[Forge Rules/Simulation]
    Forge --> ForgeBridge
```

Commander Deck AI ist Eigentümer von:

- kanonischer Deck-/Datasetrepräsentation;
- Ranking und Optimierung;
- Offline-Benchmarks;
- Provenienz- und Artefaktmanifeste.

Forge ist Eigentümer von:

- Spielregeln während einer Partie;
- Simulation und Agentverhalten;
- Simulationsresultaten mit Forge-/Agentversion.

Externe Quellen bleiben Eigentümer ihrer Daten. Das Projekt speichert nur, was der jeweilige Source-Review erlaubt.
