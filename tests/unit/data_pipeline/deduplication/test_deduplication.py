from __future__ import annotations

from datetime import UTC, datetime

from commander_ai.data_pipeline.decks.canonical_decks import (
    DeckOccurrence,
    DeckSourceReference,
    DeckStructureInput,
    canonical_deck_from_input,
)
from commander_ai.data_pipeline.deduplication.exact import report_exact_duplicates
from commander_ai.data_pipeline.deduplication.near_duplicates import (
    NearDuplicatePolicy,
    cluster_near_duplicates,
)
from commander_ai.data_pipeline.deduplication.revisions import group_revisions
from commander_ai.data_pipeline.quality.dedup_reports import build_deduplication_report
from commander_ai.domain.decks import CardQuantity, CardZone, CommandZoneEntry
from commander_ai.domain.provenance import ProvenanceReference

ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
ORACLE_C = "33333333-3333-4333-8333-333333333333"
ORACLE_D = "44444444-4444-4444-8444-444444444444"
ORACLE_E = "55555555-5555-4555-8555-555555555555"


def _occurrence(
    source_id: str,
    source_deck_id: str,
    *,
    snapshot: str = "snapshot-1",
    cards: tuple[str, ...] = (ORACLE_B, ORACLE_C, ORACLE_D),
) -> DeckOccurrence:
    source = DeckSourceReference(
        source_id=source_id,
        source_deck_id=source_deck_id,
        source_snapshot_id=snapshot,
        raw_object_id=f"{source_deck_id}-{snapshot}.json",
        raw_sha256="0" * 64,
        observed_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    provenance = (
        ProvenanceReference(
            source_id=source.source_id,
            source_snapshot_id=source.source_snapshot_id,
            source_object_id=source.raw_object_id,
            raw_sha256=source.raw_sha256,
            retrieved_at=datetime(2026, 8, 11, tzinfo=UTC),
            adapter_version="fixture-adapter-v1",
            mapper_version="fixture-deck-mapper-v1",
            approval_status="APPROVED_LOCAL",
        ),
    )
    result = canonical_deck_from_input(
        DeckStructureInput(
            source=source,
            command_zone=(CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),),
            card_zones=(
                CardZone(
                    zone="mainboard",
                    cards=tuple(
                        CardQuantity(oracle_id=oracle_id, quantity=1) for oracle_id in cards
                    ),
                ),
            ),
            provenance=provenance,
        )
    )
    return DeckOccurrence(deck=result.deck, source=source)


def test_exact_duplicates_report_cross_source_overlap_without_deleting_occurrences() -> None:
    occurrences = (
        _occurrence("source-a", "deck-a"),
        _occurrence("source-b", "deck-b"),
        _occurrence("source-a", "deck-c", cards=(ORACLE_B, ORACLE_C, ORACLE_E)),
    )
    report = report_exact_duplicates(occurrences)
    assert len(report.groups) == 1
    assert report.groups[0].source_ids == ("source-a", "source-b")
    assert report.duplicate_occurrences == 2
    assert len(occurrences) == 3


def test_revision_groups_are_source_scoped_and_deterministic() -> None:
    first = _occurrence("source-a", "deck-a", snapshot="snapshot-1")
    second = _occurrence(
        "source-a", "deck-a", snapshot="snapshot-2", cards=(ORACLE_B, ORACLE_C, ORACLE_E)
    )
    cross_source = _occurrence("source-b", "deck-a", snapshot="snapshot-2")
    groups = group_revisions((second, cross_source, first))
    assert len(groups) == 1
    assert groups[0].source_id == "source-a"
    assert len(groups[0].occurrences) == 2
    assert groups[0].revision_group_id == group_revisions((first, second))[0].revision_group_id


def test_near_duplicate_algorithm_and_threshold_are_bound_to_derived_cluster() -> None:
    base = _occurrence("source-a", "base")
    near = _occurrence("source-a", "near", cards=(ORACLE_B, ORACLE_C, ORACLE_E))
    policy = NearDuplicatePolicy(threshold=0.55)
    clusters = cluster_near_duplicates((near, base), policy=policy)
    assert len(clusters) == 1
    assert clusters[0].policy.version == "near-duplicate-v1"
    assert clusters[0].policy.threshold == 0.55
    assert base.deck.canonical_deck_id in clusters[0].canonical_deck_ids
    assert near.deck.canonical_deck_id in clusters[0].canonical_deck_ids


def test_dedup_report_is_machine_readable_and_versioned() -> None:
    occurrences = (_occurrence("source-a", "deck-a"), _occurrence("source-b", "deck-b"))
    near_occurrence = _occurrence("source-c", "deck-c", cards=(ORACLE_B, ORACLE_C, ORACLE_E))
    exact = report_exact_duplicates(occurrences)
    revisions = group_revisions(occurrences)
    near = cluster_near_duplicates(
        (*occurrences, near_occurrence), policy=NearDuplicatePolicy(threshold=0.55)
    )
    report = build_deduplication_report(
        exact,
        revisions,
        near,
        near_duplicate_policy=NearDuplicatePolicy(threshold=0.55),
    )
    assert report.as_dict() == {
        "exact_duplicate_groups": 1,
        "exact_duplicate_occurrences": 2,
        "cross_source_exact_groups": 1,
        "revision_groups": 0,
        "near_duplicate_clusters": 1,
        "near_duplicate_algorithm": "quantity_weighted_jaccard",
        "near_duplicate_version": "near-duplicate-v1",
        "near_duplicate_threshold": 0.55,
        "near_duplicate_algorithm_versions": ["quantity_weighted_jaccard:near-duplicate-v1:0.55"],
    }


def test_empty_near_duplicate_report_retains_policy() -> None:
    policy = NearDuplicatePolicy(threshold=0.77)
    report = build_deduplication_report(
        report_exact_duplicates(()),
        (),
        (),
        near_duplicate_policy=policy,
    )
    assert report.as_dict()["near_duplicate_threshold"] == 0.77
