"""Small immutable input values shared by dataset builder components."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from commander_ai.config.source_settings import normalize_source_id


@dataclass(frozen=True, slots=True)
class DatasetProjectionRecord:
    """Generic time-indexed record for combo and event projections."""

    record_id: str
    observed_at: datetime
    payload: Mapping[str, object]
    source_id: str | None = None
    source_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id must be non-empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        if (self.source_id is None) != (self.source_snapshot_id is None):
            raise ValueError("source_id and source_snapshot_id must be supplied together")
        if self.source_id is not None:
            object.__setattr__(self, "source_id", normalize_source_id(self.source_id))
            if not self.source_snapshot_id or not self.source_snapshot_id.strip():
                raise ValueError("source_snapshot_id must be non-empty")


__all__ = ["DatasetProjectionRecord"]
