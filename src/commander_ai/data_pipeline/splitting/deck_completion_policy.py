"""Leakage-safe completion splits over deck structure and source revisions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Literal

from commander_ai.data_pipeline.decks.canonical_decks import DeckOccurrence
from commander_ai.data_pipeline.deduplication.near_duplicates import (
    NearDuplicateCluster,
    NearDuplicatePolicy,
    cluster_near_duplicates,
)
from commander_ai.data_pipeline.deduplication.revisions import RevisionGroup, group_revisions
from commander_ai.domain.serialization import canonical_json_bytes

from .group_promotion import (
    SplitAssignment,
    TemporalCutoffs,
    TemporalRecord,
    assign_provisional_splits,
    promote_groups_forward,
)

CompletionBenchmark = Literal[
    "cold_fingerprint",
    "cold_command_zone",
    "cold_commander",
    "low_data_commander",
]


@dataclass(frozen=True, slots=True)
class DeckCompletionRecord:
    """One curated-eligibility candidate with a canonical deck occurrence."""

    record_id: str
    occurrence: DeckOccurrence
    observed_at: datetime
    payload: Mapping[str, object]
    complete_decklist: bool = True
    resolution_complete: bool = True
    legal_status: str = "unknown"
    quality_status: str = "unknown"
    mode: str | None = None

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id must be non-empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")

    @property
    def canonical_deck_id(self) -> str:
        return self.occurrence.deck.canonical_deck_id

    @property
    def command_zone_group_id(self) -> str:
        cards = tuple(
            sorted(
                (entry.oracle_id.lower(), entry.quantity)
                for entry in self.occurrence.deck.command_zone
            )
        )
        digest = sha256(canonical_json_bytes(cards)).hexdigest()[:32]
        return f"command-zone-{digest}"

    @property
    def commander_group_ids(self) -> tuple[str, ...]:
        return tuple(
            f"commander:{entry.oracle_id.lower()}"
            for entry in sorted(self.occurrence.deck.command_zone, key=lambda item: item.oracle_id)
        )


@dataclass(frozen=True, slots=True)
class CompletionExclusion:
    record_id: str
    code: str


@dataclass(frozen=True, slots=True)
class DeckCompletionPolicy:
    cutoffs: TemporalCutoffs
    exact_fingerprint: bool = True
    group_revisions: bool = True
    group_near_duplicates: bool = True
    near_duplicate_policy: NearDuplicatePolicy = field(default_factory=NearDuplicatePolicy)
    require_complete_decklists: bool = False
    require_resolution: bool = True
    legal_decks_only: bool = False
    accepted_quality_statuses: tuple[str, ...] = ("accepted",)


@dataclass(frozen=True, slots=True)
class DeckCompletionSplitResult:
    assignments: tuple[SplitAssignment, ...]
    eligible_records: tuple[DeckCompletionRecord, ...]
    exclusions: tuple[CompletionExclusion, ...]
    revision_groups: tuple[RevisionGroup, ...]
    near_duplicate_clusters: tuple[NearDuplicateCluster, ...]


def build_deck_completion_splits(
    records: tuple[DeckCompletionRecord, ...] | list[DeckCompletionRecord],
    policy: DeckCompletionPolicy,
) -> DeckCompletionSplitResult:
    """Filter candidates, form deck-only leakage groups, then promote forward."""

    ordered_records = tuple(sorted(records, key=lambda item: item.record_id))
    if len({record.record_id for record in ordered_records}) != len(ordered_records):
        raise ValueError("completion record_ids must be unique")
    eligible: list[DeckCompletionRecord] = []
    exclusions: list[CompletionExclusion] = []
    for record in ordered_records:
        code = _exclusion_code(record, policy)
        if code is None:
            eligible.append(record)
        else:
            exclusions.append(CompletionExclusion(record.record_id, code))

    temporal = assign_provisional_splits(
        tuple(TemporalRecord(record.record_id, record.observed_at) for record in eligible),
        policy.cutoffs,
    )
    groups: list[tuple[str, tuple[str, ...]]] = []
    if policy.exact_fingerprint:
        groups.extend(_exact_groups(eligible))
    revisions = (
        group_revisions(tuple(item.occurrence for item in eligible))
        if policy.group_revisions
        else ()
    )
    if policy.group_revisions:
        groups.extend(_occurrence_groups(eligible, revisions, "revision"))
    near_clusters = (
        cluster_near_duplicates(
            tuple(item.occurrence for item in eligible), policy=policy.near_duplicate_policy
        )
        if policy.group_near_duplicates
        else ()
    )
    for cluster in near_clusters:
        members = tuple(
            item.record_id
            for item in eligible
            if item.canonical_deck_id in cluster.canonical_deck_ids
        )
        groups.append((f"near:{cluster.cluster_id}", members))
    assignments = promote_groups_forward(temporal, tuple(groups))
    return DeckCompletionSplitResult(
        assignments=assignments,
        eligible_records=tuple(eligible),
        exclusions=tuple(exclusions),
        revision_groups=revisions,
        near_duplicate_clusters=near_clusters,
    )


def benchmark_group_id(
    record: DeckCompletionRecord,
    benchmark: CompletionBenchmark,
    *,
    commander_counts: Mapping[str, int] | None = None,
    low_data_max_records: int = 1,
) -> tuple[str, ...]:
    """Return independent holdout groups for optional cold-start benchmarks."""

    if benchmark == "cold_fingerprint":
        return (f"fingerprint:{record.canonical_deck_id}",)
    if benchmark == "cold_command_zone":
        return (record.command_zone_group_id,)
    if benchmark == "cold_commander":
        return record.commander_group_ids or ("commander:missing",)
    if commander_counts is None:
        raise ValueError("low_data_commander requires commander_counts")
    if low_data_max_records < 0:
        raise ValueError("low_data_max_records must be non-negative")
    return tuple(
        f"low-data-commander:{commander_id.removeprefix('commander:')}"
        for commander_id in record.commander_group_ids
        if commander_counts.get(commander_id.removeprefix("commander:"), 0) <= low_data_max_records
    )


def _exclusion_code(record: DeckCompletionRecord, policy: DeckCompletionPolicy) -> str | None:
    if policy.require_complete_decklists and not record.complete_decklist:
        return "quality.decklist_incomplete"
    if policy.require_resolution and not record.resolution_complete:
        return "resolution.card_unresolved"
    if policy.legal_decks_only and record.legal_status != "legal":
        return "legality.deck_not_eligible"
    if record.quality_status not in policy.accepted_quality_statuses:
        return "quality.deck_not_eligible"
    return None


def _exact_groups(
    records: tuple[DeckCompletionRecord, ...] | list[DeckCompletionRecord],
) -> list[tuple[str, tuple[str, ...]]]:
    groups: dict[str, list[str]] = {}
    for record in records:
        group_id = f"exact:{record.canonical_deck_id}"
        groups.setdefault(group_id, []).append(record.record_id)
    return [(group_id, tuple(members)) for group_id, members in sorted(groups.items())]


def _occurrence_groups(
    records: tuple[DeckCompletionRecord, ...] | list[DeckCompletionRecord],
    source_groups: tuple[RevisionGroup, ...],
    prefix: str,
) -> list[tuple[str, tuple[str, ...]]]:
    by_occurrence: dict[tuple[str, str, str, str], list[str]] = {}
    for record in records:
        by_occurrence.setdefault(_occurrence_key(record.occurrence), []).append(record.record_id)
    groups: list[tuple[str, tuple[str, ...]]] = []
    for source_group in source_groups:
        members = tuple(
            sorted(
                record_id
                for occurrence in source_group.occurrences
                for record_id in by_occurrence.get(_occurrence_key(occurrence), ())
            )
        )
        unique_members = tuple(dict.fromkeys(members))
        if len(unique_members) > 1:
            groups.append((f"{prefix}:{source_group.revision_group_id}", unique_members))
    return groups


def _occurrence_key(occurrence: DeckOccurrence) -> tuple[str, str, str, str]:
    source = occurrence.source
    return (
        source.source_id,
        source.source_deck_id,
        source.source_snapshot_id,
        source.raw_object_id,
    )


__all__ = [
    "CompletionBenchmark",
    "CompletionExclusion",
    "DeckCompletionPolicy",
    "DeckCompletionRecord",
    "DeckCompletionSplitResult",
    "benchmark_group_id",
    "build_deck_completion_splits",
]
