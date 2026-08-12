"""Machine-readable summaries for deterministic card-resolution batches."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from commander_ai.data_pipeline.resolution.card_resolution import ResolutionResult


@dataclass(frozen=True, slots=True)
class ResolutionReport:
    """Counts that expose both usable resolutions and retained failures."""

    total_entries: int
    resolved_entries: int
    source_identifier_matches: int
    exact_identifier_matches: int
    exact_name_matches: int
    split_face_matches: int
    alias_matches: int
    ambiguous_entries: int
    unresolved_entries: int
    rejected_entries: int

    @property
    def exact_matches(self) -> int:
        return (
            self.source_identifier_matches
            + self.exact_identifier_matches
            + self.exact_name_matches
            + self.split_face_matches
        )

    @property
    def failure_count(self) -> int:
        return self.ambiguous_entries + self.unresolved_entries + self.rejected_entries

    @classmethod
    def from_results(cls, results: tuple[ResolutionResult, ...]) -> ResolutionReport:
        counts = {name: 0 for name in _METHODS}
        statuses = {name: 0 for name in _STATUSES}
        for result in results:
            statuses[result.resolution.status] += 1
            if result.resolution.status == "resolved":
                counts[result.resolution.method] += 1
        return cls(
            total_entries=len(results),
            resolved_entries=statuses["resolved"],
            source_identifier_matches=counts["source_identifier"],
            exact_identifier_matches=counts["exact_identifier"],
            exact_name_matches=counts["exact_name"],
            split_face_matches=counts["split_face"],
            alias_matches=counts["alias"],
            ambiguous_entries=statuses["ambiguous"],
            unresolved_entries=statuses["unresolved"],
            rejected_entries=statuses["rejected"],
        )

    def as_dict(self) -> dict[str, int]:
        return {
            "total_entries": self.total_entries,
            "resolved_entries": self.resolved_entries,
            "source_identifier_matches": self.source_identifier_matches,
            "exact_identifier_matches": self.exact_identifier_matches,
            "exact_name_matches": self.exact_name_matches,
            "split_face_matches": self.split_face_matches,
            "alias_matches": self.alias_matches,
            "exact_matches": self.exact_matches,
            "ambiguous_entries": self.ambiguous_entries,
            "unresolved_entries": self.unresolved_entries,
            "rejected_entries": self.rejected_entries,
            "failure_count": self.failure_count,
        }


_METHODS = (
    "source_identifier",
    "exact_identifier",
    "exact_name",
    "split_face",
    "alias",
    "none",
)
_STATUSES: tuple[Literal["resolved", "ambiguous", "unresolved", "rejected"], ...] = (
    "resolved",
    "ambiguous",
    "unresolved",
    "rejected",
)


__all__ = ["ResolutionReport"]
