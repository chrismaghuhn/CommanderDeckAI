from datetime import UTC, datetime

from commander_ai.data_pipeline.decks.canonical_decks import (
    DeckOccurrence,
    DeckSourceReference,
    DeckStructureInput,
    canonical_deck_from_input,
)
from commander_ai.data_pipeline.deduplication.near_duplicates import NearDuplicatePolicy
from commander_ai.data_pipeline.deduplication.revisions import group_revisions
from commander_ai.data_pipeline.splitting.deck_completion_policy import (
    DeckCompletionPolicy,
    DeckCompletionRecord,
    benchmark_group_id,
    build_deck_completion_splits,
)
from commander_ai.data_pipeline.splitting.group_promotion import TemporalCutoffs
from commander_ai.domain.decks import CardQuantity, CardZone, CommandZoneEntry
from commander_ai.domain.provenance import ProvenanceReference

ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
ORACLE_C = "33333333-3333-4333-8333-333333333333"
ORACLE_D = "44444444-4444-4444-8444-444444444444"
ORACLE_E = "55555555-5555-4555-8555-555555555555"


def _occurrence(
    source_deck_id: str,
    snapshot: str,
    observed_at: datetime,
    cards: tuple[str, ...] = (ORACLE_B, ORACLE_C, ORACLE_D),
    *,
    source_id: str = "fixture",
    raw_object_id: str | None = None,
) -> DeckOccurrence:
    source = DeckSourceReference(
        source_id=source_id,
        source_deck_id=source_deck_id,
        source_snapshot_id=snapshot,
        raw_object_id=raw_object_id or f"{source_deck_id}-{snapshot}.json",
        raw_sha256="0" * 64,
        observed_at=observed_at,
    )
    provenance = (
        ProvenanceReference(
            source_id=source.source_id,
            source_snapshot_id=source.source_snapshot_id,
            source_object_id=source.raw_object_id,
            raw_sha256=source.raw_sha256,
            retrieved_at=observed_at,
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
                    cards=tuple(CardQuantity(oracle_id=card, quantity=1) for card in cards),
                ),
            ),
            provenance=provenance,
        )
    )
    return DeckOccurrence(deck=result.deck, source=source)


def _record(
    record_id: str,
    occurrence: DeckOccurrence,
    *,
    complete: bool = True,
    resolved: bool = True,
    legal_status: str = "legal",
    quality_status: str = "accepted",
) -> DeckCompletionRecord:
    return DeckCompletionRecord(
        record_id=record_id,
        occurrence=occurrence,
        observed_at=occurrence.source.observed_at,
        payload={"record": record_id},
        complete_decklist=complete,
        resolution_complete=resolved,
        legal_status=legal_status,
        quality_status=quality_status,
    )


def _policy(**kwargs: object) -> DeckCompletionPolicy:
    return DeckCompletionPolicy(
        cutoffs=TemporalCutoffs(
            train_until=datetime(2025, 1, 1, tzinfo=UTC),
            validation_until=datetime(2026, 1, 1, tzinfo=UTC),
        ),
        **kwargs,
    )


def test_completion_policy_counts_quality_resolution_and_legality_exclusions() -> None:
    observed = datetime(2024, 1, 1, tzinfo=UTC)
    records = (
        _record("ok", _occurrence("ok", "s1", observed)),
        _record("incomplete", _occurrence("incomplete", "s1", observed), complete=False),
        _record("unresolved", _occurrence("unresolved", "s1", observed), resolved=False),
        _record(
            "illegal",
            _occurrence("illegal", "s1", observed),
            legal_status="unknown",
        ),
        _record(
            "review",
            _occurrence("review", "s1", observed),
            quality_status="review",
        ),
    )

    result = build_deck_completion_splits(
        records,
        _policy(
            require_complete_decklists=True,
            legal_decks_only=True,
            accepted_quality_statuses=("accepted",),
            group_revisions=False,
            group_near_duplicates=False,
        ),
    )

    assert [record.record_id for record in result.eligible_records] == ["ok"]
    assert {(item.record_id, item.code) for item in result.exclusions} == {
        ("incomplete", "quality.decklist_incomplete"),
        ("unresolved", "resolution.card_unresolved"),
        ("illegal", "legality.deck_not_eligible"),
        ("review", "quality.deck_not_eligible"),
    }


