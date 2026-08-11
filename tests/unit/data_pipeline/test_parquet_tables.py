from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from commander_ai.adapters.storage import parquet_tables
from commander_ai.adapters.storage.parquet_tables import CuratedRow, ParquetTableWriter
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.data_pipeline.provenance.rows import AuditRecord, ProvenanceRow
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord
from commander_ai.domain.provenance import SourceSnapshotRequest

NOW = datetime(2026, 8, 10, 0, 0, tzinfo=UTC)


def verified_snapshot(tmp_path: Path):
    writer = RawSnapshotStore(tmp_path).start_snapshot(
        source_id="fixture",
        snapshot_id="snapshot-1",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-v1",
        usage_status="historical-approved",
        started_at=NOW,
    )
    writer.add_request(
        SourceSnapshotRequest(
            request_id="request-1",
            sanitized_method="GET",
            sanitized_endpoint="https://fixture.invalid/data",
            format="json",
        )
    )
    writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"[{}]"])
    writer.finalize()
    return SnapshotVerifier(tmp_path).verify_complete_snapshot("fixture", "snapshot-1")


def staging_record() -> StagingRecord:
    return StagingRecord.from_dto(
        SourceRecordDTO(
            source_id="fixture",
            record_type="deck",
            raw_locator=RawLocator(
                source_id="fixture",
                source_snapshot_id="snapshot-1",
                raw_object_id="object-1",
                raw_object_path="objects/object-1",
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
    first = ParquetTableWriter(first_root).write_table(
        "staging",
        rows,
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified_snapshot(first_root),
    )
    second = ParquetTableWriter(second_root).write_table(
        "staging",
        rows,
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified_snapshot(second_root),
    )

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
        staging=[staging_record()],
        audit=[audit],
        quarantine=[],
        verified_snapshot=verified_snapshot(tmp_path),
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
        ParquetTableWriter(tmp_path).write_table(
            "curated", [audit], layer="curated", row_contract=AuditRecord
        )


def test_curated_rows_require_the_explicit_curated_contract(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="curated"):
        ParquetTableWriter(tmp_path).write_table(
            "curated",
            [{"layer": "curated", "curated_id": "deck-1"}],
            layer="curated",
            row_contract=dict,
        )

    artifact = ParquetTableWriter(tmp_path).write_table(
        "curated",
        [CuratedRow(curated_id="deck-1", values={"name": "Fixture"})],
        layer="curated",
        row_contract=CuratedRow,
    )
    assert artifact.rows == 1


def test_parquet_writer_removes_published_file_when_directory_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_fsync(_directory: Path) -> None:
        raise OSError("directory durability failure")

    monkeypatch.setattr(parquet_tables, "fsync_directory", fail_fsync)

    with pytest.raises(OSError, match="directory durability failure"):
        ParquetTableWriter(tmp_path).write_table(
            "curated",
            [CuratedRow(curated_id="deck-1", values={"record_id": "deck-1"})],
            layer="curated",
            row_contract=CuratedRow,
        )

    assert not (tmp_path / "curated/curated.parquet").exists()


def test_source_locators_are_verified_against_raw_index_and_logical_rows_are_unique(
    tmp_path: Path,
) -> None:
    verified = verified_snapshot(tmp_path)
    row = staging_record()
    duplicate = row.model_copy(update={"staging_record_id": "staging-2"})
    with pytest.raises(ValueError, match="duplicate source-backed logical rows"):
        ParquetTableWriter(tmp_path).write_table(
            "staging",
            [row, duplicate],
            layer="normalized",
            row_contract=StagingRecord,
            verified_snapshot=verified,
        )

    invalid_path = row.raw_locator.model_copy(update={"raw_object_path": "objects/other"})
    with pytest.raises(ValueError, match="path"):
        ParquetTableWriter(tmp_path).write_table(
            "staging",
            [row.model_copy(update={"raw_locator": invalid_path})],
            layer="normalized",
            row_contract=StagingRecord,
            verified_snapshot=verified,
        )


def test_provenance_rows_bind_raw_hash_to_verified_object(tmp_path: Path) -> None:
    verified = verified_snapshot(tmp_path)
    raw = verified.manifest.objects[0]
    locator = staging_record().raw_locator
    provenance = ProvenanceRow(
        provenance_id="provenance-1",
        entity_id="entity-1",
        source_id="fixture",
        source_snapshot_id="snapshot-1",
        raw_object_id="object-1",
        raw_object_path=raw.path,
        raw_sha256=raw.sha256,
        raw_locator=locator,
        adapter_version="fixture-v1",
    )
    artifact = ParquetTableWriter(tmp_path).write_table(
        "audit",
        [provenance],
        layer="audit",
        row_contract=ProvenanceRow,
        verified_snapshot=verified,
    )
    assert artifact.rows == 1

    with pytest.raises(ValueError, match="sha256"):
        ParquetTableWriter(tmp_path / "bad").write_table(
            "audit",
            [provenance.model_copy(update={"raw_sha256": "a" * 64})],
            layer="audit",
            row_contract=ProvenanceRow,
            verified_snapshot=verified,
        )


def test_parquet_persistence_requires_an_explicit_layer_contract(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="layer"):
        ParquetTableWriter(tmp_path).write_table("audit", [])

    with pytest.raises(ValueError, match="layer"):
        ParquetTableWriter(tmp_path).write_table(
            "quarantine", [], layer="audit", row_contract=AuditRecord
        )

    with pytest.raises(ValueError, match="recognized"):
        ParquetTableWriter(tmp_path).write_table(
            "staging",
            [],
            layer="unknown",
            row_contract=StagingRecord,  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="typed"):
        ParquetTableWriter(tmp_path).write_table(
            "staging",
            [{"layer": "staging"}],
            layer="normalized",
            row_contract=StagingRecord,
        )


def test_parquet_paths_are_root_relative_and_non_escaping(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        ParquetTableWriter(tmp_path).write_table(
            "staging",
            [staging_record()],
            relative_path="../x",
            layer="normalized",
            row_contract=StagingRecord,
        )
