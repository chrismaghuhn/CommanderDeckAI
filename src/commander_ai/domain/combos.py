"""Source-neutral combo facts kept separate from legality evaluations."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from .contract_validation import NonEmptyString, UniqueTuple, UUIDString
from .provenance import DomainModel, ProvenanceReference


class ComboCard(DomainModel):
    """Role and quantity of one card in a combo fact."""

    schema_version: Literal["combo-card.v1"] = "combo-card.v1"
    combo_id: str = Field(min_length=1)
    oracle_id: UUIDString
    role: Literal["required", "optional", "commander", "enabler", "result"]
    quantity: int = Field(ge=1)
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)


class Combo(DomainModel):
    """Requirements and results are feature facts, never legality authority."""

    schema_version: Literal["combo.v1"] = "combo.v1"
    combo_id: str = Field(min_length=1)
    name: str | None = Field(default=None, min_length=1)
    required_cards: UniqueTuple[UUIDString] = Field(min_length=1)
    optional_cards: UniqueTuple[UUIDString] = Field(default_factory=tuple)
    requirements: UniqueTuple[NonEmptyString]
    results: UniqueTuple[NonEmptyString] = Field(min_length=1)
    steps: tuple[NonEmptyString, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)
