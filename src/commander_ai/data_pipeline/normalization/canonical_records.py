"""Versioned envelopes for source-neutral canonical records."""

from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from commander_ai.data_pipeline.staging.raw_locators import RawLocator
from commander_ai.domain.cards import CanonicalCard, CardFace, Printing
from commander_ai.domain.combos import Combo, ComboCard
from commander_ai.domain.contract_validation import JSONMapping
from commander_ai.domain.decks import CanonicalDeck
from commander_ai.domain.evaluations import DeckLegalityEvaluation, DeckQualityEvaluation
from commander_ai.domain.observations import EventDeckObservation, ParticipantReference, PodEntry
from commander_ai.domain.provenance import DomainModel, ProvenanceReference
from commander_ai.domain.serialization import canonical_json_bytes

CanonicalRecordType = Literal[
    "card",
    "card_face",
    "printing",
    "canonical_deck",
    "deck_legality_evaluation",
    "deck_quality_evaluation",
    "event_deck_observation",
    "participant_reference",
    "pod_entry",
    "combo",
    "combo_card",
]

_CANONICAL_MODELS: dict[CanonicalRecordType, type[DomainModel]] = {
    "card": CanonicalCard,
    "card_face": CardFace,
    "printing": Printing,
    "canonical_deck": CanonicalDeck,
    "deck_legality_evaluation": DeckLegalityEvaluation,
    "deck_quality_evaluation": DeckQualityEvaluation,
    "event_deck_observation": EventDeckObservation,
    "participant_reference": ParticipantReference,
    "pod_entry": PodEntry,
    "combo": Combo,
    "combo_card": ComboCard,
}


class CanonicalRecord(DomainModel):
    """One canonical entity with exact source evidence and layer identity."""

    schema_version: Literal["canonical-record.v1"] = "canonical-record.v1"
    record_id: str = Field(min_length=1)
    record_type: CanonicalRecordType
    source_record_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    raw_locator: RawLocator
    observed_at: AwareDatetime
    payload: JSONMapping
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)
    layer: Literal["normalized"] = "normalized"

    @model_validator(mode="after")
    def validate_canonical_payload(self) -> CanonicalRecord:
        if self.raw_locator.source_id != self.source_id:
            raise ValueError("canonical source_id must match raw locator")
        if self.raw_locator.source_snapshot_id != self.source_snapshot_id:
            raise ValueError("canonical source_snapshot_id must match raw locator")
        for reference in self.provenance:
            if (
                reference.source_id != self.source_id
                or reference.source_snapshot_id != self.source_snapshot_id
                or reference.source_object_id != self.raw_locator.raw_object_id
            ):
                raise ValueError("canonical provenance does not match raw evidence")
        model = _CANONICAL_MODELS[self.record_type]
        try:
            model.model_validate(self.payload)
        except (TypeError, ValueError) as error:
            raise ValueError("canonical payload does not satisfy its record type") from error
        return self


def canonical_record_from_domain(
    value: DomainModel,
    *,
    source_record_id: str,
    raw_locator: RawLocator,
    provenance: tuple[ProvenanceReference, ...],
    observed_at: datetime,
) -> CanonicalRecord:
    """Wrap one validated domain entity without weakening its contract."""

    record_type = _record_type(value)
    payload = value.model_dump(mode="json")
    record_id = _record_id(
        record_type=record_type,
        source_record_id=source_record_id,
        raw_locator=raw_locator,
        payload=payload,
    )
    return CanonicalRecord(
        record_id=record_id,
        record_type=record_type,
        source_record_id=source_record_id,
        source_id=raw_locator.source_id,
        source_snapshot_id=raw_locator.source_snapshot_id,
        raw_locator=raw_locator,
        observed_at=observed_at,
        payload=payload,
        provenance=provenance,
    )


def _record_type(value: DomainModel) -> CanonicalRecordType:
    for record_type, model in _CANONICAL_MODELS.items():
        if isinstance(value, model):
            return record_type
    raise TypeError(f"unsupported canonical domain model: {type(value).__name__}")


def _record_id(
    *,
    record_type: CanonicalRecordType,
    source_record_id: str,
    raw_locator: RawLocator,
    payload: JSONMapping,
) -> str:
    digest = sha256(
        canonical_json_bytes(
            {
                "record_type": record_type,
                "source_record_id": source_record_id,
                "raw_locator": raw_locator.model_dump(mode="json"),
                "payload": payload,
            }
        )
    ).hexdigest()
    return f"canonical-{record_type}-{digest[:32]}"


__all__ = ["CanonicalRecord", "CanonicalRecordType", "canonical_record_from_domain"]
