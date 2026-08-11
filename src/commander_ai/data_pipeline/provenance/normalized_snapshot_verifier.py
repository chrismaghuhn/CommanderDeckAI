"""Filesystem read/verify boundary for normalized snapshot manifests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq  # type: ignore[import-untyped]

from commander_ai.adapters.storage.path_policy import resolve_under_root
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier, VerifiedSnapshot

from .normalized_snapshot_contracts import NormalizedSnapshotManifestV2, NormalizedTableArtifact
from .normalized_snapshot_manifests import (
    normalized_snapshot_manifest_sha256,
    validate_normalized_snapshot_manifest,
    validate_normalized_snapshot_manifest_bytes,
)
from .run_manifests import RunManifest, verify_run_manifest


@dataclass(frozen=True, slots=True)
class VerifiedNormalizedSnapshot:
    manifest: NormalizedSnapshotManifestV2
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
    """Read one complete normalized manifest and verify all bound evidence."""

    artifact_root = Path(root).expanduser().resolve()
    manifest_file = resolve_under_root(artifact_root, manifest_path)
    if not manifest_file.is_file() or manifest_file.is_symlink():
        raise ValueError("normalized manifest file is missing")
    manifest_bytes = manifest_file.read_bytes()
    manifest = validate_normalized_snapshot_manifest_bytes(manifest_bytes)
    if not isinstance(manifest, NormalizedSnapshotManifestV2):
        raise ValueError("normalized v1 manifests lack explicit artifact bindings")
    if manifest.status != "COMPLETE" or manifest.completed_at is None:
        raise ValueError("normalized manifest is not complete")
    _verify_manifest_sidecar(manifest_file, manifest)

    selected_run_path = producing_run_path or f"runs/{manifest.producing_run_id}/manifest.json"
    selected_run_root = artifact_root if run_root is None else Path(run_root).expanduser().resolve()
    producing_run = verify_run_manifest(selected_run_root, selected_run_path)
    if producing_run.run_id != manifest.producing_run_id or producing_run.status != "succeeded":
        raise ValueError("normalized manifest producing run is not the referenced succeeded run")
    validate_normalized_snapshot_manifest(manifest, producing_run=producing_run)

    selected_raw_root = artifact_root if raw_root is None else Path(raw_root).expanduser().resolve()
    source_snapshot = SnapshotVerifier(selected_raw_root).verify_complete_snapshot(
        manifest.source_id,
        manifest.input_source_snapshot_manifest_id,
    )
    if source_snapshot.manifest.source_id != manifest.source_id:
        raise ValueError("normalized manifest source_id does not match source snapshot")
    if (
        source_snapshot.manifest.source_snapshot_id
        != manifest.input_source_snapshot_manifest_id
    ):
        raise ValueError("normalized manifest source_snapshot_id does not match source snapshot")
    if source_snapshot.manifest_sha256 != manifest.input_source_snapshot_manifest_sha256:
        raise ValueError("normalized manifest source manifest hash mismatch")

    for artifact in manifest.artifacts:
        _verify_parquet_artifact(artifact_root, artifact)
    return VerifiedNormalizedSnapshot(
        manifest=manifest,
        manifest_path=manifest_file,
        producing_run=producing_run,
        source_snapshot=source_snapshot,
        table_artifacts=manifest.artifacts,
    )


verify_normalized_snapshot_manifest = read_normalized_snapshot_manifest


def _verify_manifest_sidecar(
    manifest_file: Path,
    manifest: NormalizedSnapshotManifestV2,
) -> None:
    sidecar = manifest_file.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ValueError("normalized manifest detached digest is missing")
    expected = f"{normalized_snapshot_manifest_sha256(manifest)}\n".encode("ascii")
    if sidecar.read_bytes() != expected:
        raise ValueError("normalized manifest detached digest mismatch")


def _verify_parquet_artifact(root: Path, artifact: NormalizedTableArtifact) -> None:
    path = resolve_under_root(root, artifact.path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"normalized artifact is missing: {artifact.path}")
    if path.stat().st_size != artifact.bytes:
        raise ValueError(f"normalized artifact byte count mismatch: {artifact.path}")
    if _sha256_file(path) != artifact.sha256:
        raise ValueError(f"normalized artifact hash mismatch: {artifact.path}")
    try:
        metadata = pq.read_metadata(path)
    except Exception as error:  # pragma: no cover - backend-specific exception types
        raise ValueError(f"normalized artifact is not readable Parquet: {artifact.path}") from error
    if metadata.num_rows != artifact.rows:
        raise ValueError(f"normalized artifact row count mismatch: {artifact.path}")
    schema_metadata = metadata.metadata or {}
    expected_metadata = {
        b"commander_ai.table_name": artifact.table_name.encode("utf-8"),
        b"commander_ai.layer": artifact.layer.encode("utf-8"),
    }
    for key, expected in expected_metadata.items():
        if schema_metadata.get(key) != expected:
            raise ValueError(f"normalized artifact layer metadata mismatch: {artifact.path}")


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
