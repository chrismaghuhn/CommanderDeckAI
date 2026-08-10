"""Independent legality and semantic-quality evaluation values."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import Field

from .provenance import DomainModel, ProvenanceReference, QuarantineReference


class DeckLegalityEvaluation(DomainModel):
    """Ruleset-scoped legality result for an otherwise stable deck structure."""

    schema_version: Literal["deck-legality-evaluation.v1"] = "deck-legality-evaluation.v1"
    canonical_deck_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    ruleset_version: str = Field(min_length=1)
    ruleset_snapshot_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    evaluated_at: datetime
    validator_version: str = Field(min_length=1, default="commander-legality-v1")
    legal_status: Literal["legal", "illegal", "unknown", "quarantined"]
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...] = Field(default_factory=tuple)


class DeckQualityEvaluation(DomainModel):
    """Quality/quarantine result kept separate from legality."""

    schema_version: Literal["deck-quality-evaluation.v1"] = "deck-quality-evaluation.v1"
    canonical_deck_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    evaluated_at: datetime
    evaluator_version: str = Field(min_length=1, default="deck-quality-v1")
    quality_status: Literal["accepted", "review", "quarantined", "unknown"]
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    metrics: Mapping[str, float] = Field(default_factory=dict)
    quarantine_references: tuple[QuarantineReference, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...] = Field(default_factory=tuple)
