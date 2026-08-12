"""Application ports for task-specific dataset artifacts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class DatasetBuildResult:
    dataset_id: str
    dataset_kind: str
    status: str
    manifest_path: str
    manifest_sha256: str
    output_paths: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_kind": self.dataset_kind,
            "status": self.status,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
            "output_paths": list(self.output_paths),
        }


@dataclass(frozen=True, slots=True)
class DatasetInspectionResult:
    dataset_id: str
    dataset_kind: str
    manifest_sha256: str
    counts: dict[str, int]
    output_rows: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "dataset_kind": self.dataset_kind,
            "manifest_sha256": self.manifest_sha256,
            "counts": dict(self.counts),
            "outputs": [{"name": name, "rows": rows} for name, rows in self.output_rows],
        }


class DatasetBuildPort(Protocol):
    def build_dataset(self, config_path: str) -> DatasetBuildResult:
        """Build one task-specific dataset from a strict dataset config."""


class DatasetInspectPort(Protocol):
    def inspect_dataset(self, dataset_id: str) -> DatasetInspectionResult:
        """Verify and summarize one immutable dataset manifest."""


__all__ = [
    "DatasetBuildPort",
    "DatasetBuildResult",
    "DatasetInspectPort",
    "DatasetInspectionResult",
]
