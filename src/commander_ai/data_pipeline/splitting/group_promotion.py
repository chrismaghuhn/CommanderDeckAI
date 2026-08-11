"""Deterministic temporal assignment and conservative forward group promotion."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

SplitName = Literal["train", "validation", "test"]
_SPLIT_ORDER: dict[SplitName, int] = {"train": 0, "validation": 1, "test": 2}


@dataclass(frozen=True, slots=True)
class TemporalCutoffs:
    """Inclusive-exclusive boundaries for the three chronological segments."""

    train_until: datetime
    validation_until: datetime

    def __post_init__(self) -> None:
        _require_aware(self.train_until, "train_until")
        _require_aware(self.validation_until, "validation_until")
        if self.validation_until <= self.train_until:
            raise ValueError("validation_until must follow train_until")

    def provisional_split(self, observed_at: datetime) -> SplitName:
        _require_aware(observed_at, "observed_at")
        if observed_at < self.train_until:
            return "train"
        if observed_at < self.validation_until:
            return "validation"
        return "test"


@dataclass(frozen=True, slots=True)
class TemporalRecord:
    record_id: str
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id must be non-empty")
        _require_aware(self.observed_at, "observed_at")


@dataclass(frozen=True, slots=True)
class SplitAssignment:
    record_id: str
    provisional_split: SplitName
    split: SplitName
    group_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id must be non-empty")
        if _SPLIT_ORDER[self.split] < _SPLIT_ORDER[self.provisional_split]:
            raise ValueError("final split cannot move a record backward in time")
        if len(self.group_ids) != len(set(self.group_ids)):
            raise ValueError("group_ids must be unique")


def assign_provisional_splits(
    records: tuple[TemporalRecord, ...] | list[TemporalRecord],
    cutoffs: TemporalCutoffs,
) -> tuple[SplitAssignment, ...]:
    """Assign records by timestamp before any leakage-control grouping."""

    ordered = sorted(records, key=lambda item: item.record_id)
    record_ids = [record.record_id for record in ordered]
    if len(record_ids) != len(set(record_ids)):
        raise ValueError("record_ids must be unique")
    return tuple(
        SplitAssignment(
            record_id=record.record_id,
            provisional_split=cutoffs.provisional_split(record.observed_at),
            split=cutoffs.provisional_split(record.observed_at),
        )
        for record in ordered
    )


def promote_groups_forward(
    assignments: tuple[SplitAssignment, ...] | list[SplitAssignment],
    groups: tuple[tuple[str, tuple[str, ...]], ...] | list[tuple[str, tuple[str, ...]]],
) -> tuple[SplitAssignment, ...]:
    """Promote each complete leakage group to its latest provisional split.

    This is deliberately forward-only: a group containing a later test record
    moves earlier members to test, never the later record back to train.
    """

    ordered_assignments = tuple(sorted(assignments, key=lambda item: item.record_id))
    by_id = {item.record_id: item for item in ordered_assignments}
    if len(by_id) != len(ordered_assignments):
        raise ValueError("assignments must have unique record_ids")
    parent = {record_id: record_id for record_id in by_id}
    memberships: dict[str, set[str]] = {record_id: set() for record_id in by_id}
    for group_id, group_members in groups:
        if not group_id.strip() or not group_members:
            raise ValueError("groups require a non-empty id and at least one member")
        if len(group_members) != len(set(group_members)):
            raise ValueError("group members must be unique")
        missing = set(group_members) - by_id.keys()
        if missing:
            raise ValueError(f"group references unknown records: {sorted(missing)}")
        first = group_members[0]
        for member in group_members:
            memberships[member].add(group_id)
            _union(parent, first, member)

    component_members: dict[str, list[str]] = {}
    for record_id in sorted(by_id):
        component_members.setdefault(_find(parent, record_id), []).append(record_id)
    promoted: dict[str, SplitName] = {}
    for members in component_members.values():
        latest = max(
            (by_id[member].provisional_split for member in members),
            key=lambda split: _SPLIT_ORDER[split],
        )
        for member in members:
            promoted[member] = latest
    return tuple(
        SplitAssignment(
            record_id=item.record_id,
            provisional_split=item.provisional_split,
            split=promoted[item.record_id],
            group_ids=tuple(sorted(memberships[item.record_id])),
        )
        for item in ordered_assignments
    )


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


def _find(parent: dict[str, str], value: str) -> str:
    while parent[value] != value:
        parent[value] = parent[parent[value]]
        value = parent[value]
    return value


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root == right_root:
        return
    parent[max(left_root, right_root)] = min(left_root, right_root)


__all__ = [
    "SplitAssignment",
    "SplitName",
    "TemporalCutoffs",
    "TemporalRecord",
    "assign_provisional_splits",
    "promote_groups_forward",
]
