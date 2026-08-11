from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.data_pipeline.provenance.normalized_snapshot_manifests import (
    NormalizedTableArtifact,
    build_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    read_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
)
from commander_ai.domain.provenance import SourceSnapshotRequest
from commander_ai.domain.serialization import canonical_json_bytes

NOW = datetime(2026, 8, 11, 0, 0, tzinfo=UTC)


def test_normalized_snapshot_read_verifies_manifest_run_source_and_parquet_bytes(
    tmp_path: Path,
) -> None:
    raw_writer = RawSnapshotStore(tmp_path).start_snapshot(
        source_id="fixture",
        snapshot_id="snapshot-1",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-v1",
        usage_status="historical-approved",
        started_at=NOW,
    )
    raw_writer.add_request(
        SourceSnapshotRequest(
            request_id="request-1",
            sanitized_method="GET",
            sanitized_endpoint="https://fixture.invalid/data",
            format="json",
        )
    )
    raw_writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"{}"])
    raw_writer.finalize()
    verified = SnapshotVerifier(tmp_path).verify_complete_snapshot("fixture", "snapshot-1")

    parquet = ParquetTableWriter(tmp_path)
    normalized_file = parquet.write_table(
        "staging", [{"layer": "staging", "value": 1}], layer="normalized"
    )
    audit_file = parquet.write_table(
        "audit", [{"layer": "audit", "finding_code": "quality.example"}], layer="audit"
    )
    quarantine_file = parquet.write_table("quarantine", [], layer="quarantine")
    artifacts = tuple(
        NormalizedTableArtifact(
            table_name=item.table_name,
            layer=item.layer,
            path=item.path,
            sha256=item.sha256,
            rows=item.rows,
            bytes=item.bytes,
        )
        for item in (normalized_file, audit_file, quarantine_file)
    )
    run = build_run_manifest(
        run_id="normalize-run-1",
        run_kind="normalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/normalize.json",
        configuration_snapshot={"source": "fixture"},
        inputs=(
            RunInputReference(
                kind="source_snapshot_manifest",
                id="snapshot-1",
                path="raw/fixture/snapshot-1/manifest.json",
                sha256=verified.manifest_sha256,
            ),
        ),
        schema_versions=("records.v1",),
        mapper_versions=("fixture-mapper-v1",),
        transform_versions=("normalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=tuple(
            RunArtifactReference(path=item.path, sha256=item.sha256, kind=item.layer)
            for item in artifacts
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    ManifestFileWriter(tmp_path).write_run_manifest(
        run,
        manifest_path="runs/normalize-run-1/manifest.json",
        configuration_snapshot={"source": "fixture"},
    )
    build = build_normalized_snapshot_manifest(
        producing_run=run,
        verified_snapshot=verified,
        table_artifacts=artifacts,
        normalized_schema_version="records.v1",
        mapper_version="fixture-mapper-v1",
        transform_version="normalize-v1",
        policy_version="current-use-v1",
        counts={
            "input_records": 1,
            "normalized_records": 1,
            "audit_records": 1,
            "quarantine_records": 0,
        },
        started_at=NOW,
        created_at=NOW,
        completed_at=NOW,
    )
    ManifestFileWriter(tmp_path).write_normalized_manifest(
        build,
        manifest_path="normalized/fixture/snapshot-1/manifest.json",
    )

    verified_normalized = read_normalized_snapshot_manifest(
        tmp_path,
        "normalized/fixture/snapshot-1/manifest.json",
        producing_run_path="runs/normalize-run-1/manifest.json",
    )
    assert (
        verified_normalized.manifest.normalized_snapshot_id
        == build.manifest.normalized_snapshot_id
    )

    manifest_file = tmp_path / "normalized/fixture/snapshot-1/manifest.json"
    original_manifest_bytes = manifest_file.read_bytes()
    modified_manifest = json.loads(original_manifest_bytes.decode("utf-8"))
    modified_manifest["created_at"] = "2026-08-11T00:00:01Z"
    manifest_file.write_bytes(canonical_json_bytes(modified_manifest))
    with pytest.raises(ValueError, match="detached digest"):
        read_normalized_snapshot_manifest(
            tmp_path,
            "normalized/fixture/snapshot-1/manifest.json",
            producing_run_path="runs/normalize-run-1/manifest.json",
        )
    manifest_file.write_bytes(original_manifest_bytes)

    (tmp_path / normalized_file.path).write_bytes(
        (tmp_path / normalized_file.path).read_bytes() + b"changed"
    )
    with pytest.raises(ValueError, match=r"hash|byte count"):
        read_normalized_snapshot_manifest(
            tmp_path,
            "normalized/fixture/snapshot-1/manifest.json",
            producing_run_path="runs/normalize-run-1/manifest.json",
        )