def test_revision_group_promotes_all_source_revisions_forward() -> None:
    old = _occurrence("same-source-deck", "old", datetime(2024, 1, 1, tzinfo=UTC))
    new = _occurrence(
        "same-source-deck",
        "new",
        datetime(2026, 1, 1, tzinfo=UTC),
        cards=(ORACLE_B, ORACLE_C, ORACLE_E),
    )

    result = build_deck_completion_splits(
        [_record("old-record", old), _record("new-record", new)],
        _policy(exact_fingerprint=False, group_near_duplicates=False),
    )

    assert len(result.revision_groups) == 1
    assert {item.record_id: item.split for item in result.assignments} == {
        "old-record": "test",
        "new-record": "test",
    }


def test_revision_group_retains_multiple_records_from_one_raw_locator() -> None:
    first = _occurrence(
        "same-source-deck",
        "same-snapshot",
        datetime(2024, 1, 1, tzinfo=UTC),
        raw_object_id="response.json",
    )
    second = _occurrence(
        "same-source-deck",
        "same-snapshot",
        datetime(2024, 1, 1, tzinfo=UTC),
        cards=(ORACLE_B, ORACLE_C, ORACLE_E),
        raw_object_id="response.json",
    )

    result = build_deck_completion_splits(
        [_record("first-record", first), _record("second-record", second)],
        _policy(exact_fingerprint=False, group_near_duplicates=False),
    )

    assert {item.record_id for item in result.assignments} == {"first-record", "second-record"}


def test_revision_group_ties_are_sorted_by_raw_locator() -> None:
    first = _occurrence(
        "same-source-deck",
        "same-snapshot",
        datetime(2024, 1, 1, tzinfo=UTC),
        raw_object_id="b-response.json",
    )
    second = _occurrence(
        "same-source-deck",
        "same-snapshot",
        datetime(2024, 1, 1, tzinfo=UTC),
        cards=(ORACLE_B, ORACLE_C, ORACLE_E),
        raw_object_id="a-response.json",
    )

    groups = group_revisions([first, second])

    assert [item.source.raw_object_id for item in groups[0].occurrences] == [
        "a-response.json",
        "b-response.json",
    ]


def test_near_duplicate_policy_is_versioned_and_groups_distinct_decks() -> None:
    first = _occurrence("first", "s1", datetime(2024, 1, 1, tzinfo=UTC))
    near = _occurrence(
        "near",
        "s1",
        datetime(2026, 1, 1, tzinfo=UTC),
        cards=(ORACLE_B, ORACLE_C, ORACLE_E),
    )

    result = build_deck_completion_splits(
        [_record("first-record", first), _record("near-record", near)],
        _policy(
            exact_fingerprint=False,
            group_revisions=False,
            near_duplicate_policy=NearDuplicatePolicy(
                threshold=0.5,
                version="near-duplicate-test-v1",
            ),
        ),
    )

    assert result.near_duplicate_clusters[0].policy.version == "near-duplicate-test-v1"
    assert {item.split for item in result.assignments} == {"test"}


def test_optional_benchmark_groups_are_independent_of_primary_split() -> None:
    record = _record(
        "benchmark",
        _occurrence("benchmark", "s1", datetime(2024, 1, 1, tzinfo=UTC)),
    )

    assert benchmark_group_id(record, "cold_fingerprint")[0].startswith("fingerprint:")
    assert benchmark_group_id(record, "cold_command_zone")[0].startswith("command-zone-")
    assert benchmark_group_id(record, "cold_commander") == (f"commander:{ORACLE_A}",)
    assert benchmark_group_id(
        record,
        "low_data_commander",
        commander_counts={ORACLE_A: 1},
        low_data_max_records=1,
    ) == (f"low-data-commander:{ORACLE_A}",)
    assert (
        benchmark_group_id(
            record,
            "low_data_commander",
            commander_counts={ORACLE_A: 2},
            low_data_max_records=1,
        )
        == ()
    )
