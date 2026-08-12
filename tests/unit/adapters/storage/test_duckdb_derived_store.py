from __future__ import annotations

from pathlib import Path

import pytest

from commander_ai.adapters.storage.duckdb_derived_store import DuckDBDerivedStore
from commander_ai.adapters.storage.parquet_tables import (
    CuratedRow,
    ParquetArtifact,
    ParquetTableWriter,
)


def test_duckdb_derived_store_rebuilds_from_authoritative_parquet_after_delete(
    tmp_path: Path,
) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact = ParquetTableWriter(artifact_root).write_table(
        "fixture",
        [
            CuratedRow(curated_id="row-1", values={"value": 1}),
            CuratedRow(curated_id="row-2", values={"value": 2}),
        ],
        relative_path="curated/fixture.parquet",
        layer="curated",
        row_contract=CuratedRow,
    )
    database_path = tmp_path / "cache" / "derived.duckdb"
    store = DuckDBDerivedStore(artifact_root, database_path)

    first = store.rebuild((artifact,))
    database_path.unlink()
    second = store.rebuild((artifact,))

    assert first == second
    assert first.artifact_count == 1
    assert first.row_count == 2
    assert store.count_rows() == 2


def test_duckdb_derived_store_rejects_corrupt_authoritative_artifact(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact = ParquetTableWriter(artifact_root).write_table(
        "fixture",
        [CuratedRow(curated_id="row-1", values={"value": 1})],
        relative_path="curated/fixture.parquet",
        layer="curated",
        row_contract=CuratedRow,
    )
    corrupt = ParquetArtifact(
        table_name=artifact.table_name,
        layer=artifact.layer,
        path=artifact.path,
        sha256="0" * 64,
        rows=artifact.rows,
        bytes=artifact.bytes,
        schema_version=artifact.schema_version,
    )

    with pytest.raises(ValueError, match="Parquet digest does not match"):
        DuckDBDerivedStore(artifact_root, tmp_path / "cache" / "derived.duckdb").rebuild((corrupt,))
