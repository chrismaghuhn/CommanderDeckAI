"""Source-agnostic card identity, face, printing, and resolution values."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .provenance import DomainModel, ProvenanceReference


class CardIdentity(DomainModel):
    """Stable game identity shared by all printings of a card."""

    oracle_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    normalized_name: str | None = Field(default=None, min_length=1)
    card_snapshot_id: str | None = Field(default=None, min_length=1)


class CardFace(DomainModel):
    """One face identity; it is distinct from both oracle and printing IDs."""

    schema_version: Literal["card-face.v1"] = "card-face.v1"
    face_id: str = Field(min_length=1)
    oracle_id: str = Field(min_length=1)
    face_index: int = Field(ge=0)
    name: str = Field(min_length=1)
    normalized_name: str = Field(min_length=1)
    layout: str = Field(default="normal", min_length=1)
    mana_value: float | None = Field(default=None, ge=0)
    mana_cost: str | None = None
    colors: tuple[Literal["W", "U", "B", "R", "G"], ...] = Field(default_factory=tuple)
    color_identity: tuple[Literal["W", "U", "B", "R", "G"], ...] = Field(default_factory=tuple)
    supertypes: tuple[str, ...] = Field(default_factory=tuple)
    types: tuple[str, ...] = Field(default_factory=tuple)
    subtypes: tuple[str, ...] = Field(default_factory=tuple)
    keywords: tuple[str, ...] = Field(default_factory=tuple)
    oracle_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    provenance: tuple[ProvenanceReference, ...] = Field(default_factory=tuple)

    @model_validator(mode="before")
    @classmethod
    def default_normalized_name(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        data = dict(value)
        if "normalized_name" not in data and isinstance(data.get("name"), str):
            data["normalized_name"] = data["name"].casefold()
        return data


class Printing(DomainModel):
    """A collectible release attached to one oracle identity."""

    schema_version: Literal["printing.v1"] = "printing.v1"
    printing_id: str = Field(min_length=1)
    oracle_id: str = Field(min_length=1)
    card_snapshot_id: str = Field(min_length=1)
    set_code: str = Field(min_length=1)
    collector_number: str = Field(min_length=1)
    released_at: date
    language: str | None = Field(default=None, min_length=1)
    rarity: str | None = Field(default=None, min_length=1)
    is_foil: bool | None = None
    is_promo: bool | None = None
    face_ids: tuple[str, ...]
    provenance: tuple[ProvenanceReference, ...] = Field(default_factory=tuple)


class CardResolutionCandidate(DomainModel):
    """One deterministic candidate returned by a resolution attempt."""

    oracle_id: str = Field(min_length=1)
    printing_id: str | None = Field(default=None, min_length=1)
    face_id: str | None = Field(default=None, min_length=1)


class CardResolution(DomainModel):
    """Auditable resolution attempt without fuzzy or source-specific behavior."""

    schema_version: Literal["card-resolution.v1"] = "card-resolution.v1"
    resolution_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    source_object_id: str = Field(min_length=1)
    original_value: str = Field(min_length=1)
    raw_locator: str = Field(min_length=1)
    method: Literal[
        "source_identifier",
        "exact_identifier",
        "exact_name",
        "alias",
        "split_face",
        "none",
    ]
    status: Literal["resolved", "ambiguous", "unresolved", "rejected"]
    candidates: tuple[CardResolutionCandidate, ...] = Field(default_factory=tuple)
    canonical_oracle_id: str | None = Field(default=None, min_length=1)
    canonical_printing_id: str | None = Field(default=None, min_length=1)
    canonical_face_id: str | None = Field(default=None, min_length=1)
    resolver_version: str = Field(min_length=1)
    normalization_policy_version: str = Field(min_length=1)
    alias_catalog_version: str = Field(min_length=1)
    alias_catalog_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    card_catalog_snapshot_id: str = Field(min_length=1)
    finding_code: str | None = Field(default=None, pattern=r"^resolution\.[a-z0-9_]+$")
    provenance: tuple[ProvenanceReference, ...] = Field(default_factory=tuple)
