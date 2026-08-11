"""Canonical content payloads and identity derivation for normalized manifests."""

from __future__ import annotations

from collections.abc import Mapping

from commander_ai.domain.provenance import QuarantineReference
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .normalized_snapshot_contracts import NormalizedSnapshotManifestV2, NormalizedTableArtifact


def normalized_snapshot_content_payload(
    *,
    source_id: str,
    source_manifest_id: str,
    source_manifest_sha256: str,
    producing_run_id: str,
    schema_version: str,
    mapper_version: str,
    transform_version: str,
    policy_version: str,
    artifacts: tuple[NormalizedTableArtifact, ...],
    counts: Mapping[str, int],
    finding_codes: tuple[str, ...],
    quarantine_references: tuple[QuarantineReference, ...],
    status: str,
) -> dict[str, object]:
    return {
        "artifacts": [
            item.model_dump(mode="json") for item in sorted(artifacts, key=lambda item: item.layer)
        ],
        "counts": dict(counts),
        "finding_codes": list(finding_codes),
        "input_source_snapshot_manifest_id": source_manifest_id,
        "mapper_version": mapper_version,
        "policy_version": policy_version,
        "producing_run_id": producing_run_id,
        "quarantine_references": [item.model_dump(mode="json") for item in quarantine_references],
        "schema_version": schema_version,
        "source_id": source_id,
        "source_manifest_sha256": source_manifest_sha256,
        "status": status,
        "transform_version": transform_version,
    }


def normalized_snapshot_content_from_manifest(
    manifest: NormalizedSnapshotManifestV2,
) -> dict[str, object]:
    return normalized_snapshot_content_payload(
        source_id=manifest.source_id,
        source_manifest_id=manifest.input_source_snapshot_manifest_id,
        source_manifest_sha256=manifest.input_source_snapshot_manifest_sha256,
        producing_run_id=manifest.producing_run_id,
        schema_version=manifest.normalized_schema_version,
        mapper_version=manifest.mapper_version,
        transform_version=manifest.transform_version,
        policy_version=manifest.policy_version,
        artifacts=manifest.artifacts,
        counts=manifest.counts,
        finding_codes=manifest.finding_codes,
        quarantine_references=manifest.quarantine_references,
        status=manifest.status,
    )


def normalized_snapshot_id(content_payload: Mapping[str, object]) -> str:
    fingerprint = sha256_hex(
        canonical_json_bytes({"kind": "normalized-snapshot.v2", **content_payload})
    )
    return f"normalized-{fingerprint[:32]}"


__all__ = [
    "normalized_snapshot_content_from_manifest",
    "normalized_snapshot_content_payload",
    "normalized_snapshot_id",
]
