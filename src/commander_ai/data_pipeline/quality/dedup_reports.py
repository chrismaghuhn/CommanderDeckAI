"""Machine-readable summaries for derived deck duplicate groups."""

from __future__ import annotations

from dataclasses import dataclass

from commander_ai.data_pipeline.deduplication.exact import ExactDuplicateReport
from commander_ai.data_pipeline.deduplication.near_duplicates import (
    NearDuplicateCluster,
    NearDuplicatePolicy,
)
from commander_ai.data_pipeline.deduplication.revisions import RevisionGroup


@dataclass(frozen=True, slots=True)
class DeduplicationReport:
    exact: ExactDuplicateReport
    revision_groups: tuple[RevisionGroup, ...]
    near_duplicate_clusters: tuple[NearDuplicateCluster, ...]
    near_duplicate_policy: NearDuplicatePolicy

    def as_dict(self) -> dict[str, object]:
        return {
            "exact_duplicate_groups": len(self.exact.groups),
            "exact_duplicate_occurrences": self.exact.duplicate_occurrences,
            "cross_source_exact_groups": self.exact.cross_source_groups,
            "revision_groups": len(self.revision_groups),
            "near_duplicate_clusters": len(self.near_duplicate_clusters),
            "near_duplicate_algorithm": self.near_duplicate_policy.algorithm,
            "near_duplicate_version": self.near_duplicate_policy.version,
            "near_duplicate_threshold": self.near_duplicate_policy.threshold,
            "near_duplicate_algorithm_versions": sorted(
                {
                    f"{cluster.policy.algorithm}:{cluster.policy.version}:{cluster.policy.threshold}"
                    for cluster in self.near_duplicate_clusters
                }
            ),
        }


def build_deduplication_report(
    exact: ExactDuplicateReport,
    revision_groups: tuple[RevisionGroup, ...],
    near_duplicate_clusters: tuple[NearDuplicateCluster, ...],
    near_duplicate_policy: NearDuplicatePolicy | None = None,
) -> DeduplicationReport:
    resolved_policy = near_duplicate_policy or (
        near_duplicate_clusters[0].policy if near_duplicate_clusters else NearDuplicatePolicy()
    )
    return DeduplicationReport(
        exact=exact,
        revision_groups=revision_groups,
        near_duplicate_clusters=near_duplicate_clusters,
        near_duplicate_policy=resolved_policy,
    )


__all__ = ["DeduplicationReport", "build_deduplication_report"]
