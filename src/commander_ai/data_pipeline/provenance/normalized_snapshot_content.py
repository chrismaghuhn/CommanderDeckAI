"""Canonical content payloads and identity derivation for normalized manifests."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING

from commander_ai.domain.provenance import (
    NormalizedSnapshotManifest,
    ProvenanceReference,
    QuarantineReference,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .normalized_snapshot_contracts import NormalizedSnapshotManifestV2, NormalizedTableArtifact

if TYPE_CHECKING:
    from .run_manifests import RunManifest


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
    """Build the legacy v2 content payload without changing its identity rules."""

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


def normalized_snapshot_v1_content_payload(
    *,
    source_id: str,
    source_manifest_id: str,
    source_manifest_sha256: str,
    producing_run_id: str,
    schema_version: str,
    mapper_version: str,
    transform_version: str,
    policy_version: str,
    policy_decision_reference: str,
    policy_decision_sha256: str,
    artifacts: tuple[NormalizedTableArtifact, ...],
    counts: Mapping[str, int],
    finding_codes: tuple[str, ...],
    quarantine_references: tuple[QuarantineReference, ...],
    provenance: Sequence[ProvenanceReference],
    status: str,
) -> dict[str, object]:
    """Build the complete v1 identity payload, including hidden run bindings."""

    return {
        "artifacts": [
            item.model_dump(mode="json") for item in sorted(artifacts, key=lambda item: item.layer)
        ],
        "counts": dict(sorted(counts.items())),
        "finding_codes": list(sorted(finding_codes)),
        "input_source_snapshot_manifest_id": source_manifest_id,
        "input_source_snapshot_manifest_sha256": source_manifest_sha256,
        "mapper_version": mapper_version,
        "policy_decision_reference": policy_decision_reference,
        "policy_decision_sha256": policy_decision_sha256,
        "policy_version": policy_version,
        "producing_run_id": producing_run_id,
        "provenance": [
            item.model_dump(mode="json") for item in sorted(provenance, key=_provenance_sort_key)
        ],
        "quarantine_references": [
            item.model_dump(mode="json")
            for item in sorted(quarantine_references, key=_quarantine_sort_key)
        ],
        "schema_version": schema_version,
        "source_id": source_id,
        "status": status,
        "transform_version": transform_version,
        "contract_version": "normalized-snapshot-manifest.v1",
    }


def normalized_snapshot_content_from_manifest(
    manifest: NormalizedSnapshotManifestV2 | NormalizedSnapshotManifest,
    *,
    table_artifacts: Sequence[NormalizedTableArtifact] = (),
    producing_run: RunManifest | None = None,
) -> dict[str, object]:
    if isinstance(manifest, NormalizedSnapshotManifestV2):
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
    if producing_run is None or len(tuple(table_artifacts)) != 3:
        raise ValueError("v1 content verification requires run and layer artifact context")
    decision_reference, decision_sha256 = run_policy_binding(producing_run)
    return normalized_snapshot_v1_content_payload(
        source_id=manifest.source_id,
        source_manifest_id=manifest.input_source_snapshot_manifest_id,
        source_manifest_sha256=manifest.input_source_snapshot_manifest_sha256,
        producing_run_id=manifest.producing_run_id,
        schema_version=manifest.normalized_schema_version,
        mapper_version=manifest.mapper_version,
        transform_version=manifest.transform_version,
        policy_version=_bound_feature_version(producing_run, "policy"),
        policy_decision_reference=decision_reference,
        policy_decision_sha256=decision_sha256,
        artifacts=tuple(table_artifacts),
        counts=manifest.counts,
        finding_codes=manifest.finding_codes,
        quarantine_references=manifest.quarantine_references,
        provenance=manifest.provenance,
        status=manifest.status,
    )


def normalized_snapshot_id(
    content_payload: Mapping[str, object], *, contract_version: str = "v2"
) -> str:
    kind = f"normalized-snapshot.{contract_version}"
    fingerprint = sha256_hex(canonical_json_bytes({"kind": kind, **content_payload}))
    return f"normalized-{fingerprint[:32]}"


def run_policy_binding(run: RunManifest) -> tuple[str, str]:
    candidates = [item for item in run.inputs if item.kind == "current_use_decision"]
    if len(candidates) != 1:
        raise ValueError("run must bind exactly one current-use decision")
    reference = candidates[0]
    expected = f"current-use.v1:{_source_from_reference(reference.id)}:{reference.sha256[:32]}"
    if reference.id != expected:
        raise ValueError("current-use decision reference and digest are inconsistent")
    return reference.id, reference.sha256


def _source_from_reference(reference: str) -> str:
    prefix, separator, source_and_digest = reference.partition(":")
    if prefix != "current-use.v1" or not separator:
        raise ValueError("current-use decision reference is invalid")
    source, separator, digest = source_and_digest.rpartition(":")
    if (
        not separator
        or not source
        or len(digest) != 32
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise ValueError("current-use decision reference is invalid")
    return source


def _bound_feature_version(run: RunManifest, prefix: str) -> str:
    values = [
        item.removeprefix(f"{prefix}:")
        for item in run.feature_spec_versions
        if item.startswith(f"{prefix}:")
    ]
    if len(values) != 1 or not values[0]:
        raise ValueError(f"run must bind exactly one {prefix} version")
    return values[0]


def _provenance_sort_key(item: ProvenanceReference) -> tuple[str, str, str]:
    return item.source_object_id, item.raw_sha256, item.source_snapshot_id


def _quarantine_sort_key(item: QuarantineReference) -> tuple[str, str, str, str]:
    return (
        item.quarantine_id,
        item.reason_code,
        item.path or "",
        item.record_locator or "",
    )


__all__ = [
    "normalized_snapshot_content_from_manifest",
    "normalized_snapshot_content_payload",
    "normalized_snapshot_id",
    "normalized_snapshot_v1_content_payload",
    "run_policy_binding",
]
