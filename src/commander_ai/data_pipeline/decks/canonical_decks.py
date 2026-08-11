"""Map source-neutral deck structures into canonical structural identity."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime

from commander_ai.domain.decks import (
    CanonicalDeck,
    CardZone,
    CommandZoneEntry,
    CommandZoneRelationship,
)
from commander_ai.domain.provenance import ProvenanceReference

from .fingerprints import (
    STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION,
    structural_fingerprint,
)

_SHA256 = re.compile(r"^[a-f0-9]{64}$")


class DeckCanonicalizationError(ValueError):
    """A source-neutral deck structure cannot become a canonical deck."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class DeckSourceReference:
    """Minimized source identity kept outside canonical deck structure."""

    source_id: str
    source_deck_id: str
    source_snapshot_id: str
    raw_object_id: str
    raw_sha256: str
    observed_at: date | datetime | None = None

    def __post_init__(self) -> None:
        if any(
            not isinstance(value, str) or not value.strip()
            for value in (
                self.source_id,
                self.source_deck_id,
                self.source_snapshot_id,
                self.raw_object_id,
            )
        ):
            raise ValueError("deck source reference identifiers must be non-empty")
        if _SHA256.fullmatch(self.raw_sha256) is None:
            raise ValueError("deck source reference raw_sha256 must be lowercase SHA-256")


@dataclass(frozen=True, slots=True)
class DeckStructureInput:
    """Canonicalization input after source-specific deck parsing and resolution."""

    source: DeckSourceReference
    command_zone: tuple[CommandZoneEntry, ...]
    card_zones: tuple[CardZone, ...]
    provenance: tuple[ProvenanceReference, ...]
    command_zone_relationships: tuple[CommandZoneRelationship, ...] = ()


@dataclass(frozen=True, slots=True)
class CanonicalDeckResult:
    """Canonical deck plus the source observation that produced it."""

    deck: CanonicalDeck
    source: DeckSourceReference


@dataclass(frozen=True, slots=True)
class DeckOccurrence:
    """One source observation of a canonical deck for derived deduplication."""

    deck: CanonicalDeck
    source: DeckSourceReference

    def __post_init__(self) -> None:
        if self.deck.canonical_deck_id != self.deck.structural_fingerprint:
            raise ValueError("deck occurrence must reference deterministic canonical identity")


def canonical_deck_from_input(input_record: DeckStructureInput) -> CanonicalDeckResult:
    """Create structural identity without evaluating legality or source performance."""

    _validate_provenance(input_record)
    if not input_record.command_zone:
        raise DeckCanonicalizationError(
            "quality.command_zone_missing", "canonical decks require a command zone"
        )
    if not input_record.card_zones:
        raise DeckCanonicalizationError(
            "quality.card_zones_missing", "canonical decks require at least one card zone"
        )
    try:
        fingerprint = structural_fingerprint(input_record.command_zone, input_record.card_zones)
        deck = CanonicalDeck(
            canonical_deck_id=fingerprint,
            structural_fingerprint=fingerprint,
            fingerprint_algorithm_version=STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION,
            command_zone=input_record.command_zone,
            command_zone_relationships=input_record.command_zone_relationships,
            card_zones=input_record.card_zones,
            provenance=input_record.provenance,
        )
    except ValueError as error:
        raise DeckCanonicalizationError("quality.invalid_deck_structure", str(error)) from error
    return CanonicalDeckResult(deck=deck, source=input_record.source)


def _validate_provenance(input_record: DeckStructureInput) -> None:
    if not input_record.provenance:
        raise DeckCanonicalizationError(
            "quality.provenance_missing", "canonical decks require source provenance"
        )
    source = input_record.source
    if not any(
        reference.source_id == source.source_id
        and reference.source_snapshot_id == source.source_snapshot_id
        and reference.source_object_id == source.raw_object_id
        and reference.raw_sha256 == source.raw_sha256
        for reference in input_record.provenance
    ):
        raise DeckCanonicalizationError(
            "quality.provenance_mismatch", "deck provenance does not match source reference"
        )


__all__ = [
    "CanonicalDeckResult",
    "DeckCanonicalizationError",
    "DeckOccurrence",
    "DeckSourceReference",
    "DeckStructureInput",
    "canonical_deck_from_input",
]
