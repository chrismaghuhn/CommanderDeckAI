"""Structural Commander deck values and deterministic identity."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import Field, model_validator

from .contract_validation import UniqueTuple, UUIDString
from .provenance import DomainModel, ProvenanceReference
from .serialization import canonical_json_bytes, sha256_hex

STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION = "commander-structural-v1"


class CardQuantity(DomainModel):
    """A quantity of one oracle identity in a named structural zone."""

    oracle_id: UUIDString
    quantity: int = Field(ge=1)
    printing_id: UUIDString | None = None


class CommandZoneEntry(CardQuantity):
    """Command-zone card with preserved source role evidence."""

    source_declared_role: (
        Literal[
            "commander",
            "partner",
            "background",
            "companion",
            "unknown",
        ]
        | None
    ) = None


class CommandZoneRelationship(DomainModel):
    """Source-declared relationship evidence, not an independent legality rule."""

    kind: Literal["partner", "background"]
    card_ids: UniqueTuple[UUIDString] = Field(min_length=2)


class CardZone(DomainModel):
    """One explicit non-command card zone."""

    zone: str = Field(min_length=1)
    cards: tuple[CardQuantity, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_command_zone(self) -> CardZone:
        if self.zone == "command_zone":
            raise ValueError("command_zone must be represented by CanonicalDeck.command_zone")
        _reject_duplicate_card_identities(self.cards)
        return self


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _reject_duplicate_card_identities(cards: Sequence[object]) -> None:
    oracle_ids = [str(_field(card, "oracle_id", "")).lower() for card in cards]
    if len(oracle_ids) != len(set(oracle_ids)):
        raise ValueError("a card identity may occur only once within a zone")


def _reject_duplicate_zone_names(zones: Sequence[object]) -> None:
    zone_names = [str(_field(zone, "zone", "")) for zone in zones]
    if len(zone_names) != len(set(zone_names)):
        raise ValueError("zone names must be unique within a deck")


def _integer(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError("quantity must be an integer")


def _card_payload(value: object) -> dict[str, object]:
    return {
        "oracle_id": str(_field(value, "oracle_id", "")).lower(),
        "quantity": _integer(_field(value, "quantity", 0)),
    }


def _structural_payload(
    command_zone: Sequence[object], card_zones: Sequence[object]
) -> dict[str, object]:
    _reject_duplicate_card_identities(command_zone)
    _reject_duplicate_zone_names(card_zones)
    command_cards = [_card_payload(entry) for entry in command_zone]
    command_cards.sort(key=lambda card: (str(card["oracle_id"]), _integer(card["quantity"])))

    zones: list[dict[str, object]] = []
    for zone in card_zones:
        cards_value = _field(zone, "cards", ())
        cards_sequence = _sequence(cards_value)
        _reject_duplicate_card_identities(cards_sequence)
        cards = [_card_payload(card) for card in cards_sequence]
        cards.sort(key=lambda card: (str(card["oracle_id"]), _integer(card["quantity"])))
        zones.append({"zone": str(_field(zone, "zone", "")), "cards": cards})
    zones.sort(key=lambda item: str(item["zone"]))
    return {
        "format": "commander",
        "command_zone": command_cards,
        "card_zones": zones,
    }


def compute_structural_fingerprint(
    command_zone: Sequence[object], card_zones: Sequence[object]
) -> str:
    """Return the stable structural fingerprint for a Commander deck."""

    canonical = canonical_json_bytes(_structural_payload(command_zone, card_zones))
    return sha256_hex(canonical)


class CanonicalDeck(DomainModel):
    """Deck structure whose identity excludes provenance and evaluations."""

    schema_version: Literal["canonical-deck.v1"] = "canonical-deck.v1"
    canonical_deck_id: str
    structural_fingerprint: str
    fingerprint_algorithm_version: str = Field(
        default=STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION, min_length=1
    )
    format: Literal["commander"] = "commander"
    command_zone: tuple[CommandZoneEntry, ...] = Field(min_length=1)
    command_zone_relationships: tuple[CommandZoneRelationship, ...] = Field(default_factory=tuple)
    card_zones: tuple[CardZone, ...] = Field(min_length=1)
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def populate_structural_identity(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        command_zone = data.get("command_zone", ())
        card_zones = data.get("card_zones", ())
        fingerprint = compute_structural_fingerprint(_sequence(command_zone), _sequence(card_zones))
        data.setdefault("canonical_deck_id", fingerprint)
        data.setdefault("structural_fingerprint", fingerprint)
        return data

    @model_validator(mode="after")
    def verify_structural_identity(self) -> CanonicalDeck:
        if self.fingerprint_algorithm_version != STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION:
            raise ValueError("unsupported structural fingerprint algorithm version")
        _reject_duplicate_card_identities(self.command_zone)
        _reject_duplicate_zone_names(self.card_zones)
        command_zone_ids = {entry.oracle_id.lower() for entry in self.command_zone}
        if any(
            not {card_id.lower() for card_id in relationship.card_ids}.issubset(command_zone_ids)
            for relationship in self.command_zone_relationships
        ):
            raise ValueError("command-zone relationships must reference command-zone cards")
        expected = compute_structural_fingerprint(self.command_zone, self.card_zones)
        if self.canonical_deck_id != expected or self.structural_fingerprint != expected:
            raise ValueError(
                "canonical_deck_id and structural_fingerprint must match deck structure"
            )
        return self
