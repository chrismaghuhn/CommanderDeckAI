# Composition Root

Nur `commander_ai.cli` und spätere API-Adapter verdrahten konkrete Implementierungen.

Beispiel für `rank`:

```text
CLI config loader
  → ParquetCardCatalog
  → ParquetDeckRepository
  → LocalModelRegistry
  → concrete CardRanker
  → RankCards use case
```

## Regeln

- keine globalen Singletons;
- Clients/Repositories werden explizit erzeugt und injiziert;
- Settings werden einmal geladen;
- Ressourcen besitzen klaren Lifecycle/Context Manager;
- Tests können Ports durch In-Memory-Fakes ersetzen;
- keine Dependency-Injection-Framework-Pflicht.
