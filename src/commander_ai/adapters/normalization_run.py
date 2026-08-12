"""Run-manifest construction for normalized snapshot publication."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from commander_ai.data_pipeline.provenance.normalized_snapshot_contracts import (
    NormalizedTableArtifact,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    RunManifest,
    build_run_manifest,
)


def build_normalization_run(
    *,
    run_id: str,
    operation: Any,
    configuration_path: str,
    configuration_snapshot: dict[str, object],
    inputs: tuple[dict[str, str], ...],
    artifacts: tuple[NormalizedTableArtifact, ...],
    mapper_version: str,
    started_at: datetime,
    completed_at: datetime,
) -> RunManifest:
    """Create the deterministic run record for one normalized snapshot."""

    return build_run_manifest(
        run_id=run_id,
        run_kind="normalize",
        stage="data",
        status="succeeded",
        git_commit=operation.git_commit,
        git_dirty=operation.git_dirty,
        git_worktree_sha256=operation.git_worktree_sha256,
        dependency_lock_hash=operation.dependency_lock_hash,
        configuration_path=configuration_path,
        configuration_snapshot=configuration_snapshot,
        inputs=tuple(RunInputReference.model_validate(item) for item in inputs),
        schema_versions=("staging.v1",),
        mapper_versions=(mapper_version,),
        transform_versions=("normalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=(
            *operation.artifacts,
            *(
                RunArtifactReference(path=item.path, sha256=item.sha256, kind=item.layer)
                for item in artifacts
            ),
        ),
        determinism=operation.determinism,
        created_at=started_at,
        started_at=started_at,
        finished_at=completed_at,
    )


__all__ = ["build_normalization_run"]
