"""Source-scoped revision grouping for derived leakage metadata."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from hashlib import sha256

from commander_ai.data_pipeline.decks.canonical_decks import DeckOccurrence
from commander_ai.domain.serialization import canonical_json_bytes

REVISION_GROUP_VERSION = "source-deck-revision-v1"


@dataclass(frozen=True, slots=True)
class RevisionGroup:
    revision_group_id: str
    source_id: str
    source_deck_id: str
    occurrences: tuple[DeckOccurrence, ...]
    algorithm_version: str = REVISION_GROUP_VERSION


def group_revisions(
    occurrences: tuple[DeckOccurrence, ...] | list[DeckOccurrence],
) -> tuple[RevisionGroup, ...]:
    grouped: dict[tuple[str, str], list[DeckOccurrence]] = defaultdict(list)
    for occurrence in occurrences:
        key = (occurrence.source.source_id, occurrence.source.source_deck_id)
        grouped[key].append(occurrence)
    groups: list[RevisionGroup] = []
    for (source_id, source_deck_id), members in sorted(grouped.items()):
        if len(members) < 2:
            continue
        group_hash = sha256(
            canonical_json_bytes(
                {
                    "version": REVISION_GROUP_VERSION,
                    "source_id": source_id,
                    "source_deck_id": source_deck_id,
                }
            )
        ).hexdigest()[:32]
        groups.append(
            RevisionGroup(
                revision_group_id=f"revision-{group_hash}",
                source_id=source_id,
                source_deck_id=source_deck_id,
                occurrences=tuple(
                    sorted(
                        members,
                        key=lambda item: (
                            item.source.observed_at.isoformat()
                            if item.source.observed_at is not None
                            else "",
                            item.deck.canonical_deck_id,
                            item.source.source_snapshot_id,
                        ),
                    )
                ),
            )
        )
    return tuple(groups)


__all__ = ["REVISION_GROUP_VERSION", "RevisionGroup", "group_revisions"]
