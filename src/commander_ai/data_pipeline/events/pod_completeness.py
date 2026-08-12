"""Derive conservative event/pod completeness evidence from canonical rows."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence

from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.domain.observations import PodEntry


def complete_pod_observation_keys(
    records: Sequence[CanonicalRecord],
) -> frozenset[tuple[str, str]]:
    """Return event/deck keys proven by complete, multiplayer pod entries."""

    grouped: dict[tuple[str, str, int], list[PodEntry]] = defaultdict(list)
    for record in records:
        if record.record_type == "pod_entry":
            entry = PodEntry.model_validate(record.payload)
            grouped[(entry.event_id, entry.pod_id, entry.round_number)].append(entry)
    complete: set[tuple[str, str]] = set()
    for entries in grouped.values():
        seats = {entry.seat for entry in entries}
        if len(entries) < 2 or len(seats) != len(entries):
            continue
        complete.update((entry.event_id, entry.canonical_deck_id) for entry in entries)
    return frozenset(complete)


__all__ = ["complete_pod_observation_keys"]
