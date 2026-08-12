"""Filesystem verification for canonical snapshot manifests and tables."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel

from commander_ai.adapters.storage.path_policy import resolve_under_root
from commander_ai.adapters.storage.snapshot_verifier import VerifiedSnapshot
from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.data_pipeline.normalization.canonical_snapshot_manifests import (
    canonical_snapshot_manifest_sha256,
    validate_canonical_snapshot_manifest,
    validate_canonical_snapshot_manifest_bytes,
)
from commander_ai.data_pipeline.provenance.canonical_snapshot_contracts import (
    CanonicalSnapshotManifestV1,
    CanonicalTableArtifact,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    VerifiedNormalizedSnapshot,
    read_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.rows import (
    AuditRecord,
    ProvenanceRow,
    ResolutionAttempt,
)
from commander_ai.data_pipeline.provenance.run_manifests import RunManifest, verify_run_manifest
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.serialization import sha256_hex


@dataclass(frozen=True, slots=True)
class VerifiedCanonicalSnapshot:
    """Canonical evidence after all input, run, table, and hash checks."""

    manifest: CanonicalSnapshotManifestV1
    manifest_path: Path
    producing_run: RunManifest
    normalized_snapshot: VerifiedNormalizedSnapshot


_ROW_CONTRACTS: dict[str, type[BaseModel]] = {
    "canonical": CanonicalRecord,
    "audit": AuditRecord,
    "resolution": CardResolution,
    "resolution_attempt": ResolutionAttempt,
    "provenance": ProvenanceRow,
    "quarantine": QuarantineRecord,
}


def read_canonical_snapshot_manifest(
    root: Path | str,
    manifest_path: str,
    *,
    raw_root: Path | str | None = None,
    run_root: Path | str | None = None,
) -> VerifiedCanonicalSnapshot:
    """Read one COMPLETE canonical manifest and verify every bound artifact."""

    artifact_root = Path(root).expanduser().resolve()
    manifest_file = resolve_under_root(artifact_root, manifest_path)
    if not manifest_file.is_file() or manifest_file.is_symlink():
        raise ValueError("canonical manifest file is missing")
    manifest_bytes = manifest_file.read_bytes()
    manifest = validate_canonical_snapshot_manifest_bytes(manifest_bytes)
    if manifest.status != "COMPLETE" or manifest.completed_at is None:
        raise ValueError("canonical manifest is not complete")
    _verify_sidecar(manifest_file, manifest)

    selected_run_root = artifact_root if run_root is None else Path(run_root).expanduser().resolve()
    selected_raw_root = artifact_root if raw_root is None else Path(raw_root).expanduser().resolve()
    producing_run = verify_run_manifest(
        selected_run_root,
        f"runs/{manifest.producing_run_id}/manifest.json",
    )
    if producing_run.run_id != manifest.producing_run_id or producing_run.status != "succeeded":
        raise ValueError("canonical manifest run is not the referenced succeeded run")

    normalized_path = _find_normalized_manifest(
        artifact_root, manifest.input_normalized_snapshot_id
    )
    normalized = read_normalized_snapshot_manifest(
        artifact_root,
        normalized_path,
        raw_root=selected_raw_root,
        run_root=selected_run_root,
    )
    normalized_bytes = (artifact_root / normalized_path).read_bytes()
    if sha256_hex(normalized_bytes) != manifest.input_normalized_manifest_sha256:
        raise ValueError("canonical input normalized manifest hash mismatch")
    if normalized.manifest.source_id != manifest.source_id:
        raise ValueError("canonical source_id does not match normalized input")

    _verify_run_bindings(producing_run, manifest_path, manifest, artifact_root)
    for artifact in manifest.artifacts:
        _verify_table(artifact_root, artifact, normalized.source_snapshot)
    validate_canonical_snapshot_manifest(manifest, producing_run=producing_run)
    return VerifiedCanonicalSnapshot(
        manifest=manifest,
        manifest_path=manifest_file,
        producing_run=producing_run,
        normalized_snapshot=normalized,
    )


def _verify_sidecar(manifest_file: Path, manifest: CanonicalSnapshotManifestV1) -> None:
    sidecar = manifest_file.with_suffix(".sha256")
    if not sidecar.is_file() or sidecar.is_symlink():
        raise ValueError("canonical manifest detached digest is missing")
    expected = f"{canonical_snapshot_manifest_sha256(manifest)}\n".encode("ascii")
    if sidecar.read_bytes() != expected:
        raise ValueError("canonical manifest detached digest mismatch")


def _verify_run_bindings(
    run: RunManifest,
    manifest_path: str,
    manifest: CanonicalSnapshotManifestV1,
    root: Path,
) -> None:
    input_matches = [
        item
        for item in run.inputs
        if item.kind == "normalized_snapshot_manifest"
        and item.id == manifest.input_normalized_snapshot_id
        and item.sha256 == manifest.input_normalized_manifest_sha256
    ]
    if len(input_matches) != 1:
        raise ValueError("canonical run does not bind its normalized input")
    artifact_kinds = {item.artifact_kind for item in manifest.artifacts}
    for kind in artifact_kinds:
        matches = [item for item in run.artifacts if item.kind == kind]
        if len(matches) != 1:
            raise ValueError(f"canonical run must bind exactly one {kind} output")
    manifest_matches = [
        item for item in run.artifacts if item.kind == "canonical_snapshot_manifest"
    ]
    manifest_hash = _sha256_file(resolve_under_root(root, manifest_path))
    if len(manifest_matches) != 1 or manifest_matches[0].sha256 != manifest_hash:
        raise ValueError("canonical run does not bind its manifest")


def _verify_table(
    root: Path,
    artifact: CanonicalTableArtifact,
    source_snapshot: VerifiedSnapshot,
) -> None:
    path = resolve_under_root(root, artifact.path)
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"canonical artifact is missing: {artifact.path}")
    if _sha256_file(path) != artifact.sha256:
        raise ValueError(f"canonical artifact hash mismatch: {artifact.path}")
    if path.stat().st_size != artifact.bytes:
        raise ValueError(f"canonical artifact byte count mismatch: {artifact.path}")
    metadata = pq.read_metadata(path)
    if metadata.num_rows != artifact.rows:
        raise ValueError(f"canonical artifact row count mismatch: {artifact.path}")
    values = metadata.metadata or {}
    if values.get(b"commander_ai.layer") != artifact.layer.encode("utf-8"):
        raise ValueError(f"canonical artifact layer mismatch: {artifact.path}")
    if values.get(b"commander_ai.schema_version") != artifact.schema_version.encode("utf-8"):
        raise ValueError(f"canonical artifact schema version mismatch: {artifact.path}")
    from commander_ai.adapters.storage.parquet_tables import validate_parquet_table_rows

    validate_parquet_table_rows(
        path,
        layer=artifact.layer,
        row_contract=_ROW_CONTRACTS[artifact.artifact_kind],
        verified_snapshot=source_snapshot,
    )


def _find_normalized_manifest(root: Path, snapshot_id: str) -> str:
    normalized_root = root / "normalized"
    matches: list[str] = []
    if normalized_root.is_dir() and not normalized_root.is_symlink():
        for path in normalized_root.rglob("manifest.json"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                payload = path.read_bytes()
            except OSError:
                continue
            if f'"normalized_snapshot_id":"{snapshot_id}"'.encode() in payload:
                from commander_ai.data_pipeline.provenance.normalized_snapshot_manifests import (
                    validate_normalized_snapshot_manifest_bytes,
                )

                try:
                    manifest = validate_normalized_snapshot_manifest_bytes(payload)
                except (TypeError, ValueError):
                    continue
                if manifest.normalized_snapshot_id == snapshot_id:
                    matches.append(path.relative_to(root).as_posix())
    if not matches:
        raise ValueError("canonical input normalized manifest is missing")
    if len(matches) != 1:
        raise ValueError("canonical input normalized manifest ID is ambiguous")
    return matches[0]


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = ["VerifiedCanonicalSnapshot", "read_canonical_snapshot_manifest"]
