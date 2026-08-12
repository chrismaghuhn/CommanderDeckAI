"""Source-agnostic card identity, face, printing, and resolution values."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from .contract_validation import FiniteFloat, NonEmptyString, UniqueTuple, UUIDString
from .provenance import DomainModel, ProvenanceReference


class CardIdentity(DomainModel):
    """Stable game identity shared by all printings of a card."""

    oracle_id: UUIDString
    name: str = Field(min_length=1)
    normalized_name: str | None = Field(default=None, min_length=1)
    card_snapshot_id: str | None = Field(default=None, min_length=1)


class CanonicalCard(DomainModel):
    """Canonical card concept facts persisted by the frozen ``card.v1`` contract."""

    schema_version: Literal["card.v1"] = "card.v1"
    card_snapshot_id: str = Field(min_length=1)
    oracle_id: UUIDString
    name: str = Field(min_length=1)
    normalized_name: str = Field(min_length=1)
    layout: str = Field(min_length=1)
    mana_value: FiniteFloat = Field(ge=0)
    mana_cost: str | None = None
    colors: UniqueTuple[Literal["W", "U", "B", "R", "G"]] = Field(
        default_factory=tuple, max_length=5
    )
    color_identity: UniqueTuple[Literal["W", "U", "B", "R", "G"]] = Field(
        default_factory=tuple, max_length=5
    )
    supertypes: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    types: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    subtypes: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    keywords: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    oracle_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    legalities: Mapping[str, Literal["legal", "not_legal", "banned", "restricted", "unknown"]]
    copy_limit_policy: Literal["default_singleton", "unlimited", "fixed", "rule_derived"] = (
        "default_singleton"
    )
    fixed_copy_limit: int | None = Field(default=None, ge=1)
    is_basic_land: bool = False
    is_token: bool = False
    is_digital: bool = False
    released_at: date | None = None
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def require_commander_legality(
        self,
    ) -> CanonicalCard:
        if "commander" not in self.legalities:
            raise ValueError("legalities must include commander")
        if any(
            reference.retrieved_at is None
            or reference.adapter_version is None
            or reference.mapper_version is None
            or reference.approval_status is None
            for reference in self.provenance
        ):
            raise ValueError("canonical card provenance must be complete")
        return self


class CardFace(DomainModel):
    """One face identity; it is distinct from both oracle and printing IDs."""

    schema_version: Literal["card-face.v1"] = "card-face.v1"
    face_id: str = Field(min_length=1)
    oracle_id: UUIDString
    face_index: int = Field(ge=0)
    name: str = Field(min_length=1)
    normalized_name: str = Field(min_length=1)
    layout: str = Field(default="normal", min_length=1)
    mana_value: FiniteFloat | None = Field(default=None, ge=0)
    mana_cost: str | None = None
    colors: UniqueTuple[Literal["W", "U", "B", "R", "G"]] = Field(
        default_factory=tuple, max_length=5
    )
    color_identity: UniqueTuple[Literal["W", "U", "B", "R", "G"]] = Field(
        default_factory=tuple, max_length=5
    )
    supertypes: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    types: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    subtypes: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    keywords: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    oracle_text: str | None = None
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)

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
    printing_id: UUIDString
    oracle_id: UUIDString
    card_snapshot_id: str = Field(min_length=1)
    set_code: str = Field(min_length=1)
    collector_number: str = Field(min_length=1)
    released_at: date
    language: str | None = Field(default=None, min_length=1)
    rarity: str | None = Field(default=None, min_length=1)
    is_foil: bool | None = None
    is_promo: bool | None = None
    face_ids: UniqueTuple[NonEmptyString] = Field(min_length=1)
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)


class CardResolutionCandidate(DomainModel):
    """One deterministic candidate returned by a resolution attempt."""

    oracle_id: UUIDString
    printing_id: UUIDString | None = None
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
    candidates: UniqueTuple[CardResolutionCandidate] = Field(default_factory=tuple)
    canonical_oracle_id: UUIDString | None = None
    canonical_printing_id: UUIDString | None = None
    canonical_face_id: str | None = Field(default=None, min_length=1)
    resolver_version: str = Field(min_length=1)
    normalization_policy_version: str = Field(min_length=1)
    alias_catalog_version: str = Field(min_length=1)
    alias_catalog_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    card_catalog_snapshot_id: str = Field(min_length=1)
    finding_code: str | None = Field(default=None, pattern=r"^resolution\.[a-z0-9_]+$")
    provenance: tuple[ProvenanceReference, ...] = Field(default_factory=tuple)
