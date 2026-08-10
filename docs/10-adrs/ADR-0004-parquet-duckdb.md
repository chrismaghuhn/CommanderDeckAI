# ADR-0004-parquet-duckdb — Parquet und DuckDB als lokale Datenbasis

**Status:** Accepted<br>
**Datum:** 2026-08-10


## Entscheidung

Immutable Parquet-Artefakte plus DuckDB für Transformation und Analyse.

## Begründung

Spaltenformat, Streaming/Pushdown, portable Dateien und kein Datenbankserver passen zum Projektumfang.

## Folgen

DuckDB-Dateien sind Cache, nicht alleinige Wahrheit. Manifeste und Parquet bleiben authoritative.
