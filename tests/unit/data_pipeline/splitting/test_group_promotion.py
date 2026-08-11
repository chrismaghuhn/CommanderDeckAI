from datetime import UTC, datetime

import pytest

from commander_ai.data_pipeline.splitting.group_promotion import (
    TemporalCutoffs,
    TemporalRecord,
    assign_provisional_splits,
    promote_groups_forward,
)


def _record(record_id: str, year: int) -> TemporalRecord:
    return TemporalRecord(record_id, datetime(year, 1, 1, tzinfo=UTC))


def test_assign_provisional_splits_uses_explicit_utc_cutoffs() -> None:
    cutoffs = TemporalCutoffs(
        train_until=datetime(2025, 1, 1, tzinfo=UTC),
        validation_until=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assignments = assign_provisional_splits(
        [_record("test", 2026), _record("train", 2024), _record("validation", 2025)],
        cutoffs,
    )

    assert [(item.record_id, item.provisional_split) for item in assignments] == [
        ("test", "test"),
        ("train", "train"),
        ("validation", "validation"),
    ]


def test_forward_promotion_moves_an_entire_group_to_latest_split() -> None:
    cutoffs = TemporalCutoffs(
        train_until=datetime(2025, 1, 1, tzinfo=UTC),
        validation_until=datetime(2026, 1, 1, tzinfo=UTC),
    )
    provisional = assign_provisional_splits(
        [_record("old-a", 2024), _record("old-b", 2024), _record("future", 2026)],
        cutoffs,
    )

    promoted = promote_groups_forward(
        provisional,
        [("same-deck", ("old-a", "old-b", "future"))],
    )

    assert {item.record_id: item.split for item in promoted} == {
        "old-a": "test",
        "old-b": "test",
        "future": "test",
    }
    assert all(item.provisional_split != "test" or item.split == "test" for item in promoted)


def test_group_promotion_never_moves_a_later_record_backward() -> None:
    cutoffs = TemporalCutoffs(
        train_until=datetime(2025, 1, 1, tzinfo=UTC),
        validation_until=datetime(2026, 1, 1, tzinfo=UTC),
    )
    provisional = assign_provisional_splits(
        [_record("validation", 2025), _record("test", 2026)],
        cutoffs,
    )

    promoted = promote_groups_forward(provisional, [("revision", ("validation", "test"))])

    assert {item.record_id: item.split for item in promoted} == {
        "validation": "test",
        "test": "test",
    }


def test_group_promotion_rejects_unknown_or_duplicate_members() -> None:
    assignments = assign_provisional_splits(
        [_record("known", 2024)],
        TemporalCutoffs(
            train_until=datetime(2025, 1, 1, tzinfo=UTC),
            validation_until=datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )

    with pytest.raises(ValueError, match="unknown records"):
        promote_groups_forward(assignments, [("bad", ("known", "missing"))])
    with pytest.raises(ValueError, match="group members must be unique"):
        promote_groups_forward(assignments, [("bad", ("known", "known"))])
