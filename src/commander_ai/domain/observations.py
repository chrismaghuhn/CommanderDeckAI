"""Event standings, participant references, and round/seat pod values."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .provenance import DomainModel, ProvenanceReference


class ParticipantReference(DomainModel):
    """Scoped opaque participant reference with no retained raw name."""

    schema_version: Literal["participant-reference.v1"] = "participant-reference.v1"
    reference_id: str = Field(min_length=1)
    scope: Literal["source", "event", "snapshot_object"]
    source_id: str | None = Field(default=None, min_length=1)
    event_id: str | None = Field(default=None, min_length=1)
    source_snapshot_id: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_scope_fields(self) -> ParticipantReference:
        if self.scope == "source":
            if self.source_id is None:
                raise ValueError("source scope requires source_id")
            if self.event_id is not None or self.source_snapshot_id is not None:
                raise ValueError("source scope cannot carry event or snapshot fields")
        elif self.scope == "event":
            if self.event_id is None:
                raise ValueError("event scope requires event_id")
            if self.source_id is not None or self.source_snapshot_id is not None:
                raise ValueError("event scope cannot carry source or snapshot fields")
        elif self.source_snapshot_id is None:
            raise ValueError("snapshot_object scope requires source_snapshot_id")
        elif self.event_id is not None:
            raise ValueError("snapshot_object scope cannot carry event_id")
        return self


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

    @model_validator(mode="after")
    def validate_participant_scope(self) -> EventDeckObservation:
        if self.participant_reference is None:
            if self.participant_reference_scope != "none":
                raise ValueError("participant_reference_scope must be none without a reference")
        elif self.participant_reference.scope != self.participant_reference_scope:
            raise ValueError("participant reference scope must match its parent field")
        elif (
            self.participant_reference.scope == "event"
            and self.participant_reference.event_id != self.event_id
        ):
            raise ValueError("event participant reference must match event_id")
        return self


class PodEntry(DomainModel):
    """One round/seat record, never an implicit 1v1 outcome."""

    schema_version: Literal["pod.v1"] = "pod.v1"
    pod_id: str = Field(min_length=1)
    event_id: str = Field(min_length=1)
    round_number: int = Field(ge=1)
    seat: int = Field(ge=1)
    canonical_deck_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    result: Literal["win", "loss", "draw", "bye", "unknown"]
    points: float | None = None
    placement: int | None = Field(default=None, ge=1)
    participant_reference: ParticipantReference | None = None
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_participant_scope(self) -> PodEntry:
        if (
            self.participant_reference is not None
            and self.participant_reference.scope == "event"
            and self.participant_reference.event_id != self.event_id
        ):
            raise ValueError("event participant reference must match event_id")
        return self
