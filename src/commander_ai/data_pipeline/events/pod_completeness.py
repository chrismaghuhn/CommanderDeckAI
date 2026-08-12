"""Derive conservative event/pod completeness evidence from canonical rows."""

from __future__ import annotations

from collections.abc import Sequence

from commander_ai.data_pipeline.events.pod_entries import index_complete_pods
from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord


def complete_pod_observation_keys(
    records: Sequence[CanonicalRecord],
) -> frozenset[tuple[str, str]]:
    """Return event/deck keys proven by complete, multiplayer pod entries."""

    return frozenset(index_complete_pods(tuple(records)).complete_event_deck_keys)


__all__ = ["complete_pod_observation_keys"]
