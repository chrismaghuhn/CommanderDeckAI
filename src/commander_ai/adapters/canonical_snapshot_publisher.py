"""Publish source-neutral canonical tables and their immutable manifest."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.data_pipeline.normalization.canonical_snapshot_manifests import (
    build_canonical_snapshot_manifest,
)
from commander_ai.data_pipeline.normalization.canonicalization import canonicalize_staging
from commander_ai.data_pipeline.provenance.canonical_snapshot_contracts import (
    CanonicalTableArtifact,
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
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.provenance import QuarantineReference

from .operation_provenance import operation_context

CanonicalArtifactKind = Literal[
    "canonical",
    "audit",
    "resolution",
    "resolution_attempt",
    "provenance",
    "quarantine",
]
CanonicalArtifactLayer = Literal["normalized", "audit", "quarantine"]


def publish_canonical_snapshot(
    artifact_root: Path,
    prepared: Any,
    *,
    staging: tuple[StagingRecord, ...],
    audits: tuple[AuditRecord, ...],
    quarantine: tuple[QuarantineRecord, ...],
    mapper_version: str,
    normalized: Any,
    normalized_manifest_path: str,
    normalized_manifest_sha256: str,
) -> None:
    """Canonicalize verified staging rows and publish all derived artifacts."""

    result = canonicalize_staging(
        staging,
        source_manifest=prepared.manifest,
        attempted_at=prepared.manifest.completed_at or prepared.manifest.started_at,
    )
    all_audits = tuple(sorted((*audits, *result.audits), key=lambda item: item.audit_id))
    all_quarantine = tuple((*quarantine, *result.quarantines))
    prefix = f"canonical/{prepared.source_id}/{prepared.source_snapshot_id}"
    writer = ParquetTableWriter(artifact_root)
    outputs = (
        writer.write_table(
            "canonical",
            result.records,
            relative_path=f"{prefix}/canonical.parquet",
            schema_version="canonical-record.v1",
            layer="normalized",
            row_contract=CanonicalRecord,
            verified_snapshot=prepared.verified_snapshot,
        ),
        writer.write_table(
            "audit",
            all_audits,
            relative_path=f"{prefix}/audit.parquet",
            schema_version="audit.v1",
            layer="audit",
            row_contract=AuditRecord,
            verified_snapshot=prepared.verified_snapshot,
        ),
        writer.write_table(
            "resolution",
            result.resolutions,
            relative_path=f"{prefix}/resolution.parquet",
            schema_version="card-resolution.v1",
            layer="audit",
            row_contract=CardResolution,
            verified_snapshot=prepared.verified_snapshot,
        ),
        writer.write_table(
            "resolution_attempt",
            result.resolution_attempts,
            relative_path=f"{prefix}/resolution-attempt.parquet",
            schema_version="resolution-attempt.v1",
            layer="audit",
            row_contract=ResolutionAttempt,
            verified_snapshot=prepared.verified_snapshot,
        ),
        writer.write_table(
            "provenance",
            result.provenance,
            relative_path=f"{prefix}/provenance.parquet",
            schema_version="provenance-row.v1",
            layer="audit",
            row_contract=ProvenanceRow,
            verified_snapshot=prepared.verified_snapshot,
        ),
        writer.write_table(
            "quarantine",
            all_quarantine,
            relative_path=f"{prefix}/quarantine.parquet",
            schema_version="quarantine.v1",
            layer="quarantine",
            row_contract=QuarantineRecord,
            verified_snapshot=prepared.verified_snapshot,
        ),
    )
    artifact_specs: tuple[tuple[CanonicalArtifactKind, CanonicalArtifactLayer], ...] = (
        ("canonical", "normalized"),
        ("audit", "audit"),
        ("resolution", "audit"),
        ("resolution_attempt", "audit"),
        ("provenance", "audit"),
        ("quarantine", "quarantine"),
    )
    table_artifacts = tuple(
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
        for item, (kind, layer) in zip(outputs, artifact_specs, strict=True)
    )
    run_id = f"canonicalize-{prepared.source_id}-{prepared.source_snapshot_id}"
    operation = operation_context(artifact_root, run_id)
    started_at = normalized.manifest.started_at
    completed_at = normalized.manifest.completed_at or datetime.now(UTC)
    current = prepared.policy_decision
    if current.decision_reference is None or current.decision_sha256 is None:
        raise ValueError("canonicalization policy decision is not bound")
    run_inputs = (
        RunInputReference(
            kind="normalized_snapshot_manifest",
            id=normalized.manifest.normalized_snapshot_id,
            path=normalized_manifest_path,
            sha256=normalized_manifest_sha256,
        ),
        RunInputReference(
            kind="current_use_decision",
            id=current.decision_reference,
            sha256=current.decision_sha256,
        ),
    )
    run_artifacts = (
        *operation.artifacts,
        *(
            RunArtifactReference(path=item.path, sha256=item.sha256, kind=kind)
            for item, (kind, _) in zip(outputs, artifact_specs, strict=True)
        ),
    )
    configuration_snapshot = {
        "source_id": prepared.source_id,
        "source_snapshot_id": prepared.source_snapshot_id,
        "normalized_snapshot_id": normalized.manifest.normalized_snapshot_id,
        "mapper_version": mapper_version,
        "canonicalizer_version": "canonicalizer-v1",
    }
    run = build_run_manifest(
        run_id=run_id,
        run_kind="canonicalize",
        stage="data",
        status="succeeded",
        git_commit=operation.git_commit,
        git_dirty=operation.git_dirty,
        git_worktree_sha256=operation.git_worktree_sha256,
        dependency_lock_hash=operation.dependency_lock_hash,
        configuration_path=f"configs/canonicalize/{prepared.source_id}/{prepared.source_snapshot_id}.json",
        configuration_snapshot=configuration_snapshot,
        inputs=run_inputs,
        schema_versions=("canonical-record.v1",),
        mapper_versions=(mapper_version, "canonicalizer-v1"),
        transform_versions=("canonicalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=run_artifacts,
        determinism=operation.determinism,
        created_at=started_at,
        started_at=started_at,
        finished_at=completed_at,
    )
    canonical = build_canonical_snapshot_manifest(
        producing_run=run,
        input_normalized_snapshot_id=normalized.manifest.normalized_snapshot_id,
        input_normalized_manifest_sha256=normalized_manifest_sha256,
        source_id=prepared.source_id,
        artifacts=table_artifacts,
        counts={
            "input_records": len(staging),
            "canonical_records": len(result.records),
            "audit_records": len(all_audits),
            "resolution_records": len(result.resolutions),
            "resolution_attempt_records": len(result.resolution_attempts),
            "provenance_records": len(result.provenance),
            "quarantine_records": len(all_quarantine),
        },
        finding_codes=tuple(
            sorted(
                {
                    *result.finding_codes,
                    *(code for item in staging for code in item.finding_codes),
                }
            )
        ),
        quarantine_references=tuple(
            QuarantineReference(
                quarantine_id=item.quarantine_id,
                reason_code=item.reason_code,
                path=next(
                    artifact.path
                    for artifact in table_artifacts
                    if artifact.artifact_kind == "quarantine"
                ),
                record_locator=item.raw_locator.exact_locator,
            )
            for item in all_quarantine
        ),
        provenance=normalized.manifest.provenance,
        mapper_version="canonicalizer-v1",
        transform_version="canonicalize-v1",
        started_at=started_at,
        created_at=started_at,
        completed_at=completed_at,
    )
    manifest_writer = ManifestFileWriter(artifact_root)
    manifest_artifact, sidecar = manifest_writer.write_canonical_manifest(
        canonical,
        manifest_path=f"{prefix}/manifest.json",
    )
    final_run = build_run_manifest(
        run_id=run_id,
        run_kind="canonicalize",
        stage="data",
        status="succeeded",
        git_commit=operation.git_commit,
        git_dirty=operation.git_dirty,
        git_worktree_sha256=operation.git_worktree_sha256,
        dependency_lock_hash=operation.dependency_lock_hash,
        configuration_path=run.configuration.path,
        configuration_snapshot=configuration_snapshot,
        inputs=run_inputs,
        schema_versions=("canonical-record.v1", "canonical-snapshot-manifest.v1"),
        mapper_versions=(mapper_version, "canonicalizer-v1"),
        transform_versions=("canonicalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=(
            *run_artifacts,
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
        determinism=operation.determinism,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )
    manifest_writer.write_run_manifest(
        final_run,
        manifest_path=f"runs/{run_id}/manifest.json",
        configuration_snapshot=configuration_snapshot,
    )


__all__ = ["publish_canonical_snapshot"]
