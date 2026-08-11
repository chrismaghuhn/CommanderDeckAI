from datetime import UTC, datetime

from commander_ai.data_pipeline.splitting.group_promotion import TemporalCutoffs
from commander_ai.data_pipeline.splitting.tournament_policy import (
    TournamentRecord,
    TournamentSplitPolicy,
    build_tournament_splits,
)


def _record(
    record_id: str,
    event_id: str,
    year: int,
    canonical_deck_id: str,
    *,
    complete: bool = True,
) -> TournamentRecord:
    return TournamentRecord(
        record_id=record_id,
        event_id=event_id,
        observed_at=datetime(year, 1, 1, tzinfo=UTC),
        canonical_deck_id=canonical_deck_id,
        payload={"event": event_id},
        complete_event=complete,
    )


def _policy() -> TournamentSplitPolicy:
    return TournamentSplitPolicy(
        cutoffs=TemporalCutoffs(
            train_until=datetime(2025, 1, 1, tzinfo=UTC),
            validation_until=datetime(2026, 1, 1, tzinfo=UTC),
        )
    )


def test_tournament_splits_group_complete_events_without_grouping_decks() -> None:
    records = (
        _record("train-entry", "event-train", 2024, "deck-a"),
        _record("later-a", "event-later", 2026, "deck-a"),
        _record("later-b", "event-later", 2026, "deck-b"),
    )

    result = build_tournament_splits(records, _policy())

    assert {item.record_id: item.split for item in result.assignments} == {
        "train-entry": "train",
        "later-a": "test",
        "later-b": "test",
    }
    assert dict(result.familiar_strata) == {
        "train-entry": "familiar",
        "later-a": "familiar",
        "later-b": "unseen",
    }


def test_event_group_promotion_is_forward_only_and_incomplete_events_are_excluded() -> None:
    records = (
        _record("early-entry", "same-event", 2024, "deck-a"),
        _record("late-entry", "same-event", 2026, "deck-b"),
        _record("incomplete", "broken-event", 2024, "deck-c", complete=False),
    )

    result = build_tournament_splits(records, _policy())

    assert {item.record_id: item.split for item in result.assignments} == {
        "early-entry": "test",
        "late-entry": "test",
    }
    assert [(item.record_id, item.code) for item in result.exclusions] == [
        ("incomplete", "quality.event_incomplete")
    ]


def test_one_incomplete_entry_excludes_the_entire_event() -> None:
    records = (
        _record("complete-entry", "partially-known", 2024, "deck-a"),
        _record("incomplete-entry", "partially-known", 2024, "deck-b", complete=False),
    )

    result = build_tournament_splits(records, _policy())

    assert result.assignments == ()
    assert {(item.record_id, item.code) for item in result.exclusions} == {
        ("complete-entry", "quality.event_incomplete"),
        ("incomplete-entry", "quality.event_incomplete"),
    }
