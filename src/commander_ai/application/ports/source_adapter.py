"""Application ports for source discovery, review, and sync."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class SourceSummary:
    source_id: str
    approval_status: str
    current_use_status: str | None
    local_sync_allowed: bool
    public_export_allowed: bool
    research_only: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "approval_status": self.approval_status,
            "current_use_status": self.current_use_status,
            "local_sync_allowed": self.local_sync_allowed,
            "public_export_allowed": self.public_export_allowed,
            "research_only": self.research_only,
        }


@dataclass(frozen=True, slots=True)
class SourceReview:
    source_id: str
    approval_status: str
    review_path: str
    review_exists: bool
    research_only: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "approval_status": self.approval_status,
            "review_path": self.review_path,
            "review_exists": self.review_exists,
            "research_only": self.research_only,
        }


@dataclass(frozen=True, slots=True)
class SourceSyncResult:
    source_id: str
    snapshot_id: str
    status: str
    manifest_path: str
    manifest_sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "manifest_path": self.manifest_path,
            "manifest_sha256": self.manifest_sha256,
        }


class SourceCatalogPort(Protocol):
    def list_sources(self) -> Sequence[SourceSummary]:
        """Return source summaries in deterministic order."""

    def review_source(self, source_id: str) -> SourceReview:
        """Return source-review metadata without acquiring source data."""


class SourceSyncPort(Protocol):
    def sync_source(self, source_id: str, config_path: str) -> SourceSyncResult:
        """Acquire one source through its explicit adapter and policy gate."""


__all__ = [
    "SourceCatalogPort",
    "SourceReview",
    "SourceSummary",
    "SourceSyncPort",
    "SourceSyncResult",
]
