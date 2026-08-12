from __future__ import annotations

from datetime import UTC, datetime

from commander_ai.data_pipeline.normalization.canonical_snapshot_manifests import (
    build_canonical_snapshot_manifest,
    canonical_snapshot_manifest_bytes,
    validate_canonical_snapshot_manifest_bytes,
)
from commander_ai.data_pipeline.provenance.canonical_snapshot_contracts import (
    CanonicalTableArtifact,
)
from commander_ai.data_pipeline.provenance.run_manifests import build_run_manifest
from commander_ai.domain.provenance import ProvenanceReference

NOW = datetime(2026, 8, 10, tzinfo=UTC)


def _run():
    return build_run_manifest(
        run_id="canonicalize-run-1",
        run_kind="canonicalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/canonicalize/mtgjson/snapshot-1.json",
        configuration_snapshot={"source_id": "mtgjson"},
        inputs=(
            {
                "kind": "normalized_snapshot_manifest",
                "id": "normalized-1",
                "path": "normalized/mtgjson/snapshot-1/manifest.json",
                "sha256": "c" * 64,
            },
        ),
        schema_versions=("canonical-record.v1",),
        mapper_versions=("mtgjson-card-mapper-v1",),
        transform_versions=("canonicalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=(
            {
                "path": "canonical/mtgjson/snapshot-1/records.parquet",
                "sha256": "d" * 64,
                "kind": "canonical",
            },
            {
                "path": "canonical/mtgjson/snapshot-1/audit.parquet",
                "sha256": "e" * 64,
                "kind": "audit",
            },
            {
                "path": "canonical/mtgjson/snapshot-1/resolutions.parquet",
                "sha256": "f" * 64,
                "kind": "resolution",
            },
            {
                "path": "canonical/mtgjson/snapshot-1/resolution-attempt.parquet",
                "sha256": "0" * 64,
                "kind": "resolution_attempt",
            },
            {
                "path": "canonical/mtgjson/snapshot-1/provenance.parquet",
                "sha256": "1" * 64,
                "kind": "provenance",
            },
            {
                "path": "canonical/mtgjson/snapshot-1/quarantine.parquet",
                "sha256": "2" * 64,
                "kind": "quarantine",
            },
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )


def _artifacts() -> tuple[CanonicalTableArtifact, ...]:
    return (
        CanonicalTableArtifact(
            artifact_name="records",
            artifact_kind="canonical",
            layer="normalized",
            schema_version="canonical-record.v1",
            path="canonical/mtgjson/snapshot-1/records.parquet",
            sha256="d" * 64,
            rows=1,
            bytes=10,
        ),
        CanonicalTableArtifact(
            artifact_name="audit",
            artifact_kind="audit",
            layer="audit",
            schema_version="audit.v1",
            path="canonical/mtgjson/snapshot-1/audit.parquet",
            sha256="e" * 64,
            rows=0,
            bytes=10,
        ),
        CanonicalTableArtifact(
            artifact_name="resolutions",
            artifact_kind="resolution",
            layer="audit",
            schema_version="card-resolution.v1",
            path="canonical/mtgjson/snapshot-1/resolutions.parquet",
            sha256="f" * 64,
            rows=0,
            bytes=10,
        ),
        CanonicalTableArtifact(
            artifact_name="provenance",
            artifact_kind="provenance",
            layer="audit",
            schema_version="provenance.v1",
            path="canonical/mtgjson/snapshot-1/provenance.parquet",
            sha256="1" * 64,
            rows=1,
            bytes=10,
        ),
        CanonicalTableArtifact(
            artifact_name="resolution-attempt",
            artifact_kind="resolution_attempt",
            layer="audit",
            schema_version="resolution-attempt.v1",
            path="canonical/mtgjson/snapshot-1/resolution-attempt.parquet",
            sha256="0" * 64,
            rows=0,
            bytes=10,
        ),
        CanonicalTableArtifact(
            artifact_name="quarantine",
            artifact_kind="quarantine",
            layer="quarantine",
            schema_version="quarantine.v1",
            path="canonical/mtgjson/snapshot-1/quarantine.parquet",
            sha256="2" * 64,
            rows=0,
            bytes=10,
        ),
    )


def test_canonical_snapshot_manifest_binds_input_run_and_artifacts() -> None:
    build = build_canonical_snapshot_manifest(
        producing_run=_run(),
        input_normalized_snapshot_id="normalized-1",
        input_normalized_manifest_sha256="c" * 64,
        source_id="mtgjson",
        artifacts=_artifacts(),
        counts={
            "canonical_records": 1,
            "audit_records": 0,
            "resolution_records": 0,
            "resolution_attempt_records": 0,
            "provenance_records": 1,
            "quarantine_records": 0,
        },
        finding_codes=(),
        quarantine_references=(),
        provenance=(
            ProvenanceReference(
                source_id="mtgjson",
                source_snapshot_id="snapshot-1",
                source_object_id="AllPrintings.json.zip",
                raw_sha256="4" * 64,
            ),
        ),
        started_at=NOW,
        created_at=NOW,
        completed_at=NOW,
    )

    payload = canonical_snapshot_manifest_bytes(build)
    parsed = validate_canonical_snapshot_manifest_bytes(payload)
    assert parsed.canonical_snapshot_id == build.manifest.canonical_snapshot_id
    assert build.manifest.status == "COMPLETE"
