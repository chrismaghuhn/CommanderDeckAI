"""Fail-closed binding checks shared by normalized manifest build and read paths."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.domain.provenance import (
    ProvenanceReference,
    QuarantineReference,
    SourceSnapshotManifest,
    detached_manifest_sha256,
)

from ..quality.finding_codes import validate_finding_codes
from .normalized_snapshot_content import run_policy_binding
from .normalized_snapshot_contracts import NormalizedTableArtifact
from .run_manifests import RunManifest

VerifiedSnapshotEvidence = VerifiedSourceSnapshot


def require_verified_source(
    *,
    verified_snapshot: VerifiedSnapshotEvidence | None,
    source_manifest: SourceSnapshotManifest | None,
    source_manifest_sha256: str | None,
    raw_snapshot_verified: bool | None,
) -> tuple[SourceSnapshotManifest, str]:
    if raw_snapshot_verified is not None or not isinstance(
        verified_snapshot, VerifiedSourceSnapshot
    ):
        raise ValueError("verified raw snapshot evidence is required")
    try:
        verified_snapshot.assert_consistent()
    except (TypeError, ValueError) as error:
        raise ValueError("verified raw snapshot evidence is inconsistent") from error
    manifest = verified_snapshot.manifest
    if manifest.status != "COMPLETE" or manifest.completed_at is None:
        raise ValueError("raw snapshot must be COMPLETE and integrity verified")
    if verified_snapshot.snapshot_dir.parts[-3:] != (
        "raw",
        manifest.source_id,
        manifest.source_snapshot_id,
    ):
        raise ValueError("verified source snapshot path identity is inconsistent")
    if source_manifest is not None and (
        source_manifest.status != "COMPLETE" or source_manifest.completed_at is None
    ):
        raise ValueError("raw snapshot source manifest must be COMPLETE")
    if source_manifest is not None and source_manifest != manifest:
        raise ValueError("requested source manifest differs from verified snapshot")
    derived_hash = detached_manifest_sha256(manifest.model_dump(mode="json"))
    if verified_snapshot.manifest_sha256 != derived_hash:
        raise ValueError("verified source manifest hash is inconsistent")
    if source_manifest_sha256 is not None and source_manifest_sha256 != derived_hash:
        raise ValueError("source manifest hash does not match verified manifest")
    return manifest, derived_hash


def require_run_bindings(
    producing_run: RunManifest,
    *,
    source_manifest_id: str,
    source_id: str,
    source_manifest_sha256: str,
    artifacts: tuple[NormalizedTableArtifact, ...],
    schema_version: str,
    mapper_version: str,
    transform_version: str,
    policy_version: str,
) -> None:
    source_inputs = [
        item for item in producing_run.inputs if item.kind == "source_snapshot_manifest"
    ]
    if len(source_inputs) != 1:
        raise ValueError("producing run must bind exactly one source snapshot manifest")
    source_input = source_inputs[0]
    if source_input.id != source_manifest_id or source_input.sha256 != source_manifest_sha256:
        raise ValueError("producing run does not bind the verified source snapshot manifest")
    expected_path = f"raw/{source_id}/{source_manifest_id}/manifest.json"
    if source_input.path != expected_path:
        raise ValueError("producing run source manifest path is inconsistent")
    policy_reference, policy_hash = run_policy_binding(producing_run)
    if not policy_reference.startswith(f"current-use.v1:{source_id}:"):
        raise ValueError("producing run current-use decision source is inconsistent")
    if len(policy_hash) != 64:
        raise ValueError("producing run current-use decision digest is invalid")
    for layer in ("normalized", "audit", "quarantine"):
        if len([item for item in producing_run.artifacts if item.kind == layer]) != 1:
            raise ValueError(f"producing run must bind exactly one {layer} output")
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


def policy_version_from_run(run: RunManifest) -> str:
    values = [
        item.removeprefix("policy:")
        for item in run.feature_spec_versions
        if item.startswith("policy:")
    ]
    if len(values) != 1 or not values[0]:
        raise ValueError("producing run must bind exactly one policy version")
    return values[0]


def validate_counts(counts: Mapping[str, int]) -> dict[str, int]:
    if not counts or any(
        not isinstance(key, str) or not key or type(value) is not int or value < 0
        for key, value in counts.items()
    ):
        raise ValueError("manifest counts must be non-negative integers")
    return dict(sorted(counts.items()))


def require_count_bindings(
    counts: Mapping[str, int],
    artifacts: tuple[NormalizedTableArtifact, ...],
    quarantine_count: int,
) -> None:
    for artifact in artifacts:
        key = f"{artifact.layer}_records"
        if counts.get(key) != artifact.rows:
            raise ValueError(f"count for {key} does not match artifact rows")
    if counts.get("quarantine_records") != quarantine_count:
        raise ValueError("quarantine reference count does not match quarantine output")


def require_layer_artifacts(artifacts: tuple[NormalizedTableArtifact, ...]) -> None:
    if len(artifacts) != 3 or sorted(item.layer for item in artifacts) != [
        "audit",
        "normalized",
        "quarantine",
    ]:
        raise ValueError("normalized manifest requires exactly one artifact per layer")
    identities = [(item.layer, item.table_name, item.path) for item in artifacts]
    if len(identities) != len(set(identities)):
        raise ValueError("normalized artifact bindings must be unique")


def unique_findings(finding_codes: Sequence[str]) -> tuple[str, ...]:
    findings = validate_finding_codes(tuple(finding_codes))
    if len(findings) != len(set(findings)):
        raise ValueError("normalized finding codes must be unique")
    return tuple(sorted(findings))


def sorted_quarantine(
    references: Sequence[QuarantineReference | Mapping[str, object]],
) -> tuple[QuarantineReference, ...]:
    values = [QuarantineReference.model_validate(item) for item in references]
    if len({item.quarantine_id for item in values}) != len(values):
        raise ValueError("quarantine references must be unique")
    return tuple(sorted(values, key=quarantine_sort_key))


def quarantine_sort_key(item: QuarantineReference) -> tuple[str, str, str, str]:
    return item.quarantine_id, item.reason_code, item.path or "", item.record_locator or ""


def source_provenance(source_manifest: SourceSnapshotManifest) -> tuple[ProvenanceReference, ...]:
    return tuple(
        sorted(
            (
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
            ),
            key=lambda item: (item.source_object_id, item.raw_sha256),
        )
    )


def artifact_for_layer(
    artifacts: Sequence[NormalizedTableArtifact], layer: str
) -> NormalizedTableArtifact:
    matches = [item for item in artifacts if item.layer == layer]
    if len(matches) != 1:
        raise ValueError(f"normalized manifest requires exactly one {layer} artifact")
    return matches[0]


__all__ = [
    "VerifiedSnapshotEvidence",
    "artifact_for_layer",
    "policy_version_from_run",
    "quarantine_sort_key",
    "require_count_bindings",
    "require_layer_artifacts",
    "require_run_bindings",
    "require_verified_source",
    "sorted_quarantine",
    "source_provenance",
    "unique_findings",
    "validate_counts",
]
