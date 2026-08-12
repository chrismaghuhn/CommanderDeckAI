"""Nominal evidence issued after complete raw-snapshot verification."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from commander_ai.domain.provenance import (
    RawObjectReference,
    SourceSnapshotManifest,
    detached_manifest_sha256,
)

_VERIFIER_TOKEN = object()


@dataclass(frozen=True, slots=True, init=False)
class VerifiedSourceSnapshot:
    manifest: SourceSnapshotManifest
    snapshot_dir: Path
    object_paths: Mapping[str, Path]
    record_count: int
    manifest_sha256: str
    manifest_path: Path

    @classmethod
    def _issue(
        cls,
        *,
        token: object,
        manifest: SourceSnapshotManifest,
        snapshot_dir: Path,
        object_paths: Mapping[str, Path],
        record_count: int,
        manifest_sha256: str,
        manifest_path: Path,
    ) -> VerifiedSourceSnapshot:
        if token is not _VERIFIER_TOKEN:
            raise TypeError("verified source evidence can only be issued by the verifier")
        evidence = object.__new__(cls)
        object.__setattr__(evidence, "manifest", manifest)
        object.__setattr__(evidence, "snapshot_dir", snapshot_dir)
        object.__setattr__(evidence, "object_paths", MappingProxyType(dict(object_paths)))
        object.__setattr__(evidence, "record_count", record_count)
        object.__setattr__(evidence, "manifest_sha256", manifest_sha256)
        object.__setattr__(evidence, "manifest_path", manifest_path)
        evidence.assert_consistent()
        return evidence

    def assert_consistent(self) -> None:
        if self.record_count < 0:
            raise ValueError("verified record count must be non-negative")
        if self.manifest.status != "COMPLETE" or self.manifest.completed_at is None:
            raise ValueError("verified source manifest is not complete")
        if self.manifest_path != self.snapshot_dir / "manifest.json":
            raise ValueError("verified source manifest path is inconsistent")
        if self.manifest_sha256 != detached_manifest_sha256(self.manifest.model_dump(mode="json")):
            raise ValueError("verified source manifest digest is inconsistent")
        expected_ids = {item.raw_object_id for item in self.manifest.objects}
        if set(self.object_paths) != expected_ids:
            raise ValueError("verified source object index is inconsistent")
        for reference in self.manifest.objects:
            expected_path = self.snapshot_dir.joinpath(*reference.path.split("/"))
            if self.object_paths[reference.raw_object_id] != expected_path:
                raise ValueError("verified source object path is inconsistent")

    @property
    def object_index(self) -> Mapping[str, RawObjectReference]:
        return MappingProxyType({item.raw_object_id: item for item in self.manifest.objects})


__all__ = ["VerifiedSourceSnapshot"]
