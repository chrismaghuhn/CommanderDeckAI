"""Versioned Commander ruleset snapshots used for historical evaluation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Annotated, Literal

from pydantic import Field, model_validator

from .contract_validation import UniqueTuple, URIString, UUIDString
from .provenance import DomainModel, Sha256


class CommandZonePolicy(DomainModel):
    """Structural command-zone bounds plus the authoritative validator version."""

    min_cards: int = Field(ge=1)
    max_cards: int = Field(ge=1)
    validator_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_bounds(self) -> CommandZonePolicy:
        if self.max_cards < self.min_cards:
            raise ValueError("command-zone max_cards cannot be below min_cards")
        return self


class RulesetSnapshot(DomainModel):
    """Immutable effective-dated rules and ban facts."""

    schema_version: Literal["ruleset.v1"] = "ruleset.v1"
    ruleset_version: str = Field(min_length=1)
    format: Literal["commander"] = "commander"
    effective_from: date
    effective_until: date | None = None
    required_total_cards: int = Field(ge=1)
    default_copy_limit: int = Field(ge=1)
    banned_oracle_ids: UniqueTuple[UUIDString] = Field(default_factory=tuple)
    banned_as_companion_oracle_ids: UniqueTuple[UUIDString] = Field(default_factory=tuple)
    copy_limit_overrides: Mapping[UUIDString, Annotated[int, Field(ge=1)]] = Field(
        default_factory=dict
    )
    unlimited_copy_oracle_ids: UniqueTuple[UUIDString] = Field(default_factory=tuple)
    command_zone_policy: CommandZonePolicy
    source_references: UniqueTuple[URIString] = Field(min_length=1)
    sha256: Sha256

    @model_validator(mode="after")
    def validate_effective_range(self) -> RulesetSnapshot:
        if self.effective_until is not None and self.effective_until <= self.effective_from:
            raise ValueError("ruleset effective_until must be after effective_from")
        if set(self.copy_limit_overrides).intersection(self.unlimited_copy_oracle_ids):
            raise ValueError("copy limit overrides cannot also be unlimited")
        return self


__all__ = ["CommandZonePolicy", "RulesetSnapshot"]
