"""Run-manifest construction for normalized snapshot publication."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from commander_ai.adapters.storage.manifest_files import JsonArtifact
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
    additional_artifacts: Sequence[RunArtifactReference] = (),
    schema_versions: Sequence[str] = ("staging.v1",),
    ruleset_snapshot_ids: Sequence[str] = (),
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
        schema_versions=tuple(schema_versions),
        mapper_versions=(mapper_version,),
        transform_versions=("normalize-v1",),
        policy_versions=("current-use-v1",),
        ruleset_snapshot_ids=ruleset_snapshot_ids,
        artifacts=(
            *operation.artifacts,
            *(
                RunArtifactReference(path=item.path, sha256=item.sha256, kind=item.layer)
                for item in artifacts
            ),
            *additional_artifacts,
        ),
        determinism=operation.determinism,
        created_at=started_at,
        started_at=started_at,
        finished_at=completed_at,
    )


def build_final_normalization_run(
    *,
    preliminary_run: RunManifest,
    operation: Any,
    configuration_snapshot: dict[str, object],
    inputs: tuple[dict[str, str], ...],
    artifacts: tuple[NormalizedTableArtifact, ...],
    mapper_version: str,
    started_at: datetime,
    completed_at: datetime,
    manifest_artifact: JsonArtifact,
    manifest_sidecar: JsonArtifact,
    ruleset_snapshot_ids: Sequence[str] = (),
) -> RunManifest:
    """Bind the normalized manifest outputs to the final frozen run record."""

    return build_normalization_run(
        run_id=preliminary_run.run_id,
        operation=operation,
        configuration_path=preliminary_run.configuration.path,
        configuration_snapshot=configuration_snapshot,
        inputs=inputs,
        artifacts=artifacts,
        mapper_version=mapper_version,
        started_at=started_at,
        completed_at=completed_at,
        schema_versions=("staging.v1", "normalized-snapshot-manifest.v1"),
        additional_artifacts=(
            RunArtifactReference(
                path=manifest_artifact.path,
                sha256=manifest_artifact.sha256,
                kind="normalized_snapshot_manifest",
            ),
            RunArtifactReference(
                path=manifest_sidecar.path,
                sha256=manifest_sidecar.sha256,
                kind="normalized_snapshot_manifest_digest",
            ),
        ),
        ruleset_snapshot_ids=ruleset_snapshot_ids,
    )


__all__ = ["build_final_normalization_run", "build_normalization_run"]
