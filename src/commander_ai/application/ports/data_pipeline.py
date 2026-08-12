"""Application ports for normalized snapshot operations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class NormalizeResult:
    source_id: str
    source_snapshot_id: str
    normalized_snapshot_id: str
    status: str
    manifest_path: str
    manifest_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_snapshot_id": self.source_snapshot_id,
            "normalized_snapshot_id": self.normalized_snapshot_id,
            "status": self.status,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
        }


@dataclass(frozen=True, slots=True)
class ValidateResult:
    normalized_snapshot_id: str
    status: str
    finding_counts: dict[str, int]
    artifact_paths: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "normalized_snapshot_id": self.normalized_snapshot_id,
            "status": self.status,
            "finding_counts": dict(self.finding_counts),
            "artifact_paths": list(self.artifact_paths),
        }


class NormalizeDataPort(Protocol):
    def normalize_snapshot(self, snapshot_id: str) -> NormalizeResult:
        """Normalize one verified complete source snapshot."""


class ValidateDataPort(Protocol):
    def validate_snapshot(self, normalized_snapshot_id: str) -> ValidateResult:
        """Validate one verified normalized snapshot manifest."""


__all__ = ["NormalizeDataPort", "NormalizeResult", "ValidateDataPort", "ValidateResult"]
