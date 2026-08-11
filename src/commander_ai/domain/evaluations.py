"""Independent legality and semantic-quality evaluation values."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator

from .contract_validation import FiniteFloat, validate_namespaced_codes
from .provenance import DomainModel, ProvenanceReference, QuarantineReference


class DeckLegalityEvaluation(DomainModel):
    """Ruleset-scoped legality result for an otherwise stable deck structure."""

    schema_version: Literal["deck-legality-evaluation.v1"] = "deck-legality-evaluation.v1"
    canonical_deck_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    ruleset_version: str = Field(min_length=1)
    ruleset_snapshot_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    evaluated_at: AwareDatetime
    validator_version: str = Field(min_length=1, default="commander-legality-v1")
    legal_status: Literal["legal", "illegal", "unknown", "quarantined"]
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...] = Field(default_factory=tuple)

    @field_validator("finding_codes")
    @classmethod
    def validate_finding_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return validate_namespaced_codes(value, "legality")


class DeckQualityEvaluation(DomainModel):
    """Quality/quarantine result kept separate from legality."""

    schema_version: Literal["deck-quality-evaluation.v1"] = "deck-quality-evaluation.v1"
    canonical_deck_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_at: AwareDatetime
    evaluator_version: str = Field(min_length=1, default="deck-quality-v1")
    quality_status: Literal["accepted", "review", "quarantined", "unknown"]
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    metrics: Mapping[str, FiniteFloat] = Field(default_factory=dict)
    quarantine_references: tuple[QuarantineReference, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...] = Field(default_factory=tuple)

    @field_validator("finding_codes")
    @classmethod
    def validate_finding_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return validate_namespaced_codes(value, "quality")

    @field_validator("quarantine_references")
    @classmethod
    def validate_quarantine_references(
        cls, value: tuple[QuarantineReference, ...]
    ) -> tuple[QuarantineReference, ...]:
        for reference in value:
            validate_namespaced_codes((reference.reason_code,), "quality")
        return value
