"""Rebuildable DuckDB projections backed only by immutable Parquet artifacts."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import duckdb

from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .parquet_tables import ParquetArtifact
from .path_policy import resolve_under_root
from .raw_snapshot_io import sha256_file


@dataclass(frozen=True, slots=True)
class DuckDBRebuildResult:
    """Stable summary of one derived-cache rebuild."""

    artifact_count: int
    row_count: int
    content_sha256: str


class _CountQueryResult(Protocol):
    def fetchone(self) -> tuple[object, ...] | None:
        """Return one aggregate row."""


class DuckDBDerivedStore:
    """Materialize a small query cache without becoming an artifact authority."""

    def __init__(self, artifact_root: Path | str, database_path: Path | str) -> None:
        self._artifact_root = Path(artifact_root).expanduser().absolute()
        self._database_path = Path(database_path).expanduser().absolute()

    def rebuild(self, artifacts: Sequence[ParquetArtifact]) -> DuckDBRebuildResult:
        ordered = tuple(sorted(artifacts, key=lambda item: item.path))
        if len({item.path for item in ordered}) != len(ordered):
            raise ValueError("DuckDB rebuild artifacts must have unique paths")
        self._database_path.parent.mkdir(parents=True, exist_ok=True)
        connection = duckdb.connect(str(self._database_path))
        total_rows = 0
        try:
            connection.execute("BEGIN")
            connection.execute("DROP TABLE IF EXISTS derived_rows")
            connection.execute("DROP TABLE IF EXISTS derived_artifacts")
            connection.execute(
                """
                CREATE TABLE derived_artifacts (
                    table_name VARCHAR NOT NULL,
                    layer VARCHAR NOT NULL,
                    path VARCHAR PRIMARY KEY,
                    schema_version VARCHAR NOT NULL,
                    sha256 VARCHAR NOT NULL,
                    row_count BIGINT NOT NULL,
                    byte_count BIGINT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE derived_rows (
                    artifact_path VARCHAR NOT NULL,
                    row_number BIGINT NOT NULL,
                    row_json JSON NOT NULL,
                    PRIMARY KEY (artifact_path, row_number)
                )
                """
            )
            for artifact in ordered:
                path = resolve_under_root(self._artifact_root, artifact.path)
                self._verify_artifact(path, artifact)
                connection.execute(
                    "INSERT INTO derived_artifacts VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [
                        artifact.table_name,
                        artifact.layer,
                        artifact.path,
                        artifact.schema_version,
                        artifact.sha256,
                        artifact.rows,
                        artifact.bytes,
                    ],
                )
                count = _fetch_count(
                    connection.execute("SELECT count(*) FROM read_parquet(?)", [str(path)])
                )
                if count != artifact.rows:
                    raise ValueError(f"Parquet row count does not match: {artifact.path}")
                connection.execute(
                    """
                    INSERT INTO derived_rows
                    SELECT ?, row_number() OVER () - 1, row_json::JSON
                    FROM read_parquet(?)
                    """,
                    [artifact.path, str(path)],
                )
                total_rows += count
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        finally:
            connection.close()
        content = {
            "artifacts": [
                {
                    "path": item.path,
                    "sha256": item.sha256,
                    "rows": item.rows,
                    "bytes": item.bytes,
                }
                for item in ordered
            ]
        }
        return DuckDBRebuildResult(
            artifact_count=len(ordered),
            row_count=total_rows,
            content_sha256=sha256_hex(canonical_json_bytes(content)),
        )

    def count_rows(self) -> int:
        """Return the number of rows in the derived cache."""

        connection = duckdb.connect(str(self._database_path), read_only=True)
        try:
            return _fetch_count(connection.execute("SELECT count(*) FROM derived_rows"))
        finally:
            connection.close()

    @staticmethod
    def _verify_artifact(path: Path, artifact: ParquetArtifact) -> None:
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(artifact.path)
        if path.stat().st_size != artifact.bytes:
            raise ValueError(f"Parquet byte count does not match: {artifact.path}")
        if sha256_file(path) != artifact.sha256:
            raise ValueError(f"Parquet digest does not match: {artifact.path}")


def _fetch_count(result: _CountQueryResult) -> int:
    row = result.fetchone()
    if row is None:
        raise RuntimeError("DuckDB count query returned no row")
    return int(str(row[0]))


__all__ = ["DuckDBDerivedStore", "DuckDBRebuildResult"]
