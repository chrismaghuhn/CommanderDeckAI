"""Filesystem read/verify boundary for normalized snapshot manifests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from commander_ai.adapters.storage.path_policy import resolve_under_root
from commander_ai.adapters.storage.snapshot_verifier import (
    SnapshotIntegrityError,
    SnapshotVerifier,
    VerifiedSnapshot,
)
from commander_ai.domain.provenance import NormalizedSnapshotManifest

from .normalized_snapshot_contracts import NormalizedSnapshotManifestV2, NormalizedTableArtifact
from .normalized_snapshot_manifests import (
    normalized_snapshot_manifest_sha256,
    validate_normalized_snapshot_manifest,
    validate_normalized_snapshot_manifest_bytes,
)
from .normalized_snapshot_validation import source_provenance
from .run_manifests import RunManifest, verify_run_manifest


@dataclass(frozen=True, slots=True)
class VerifiedNormalizedSnapshot:
    manifest: NormalizedSnapshotManifest | NormalizedSnapshotManifestV2
    manifest_path: Path
    producing_run: RunManifest
    source_snapshot: VerifiedSnapshot
    table_artifacts: tuple[NormalizedTableArtifact, ...]


def read_normalized_snapshot_manifest(
    root: Path | str,
    manifest_path: str,
    *,
    producing_run_path: str | None = None,
    raw_root: Path | str | None = None,
    run_root: Path | str | None = None,
) -> VerifiedNormalizedSnapshot:
    """Read one complete v1/v2 manifest and verify every bound artifact."""

    artifact_root = Path(root).expanduser().resolve()
    manifest_file = resolve_under_root(artifact_root, manifest_path)
    if not manifest_file.is_file() or manifest_file.is_symlink():
        raise ValueError("normalized manifest file is missing")
    manifest = validate_normalized_snapshot_manifest_bytes(manifest_file.read_bytes())
    if manifest.status != "COMPLETE" or manifest.completed_at is None:
        raise ValueError("normalized manifest is not complete")
    _verify_manifest_sidecar(manifest_file, manifest)

    selected_run_path = producing_run_path or f"runs/{manifest.producing_run_id}/manifest.json"
    selected_run_root = artifact_root if run_root is None else Path(run_root).expanduser().resolve()
    selected_raw_root = artifact_root if raw_root is None else Path(raw_root).expanduser().resolve()
    producing_run = verify_run_manifest(
        selected_run_root,
        selected_run_path,
        external_input_root=selected_raw_root,
    )
    if producing_run.run_id != manifest.producing_run_id or producing_run.status != "succeeded":
        raise ValueError("normalized manifest producing run is not the referenced succeeded run")

    try:
        source_snapshot = SnapshotVerifier(selected_raw_root).verify_complete_snapshot(
            manifest.source_id,
            manifest.input_source_snapshot_manifest_id,
        )
    except SnapshotIntegrityError as error:
        raise ValueError(str(error)) from error
    _verify_source_binding(manifest, source_snapshot)

    if isinstance(manifest, NormalizedSnapshotManifestV2):
        artifacts = manifest.artifacts
        for artifact in artifacts:
            _verify_parquet_artifact(artifact_root, artifact, source_snapshot)
    else:
        artifacts = _artifacts_from_run(artifact_root, producing_run, source_snapshot)
        _verify_provenance(manifest, source_snapshot)
        validate_normalized_snapshot_manifest(
            manifest,
            artifacts,
            producing_run=producing_run,
        )
        _verify_quarantine_references(manifest, artifacts)
    if isinstance(manifest, NormalizedSnapshotManifestV2):
        validate_normalized_snapshot_manifest(manifest, artifacts, producing_run=producing_run)
    return VerifiedNormalizedSnapshot(
        manifest=manifest,
        manifest_path=manifest_file,
        producing_run=producing_run,
        source_snapshot=source_snapshot,
        table_artifacts=tuple(artifacts),
    )


verify_normalized_snapshot_manifest = read_normalized_snapshot_manifest


def _verify_manifest_sidecar(
    manifest_file: Path,
    manifest: NormalizedSnapshotManifest | NormalizedSnapshotManifestV2,
) -> None:
    sidecar = manifest_file.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ValueError("normalized manifest detached digest is missing")
    expected = f"{normalized_snapshot_manifest_sha256(manifest)}\n".encode("ascii")
    if sidecar.read_bytes() != expected:
        raise ValueError("normalized manifest detached digest mismatch")


def _verify_source_binding(
    manifest: NormalizedSnapshotManifest | NormalizedSnapshotManifestV2,
    source_snapshot: VerifiedSnapshot,
) -> None:
    if source_snapshot.manifest.source_id != manifest.source_id:
        raise ValueError("normalized manifest source_id does not match source snapshot")
    if source_snapshot.manifest.source_snapshot_id != manifest.input_source_snapshot_manifest_id:
        raise ValueError("normalized manifest source_snapshot_id does not match source snapshot")
    if source_snapshot.manifest_sha256 != manifest.input_source_snapshot_manifest_sha256:
        raise ValueError("normalized manifest source manifest hash mismatch")


def _artifacts_from_run(
    root: Path, run: RunManifest, source_snapshot: VerifiedSnapshot
) -> tuple[NormalizedTableArtifact, ...]:
    artifacts: list[NormalizedTableArtifact] = []
    layers: tuple[Literal["normalized", "audit", "quarantine"], ...] = (
        "normalized",
        "audit",
        "quarantine",
    )
    for layer in layers:
        matches = [item for item in run.artifacts if item.kind == layer]
        if len(matches) != 1:
            raise ValueError(f"run must bind exactly one {layer} output")
        reference = matches[0]
        artifacts.append(
            _verify_parquet_reference(
                root,
                reference.path,
                reference.sha256,
                layer,
                source_snapshot,
            )
        )
    return tuple(artifacts)


def _verify_parquet_reference(
    root: Path,
    relative_path: str,
    expected_sha256: str,
    expected_layer: Literal["normalized", "audit", "quarantine"],
    source_snapshot: VerifiedSnapshot,
) -> NormalizedTableArtifact:
    path = resolve_under_root(root, relative_path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"normalized artifact is missing: {relative_path}")
    actual_bytes = path.stat().st_size
    actual_sha256 = _sha256_file(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(f"normalized artifact hash mismatch: {relative_path}")
    try:
        metadata = pq.read_metadata(path)
    except Exception as error:  # pragma: no cover - backend-specific exception types
        raise ValueError(f"normalized artifact is not readable Parquet: {relative_path}") from error
    schema_metadata = metadata.metadata or {}
    expected_metadata = {
        b"commander_ai.layer": expected_layer.encode("utf-8"),
    }
    for key, expected in expected_metadata.items():
        if schema_metadata.get(key) != expected:
            raise ValueError(f"normalized artifact layer metadata mismatch: {relative_path}")
    from commander_ai.adapters.storage.parquet_tables import validate_parquet_table_rows

    validate_parquet_table_rows(
        path,
        layer=expected_layer,
        verified_snapshot=source_snapshot,
    )
    table_name = schema_metadata.get(b"commander_ai.table_name")
    if table_name is None:
        raise ValueError(f"normalized artifact table metadata is missing: {relative_path}")
    try:
        decoded_table_name = table_name.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError(
            f"normalized artifact table metadata is invalid: {relative_path}"
        ) from error
    return NormalizedTableArtifact(
        table_name=decoded_table_name,
        layer=expected_layer,
        path=relative_path,
        sha256=expected_sha256,
        rows=metadata.num_rows,
        bytes=actual_bytes,
    )


def _verify_parquet_artifact(
    root: Path, artifact: NormalizedTableArtifact, source_snapshot: VerifiedSnapshot
) -> None:
    derived = _verify_parquet_reference(
        root,
        artifact.path,
        artifact.sha256,
        artifact.layer,
        source_snapshot,
    )
    if derived.table_name != artifact.table_name:
        raise ValueError(f"normalized artifact table metadata mismatch: {artifact.path}")
    if derived.rows != artifact.rows:
        raise ValueError(f"normalized artifact row count mismatch: {artifact.path}")
    if derived.bytes != artifact.bytes:
        raise ValueError(f"normalized artifact byte count mismatch: {artifact.path}")


def _verify_provenance(
    manifest: NormalizedSnapshotManifest,
    source_snapshot: VerifiedSnapshot,
) -> None:
    expected = source_provenance(source_snapshot.manifest)
    if tuple(manifest.provenance) != expected:
        raise ValueError("normalized provenance does not match the verified source object index")


def _verify_quarantine_references(
    manifest: NormalizedSnapshotManifest,
    artifacts: tuple[NormalizedTableArtifact, ...],
) -> None:
    quarantine = next(item for item in artifacts if item.layer == "quarantine")
    if len(manifest.quarantine_references) != quarantine.rows:
        raise ValueError("quarantine reference count does not match persisted output")
    if any(
        item.path != quarantine.path or item.record_locator is None
        for item in manifest.quarantine_references
    ):
        raise ValueError("quarantine reference path does not match persisted output")
    identities = [(item.path, item.record_locator) for item in manifest.quarantine_references]
    if len(identities) != len(set(identities)):
        raise ValueError("quarantine record locators must be unique")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "VerifiedNormalizedSnapshot",
    "read_normalized_snapshot_manifest",
    "verify_normalized_snapshot_manifest",
]
