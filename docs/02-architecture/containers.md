# Logische Container

## 1. CLI/Batch Entry Points

Parst Argumente und Konfiguration, ruft Use Cases auf, enthält keine Geschäftslogik.

## 2. Application Core

Orchestriert Source-Sync, Dataset-Build, Ranking, Optimierung und Evaluation über Ports.

## 3. Domain

Reine Typen und Invarianten: Kartenidentität, Deckzonen, Constraints, Ruleset-Referenzen, Provenienz.

## 4. Data Pipeline

Normalisierung, Deduplikation, Qualitätsprüfung, Splitting und Dataset-Erzeugung.

## 5. Models

Einheitliches Ranking-Protokoll sowie Baselines, Matrix Factorization und DeepSets.

## 6. Optimization

Kandidatenreduktion, Core-Deck-Solver, Mana-Base-Solver, objektive Score-Komponenten und finaler Validator.

## 7. Evaluation

Metriken, Benchmark-Protokolle, Leakage-Kontrollen und Reports.

## 8. Adapters

HTTP, Source-Clients, Parquet/DuckDB, Modellartefakte und Forge-Dateiaustausch.

Es sind **Module in einem Prozess**, keine separat deployten Services.
