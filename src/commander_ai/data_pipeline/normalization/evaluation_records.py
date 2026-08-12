"""Build and index canonical deck evaluation records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from commander_ai.data_pipeline.decks.quality import evaluate_deck_quality
from commander_ai.data_pipeline.decks.ruleset_evaluation import evaluate_deck_legality
from commander_ai.data_pipeline.decks.ruleset_inputs import RulesetSnapshotInput
from commander_ai.data_pipeline.decks.ruleset_selection import select_applicable_ruleset
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CanonicalCard, CardResolution
from commander_ai.domain.decks import CanonicalDeck
from commander_ai.domain.evaluations import DeckLegalityEvaluation, DeckQualityEvaluation
from commander_ai.domain.provenance import SourceSnapshotManifest

from .canonical_records import CanonicalRecord, canonical_record_from_domain
from .canonicalization_support import observed_at, provenance_for


@dataclass(frozen=True, slots=True)
class DeckEvaluationIndex:
    """Evaluation records keyed by their source deck observation and structure."""

    legality: Mapping[tuple[str, str], DeckLegalityEvaluation]
    quality: Mapping[tuple[str, str], DeckQualityEvaluation]
    legality_record_ids: Mapping[tuple[str, str], str]
    quality_record_ids: Mapping[tuple[str, str], str]


def build_deck_evaluation_records(
    deck: CanonicalDeck,
    *,
    source_record: StagingRecord,
    source_deck_id: str,
    source_manifest: SourceSnapshotManifest,
    card_facts: Mapping[str, CanonicalCard],
    resolutions: Sequence[CardResolution],
    ruleset_inputs: Sequence[RulesetSnapshotInput] = (),
) -> tuple[tuple[CanonicalRecord, ...], tuple[str, ...]]:
    """Evaluate one canonical deck using only supplied facts and provenance."""

    evaluation_at = observed_at(source_record, source_manifest)
    resolution_rate = (
        sum(resolution.status == "resolved" for resolution in resolutions) / len(resolutions)
        if resolutions
        else None
    )
    ruleset_selection = select_applicable_ruleset(
        (item.snapshot for item in ruleset_inputs),
        _ruleset_context_at(source_record, evaluation_at),
    )
    legality = evaluate_deck_legality(
        deck,
        card_facts,
        ruleset_selection,
        evaluated_at=evaluation_at,
    )
    quality = evaluate_deck_quality(
        deck,
        evaluated_at=evaluation_at,
        resolution_rate=resolution_rate,
    )
    provenance = provenance_for(source_record, source_manifest, "mtgjson-deck-mapper-v1")
    return (
        (
            canonical_record_from_domain(
                legality,
                source_record_id=source_deck_id,
                raw_locator=source_record.raw_locator,
                provenance=provenance,
                observed_at=evaluation_at,
            ),
            canonical_record_from_domain(
                quality,
                source_record_id=source_deck_id,
                raw_locator=source_record.raw_locator,
                provenance=provenance,
                observed_at=evaluation_at,
            ),
        ),
        tuple(sorted({*legality.finding_codes, *quality.finding_codes})),
    )


def index_deck_evaluations(records: Sequence[CanonicalRecord]) -> DeckEvaluationIndex:
    """Index persisted evaluations without treating missing records as accepted."""

    legality: dict[tuple[str, str], DeckLegalityEvaluation] = {}
    quality: dict[tuple[str, str], DeckQualityEvaluation] = {}
    legality_record_ids: dict[tuple[str, str], str] = {}
    quality_record_ids: dict[tuple[str, str], str] = {}
    for record in records:
        if record.record_type == "deck_legality_evaluation":
            legality_evaluation = DeckLegalityEvaluation.model_validate(record.payload)
            legality[(record.source_record_id, legality_evaluation.canonical_deck_id)] = (
                legality_evaluation
            )
            legality_record_ids[
                (record.source_record_id, legality_evaluation.canonical_deck_id)
            ] = record.record_id
        elif record.record_type == "deck_quality_evaluation":
            quality_evaluation = DeckQualityEvaluation.model_validate(record.payload)
            quality[(record.source_record_id, quality_evaluation.canonical_deck_id)] = (
                quality_evaluation
            )
            quality_record_ids[(record.source_record_id, quality_evaluation.canonical_deck_id)] = (
                record.record_id
            )
    return DeckEvaluationIndex(
        legality=legality,
        quality=quality,
        legality_record_ids=legality_record_ids,
        quality_record_ids=quality_record_ids,
    )


def _ruleset_context_at(record: StagingRecord, observed: datetime) -> date | datetime:
    """Use a source-declared historical deck date when it is available."""

    values = record.original_source_values
    if record.source_id == "mtgjson" and isinstance(values, Mapping):
        for key in ("releaseDate", "release_date"):
            value = values.get(key)
            if isinstance(value, date) and not isinstance(value, datetime):
                return value
            if isinstance(value, str) and value.strip():
                try:
                    return date.fromisoformat(value.strip())
                except ValueError:
                    break
    return observed


__all__ = ["DeckEvaluationIndex", "build_deck_evaluation_records", "index_deck_evaluations"]
