"""Event-grouped temporal splits for multiplayer tournament observations."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from commander_ai.config.source_settings import normalize_source_id

from .group_promotion import (
    SplitAssignment,
    SplitName,
    TemporalCutoffs,
    TemporalRecord,
    assign_provisional_splits,
    promote_groups_forward,
)


@dataclass(frozen=True, slots=True)
class TournamentRecord:
    """One event or pod observation; event identity remains the grouping key."""

    record_id: str
    event_id: str
    observed_at: datetime
    canonical_deck_id: str | None
    payload: Mapping[str, object]
    complete_event: bool = False
    complete_decklist: bool = False
    source_id: str | None = None
    source_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        if not self.record_id.strip() or not self.event_id.strip():
            raise ValueError("record_id and event_id must be non-empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")
        if (self.source_id is None) != (self.source_snapshot_id is None):
            raise ValueError("source_id and source_snapshot_id must be supplied together")
        if self.source_id is not None:
            object.__setattr__(self, "source_id", normalize_source_id(self.source_id))
            if not self.source_snapshot_id or not self.source_snapshot_id.strip():
                raise ValueError("source_snapshot_id must be non-empty")


@dataclass(frozen=True, slots=True)
class TournamentSplitPolicy:
    cutoffs: TemporalCutoffs
    require_complete_event: bool = True
    require_complete_decklists: bool = False


@dataclass(frozen=True, slots=True)
class TournamentExclusion:
    record_id: str
    code: str


@dataclass(frozen=True, slots=True)
class TournamentSplitResult:
    assignments: tuple[SplitAssignment, ...]
    eligible_records: tuple[TournamentRecord, ...]
    exclusions: tuple[TournamentExclusion, ...]
    familiar_strata: tuple[tuple[str, str], ...]


def build_tournament_splits(
    records: tuple[TournamentRecord, ...] | list[TournamentRecord],
    policy: TournamentSplitPolicy,
) -> TournamentSplitResult:
    """Group complete events only; never group by canonical deck identity."""

    ordered = tuple(sorted(records, key=lambda item: item.record_id))
    if len({record.record_id for record in ordered}) != len(ordered):
        raise ValueError("tournament record_ids must be unique")
    incomplete_events = {record.event_id for record in ordered if not record.complete_event}
    eligible: list[TournamentRecord] = []
    exclusions: list[TournamentExclusion] = []
    for record in ordered:
        if policy.require_complete_event and record.event_id in incomplete_events:
            exclusions.append(TournamentExclusion(record.record_id, "quality.event_incomplete"))
        elif policy.require_complete_decklists and not record.complete_decklist:
            exclusions.append(TournamentExclusion(record.record_id, "quality.decklist_incomplete"))
        else:
            eligible.append(record)
    provisional = assign_provisional_splits(
        tuple(TemporalRecord(record.record_id, record.observed_at) for record in eligible),
        policy.cutoffs,
    )
    event_groups: dict[str, list[str]] = {}
    for record in eligible:
        event_groups.setdefault(record.event_id, []).append(record.record_id)
    assignments = promote_groups_forward(
        provisional,
        tuple(
            (f"event:{event_id}", tuple(members))
            for event_id, members in sorted(event_groups.items())
        ),
    )
    strata = _familiar_strata(eligible, assignments)
    return TournamentSplitResult(
        assignments=assignments,
        eligible_records=tuple(eligible),
        exclusions=tuple(exclusions),
        familiar_strata=tuple(sorted(strata.items())),
    )


def _familiar_strata(
    records: tuple[TournamentRecord, ...] | list[TournamentRecord],
    assignments: tuple[SplitAssignment, ...],
) -> dict[str, str]:
    by_id = {record.record_id: record for record in records}
    train_decks = {
        by_id[assignment.record_id].canonical_deck_id
        for assignment in assignments
        if assignment.split == "train" and by_id[assignment.record_id].canonical_deck_id is not None
    }
    return {
        assignment.record_id: (
            "familiar" if by_id[assignment.record_id].canonical_deck_id in train_decks else "unseen"
        )
        for assignment in assignments
    }


def split_for_record(assignments: tuple[SplitAssignment, ...], record_id: str) -> SplitName:
    """Read one deterministic assignment without exposing a mutable index."""

    for assignment in assignments:
        if assignment.record_id == record_id:
            return assignment.split
    raise KeyError(record_id)


__all__ = [
    "TournamentExclusion",
    "TournamentRecord",
    "TournamentSplitPolicy",
    "TournamentSplitResult",
    "build_tournament_splits",
    "split_for_record",
]
