# DuckDB Canonical Schema Blueprint

Die Dateien sind bewusst nach Verantwortungsgruppen getrennt. Migrations-/Produktionsschema kann Pydantic/SQL-Modelle verwenden, aber die resultierenden Tabellen müssen diese Semantik beibehalten.

Ausführungsreihenfolge: `001` bis `006`. Alle DDLs sind idempotent (`CREATE TABLE IF NOT EXISTS`). Parquet bleibt die veröffentlichte/immutable Wahrheit; diese Tabellen dienen lokalen Materialisierungen und Qualitätsabfragen.
