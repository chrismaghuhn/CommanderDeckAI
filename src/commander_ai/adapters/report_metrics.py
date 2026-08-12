"""Canonical-row metrics for source-quality and dataset audit reports."""

from __future__ import annotations

from collections import Counter

from commander_ai.data_pipeline.events.pod_entries import index_complete_pods
from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.data_pipeline.normalization.evaluation_records import index_deck_evaluations
from commander_ai.data_pipeline.reports.source_metrics import DeckMetricRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.decks import CanonicalDeck
from commander_ai.domain.observations import EventDeckObservation, PodEntry


def canonical_metrics(
    canonical_rows: list[dict[str, object]],
    resolution_rows: list[dict[str, object]],
    *,
    source_id: str,
) -> tuple[
    tuple[DeckMetricRecord, ...],
    tuple[int, int, int, int],
    tuple[int, int],
    tuple[int, int],
]:
    """Calculate deterministic deck, event, and complete-pod measurements."""

    records = tuple(CanonicalRecord.model_validate(row) for row in canonical_rows)
    evaluations = index_deck_evaluations(records)
    pod_index = index_complete_pods(records)
    full_pod_decks = {deck_id for _, deck_id in pod_index.complete_event_deck_keys}
    outcome_decks: set[str] = set()
    event_ids: set[str] = set()
    observation_count = 0
    pod_ids: set[str] = set()
    for record in records:
        if record.record_type == "event_deck_observation":
            observation = EventDeckObservation.model_validate(record.payload)
            outcome_decks.add(observation.canonical_deck_id)
            event_ids.add(observation.event_id)
            observation_count += 1
        elif record.record_type == "pod_entry":
            pod_ids.add(PodEntry.model_validate(record.payload).pod_id)

    decks: list[DeckMetricRecord] = []
    for record in records:
        if record.record_type != "canonical_deck":
            continue
        deck = CanonicalDeck.model_validate(record.payload)
        evaluation_key = (record.source_record_id, deck.canonical_deck_id)
        legality = evaluations.legality.get(evaluation_key)
        quality = evaluations.quality.get(evaluation_key)
        card_ids = [entry.oracle_id for entry in deck.command_zone]
        card_ids.extend(card.oracle_id for zone in deck.card_zones for card in zone.cards)
        decks.append(
            DeckMetricRecord(
                deck_id=record.source_record_id,
                source_id=source_id,
                canonical_deck_id=deck.canonical_deck_id,
                commander_ids=tuple(entry.oracle_id for entry in deck.command_zone),
                card_ids=tuple(card_ids),
                observed_at=record.observed_at,
                complete_decklist=True,
                resolution_complete=quality is not None
                and "quality.card_resolution_incomplete" not in quality.finding_codes,
                legal_status="unknown" if legality is None else legality.legal_status,
                quality_status="unknown" if quality is None else quality.quality_status,
                usable_outcome=deck.canonical_deck_id in outcome_decks,
                full_pod=deck.canonical_deck_id in full_pod_decks,
            )
        )

    resolution_counts = Counter(
        CardResolution.model_validate(row).status for row in resolution_rows
    )
    total = sum(resolution_counts.values())
    return (
        tuple(sorted(decks, key=lambda item: item.deck_id)),
        (
            total,
            resolution_counts.get("resolved", 0),
            resolution_counts.get("ambiguous", 0),
            resolution_counts.get("unresolved", 0) + resolution_counts.get("rejected", 0),
        ),
        (len(event_ids), observation_count),
        (len(pod_ids), len(pod_index.complete_pod_ids)),
    )


__all__ = ["canonical_metrics"]
