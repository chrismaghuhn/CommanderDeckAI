"""Structural and resolution-quality evaluation separate from legality."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from typing import Literal

from commander_ai.domain.decks import CanonicalDeck
from commander_ai.domain.evaluations import DeckQualityEvaluation
from commander_ai.domain.provenance import QuarantineReference


def evaluate_deck_quality(
    deck: CanonicalDeck,
    *,
    evaluated_at: datetime | None = None,
    resolution_rate: float | None = None,
    finding_codes: Iterable[str] = (),
    quarantine_references: Iterable[QuarantineReference] = (),
    evaluator_version: str = "deck-quality-v1",
) -> DeckQualityEvaluation:
    """Evaluate completeness without making any legality determination."""

    when = evaluated_at or datetime.now(UTC)
    findings = set(finding_codes)
    if not any(zone.zone == "mainboard" for zone in deck.card_zones):
        findings.add("quality.mainboard_missing")
    if resolution_rate is not None and resolution_rate < 1:
        findings.add("quality.card_resolution_incomplete")
    quarantines = tuple(quarantine_references)
    status: Literal["accepted", "review", "quarantined", "unknown"]
    if quarantines:
        status = "quarantined"
    elif findings:
        status = "review"
    else:
        status = "accepted"
    metrics = {
        "card_resolution_rate": resolution_rate,
        "command_zone_entries": float(len(deck.command_zone)),
        "card_zone_count": float(len(deck.card_zones)),
    }
    return DeckQualityEvaluation(
        canonical_deck_id=deck.canonical_deck_id,
        evaluated_at=when,
        evaluator_version=evaluator_version,
        quality_status=status,
        finding_codes=tuple(sorted(findings)),
        metrics={key: value for key, value in metrics.items() if value is not None},
        quarantine_references=quarantines,
        provenance=deck.provenance,
    )


__all__ = ["evaluate_deck_quality"]
