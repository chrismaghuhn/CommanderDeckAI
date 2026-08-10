"""Structural Commander deck values and deterministic identity."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import Field, model_validator

from .provenance import DomainModel, ProvenanceReference


class CardQuantity(DomainModel):
    """A quantity of one oracle identity in a named structural zone."""

    oracle_id: str = Field(min_length=1)
    quantity: int = Field(ge=1)
    printing_id: str | None = Field(default=None, min_length=1)


class CommandZoneEntry(CardQuantity):
    """Command-zone card with preserved source role evidence."""

    source_declared_role: Literal[
        "commander",
        "partner",
        "background",
        "companion",
        "unknown",
    ] | None = None


class CommandZoneRelationship(DomainModel):
    """Source-declared relationship evidence, not an independent legality rule."""

    kind: Literal["partner", "background"]
    card_ids: tuple[str, ...] = Field(min_length=2)


class CardZone(DomainModel):
    """One explicit non-command card zone."""

    zone: str = Field(min_length=1)
    cards: tuple[CardQuantity, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def reject_command_zone(self) -> CardZone:
        if self.zone == "command_zone":
            raise ValueError("command_zone must be represented by CanonicalDeck.command_zone")
        return self


def _field(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _sequence(value: object) -> Sequence[object]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _integer(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value)
    raise TypeError("quantity must be an integer")


def _card_payload(value: object) -> dict[str, object]:
    return {
        "oracle_id": str(_field(value, "oracle_id", "")),
        "quantity": _integer(_field(value, "quantity", 0)),
    }


def _structural_payload(
    command_zone: Sequence[object], card_zones: Sequence[object]
) -> dict[str, object]:
    command_cards = [_card_payload(entry) for entry in command_zone]
    command_cards.sort(key=lambda card: (str(card["oracle_id"]), _integer(card["quantity"])))

    zones: list[dict[str, object]] = []
    for zone in card_zones:
        cards_value = _field(zone, "cards", ())
        cards = [_card_payload(card) for card in _sequence(cards_value)]
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

    canonical = json.dumps(
        _structural_payload(command_zone, card_zones),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class CanonicalDeck(DomainModel):
    """Deck structure whose identity excludes provenance and evaluations."""

    schema_version: Literal["canonical-deck.v1"] = "canonical-deck.v1"
    canonical_deck_id: str
    structural_fingerprint: str
    fingerprint_algorithm_version: str = Field(default="commander-structural-v1", min_length=1)
    format: Literal["commander"] = "commander"
    command_zone: tuple[CommandZoneEntry, ...] = Field(min_length=1)
    command_zone_relationships: tuple[CommandZoneRelationship, ...] = Field(default_factory=tuple)
    card_zones: tuple[CardZone, ...] = Field(min_length=1)
    provenance: tuple[ProvenanceReference, ...]

    @model_validator(mode="before")
    @classmethod
    def populate_structural_identity(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        command_zone = data.get("command_zone", ())
        card_zones = data.get("card_zones", ())
        fingerprint = compute_structural_fingerprint(
            _sequence(command_zone), _sequence(card_zones)
        )
        data.setdefault("canonical_deck_id", fingerprint)
        data.setdefault("structural_fingerprint", fingerprint)
        return data

    @model_validator(mode="after")
    def verify_structural_identity(self) -> CanonicalDeck:
        expected = compute_structural_fingerprint(self.command_zone, self.card_zones)
        if self.canonical_deck_id != expected or self.structural_fingerprint != expected:
            raise ValueError(
                "canonical_deck_id and structural_fingerprint must match deck structure"
            )
        return self
