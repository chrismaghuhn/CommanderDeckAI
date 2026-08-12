"""Build and semantically validate versioned normalized snapshot manifests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from commander_ai.domain.provenance import (
    NormalizedSnapshotManifest,
    QuarantineReference,
    SourceSnapshotManifest,
    detached_manifest_sha256,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .normalized_snapshot_content import (
    normalized_snapshot_content_from_manifest,
    normalized_snapshot_id,
    normalized_snapshot_v1_content_payload,
    run_policy_binding,
)
from .normalized_snapshot_contracts import (
    NormalizedSnapshotManifestV2,
    NormalizedTableArtifact,
)
from .normalized_snapshot_validation import (
    VerifiedSnapshotEvidence,
    artifact_for_layer,
    policy_version_from_run,
    require_count_bindings,
    require_layer_artifacts,
    require_run_bindings,
    require_verified_source,
    sorted_quarantine,
    source_provenance,
    unique_findings,
    validate_counts,
)
from .run_manifests import RunManifest


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotBuild:
    manifest: NormalizedSnapshotManifest | NormalizedSnapshotManifestV2
    table_artifacts: tuple[NormalizedTableArtifact, ...]
    manifest_sha256: str


def build_normalized_snapshot_manifest(
    *,
    producing_run: RunManifest,
    table_artifacts: Sequence[NormalizedTableArtifact],
    normalized_schema_version: str,
    mapper_version: str,
    transform_version: str,
    policy_version: str,
    counts: Mapping[str, int],
    started_at: datetime,
    created_at: datetime,
    completed_at: datetime | None,
    verified_snapshot: VerifiedSnapshotEvidence | None = None,
    source_manifest: SourceSnapshotManifest | None = None,
    source_manifest_sha256: str | None = None,
    finding_codes: Sequence[str] = (),
    quarantine_references: Sequence[QuarantineReference | Mapping[str, object]] = (),
    raw_snapshot_verified: bool | None = None,
) -> NormalizedSnapshotBuild:
    verified_manifest, verified_hash = require_verified_source(
        verified_snapshot=verified_snapshot,
        source_manifest=source_manifest,
        source_manifest_sha256=source_manifest_sha256,
        raw_snapshot_verified=raw_snapshot_verified,
    )
    if producing_run.status != "succeeded":
        raise ValueError("normalized manifest requires a succeeded producing run")
    artifacts = tuple(table_artifacts)
    require_layer_artifacts(artifacts)
    findings = unique_findings(finding_codes)
    quarantine = sorted_quarantine(quarantine_references)
    normalized_counts = validate_counts(counts)
    require_count_bindings(normalized_counts, artifacts, len(quarantine))
    require_run_bindings(
        producing_run,
        source_manifest_id=verified_manifest.source_snapshot_id,
        source_id=verified_manifest.source_id,
        source_manifest_sha256=verified_hash,
        artifacts=artifacts,
        schema_version=normalized_schema_version,
        mapper_version=mapper_version,
        transform_version=transform_version,
        policy_version=policy_version,
    )
    provenance = source_provenance(verified_manifest)
    policy_reference, policy_hash = run_policy_binding(producing_run)
    content_payload = normalized_snapshot_v1_content_payload(
        source_id=verified_manifest.source_id,
        source_manifest_id=verified_manifest.source_snapshot_id,
        source_manifest_sha256=verified_hash,
        producing_run_id=producing_run.run_id,
        schema_version=normalized_schema_version,
        mapper_version=mapper_version,
        transform_version=transform_version,
        policy_version=policy_version,
        policy_decision_reference=policy_reference,
        policy_decision_sha256=policy_hash,
        artifacts=artifacts,
        counts=normalized_counts,
        finding_codes=findings,
        quarantine_references=quarantine,
        provenance=provenance,
        status="COMPLETE",
    )
    normalized = artifact_for_layer(artifacts, "normalized")
    audit = artifact_for_layer(artifacts, "audit")
    manifest = NormalizedSnapshotManifest(
        normalized_snapshot_id=normalized_snapshot_id(content_payload, contract_version="v1"),
        producing_run_id=producing_run.run_id,
        input_source_snapshot_manifest_id=verified_manifest.source_snapshot_id,
        input_source_snapshot_manifest_sha256=verified_hash,
        source_id=verified_manifest.source_id,
        status="COMPLETE",
        normalized_schema_version=normalized_schema_version,
        mapper_version=mapper_version,
        transform_version=transform_version,
        normalized_artifact_path=normalized.path,
        normalized_artifact_sha256=normalized.sha256,
        audit_artifact_path=audit.path,
        audit_artifact_sha256=audit.sha256,
        counts=normalized_counts,
        finding_codes=findings,
        quarantine_references=quarantine,
        provenance=provenance,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        normalized_content_sha256=sha256_hex(canonical_json_bytes(content_payload)),
    )
    result = NormalizedSnapshotBuild(
        manifest=manifest,
        table_artifacts=artifacts,
        manifest_sha256=normalized_snapshot_manifest_sha256(manifest),
    )
    validate_normalized_snapshot_manifest(result.manifest, artifacts, producing_run)
    return result


def validate_normalized_snapshot_manifest(
    manifest: NormalizedSnapshotManifestV2 | NormalizedSnapshotManifest,
    table_artifacts: Sequence[NormalizedTableArtifact] = (),
    producing_run: RunManifest | None = None,
) -> None:
    if isinstance(manifest, NormalizedSnapshotManifestV2):
        artifacts = tuple(manifest.artifacts)
        if table_artifacts and tuple(table_artifacts) != artifacts:
            raise ValueError("normalized artifact bindings differ from manifest artifacts")
        expected_content = normalized_snapshot_content_from_manifest(manifest)
        if sha256_hex(canonical_json_bytes(expected_content)) != manifest.normalized_content_sha256:
            raise ValueError("normalized content digest mismatch")
        if manifest.normalized_snapshot_id != normalized_snapshot_id(expected_content):
            raise ValueError("normalized snapshot ID mismatch")
        if producing_run is not None:
            require_run_bindings(
                producing_run,
                source_manifest_id=manifest.input_source_snapshot_manifest_id,
                source_id=manifest.source_id,
                source_manifest_sha256=manifest.input_source_snapshot_manifest_sha256,
                artifacts=artifacts,
                schema_version=manifest.normalized_schema_version,
                mapper_version=manifest.mapper_version,
                transform_version=manifest.transform_version,
                policy_version=manifest.policy_version,
            )
        return

    artifacts = tuple(table_artifacts)
    if not artifacts:
        if producing_run is not None:
            raise ValueError("v1 normalized manifest verification requires layer artifacts")
        return
    require_layer_artifacts(artifacts)
    require_count_bindings(manifest.counts, artifacts, len(manifest.quarantine_references))
    normalized = artifact_for_layer(artifacts, "normalized")
    audit = artifact_for_layer(artifacts, "audit")
    if (manifest.normalized_artifact_path, manifest.normalized_artifact_sha256) != (
        normalized.path,
        normalized.sha256,
    ):
        raise ValueError("normalized artifact binding mismatch")
    if (manifest.audit_artifact_path, manifest.audit_artifact_sha256) != (
        audit.path,
        audit.sha256,
    ):
        raise ValueError("audit artifact binding mismatch")
    quarantine = artifact_for_layer(artifacts, "quarantine")
    if any(
        reference.path != quarantine.path or reference.record_locator is None
        for reference in manifest.quarantine_references
    ):
        raise ValueError("quarantine reference binding mismatch")
    if producing_run is None:
        return
    require_run_bindings(
        producing_run,
        source_manifest_id=manifest.input_source_snapshot_manifest_id,
        source_id=manifest.source_id,
        source_manifest_sha256=manifest.input_source_snapshot_manifest_sha256,
        artifacts=artifacts,
        schema_version=manifest.normalized_schema_version,
        mapper_version=manifest.mapper_version,
        transform_version=manifest.transform_version,
        policy_version=policy_version_from_run(producing_run),
    )
    expected_content = normalized_snapshot_content_from_manifest(
        manifest,
        table_artifacts=artifacts,
        producing_run=producing_run,
    )
    if sha256_hex(canonical_json_bytes(expected_content)) != manifest.normalized_content_sha256:
        raise ValueError("normalized content digest mismatch")
    if manifest.normalized_snapshot_id != normalized_snapshot_id(
        expected_content,
        contract_version="v1",
    ):
        raise ValueError("normalized snapshot ID mismatch")


def normalized_snapshot_manifest_bytes(
    value: NormalizedSnapshotBuild | NormalizedSnapshotManifestV2 | NormalizedSnapshotManifest,
) -> bytes:
    manifest = value.manifest if isinstance(value, NormalizedSnapshotBuild) else value
    return canonical_json_bytes(manifest.model_dump(mode="json"))


def normalized_snapshot_manifest_sha256(
    value: NormalizedSnapshotBuild | NormalizedSnapshotManifestV2 | NormalizedSnapshotManifest,
) -> str:
    return detached_manifest_sha256(
        json.loads(normalized_snapshot_manifest_bytes(value).decode("utf-8"))
    )


def normalized_table_artifact_index_bytes(build: NormalizedSnapshotBuild) -> bytes:
    return canonical_json_bytes(
        {
            "schema_version": "normalized-table-artifacts.v1",
            "normalized_snapshot_id": build.manifest.normalized_snapshot_id,
            "normalized_content_sha256": build.manifest.normalized_content_sha256,
            "artifacts": [
                item.model_dump(mode="json")
                for item in sorted(build.table_artifacts, key=lambda item: item.layer)
            ],
        }
    )


def validate_normalized_snapshot_manifest_bytes(
    value: bytes,
    *,
    table_artifacts: Sequence[NormalizedTableArtifact] = (),
    producing_run: RunManifest | None = None,
) -> NormalizedSnapshotManifestV2 | NormalizedSnapshotManifest:
    try:
        payload = json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("normalized manifest is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("normalized manifest must be a JSON object")
    if canonical_json_bytes(payload) != value:
        raise ValueError("normalized manifest serialization is not canonical")
    manifest: NormalizedSnapshotManifestV2 | NormalizedSnapshotManifest
    if payload.get("schema_version") == "normalized-snapshot-manifest.v2":
        manifest = NormalizedSnapshotManifestV2.model_validate(payload)
    else:
        manifest = NormalizedSnapshotManifest.model_validate(payload)
    validate_normalized_snapshot_manifest(manifest, table_artifacts, producing_run)
    return manifest


serialize_normalized_snapshot_manifest = normalized_snapshot_manifest_bytes

__all__ = [
    "NormalizedSnapshotBuild",
    "NormalizedSnapshotManifestV2",
    "NormalizedTableArtifact",
    "VerifiedSnapshotEvidence",
    "build_normalized_snapshot_manifest",
    "normalized_snapshot_manifest_bytes",
    "normalized_snapshot_manifest_sha256",
    "normalized_table_artifact_index_bytes",
    "serialize_normalized_snapshot_manifest",
    "validate_normalized_snapshot_manifest",
    "validate_normalized_snapshot_manifest_bytes",
]
