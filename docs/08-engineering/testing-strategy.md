# Teststrategie

## Unit

Reine Funktionen, Domain-Invarianten, Score-Komponenten, Mapperhelfer.

## Contract

JSON-Schemas, Source-Payload-Fixtures, Modell-/Datasetmanifeste, Forge-Verträge.

## Integration

DuckDB/Parquet-Roundtrips, Adapter mit lokalem HTTP-Stub, Dataset-Build aus Tiny Snapshot.

## Property

Decklegalität, Copy Limits, Deduplikationsinvarianten, Optimizerresultate, deterministische Masken.

## Golden

Stabile Source-Responses, SQL-Outputs und Benchmarkreports. Änderungen benötigen bewusste Review.

## End-to-End

Tiny Card Catalog → Deck Import → Completion Samples → Baseline Ranking → Optimizer → Result Validation.

## Kein Live-Netz in PR-CI

Live-Smokes sind manuell oder geplant und dürfen normale Pull Requests nicht flakig machen.
