"""Build and semantically validate versioned normalized snapshot manifests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from commander_ai.domain.provenance import (
    NormalizedSnapshotManifest,
    ProvenanceReference,
    QuarantineReference,
    SourceSnapshotManifest,
    detached_manifest_sha256,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from ..quality.finding_codes import validate_finding_codes
from .normalized_snapshot_content import (
    normalized_snapshot_content_from_manifest,
    normalized_snapshot_content_payload,
    normalized_snapshot_id,
)
from .normalized_snapshot_contracts import (
    NormalizedSnapshotManifestV2,
    NormalizedTableArtifact,
)
from .run_manifests import RunManifest


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotBuild:
    manifest: NormalizedSnapshotManifestV2
    table_artifacts: tuple[NormalizedTableArtifact, ...]
    manifest_sha256: str


class VerifiedSnapshotEvidence(Protocol):
    """Immutable evidence supplied by the raw-snapshot verification port."""

    manifest: SourceSnapshotManifest
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
    verified_manifest, verified_hash = _require_verified_source(
        verified_snapshot=verified_snapshot,
        source_manifest=source_manifest,
        source_manifest_sha256=source_manifest_sha256,
        raw_snapshot_verified=raw_snapshot_verified,
    )
    if producing_run.status != "succeeded":
        raise ValueError("normalized manifest requires a succeeded producing run")
    artifacts = tuple(table_artifacts)
    findings = _unique_findings(finding_codes)
    quarantine = tuple(QuarantineReference.model_validate(item) for item in quarantine_references)
    normalized_counts = _validate_counts(counts)
    _require_run_bindings(
        producing_run,
        source_manifest=verified_manifest,
        source_manifest_sha256=verified_hash,
        artifacts=artifacts,
        schema_version=normalized_schema_version,
        mapper_version=mapper_version,
        transform_version=transform_version,
        policy_version=policy_version,
    )
    content_payload = normalized_snapshot_content_payload(
        source_id=verified_manifest.source_id,
        source_manifest_id=verified_manifest.source_snapshot_id,
        source_manifest_sha256=verified_hash,
        producing_run_id=producing_run.run_id,
        schema_version=normalized_schema_version,
        mapper_version=mapper_version,
        transform_version=transform_version,
        policy_version=policy_version,
        artifacts=artifacts,
        counts=normalized_counts,
        finding_codes=findings,
        quarantine_references=quarantine,
        status="COMPLETE",
    )
    content_digest = sha256_hex(canonical_json_bytes(content_payload))
    snapshot_id = normalized_snapshot_id(content_payload)
    normalized = _artifact_for_layer(artifacts, "normalized")
    audit = _artifact_for_layer(artifacts, "audit")
    manifest = NormalizedSnapshotManifestV2(
        normalized_snapshot_id=snapshot_id,
        producing_run_id=producing_run.run_id,
        input_source_snapshot_manifest_id=verified_manifest.source_snapshot_id,
        input_source_snapshot_manifest_sha256=verified_hash,
        source_id=verified_manifest.source_id,
        status="COMPLETE",
        normalized_schema_version=normalized_schema_version,
        mapper_version=mapper_version,
        transform_version=transform_version,
        policy_version=policy_version,
        normalized_artifact_path=normalized.path,
        normalized_artifact_sha256=normalized.sha256,
        audit_artifact_path=audit.path,
        audit_artifact_sha256=audit.sha256,
        artifacts=artifacts,
        counts=normalized_counts,
        finding_codes=findings,
        quarantine_references=quarantine,
        provenance=_provenance(verified_manifest),
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        normalized_content_sha256=content_digest,
    )
    result = NormalizedSnapshotBuild(
        manifest=manifest,
        table_artifacts=artifacts,
        manifest_sha256=normalized_snapshot_manifest_sha256(manifest),
    )
    validate_normalized_snapshot_manifest(result.manifest, result.table_artifacts)
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
            _require_run_bindings(
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
    if len(artifacts) != 3:
        raise ValueError("v1 normalized manifest verification requires all layer artifacts")
    normalized = _artifact_for_layer(artifacts, "normalized")
    audit = _artifact_for_layer(artifacts, "audit")
    if (manifest.normalized_artifact_path, manifest.normalized_artifact_sha256) != (
        normalized.path,
        normalized.sha256,
    ):
        raise ValueError("normalized artifact binding mismatch")
    if (manifest.audit_artifact_path, manifest.audit_artifact_sha256) != (audit.path, audit.sha256):
        raise ValueError("audit artifact binding mismatch")


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
) -> NormalizedSnapshotManifestV2 | NormalizedSnapshotManifest:
    try:
        payload = json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("normalized manifest is not valid JSON") from error
    if not isinstance(payload, dict):
        raise ValueError("normalized manifest must be a JSON object")
    if canonical_json_bytes(payload) != value:
        raise ValueError("normalized manifest serialization is not canonical")
    if payload.get("schema_version") == "normalized-snapshot-manifest.v2":
        manifest = NormalizedSnapshotManifestV2.model_validate(payload)
        validate_normalized_snapshot_manifest(manifest)
        return manifest
    return NormalizedSnapshotManifest.model_validate(payload)


def _require_verified_source(
    *,
    verified_snapshot: VerifiedSnapshotEvidence | None,
    source_manifest: SourceSnapshotManifest | None,
    source_manifest_sha256: str | None,
    raw_snapshot_verified: bool | None,
) -> tuple[SourceSnapshotManifest, str]:
    if verified_snapshot is None:
        raise ValueError("verified raw snapshot evidence is required")
    if raw_snapshot_verified is False:
        raise ValueError("raw snapshot integrity verification failed")
    manifest = verified_snapshot.manifest
    if not isinstance(manifest, SourceSnapshotManifest):
        raise ValueError("verified raw snapshot evidence has no typed source manifest")
    if source_manifest is not None and source_manifest != manifest:
        raise ValueError("requested source manifest differs from verified snapshot")
    derived_hash = detached_manifest_sha256(manifest.model_dump(mode="json"))
    if verified_snapshot.manifest_sha256 != derived_hash:
        raise ValueError("verified source manifest hash is inconsistent")
    if source_manifest_sha256 is not None and source_manifest_sha256 != derived_hash:
        raise ValueError("source manifest hash does not match verified manifest")
    if manifest.status != "COMPLETE" or manifest.completed_at is None:
        raise ValueError("raw snapshot must be COMPLETE and integrity verified")
    return manifest, derived_hash


def _require_run_bindings(
    producing_run: RunManifest,
    *,
    source_manifest: SourceSnapshotManifest | None = None,
    source_manifest_id: str | None = None,
    source_id: str | None = None,
    source_manifest_sha256: str,
    artifacts: tuple[NormalizedTableArtifact, ...],
    schema_version: str,
    mapper_version: str,
    transform_version: str,
    policy_version: str,
) -> None:
    expected_source_id = (
        source_manifest.source_snapshot_id if source_manifest else source_manifest_id
    )
    expected_source = source_manifest.source_id if source_manifest else source_id
    if expected_source_id is None or expected_source is None:
        raise ValueError("source manifest identity is required")
    source_inputs = [
        item
        for item in producing_run.inputs
        if item.kind == "source_snapshot_manifest" and item.id == expected_source_id
    ]
    if len(source_inputs) != 1 or source_inputs[0].sha256 != source_manifest_sha256:
        raise ValueError("producing run does not bind the verified source snapshot manifest")
    expected_path = f"raw/{expected_source}/{expected_source_id}/manifest.json"
    if source_inputs[0].path != expected_path:
        raise ValueError("producing run source manifest path is inconsistent")
    for artifact in artifacts:
        matches = [
            item
            for item in producing_run.artifacts
            if item.kind == artifact.layer and item.path == artifact.path
        ]
        if len(matches) != 1 or matches[0].sha256 != artifact.sha256:
            raise ValueError(f"producing run does not bind {artifact.layer} output artifact")
    for prefix, version in (
        ("schema", schema_version),
        ("mapper", mapper_version),
        ("transform", transform_version),
        ("policy", policy_version),
    ):
        if f"{prefix}:{version}" not in producing_run.feature_spec_versions:
            raise ValueError(f"producing run does not bind {prefix} version")


def _validate_counts(counts: Mapping[str, int]) -> dict[str, int]:
    if not counts or any(
        not isinstance(key, str) or not key or type(value) is not int or value < 0
        for key, value in counts.items()
    ):
        raise ValueError("manifest counts must be non-negative integers")
    return dict(sorted(counts.items()))


def _unique_findings(finding_codes: Sequence[str]) -> tuple[str, ...]:
    findings = validate_finding_codes(tuple(finding_codes))
    if len(findings) != len(set(findings)):
        raise ValueError("normalized finding codes must be unique")
    return tuple(sorted(findings))


def _provenance(source_manifest: SourceSnapshotManifest) -> tuple[ProvenanceReference, ...]:
    return tuple(
        ProvenanceReference(
            source_id=source_manifest.source_id,
            source_snapshot_id=source_manifest.source_snapshot_id,
            source_object_id=raw_object.raw_object_id,
            raw_sha256=raw_object.sha256,
            retrieved_at=raw_object.retrieved_at,
            adapter_version=source_manifest.adapter_version,
            approval_status=source_manifest.approval_status,
        )
        for raw_object in source_manifest.objects
    )


def _artifact_for_layer(
    artifacts: Sequence[NormalizedTableArtifact], layer: str
) -> NormalizedTableArtifact:
    matches = [item for item in artifacts if item.layer == layer]
    if len(matches) != 1:
        raise ValueError(f"normalized manifest requires exactly one {layer} artifact")
    return matches[0]


serialize_normalized_snapshot_manifest = normalized_snapshot_manifest_bytes

__all__ = [
    "NormalizedSnapshotBuild",
    "NormalizedSnapshotManifestV2",
    "NormalizedTableArtifact",
    "build_normalized_snapshot_manifest",
    "normalized_snapshot_manifest_bytes",
    "normalized_snapshot_manifest_sha256",
    "normalized_table_artifact_index_bytes",
    "serialize_normalized_snapshot_manifest",
    "validate_normalized_snapshot_manifest",
    "validate_normalized_snapshot_manifest_bytes",
]
