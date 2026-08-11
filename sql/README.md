# DuckDB Canonical Schema Blueprint

Migration `007_snapshot_objects.sql` adds only derived local indexes for verified raw
snapshot manifests, requests, and objects. The files under `data/raw/` remain the
authoritative source and the SQL tables must be reconstructable from them without
reacquisition. The migration is idempotent and does not replace the raw-byte or
`COMPLETE` verification boundary.

Die Dateien sind bewusst nach Verantwortungsgruppen getrennt. Migrations-/Produktionsschema kann Pydantic/SQL-Modelle verwenden, aber die resultierenden Tabellen müssen diese Semantik beibehalten.

Ausführungsreihenfolge: `001` bis `008`. Migration `008_staging_audit_runs.sql` ergänzt ausschließlich rebuildbare lokale Indizes für Staging, Audit/Resolution/Quarantäne, Run-Manifeste und normalisierte Snapshot-Manifeste samt Artefakt-Referenzen. Parquet, Raw-Manifeste und normalisierte Manifeste bleiben die veröffentlichte/immutable Wahrheit; alle Tabellen können aus diesen Dateien ohne erneuten Quellenabruf rekonstruiert werden.
