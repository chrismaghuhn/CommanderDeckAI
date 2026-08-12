from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.data_pipeline.normalization.canonical_records import (
    canonical_record_from_domain,
)
from commander_ai.data_pipeline.normalization.canonical_snapshot_manifests import (
    build_canonical_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.canonical_snapshot_contracts import (
    CanonicalTableArtifact,
)
from commander_ai.data_pipeline.provenance.canonical_snapshot_verifier import (
    read_canonical_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_contracts import (
    NormalizedTableArtifact,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_manifests import (
    build_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.rows import (
    AuditRecord,
    ProvenanceRow,
    ResolutionAttempt,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
)
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.observations import ParticipantReference
from commander_ai.domain.provenance import ProvenanceReference, SourceSnapshotRequest

NOW = datetime(2026, 8, 11, tzinfo=UTC)
POLICY_REFERENCE = "current-use.v1:fixture:" + "a" * 32
POLICY_SHA256 = "a" * 64


def _fixture(root: Path) -> tuple[str, str]:
    raw = RawSnapshotStore(root).start_snapshot(
        source_id="fixture",
        snapshot_id="snapshot-1",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-v1",
        usage_status="APPROVED_LOCAL",
        started_at=NOW,
    )
    raw.add_request(
        SourceSnapshotRequest(
            request_id="request-1",
            sanitized_method="GET",
            sanitized_endpoint="https://fixture.invalid/data",
            format="json",
        )
    )
    raw.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"{}"])
    raw.finalize()
    verified = SnapshotVerifier(root).verify_complete_snapshot("fixture", "snapshot-1")
    locator = RawLocator(
        source_id="fixture",
        source_snapshot_id="snapshot-1",
        raw_object_id="object-1",
        raw_object_path="objects/object-1",
        location=JsonPointerLocator(pointer=""),
    )
    staging = StagingRecord.from_dto(
        SourceRecordDTO(
            source_id="fixture",
            record_type="participant",
            raw_locator=locator,
            original_source_values={"reference_id": "participant-1"},
        ),
        staging_record_id="staging-1",
        status="OBSERVED",
    )
    writer = ParquetTableWriter(root)
    normalized_outputs = (
        writer.write_table(
            "staging",
            [staging],
            layer="normalized",
            row_contract=StagingRecord,
            verified_snapshot=verified,
        ),
        writer.write_table(
            "audit",
            [],
            layer="audit",
            row_contract=AuditRecord,
            verified_snapshot=verified,
        ),
        writer.write_table(
            "quarantine",
            [],
            layer="quarantine",
            row_contract=QuarantineRecord,
            verified_snapshot=verified,
        ),
    )
    normalized_artifacts = tuple(
        NormalizedTableArtifact(
            table_name=item.table_name,
            layer=item.layer,
            path=item.path,
            sha256=item.sha256,
            rows=item.rows,
            bytes=item.bytes,
        )
        for item in normalized_outputs
    )
    normalized_run = build_run_manifest(
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
            RunInputReference(
                kind="current_use_decision",
                id=POLICY_REFERENCE,
                sha256=POLICY_SHA256,
            ),
        ),
        schema_versions=("staging.v1",),
        mapper_versions=("fixture-mapper-v1",),
        transform_versions=("normalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=tuple(
            RunArtifactReference(path=item.path, sha256=item.sha256, kind=item.layer)
            for item in normalized_artifacts
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    ManifestFileWriter(root).write_run_manifest(
        normalized_run,
        manifest_path="runs/normalize-run-1/manifest.json",
        configuration_snapshot={"source": "fixture"},
    )
    normalized = build_normalized_snapshot_manifest(
        producing_run=normalized_run,
        verified_snapshot=verified,
        table_artifacts=normalized_artifacts,
        normalized_schema_version="staging.v1",
        mapper_version="fixture-mapper-v1",
        transform_version="normalize-v1",
        policy_version="current-use-v1",
        counts={
            "input_records": 1,
            "normalized_records": 1,
            "audit_records": 0,
            "quarantine_records": 0,
        },
        started_at=NOW,
        created_at=NOW,
        completed_at=NOW,
    )
    normalized_path = "normalized/fixture/snapshot-1/manifest.json"
    _normalized_artifact, _ = ManifestFileWriter(root).write_normalized_manifest(
        normalized,
        manifest_path=normalized_path,
    )

    provenance = ProvenanceReference(
        source_id="fixture",
        source_snapshot_id="snapshot-1",
        source_object_id="object-1",
        raw_sha256=verified.manifest.objects[0].sha256,
        retrieved_at=NOW,
        adapter_version="fixture-v1",
        mapper_version="fixture-canonicalizer-v1",
        approval_status="APPROVED_LOCAL",
    )
    participant = ParticipantReference(
        reference_id="participant-1",
        scope="event",
        event_id="event-1",
    )
    canonical_record = canonical_record_from_domain(
        participant,
        source_record_id="staging-1",
        raw_locator=locator,
        provenance=(provenance,),
        observed_at=NOW,
    )
    canonical_prefix = "canonical/fixture/snapshot-1"
    canonical_outputs = (
        writer.write_table(
            "canonical",
            [canonical_record],
            relative_path=f"{canonical_prefix}/canonical.parquet",
            schema_version="canonical-record.v1",
            layer="normalized",
            row_contract=type(canonical_record),
            verified_snapshot=verified,
        ),
        writer.write_table(
            "audit",
            [],
            relative_path=f"{canonical_prefix}/audit.parquet",
            schema_version="audit.v1",
            layer="audit",
            row_contract=AuditRecord,
            verified_snapshot=verified,
        ),
        writer.write_table(
            "resolution",
            [],
            relative_path=f"{canonical_prefix}/resolution.parquet",
            schema_version="card-resolution.v1",
            layer="audit",
            row_contract=CardResolution,
            verified_snapshot=verified,
        ),
        writer.write_table(
            "resolution_attempt",
            [],
            relative_path=f"{canonical_prefix}/resolution-attempt.parquet",
            schema_version="resolution-attempt.v1",
            layer="audit",
            row_contract=ResolutionAttempt,
            verified_snapshot=verified,
        ),
        writer.write_table(
            "provenance",
            [],
            relative_path=f"{canonical_prefix}/provenance.parquet",
            schema_version="provenance-row.v1",
            layer="audit",
            row_contract=ProvenanceRow,
            verified_snapshot=verified,
        ),
        writer.write_table(
            "quarantine",
            [],
            relative_path=f"{canonical_prefix}/quarantine.parquet",
            schema_version="quarantine.v1",
            layer="quarantine",
            row_contract=QuarantineRecord,
            verified_snapshot=verified,
        ),
    )
    # Empty tables use their typed contract only for the writer; the verifier
    # still checks the exact canonical contract when rows are present.
    canonical_artifacts = tuple(
        CanonicalTableArtifact(
            artifact_name=item.table_name,
            artifact_kind=kind,
            layer=layer,
            schema_version=item.schema_version,
            path=item.path,
            sha256=item.sha256,
            rows=item.rows,
            bytes=item.bytes,
        )
        for item, (kind, layer) in zip(
            canonical_outputs,
            (
                ("canonical", "normalized"),
                ("audit", "audit"),
                ("resolution", "audit"),
                ("resolution_attempt", "audit"),
                ("provenance", "audit"),
                ("quarantine", "quarantine"),
            ),
            strict=True,
        )
    )
    normalized_hash = sha256((root / normalized_path).read_bytes()).hexdigest()
    canonical_run_id = "canonicalize-fixture-snapshot-1"
    canonical_run = build_run_manifest(
        run_id=canonical_run_id,
        run_kind="canonicalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/canonicalize.json",
        configuration_snapshot={"source": "fixture"},
        inputs=(
            RunInputReference(
                kind="normalized_snapshot_manifest",
                id=normalized.manifest.normalized_snapshot_id,
                path=normalized_path,
                sha256=normalized_hash,
            ),
        ),
        schema_versions=("canonical-record.v1",),
        mapper_versions=("fixture-canonicalizer-v1",),
        transform_versions=("canonicalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=tuple(
            RunArtifactReference(path=item.path, sha256=item.sha256, kind=kind)
            for item, (kind, _) in zip(
                canonical_outputs,
                (
                    ("canonical", "normalized"),
                    ("audit", "audit"),
                    ("resolution", "audit"),
                    ("resolution_attempt", "audit"),
                    ("provenance", "audit"),
                    ("quarantine", "quarantine"),
                ),
                strict=True,
            )
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    canonical = build_canonical_snapshot_manifest(
        producing_run=canonical_run,
        input_normalized_snapshot_id=normalized.manifest.normalized_snapshot_id,
        input_normalized_manifest_sha256=normalized_hash,
        source_id="fixture",
        artifacts=canonical_artifacts,
        counts={
            "input_records": 1,
            "canonical_records": 1,
            "audit_records": 0,
            "resolution_records": 0,
            "resolution_attempt_records": 0,
            "provenance_records": 0,
            "quarantine_records": 0,
        },
        finding_codes=(),
        quarantine_references=(),
        provenance=(provenance,),
        started_at=NOW,
        created_at=NOW,
        completed_at=NOW,
        mapper_version="canonicalizer-v1",
        transform_version="canonicalize-v1",
    )
    canonical_manifest_path = f"{canonical_prefix}/manifest.json"
    manifest_artifact, sidecar = ManifestFileWriter(root).write_canonical_manifest(
        canonical,
        manifest_path=canonical_manifest_path,
    )
    final_run = build_run_manifest(
        run_id=canonical_run_id,
        run_kind="canonicalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/canonicalize.json",
        configuration_snapshot={"source": "fixture"},
        inputs=canonical_run.inputs,
        schema_versions=("canonical-record.v1", "canonical-snapshot-manifest.v1"),
        mapper_versions=("fixture-canonicalizer-v1",),
        transform_versions=("canonicalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=(
            *canonical_run.artifacts,
            RunArtifactReference(
                path=manifest_artifact.path,
                sha256=manifest_artifact.sha256,
                kind="canonical_snapshot_manifest",
            ),
            RunArtifactReference(
                path=sidecar.path,
                sha256=sidecar.sha256,
                kind="canonical_snapshot_manifest_digest",
            ),
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    ManifestFileWriter(root).write_run_manifest(
        final_run,
        manifest_path=f"runs/{canonical_run_id}/manifest.json",
        configuration_snapshot={"source": "fixture"},
    )
    return canonical_manifest_path, canonical_outputs[0].path


def test_canonical_snapshot_verifier_checks_all_boundaries(tmp_path: Path) -> None:
    manifest_path, canonical_path = _fixture(tmp_path)

    verified = read_canonical_snapshot_manifest(tmp_path, manifest_path)

    assert verified.manifest.status == "COMPLETE"
    assert verified.manifest.source_id == "fixture"
    (tmp_path / canonical_path).write_bytes((tmp_path / canonical_path).read_bytes() + b"x")
    with pytest.raises(ValueError, match="hash mismatch"):
        read_canonical_snapshot_manifest(tmp_path, manifest_path)


def test_canonical_snapshot_verifier_rejects_complete_input_with_corrupt_raw_object(
    tmp_path: Path,
) -> None:
    manifest_path, _ = _fixture(tmp_path)
    (tmp_path / "raw/fixture/snapshot-1/objects/object-1").write_bytes(b"tampered")

    with pytest.raises(ValueError, match=r"INTEGRITY|hash|size"):
        read_canonical_snapshot_manifest(tmp_path, manifest_path)
