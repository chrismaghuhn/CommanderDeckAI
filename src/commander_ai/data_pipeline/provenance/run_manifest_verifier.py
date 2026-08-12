"""Filesystem verification for persisted run-manifest.v1 bindings."""

from __future__ import annotations

import hashlib
from pathlib import Path

from commander_ai.domain.path_policy import validate_portable_relative_path

from .run_manifests import RunManifest, validate_run_manifest_bytes


def verify_run_manifest(
    root: Path | str,
    manifest_path: str,
    *,
    external_input_root: Path | str | None = None,
) -> RunManifest:
    """Read one run manifest and verify every persisted binding it references."""

    root_path = Path(root).expanduser().resolve()
    portable = validate_portable_relative_path(manifest_path)
    path = _resolve_artifact(root_path, portable)
    if not path.is_file() or path.is_symlink():
        raise ValueError("run manifest file is missing")
    manifest = validate_run_manifest_bytes(path.read_bytes())
    _verify_file_binding(root_path, manifest.configuration.path, manifest.configuration.sha256)
    external_root = None if external_input_root is None else Path(external_input_root).resolve()
    for input_reference in manifest.inputs:
        if input_reference.path is not None:
            input_root = (
                external_root
                if input_reference.kind in {"source_snapshot_manifest", "ruleset_snapshot"}
                and external_root is not None
                else root_path
            )
            _verify_file_binding(input_root, input_reference.path, input_reference.sha256)
    for artifact_reference in manifest.artifacts:
        _verify_file_binding(root_path, artifact_reference.path, artifact_reference.sha256)
    return manifest


def _resolve_artifact(root: Path, relative_path: str) -> Path:
    candidate = (root / Path(*relative_path.split("/"))).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("artifact path escapes its configured root") from error
    return candidate


def _verify_file_binding(root: Path, relative_path: str, expected_sha256: str) -> None:
    path = _resolve_artifact(root, validate_portable_relative_path(relative_path))
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"referenced artifact is missing: {relative_path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != expected_sha256:
        raise ValueError(f"referenced artifact hash mismatch: {relative_path}")


__all__ = ["verify_run_manifest"]
