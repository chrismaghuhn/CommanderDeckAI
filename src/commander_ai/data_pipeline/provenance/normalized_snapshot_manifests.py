"""Semantic production and validation for normalized-snapshot-manifest.v1."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from commander_ai.domain.path_policy import validate_portable_relative_path
from commander_ai.domain.provenance import (
    DomainModel,
    NormalizedSnapshotManifest,
    ProvenanceReference,
    QuarantineReference,
    SourceSnapshotManifest,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from ..quality.finding_codes import validate_finding_codes
from .run_manifests import RunManifest


class NormalizedTableArtifact(DomainModel):
    """Hash and row metadata for one authoritative normalized-layer Parquet table."""

    table_name: str = Field(min_length=1)
    layer: Literal["normalized", "audit", "quarantine"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rows: int = Field(ge=0)
    bytes: int = Field(ge=0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)


@dataclass(frozen=True, slots=True)
class NormalizedSnapshotBuild:
    manifest: NormalizedSnapshotManifest
    table_artifacts: tuple[NormalizedTableArtifact, ...]
    manifest_sha256: str


def build_normalized_snapshot_manifest(
    *,
    source_manifest: SourceSnapshotManifest,
    source_manifest_sha256: str,
    producing_run: RunManifest,
    table_artifacts: Sequence[NormalizedTableArtifact],
    normalized_schema_version: str,
    mapper_version: str,
    transform_version: str,
    policy_version: str,
    counts: Mapping[str, int],
    finding_codes: Sequence[str] = (),
    quarantine_references: Sequence[QuarantineReference | Mapping[str, object]] = (),
    started_at: datetime,
    created_at: datetime,
    completed_at: datetime | None,
    raw_snapshot_verified: bool,
) -> NormalizedSnapshotBuild:
    _require_verified_source(source_manifest, source_manifest_sha256, raw_snapshot_verified)
    if producing_run.status != "succeeded":
        raise ValueError("normalized manifest requires a succeeded producing run")
    _require_run_bindings(
        producing_run,
        source_manifest.source_snapshot_id,
        source_manifest_sha256,
        normalized_schema_version,
        mapper_version,
        transform_version,
        policy_version,
    )
    artifacts = tuple(table_artifacts)
    _require_layers(artifacts)
    normalized = next(item for item in artifacts if item.layer == "normalized")
    audit = next(item for item in artifacts if item.layer == "audit")
    normalized_findings = tuple(sorted(set(validate_finding_codes(tuple(finding_codes)))))
    quarantine = tuple(QuarantineReference.model_validate(item) for item in quarantine_references)
    normalized_counts = _validate_counts(counts)
    _validate_artifact_counts(artifacts, normalized_counts)
    for reference in quarantine:
        if reference.path is not None and reference.path not in {
            item.path for item in artifacts if item.layer == "quarantine"
        }:
            raise ValueError("quarantine reference path is not a quarantine artifact")
    content_payload = _content_payload(
        source_manifest_sha256=source_manifest_sha256,
        producing_run_id=producing_run.run_id,
        source_id=source_manifest.source_id,
        schema_version=normalized_schema_version,
        mapper_version=mapper_version,
        transform_version=transform_version,
        policy_version="current-use-bound-in-run",
        artifacts=artifacts,
        counts=normalized_counts,
        finding_codes=normalized_findings,
        quarantine_references=quarantine,
    )
    content_digest = sha256_hex(canonical_json_bytes(content_payload))
    snapshot_fingerprint = sha256_hex(
        canonical_json_bytes({"kind": "normalized-snapshot.v1", **content_payload})
    )
    manifest = NormalizedSnapshotManifest(
        normalized_snapshot_id=f"normalized-{snapshot_fingerprint[:32]}",
        producing_run_id=producing_run.run_id,
        input_source_snapshot_manifest_id=source_manifest.source_snapshot_id,
        input_source_snapshot_manifest_sha256=source_manifest_sha256,
        source_id=source_manifest.source_id,
        status="COMPLETE",
        normalized_schema_version=normalized_schema_version,
        mapper_version=mapper_version,
        transform_version=transform_version,
        normalized_artifact_path=normalized.path,
        normalized_artifact_sha256=normalized.sha256,
        audit_artifact_path=audit.path,
        audit_artifact_sha256=audit.sha256,
        counts=normalized_counts,
        finding_codes=normalized_findings,
        quarantine_references=quarantine,
        provenance=_provenance(source_manifest),
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
    manifest: NormalizedSnapshotManifest,
    table_artifacts: Sequence[NormalizedTableArtifact],
) -> None:
    artifacts = tuple(table_artifacts)
    _require_layers(artifacts)
    normalized = next(item for item in artifacts if item.layer == "normalized")
    audit = next(item for item in artifacts if item.layer == "audit")
    if (manifest.normalized_artifact_path, manifest.normalized_artifact_sha256) != (
        normalized.path,
        normalized.sha256,
    ):
        raise ValueError("normalized artifact binding mismatch")
    if (manifest.audit_artifact_path, manifest.audit_artifact_sha256) != (audit.path, audit.sha256):
        raise ValueError("audit artifact binding mismatch")
    _validate_artifact_counts(artifacts, manifest.counts)
    expected_content = _content_payload_from_manifest(manifest, artifacts)
    if sha256_hex(canonical_json_bytes(expected_content)) != manifest.normalized_content_sha256:
        raise ValueError("normalized content digest mismatch")
    expected_id = sha256_hex(
        canonical_json_bytes({"kind": "normalized-snapshot.v1", **expected_content})
    )
    if manifest.normalized_snapshot_id != f"normalized-{expected_id[:32]}":
        raise ValueError("normalized snapshot ID mismatch")


def normalized_snapshot_manifest_bytes(
    value: NormalizedSnapshotBuild | NormalizedSnapshotManifest,
) -> bytes:
    manifest = value.manifest if isinstance(value, NormalizedSnapshotBuild) else value
    return canonical_json_bytes(manifest.model_dump(mode="json"))


def normalized_snapshot_manifest_sha256(
    value: NormalizedSnapshotBuild | NormalizedSnapshotManifest,
) -> str:
    return sha256_hex(normalized_snapshot_manifest_bytes(value))


def normalized_table_artifact_index_bytes(build: NormalizedSnapshotBuild) -> bytes:
    """Serialize the complete normalized/audit/quarantine artifact binding."""

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


def validate_normalized_snapshot_manifest_bytes(value: bytes) -> NormalizedSnapshotManifest:
    payload = json.loads(value.decode("utf-8"))
    if canonical_json_bytes(payload) != value:
        raise ValueError("normalized manifest serialization is not canonical")
    manifest = NormalizedSnapshotManifest.model_validate(payload)
    return manifest


serialize_normalized_snapshot_manifest = normalized_snapshot_manifest_bytes


def _require_verified_source(
    source_manifest: SourceSnapshotManifest,
    source_manifest_sha256: str,
    raw_snapshot_verified: bool,
) -> None:
    if source_manifest.status != "COMPLETE" or not raw_snapshot_verified:
        raise ValueError("raw snapshot must be COMPLETE and integrity verified")
    if len(source_manifest_sha256) != 64 or any(
        char not in "0123456789abcdef" for char in source_manifest_sha256
    ):
        raise ValueError("source manifest hash must be lowercase SHA-256")


def _require_run_bindings(
    producing_run: RunManifest,
    source_snapshot_id: str,
    source_manifest_sha256: str,
    schema_version: str,
    mapper_version: str,
    transform_version: str,
    policy_version: str,
) -> None:
    input_match = any(
        item.kind == "source_snapshot_manifest"
        and item.id == source_snapshot_id
        and item.sha256 == source_manifest_sha256
        for item in producing_run.inputs
    )
    if not input_match:
        raise ValueError("producing run does not bind the source snapshot manifest")
    for prefix, version in (
        ("schema", schema_version),
        ("mapper", mapper_version),
        ("transform", transform_version),
        ("policy", policy_version),
    ):
        if f"{prefix}:{version}" not in producing_run.feature_spec_versions:
            raise ValueError(f"producing run does not bind {prefix} version")


def _require_layers(artifacts: tuple[NormalizedTableArtifact, ...]) -> None:
    layers: list[str] = [item.layer for item in artifacts]
    if any(layers.count(layer) != 1 for layer in ("normalized", "audit", "quarantine")):
        raise ValueError(
            "normalized manifest requires exactly one normalized, audit, and quarantine artifact"
        )


def _validate_counts(counts: Mapping[str, int]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in counts.items():
        if not isinstance(key, str) or not key or type(value) is not int or value < 0:
            raise ValueError("manifest counts must be non-negative integers")
        result[key] = value
    return dict(sorted(result.items()))


def _validate_artifact_counts(
    artifacts: tuple[NormalizedTableArtifact, ...], counts: Mapping[str, int]
) -> None:
    for artifact in artifacts:
        expected_keys = {
            f"{artifact.table_name}_records",
            f"{artifact.table_name}_rows",
            f"{artifact.layer}_records",
            f"{artifact.layer}_rows",
        }
        for key in expected_keys & counts.keys():
            if counts[key] != artifact.rows:
                raise ValueError(f"count for {key} does not match {artifact.layer} artifact rows")


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


def _content_payload(
    *,
    source_manifest_sha256: str,
    producing_run_id: str,
    source_id: str,
    schema_version: str,
    mapper_version: str,
    transform_version: str,
    policy_version: str,
    artifacts: tuple[NormalizedTableArtifact, ...],
    counts: Mapping[str, int],
    finding_codes: tuple[str, ...],
    quarantine_references: tuple[QuarantineReference, ...],
) -> dict[str, object]:
    return {
        "artifacts": [
            item.model_dump(mode="json") for item in sorted(artifacts, key=lambda item: item.layer)
        ],
        "counts": dict(counts),
        "finding_codes": list(finding_codes),
        "mapper_version": mapper_version,
        "policy_version": policy_version,
        "producing_run_id": producing_run_id,
        "quarantine_references": [item.model_dump(mode="json") for item in quarantine_references],
        "schema_version": schema_version,
        "source_id": source_id,
        "source_manifest_sha256": source_manifest_sha256,
        "transform_version": transform_version,
    }


def _content_payload_from_manifest(
    manifest: NormalizedSnapshotManifest,
    artifacts: tuple[NormalizedTableArtifact, ...],
) -> dict[str, object]:
    return _content_payload(
        source_manifest_sha256=manifest.input_source_snapshot_manifest_sha256,
        producing_run_id=manifest.producing_run_id,
        source_id=manifest.source_id,
        schema_version=manifest.normalized_schema_version,
        mapper_version=manifest.mapper_version,
        transform_version=manifest.transform_version,
        policy_version="current-use-bound-in-run",
        artifacts=artifacts,
        counts=manifest.counts,
        finding_codes=manifest.finding_codes,
        quarantine_references=manifest.quarantine_references,
    )


__all__ = [
    "NormalizedSnapshotBuild",
    "NormalizedTableArtifact",
    "build_normalized_snapshot_manifest",
    "normalized_snapshot_manifest_bytes",
    "normalized_snapshot_manifest_sha256",
    "normalized_table_artifact_index_bytes",
    "serialize_normalized_snapshot_manifest",
    "validate_normalized_snapshot_manifest",
    "validate_normalized_snapshot_manifest_bytes",
]
