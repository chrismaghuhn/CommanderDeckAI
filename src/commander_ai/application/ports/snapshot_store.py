"""Application port for raw snapshot integrity inspection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SnapshotInspectionResult:
    source_id: str
    snapshot_id: str
    status: str | None
    consumable: bool
    issue_codes: tuple[str, ...]
    manifest_sha256: str | None
    record_count: int

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "consumable": self.consumable,
            "issue_codes": list(self.issue_codes),
            "manifest_sha256": self.manifest_sha256,
            "record_count": self.record_count,
        }


class SnapshotStorePort(Protocol):
    def inspect_snapshot(self, source_id: str, snapshot_id: str) -> SnapshotInspectionResult:
        """Inspect a raw snapshot without parsing or mutating it."""


__all__ = ["SnapshotInspectionResult", "SnapshotStorePort"]
