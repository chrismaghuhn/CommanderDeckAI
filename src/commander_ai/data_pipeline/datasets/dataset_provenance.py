"""Exact source and current-use bindings required for curated datasets."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from commander_ai.config.current_use_policy import CurrentUseDecision
from commander_ai.config.source_settings import normalize_source_id
from commander_ai.data_pipeline.splitting.deck_completion_policy import DeckCompletionRecord
from commander_ai.data_pipeline.splitting.tournament_policy import TournamentRecord

from .dataset_builder_types import DatasetProjectionRecord


def require_observation_provenance(
    records: Sequence[TournamentRecord | DatasetProjectionRecord],
    current_use_decisions: Mapping[str, CurrentUseDecision],
    source_snapshot_bindings: Sequence[tuple[str, str]],
) -> None:
    """Require source bindings before event/combo observations enter curated data."""

    allowed_bindings = {
        (normalize_source_id(source_id), source_snapshot_id)
        for source_id, source_snapshot_id in source_snapshot_bindings
    }
    for record in records:
        source_id = getattr(record, "source_id", None)
        source_snapshot_id = getattr(record, "source_snapshot_id", None)
        if source_id is None or source_snapshot_id is None:
            raise ValueError("dataset observation requires source provenance")
        normalized_source = normalize_source_id(source_id)
        if normalized_source not in current_use_decisions:
            raise ValueError("dataset observation source has no current-use decision")
        if (normalized_source, source_snapshot_id) not in allowed_bindings:
            raise ValueError("dataset observation source snapshot is not bound to dataset inputs")


def require_completion_provenance(
    records: Sequence[DeckCompletionRecord],
    current_use_decisions: Mapping[str, CurrentUseDecision],
    source_snapshot_bindings: Sequence[tuple[str, str]],
) -> None:
    """Require exact source/snapshot bindings before deck data is curated."""

    allowed = {
        (normalize_source_id(source_id), snapshot_id)
        for source_id, snapshot_id in source_snapshot_bindings
    }
    for record in records:
        source = record.occurrence.source
        source_id = normalize_source_id(source.source_id)
        if source_id not in current_use_decisions:
            raise ValueError("dataset deck source has no current-use decision")
        if (source_id, source.source_snapshot_id) not in allowed:
            raise ValueError("dataset deck source snapshot is not bound to dataset inputs")


__all__ = ["require_completion_provenance", "require_observation_provenance"]
