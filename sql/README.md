# DuckDB Canonical Schema Blueprint

Migration `007_snapshot_objects.sql` adds only derived local indexes for verified raw
snapshot manifests, requests, and objects. The files under `data/raw/` remain the
authoritative source and the SQL tables must be reconstructable from them without
reacquisition. The migration is idempotent and does not replace the raw-byte or
`COMPLETE` verification boundary.

Die Dateien sind bewusst nach Verantwortungsgruppen getrennt. Migrations-/Produktionsschema kann Pydantic/SQL-Modelle verwenden, aber die resultierenden Tabellen müssen diese Semantik beibehalten.

Ausführungsreihenfolge: `001` bis `007`. Alle DDLs sind idempotent (`CREATE TABLE IF NOT EXISTS`). Parquet und Raw-Manifeste bleiben die veröffentlichte/immutable Wahrheit; diese Tabellen dienen lokalen Materialisierungen und Qualitätsabfragen.
