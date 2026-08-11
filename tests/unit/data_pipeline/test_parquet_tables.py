from __future__ import annotations

from pathlib import Path

import pytest

from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord


def staging_record() -> StagingRecord:
    return StagingRecord.from_dto(
        SourceRecordDTO(
            source_id="fixture",
            record_type="deck",
            raw_locator=RawLocator(
                source_snapshot_id="snapshot-1",
                raw_object_id="object-1",
                raw_object_path="objects/object-1.json",
                location=JsonPointerLocator(pointer="/0"),
            ),
            original_source_values={"title": "Fixture", "cards": ["a", "b"]},
        ),
        staging_record_id="staging-1",
        status="OBSERVED",
    )


def test_parquet_output_is_deterministic_and_rebuildable(tmp_path: Path) -> None:
    rows = [staging_record()]
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first = ParquetTableWriter(first_root).write_table("staging", rows, layer="normalized")
    second = ParquetTableWriter(second_root).write_table("staging", rows, layer="normalized")

    assert first.path == "normalized/staging.parquet"
    assert first.sha256 == second.sha256
    assert first.bytes == second.bytes
    assert first.rows == 1
    assert ParquetTableWriter(first_root).read_table(first.path) == [
        rows[0].model_dump(mode="json")
    ]


def test_normalized_layers_are_written_as_three_separate_artifacts(tmp_path: Path) -> None:
    audit = AuditRecord(
        audit_id="audit-1",
        entity_id="staging-1",
        stage="quality",
        finding_code="quality.missing_field",
    )

    artifacts = ParquetTableWriter(tmp_path).write_normalized_tables(
        staging=[staging_record()], audit=[audit], quarantine=[]
    )

    assert [artifact.path for artifact in artifacts] == [
        "normalized/staging.parquet",
        "normalized/audit.parquet",
        "normalized/quarantine.parquet",
    ]
    assert [artifact.rows for artifact in artifacts] == [1, 1, 0]


def test_audit_rows_cannot_be_written_as_curated(tmp_path: Path) -> None:
    audit = AuditRecord(
        audit_id="audit-1",
        entity_id="staging-1",
        stage="quality",
        finding_code="quality.missing_field",
        details={"field": "commander"},
    )

    with pytest.raises(ValueError, match="curated"):
        ParquetTableWriter(tmp_path).write_table("curated", [audit], layer="curated")


def test_parquet_persistence_requires_an_explicit_layer_mapping(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="layer"):
        ParquetTableWriter(tmp_path).write_table("audit", [])

    with pytest.raises(ValueError, match="layer"):
        ParquetTableWriter(tmp_path).write_table(
            "quarantine", [], layer="audit"
        )

    with pytest.raises(ValueError, match="recognized"):
        ParquetTableWriter(tmp_path).write_table(
            "staging", [], layer="unknown"  # type: ignore[arg-type]
        )


def test_parquet_paths_are_root_relative_and_non_escaping(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ParquetTableWriter(tmp_path).write_table(
            "staging", [staging_record()], relative_path="../x", layer="normalized"
        )
