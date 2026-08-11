"""Immutable filesystem publication for run and normalized manifest JSON."""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from commander_ai.data_pipeline.provenance.normalized_snapshot_manifests import (
    NormalizedSnapshotBuild,
    normalized_snapshot_manifest_bytes,
    normalized_snapshot_manifest_sha256,
    normalized_table_artifact_index_bytes,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunManifest,
    configuration_snapshot_bytes,
    run_manifest_bytes,
)
from commander_ai.domain.serialization import sha256_hex

from .path_policy import resolve_under_root, validate_portable_relative_path
from .raw_snapshot_io import fsync_directory, publish_new, write_temp_file


@dataclass(frozen=True, slots=True)
class JsonArtifact:
    path: str
    sha256: str
    bytes: int


class ManifestFileWriter:
    """Publish immutable manifest/config bytes beneath one portable artifact root."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def write_run_manifest(
        self,
        manifest: RunManifest,
        *,
        manifest_path: str,
        configuration_snapshot: object,
    ) -> tuple[JsonArtifact, JsonArtifact]:
        manifest_artifact = self.write_json(manifest_path, run_manifest_bytes(manifest))
        configuration = self.write_json(
            manifest.configuration.path,
            configuration_snapshot_bytes(configuration_snapshot),
        )
        return manifest_artifact, configuration

    def write_normalized_manifest(
        self,
        build: NormalizedSnapshotBuild,
        *,
        manifest_path: str,
    ) -> tuple[JsonArtifact, JsonArtifact]:
        manifest_artifact = self.write_json(
            manifest_path,
            normalized_snapshot_manifest_bytes(build),
        )
        sidecar_path = _sidecar_path(manifest_path)
        sidecar = self.write_json(
            sidecar_path,
            f"{normalized_snapshot_manifest_sha256(build)}\n".encode("ascii"),
        )
        return manifest_artifact, sidecar

    def write_normalized_table_artifact_index(
        self,
        build: NormalizedSnapshotBuild,
        *,
        relative_path: str,
    ) -> JsonArtifact:
        return self.write_json(relative_path, normalized_table_artifact_index_bytes(build))

    def write_json(self, relative_path: str, payload: bytes) -> JsonArtifact:
        portable = validate_portable_relative_path(relative_path)
        final_path = resolve_under_root(self.root, portable)
        if final_path.exists() or final_path.is_symlink():
            raise FileExistsError(portable)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = write_temp_file(final_path.parent, ".artifact-", payload)
        published = False
        try:
            publish_new(temporary, final_path)
            published = True
            fsync_directory(final_path.parent)
        finally:
            if not published:
                with suppress(FileNotFoundError):
                    temporary.unlink()

        return JsonArtifact(
            path=portable,
            sha256=sha256_hex(payload),
            bytes=len(payload),
        )


def _sidecar_path(manifest_path: str) -> str:
    portable = validate_portable_relative_path(manifest_path)
    if not portable.endswith(".json"):
        raise ValueError("manifest path must end with .json")
    return f"{portable[:-5]}.sha256"


__all__ = ["JsonArtifact", "ManifestFileWriter"]
