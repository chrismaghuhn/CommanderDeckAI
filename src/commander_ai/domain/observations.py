"""Event standings, participant references, and round/seat pod values."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from .provenance import DomainModel, ProvenanceReference


class ParticipantReference(DomainModel):
    """Scoped opaque participant reference with no retained raw name."""

    schema_version: Literal["participant-reference.v1"] = "participant-reference.v1"
    reference_id: str = Field(min_length=1)
    scope: Literal["source", "event", "snapshot_object"]
    source_id: str | None = Field(default=None, min_length=1)
    event_id: str | None = Field(default=None, min_length=1)
    source_snapshot_id: str | None = Field(default=None, min_length=1)


class EventDeckObservation(DomainModel):
    """One event-level observation; the same deck may recur across events."""

    schema_version: Literal["event-deck-observation.v1"] = "event-deck-observation.v1"
    observation_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    canonical_deck_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    observed_at: datetime
    participant_reference: ParticipantReference | None = None
    participant_reference_scope: Literal["source", "event", "snapshot_object", "none"]
    final_placement: int | None = Field(default=None, ge=1)
    aggregate_wins: int = Field(ge=0)
    aggregate_losses: int = Field(ge=0)
    aggregate_draws: int = Field(ge=0)
    source_result_semantics: str = Field(min_length=1)
    provenance: tuple[ProvenanceReference, ...]


class PodEntry(DomainModel):
    """One round/seat record, never an implicit 1v1 outcome."""

    pod_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    round_number: int = Field(ge=1)
    seat: int = Field(ge=1)
    canonical_deck_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    result: Literal["win", "loss", "draw", "bye", "unknown"]
    points: float | None = None
    placement: int | None = Field(default=None, ge=1)
    participant_reference: ParticipantReference | None = None
