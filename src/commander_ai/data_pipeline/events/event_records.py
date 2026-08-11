"""Source-neutral event and final-standing inputs."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Literal

from commander_ai.data_pipeline.events.participants import ParticipantInput
from commander_ai.data_pipeline.provenance.evidence import SourceEvidence, source_scoped_id


@dataclass(frozen=True, slots=True)
class EventRecord:
    """One normalized event header before observation mapping."""

    schema_version: ClassVar[Literal["event.v1"]] = "event.v1"
    event_id: str
    evidence: SourceEvidence
    format: str | None = None
    name: str | None = None
    observed_at: datetime | None = None
    source_status: str | None = None

    def __post_init__(self) -> None:
        _require_text(self.event_id, "event_id")
        _validate_datetime(self.observed_at, "observed_at")
        if self.format is not None:
            _require_text(self.format, "format")
        if self.name is not None:
            _require_text(self.name, "name")
        if self.source_status is not None:
            _require_text(self.source_status, "source_status")

    @property
    def canonical_event_id(self) -> str:
        return source_scoped_id("event", self.evidence.source_id, self.event_id)

    def as_dict(self) -> dict[str, object]:
        """Serialize the versioned event row with exact raw evidence."""

        return {
            "schema_version": self.schema_version,
            "event_id": self.canonical_event_id,
            "source_id": self.evidence.source_id,
            "source_snapshot_id": self.evidence.source_snapshot_id,
            "format": self.format,
            "name": self.name,
            "observed_at": None if self.observed_at is None else self.observed_at.isoformat(),
            "source_status": self.source_status,
            "raw_locator": self.evidence.raw_locator.exact_locator,
            "provenance": [item.model_dump(mode="json") for item in self.evidence.provenance],
        }


@dataclass(frozen=True, slots=True)
class EventDeckStandingRecord:
    """One source-neutral final event standing for a canonical deck."""

    observation_id: str
    event_id: str
    canonical_deck_id: str | None
    evidence: SourceEvidence
    observed_at: datetime | None
    aggregate_wins: int | None
    aggregate_losses: int | None
    aggregate_draws: int | None
    source_result_semantics: str | None
    final_placement: int | None = None
    participant: ParticipantInput | None = None

    def __post_init__(self) -> None:
        _require_text(self.observation_id, "observation_id")
        _require_text(self.event_id, "event_id")
        _validate_datetime(self.observed_at, "observed_at")
        if self.final_placement is not None and self.final_placement < 1:
            raise ValueError("final_placement must be positive")
        for field_name, value in (
            ("aggregate_wins", self.aggregate_wins),
            ("aggregate_losses", self.aggregate_losses),
            ("aggregate_draws", self.aggregate_draws),
        ):
            if value is not None and (isinstance(value, bool) or value < 0):
                raise ValueError(f"{field_name} must be a non-negative integer")
        if self.source_result_semantics is not None:
            _require_text(self.source_result_semantics, "source_result_semantics")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _validate_datetime(value: datetime | None, field_name: str) -> None:
    if value is not None and (value.tzinfo is None or value.utcoffset() is None):
        raise ValueError(f"{field_name} must include a timezone")


__all__ = ["EventDeckStandingRecord", "EventRecord"]
