"""Temporal and dataset-specific leakage-control policies."""

from .deck_completion_policy import (
    CompletionBenchmark,
    CompletionExclusion,
    DeckCompletionPolicy,
    DeckCompletionRecord,
    DeckCompletionSplitResult,
    benchmark_group_id,
    build_deck_completion_splits,
)
from .group_promotion import (
    SplitAssignment,
    SplitName,
    TemporalCutoffs,
    TemporalRecord,
    assign_provisional_splits,
    promote_groups_forward,
)
from .tournament_policy import (
    TournamentExclusion,
    TournamentRecord,
    TournamentSplitPolicy,
    TournamentSplitResult,
    build_tournament_splits,
    split_for_record,
)

__all__ = [
    "CompletionBenchmark",
    "CompletionExclusion",
    "DeckCompletionPolicy",
    "DeckCompletionRecord",
    "DeckCompletionSplitResult",
    "SplitAssignment",
    "SplitName",
    "TemporalCutoffs",
    "TemporalRecord",
    "TournamentExclusion",
    "TournamentRecord",
    "TournamentSplitPolicy",
    "TournamentSplitResult",
    "assign_provisional_splits",
    "benchmark_group_id",
    "build_deck_completion_splits",
    "build_tournament_splits",
    "promote_groups_forward",
    "split_for_record",
]
