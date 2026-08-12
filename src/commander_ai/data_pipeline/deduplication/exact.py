"""Exact structural duplicate reporting without deleting source observations."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from commander_ai.data_pipeline.decks.canonical_decks import DeckOccurrence


@dataclass(frozen=True, slots=True)
class ExactDuplicateGroup:
    group_id: str
    canonical_deck_id: str
    occurrences: tuple[DeckOccurrence, ...]

    @property
    def source_ids(self) -> tuple[str, ...]:
        return tuple(sorted({item.source.source_id for item in self.occurrences}))


@dataclass(frozen=True, slots=True)
class ExactDuplicateReport:
    groups: tuple[ExactDuplicateGroup, ...]
    duplicate_occurrences: int
    cross_source_groups: int


def report_exact_duplicates(
    occurrences: tuple[DeckOccurrence, ...] | list[DeckOccurrence],
) -> ExactDuplicateReport:
    grouped: dict[str, list[DeckOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        grouped[occurrence.deck.canonical_deck_id].append(occurrence)
    groups = tuple(
        ExactDuplicateGroup(
            group_id=f"exact-{canonical_id}",
            canonical_deck_id=canonical_id,
            occurrences=tuple(
                sorted(
                    members,
                    key=lambda item: (
                        item.source.source_id,
                        item.source.source_deck_id,
                        item.source.source_snapshot_id,
                        item.source.raw_object_id,
                    ),
                )
            ),
        )
        for canonical_id, members in sorted(grouped.items())
        if len(members) > 1
    )
    return ExactDuplicateReport(
        groups=groups,
        duplicate_occurrences=sum(len(group.occurrences) for group in groups),
        cross_source_groups=sum(len(group.source_ids) > 1 for group in groups),
    )


__all__ = ["ExactDuplicateGroup", "ExactDuplicateReport", "report_exact_duplicates"]
