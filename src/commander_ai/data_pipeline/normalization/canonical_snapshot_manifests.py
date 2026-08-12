"""Build and validate canonicalization manifests."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from commander_ai.data_pipeline.provenance.canonical_snapshot_contracts import (
    CanonicalSnapshotManifestV1,
    CanonicalTableArtifact,
)
from commander_ai.data_pipeline.provenance.run_manifests import RunManifest
from commander_ai.domain.provenance import (
    ProvenanceReference,
    QuarantineReference,
    detached_manifest_sha256,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex


@dataclass(frozen=True, slots=True)
class CanonicalSnapshotBuild:
    manifest: CanonicalSnapshotManifestV1
    manifest_sha256: str


def build_canonical_snapshot_manifest(
    *,
    producing_run: RunManifest,
    input_normalized_snapshot_id: str,
    input_normalized_manifest_sha256: str,
    source_id: str,
    artifacts: Sequence[CanonicalTableArtifact],
    counts: Mapping[str, int],
    finding_codes: Sequence[str],
    quarantine_references: Sequence[QuarantineReference | Mapping[str, object]],
    provenance: Sequence[ProvenanceReference],
    started_at: datetime,
    created_at: datetime,
    completed_at: datetime | None,
    mapper_version: str = "canonicalizer-v1",
    transform_version: str = "canonicalize-v1",
) -> CanonicalSnapshotBuild:
    if producing_run.status != "succeeded":
        raise ValueError("canonical manifest requires a succeeded producing run")
    normalized_inputs = [
        item for item in producing_run.inputs if item.kind == "normalized_snapshot_manifest"
    ]
    if len(normalized_inputs) != 1:
        raise ValueError("canonical run must bind exactly one normalized snapshot manifest")
    input_reference = normalized_inputs[0]
    if (
        input_reference.id != input_normalized_snapshot_id
        or input_reference.sha256 != input_normalized_manifest_sha256
    ):
        raise ValueError("canonical run input does not match normalized snapshot")
    artifact_values = tuple(artifacts)
    if len({item.artifact_kind for item in artifact_values}) != len(artifact_values):
        raise ValueError("canonical run artifacts must have unique kinds")
    for artifact in artifact_values:
        matches = [
            item
            for item in producing_run.artifacts
            if item.kind == artifact.artifact_kind and item.path == artifact.path
        ]
        if len(matches) != 1 or matches[0].sha256 != artifact.sha256:
            raise ValueError(f"canonical run does not bind {artifact.artifact_kind} output")

    normalized_counts = dict(sorted((str(key), value) for key, value in counts.items()))
    normalized_findings = tuple(sorted(set(str(item) for item in finding_codes)))
    normalized_quarantine = tuple(
        sorted(
            (QuarantineReference.model_validate(item) for item in quarantine_references),
            key=lambda item: (
                item.quarantine_id,
                item.reason_code,
                item.path or "",
                item.record_locator or "",
            ),
        )
    )
    normalized_provenance = tuple(
        sorted(
            (ProvenanceReference.model_validate(item) for item in provenance),
            key=lambda item: (item.source_object_id, item.raw_sha256),
        )
    )
    content_payload = _content_payload(
        input_normalized_snapshot_id=input_normalized_snapshot_id,
        input_normalized_manifest_sha256=input_normalized_manifest_sha256,
        source_id=source_id,
        producing_run_id=producing_run.run_id,
        mapper_version=mapper_version,
        transform_version=transform_version,
        artifacts=artifact_values,
        counts=normalized_counts,
        finding_codes=normalized_findings,
        quarantine_references=normalized_quarantine,
        provenance=normalized_provenance,
    )
    content_digest = sha256_hex(canonical_json_bytes(content_payload))
    manifest = CanonicalSnapshotManifestV1(
        canonical_snapshot_id=f"canonical-{content_digest[:32]}",
        producing_run_id=producing_run.run_id,
        input_normalized_snapshot_id=input_normalized_snapshot_id,
        input_normalized_manifest_sha256=input_normalized_manifest_sha256,
        source_id=source_id,
        status="COMPLETE",
        canonical_schema_version="canonical-record.v1",
        mapper_version=mapper_version,
        transform_version=transform_version,
        artifacts=artifact_values,
        counts=normalized_counts,
        finding_codes=normalized_findings,
        quarantine_references=normalized_quarantine,
        provenance=normalized_provenance,
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        canonical_content_sha256=content_digest,
    )
    validate_canonical_snapshot_manifest(manifest, producing_run=producing_run)
    return CanonicalSnapshotBuild(
        manifest=manifest,
        manifest_sha256=canonical_snapshot_manifest_sha256(manifest),
    )


def validate_canonical_snapshot_manifest(
    manifest: CanonicalSnapshotManifestV1,
    *,
    producing_run: RunManifest | None = None,
) -> None:
    payload = _content_payload(
        input_normalized_snapshot_id=manifest.input_normalized_snapshot_id,
        input_normalized_manifest_sha256=manifest.input_normalized_manifest_sha256,
        source_id=manifest.source_id,
        producing_run_id=manifest.producing_run_id,
        mapper_version=manifest.mapper_version,
        transform_version=manifest.transform_version,
        artifacts=manifest.artifacts,
        counts=manifest.counts,
        finding_codes=manifest.finding_codes,
        quarantine_references=manifest.quarantine_references,
        provenance=manifest.provenance,
    )
    expected_content = sha256_hex(canonical_json_bytes(payload))
    if expected_content != manifest.canonical_content_sha256:
        raise ValueError("canonical content digest mismatch")
    if manifest.canonical_snapshot_id != f"canonical-{expected_content[:32]}":
        raise ValueError("canonical snapshot ID mismatch")
    if producing_run is not None:
        inputs = [
            item for item in producing_run.inputs if item.kind == "normalized_snapshot_manifest"
        ]
        if len(inputs) != 1 or (
            inputs[0].id != manifest.input_normalized_snapshot_id
            or inputs[0].sha256 != manifest.input_normalized_manifest_sha256
        ):
            raise ValueError("canonical run input does not match normalized snapshot")
        for artifact in manifest.artifacts:
            matches = [
                item
                for item in producing_run.artifacts
                if item.kind == artifact.artifact_kind and item.path == artifact.path
            ]
            if len(matches) != 1 or matches[0].sha256 != artifact.sha256:
                raise ValueError(f"canonical run does not bind {artifact.artifact_kind} output")


def canonical_snapshot_manifest_bytes(
    value: CanonicalSnapshotBuild | CanonicalSnapshotManifestV1,
) -> bytes:
    manifest = value.manifest if isinstance(value, CanonicalSnapshotBuild) else value
    return canonical_json_bytes(manifest.model_dump(mode="json"))


def canonical_snapshot_manifest_sha256(
    value: CanonicalSnapshotBuild | CanonicalSnapshotManifestV1,
) -> str:
    payload = json.loads(canonical_snapshot_manifest_bytes(value).decode("utf-8"))
    return detached_manifest_sha256(payload)


def validate_canonical_snapshot_manifest_bytes(value: bytes) -> CanonicalSnapshotManifestV1:
    try:
        payload = json.loads(value.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("canonical snapshot manifest is not valid JSON") from error
    if not isinstance(payload, dict) or canonical_json_bytes(payload) != value:
        raise ValueError("canonical snapshot manifest is not canonical JSON")
    manifest = CanonicalSnapshotManifestV1.model_validate(payload)
    validate_canonical_snapshot_manifest(manifest)
    return manifest


def _content_payload(
    *,
    input_normalized_snapshot_id: str,
    input_normalized_manifest_sha256: str,
    source_id: str,
    producing_run_id: str,
    mapper_version: str,
    transform_version: str,
    artifacts: Sequence[CanonicalTableArtifact],
    counts: Mapping[str, int],
    finding_codes: Sequence[str],
    quarantine_references: Sequence[QuarantineReference],
    provenance: Sequence[ProvenanceReference],
) -> dict[str, object]:
    return {
        "contract_version": "canonical-snapshot-manifest.v1",
        "input_normalized_snapshot_id": input_normalized_snapshot_id,
        "input_normalized_manifest_sha256": input_normalized_manifest_sha256,
        "source_id": source_id,
        "producing_run_id": producing_run_id,
        "mapper_version": mapper_version,
        "transform_version": transform_version,
        "artifacts": [
            item.model_dump(mode="json")
            for item in sorted(artifacts, key=lambda item: item.artifact_kind)
        ],
        "counts": dict(sorted(counts.items())),
        "finding_codes": list(sorted(finding_codes)),
        "quarantine_references": [item.model_dump(mode="json") for item in quarantine_references],
        "provenance": [item.model_dump(mode="json") for item in provenance],
    }


__all__ = [
    "CanonicalSnapshotBuild",
    "build_canonical_snapshot_manifest",
    "canonical_snapshot_manifest_bytes",
    "canonical_snapshot_manifest_sha256",
    "validate_canonical_snapshot_manifest",
    "validate_canonical_snapshot_manifest_bytes",
]
