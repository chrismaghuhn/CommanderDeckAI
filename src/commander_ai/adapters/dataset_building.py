"""Application adapter for building task-specific datasets from verified tables."""

from __future__ import annotations

from datetime import UTC, datetime

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.application.errors import ApplicationError
from commander_ai.application.ports.dataset_store import DatasetBuildResult
from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config import RuntimeConfig, load_dataset_settings, serialize_config
from commander_ai.config.current_use_policy import (
    PolicyOperation,
    current_use_decision_binding,
)
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.datasets.dataset_builder import (
    DatasetBuildRequest,
    DatasetProjectionRecord,
    build_dataset,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    read_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
)
from commander_ai.domain.dataset_contracts import DatasetInputReference
from commander_ai.domain.serialization import canonical_json_bytes

from .operation_provenance import operation_context
from .registry_context import SourceRegistryProvider
from .reporting import _select_manifests, _sha256


class ConfiguredDatasetBuild:
    """Build task datasets only from explicitly canonicalized input records."""

    def __init__(self, runtime: RuntimeConfig, registry_provider: SourceRegistryProvider) -> None:
        self._runtime = runtime
        self._registry_provider = registry_provider

    def build_dataset(self, config_path: str) -> DatasetBuildResult:
        registry, _ = self._registry_provider.load()
        try:
            settings = load_dataset_settings(config_path)
        except ValueError:
            raise ApplicationError("CONFIG_DATASET_CONFIG_INVALID") from None
        policy = SourcePolicy(registry)
        input_manifests: list[DatasetInputReference] = []
        records: list[DatasetProjectionRecord] = []
        decisions = []
        source_snapshot_ids: list[str] = []
        source_snapshot_bindings: set[tuple[str, str]] = set()
        historical_statuses: dict[str, SourceApprovalStatus] = {}
        input_created_at: list[datetime] = []
        selected_sources = settings.source_ids
        manifest_paths = _select_manifests(self._runtime.artifact_root, "all")
        for manifest_path in manifest_paths:
            verified = read_normalized_snapshot_manifest(
                self._runtime.artifact_root,
                manifest_path,
                raw_root=self._runtime.data_root,
                run_root=self._runtime.artifact_root,
            )
            source_id = verified.manifest.source_id
            if selected_sources and source_id not in selected_sources:
                continue
            try:
                policy.require_operation(source_id, PolicyOperation.DATASET_BUILD)
            except SourcePolicyError as error:
                raise ApplicationError(error.code) from None
            entry = registry.lookup(source_id)
            if entry.current_use is None:
                raise ApplicationError("POLICY_CURRENT_USE_REQUIRED")
            decision = entry.current_use
            if decision not in decisions:
                decisions.append(decision)
            source_snapshot_id = verified.manifest.input_source_snapshot_manifest_id
            source_snapshot_ids.append(source_snapshot_id)
            source_snapshot_bindings.add((source_id, source_snapshot_id))
            historical_statuses[source_id] = entry.historical_approval.approval_status
            input_created_at.append(verified.manifest.created_at)
            if verified.manifest.normalized_schema_version == "staging.v1":
                raise ApplicationError("QUALITY_CANONICALIZATION_REQUIRED")
            normalized_hash = _sha256(self._runtime.artifact_root / manifest_path)
            input_manifests.append(
                DatasetInputReference(
                    kind="normalized_snapshot_manifest",
                    id=verified.manifest.normalized_snapshot_id,
                    path=manifest_path,
                    sha256=normalized_hash,
                )
            )
            rows = ParquetTableWriter(self._runtime.artifact_root).read_table(
                verified.manifest.normalized_artifact_path
            )
            observed_at = verified.manifest.created_at
            for index, row in enumerate(rows):
                record_id = str(
                    row.get("staging_record_id", f"{source_id}-{source_snapshot_id}-{index}")
                )
                records.append(
                    DatasetProjectionRecord(
                        record_id=record_id,
                        observed_at=observed_at,
                        payload=row,
                        source_id=source_id,
                        source_snapshot_id=source_snapshot_id,
                    )
                )
        if not input_manifests:
            raise ApplicationError("INTEGRITY_NORMALIZED_SNAPSHOT_NOT_FOUND")

        configuration_snapshot = serialize_config(settings)
        configuration_path = f"configs/datasets/{settings.dataset_id}.json"
        ManifestFileWriter(self._runtime.artifact_root).write_json(
            configuration_path,
            canonical_json_bytes(configuration_snapshot),
        )
        run_id = f"dataset-build-{settings.dataset_id}"
        operation = operation_context(self._runtime.artifact_root, run_id)
        run_inputs = [
            RunInputReference(
                kind=item.kind,
                id=item.id,
                path=item.path,
                sha256=item.sha256,
            )
            for item in input_manifests
        ]
        for decision in decisions:
            entry = registry.lookup(decision.source_id)
            reference, digest = current_use_decision_binding(
                source_id=decision.source_id,
                historical_status=entry.historical_approval.approval_status,
                current_use=decision,
                operation=PolicyOperation.DATASET_BUILD,
            )
            run_inputs.append(
                RunInputReference(kind="current_use_decision", id=reference, sha256=digest)
            )
        created_at = max(
            input_created_at,
            default=datetime(1970, 1, 1, tzinfo=UTC),
        )
        dataset_schema_version = _dataset_schema_version(settings.dataset_kind)
        run = build_run_manifest(
            run_id=run_id,
            run_kind="dataset_build",
            stage="data",
            status="succeeded",
            git_commit=operation.git_commit,
            git_dirty=operation.git_dirty,
            git_worktree_sha256=operation.git_worktree_sha256,
            dependency_lock_hash=operation.dependency_lock_hash,
            configuration_path=configuration_path,
            configuration_snapshot=configuration_snapshot,
            inputs=tuple(run_inputs),
            schema_versions=(dataset_schema_version,),
            transform_versions=("dataset-transform-v1",),
            policy_versions=("current-use-v1", settings.split_policy.version),
            artifacts=operation.artifacts,
            determinism=operation.determinism,
            created_at=created_at,
            started_at=created_at,
            finished_at=created_at,
        )
        request = DatasetBuildRequest(
            settings=settings,
            input_manifests=tuple(input_manifests),
            output_root=self._runtime.artifact_root,
            input_root=self._runtime.artifact_root,
            code_commit=operation.git_commit,
            dependency_lock_hash=operation.dependency_lock_hash,
            source_snapshot_ids=tuple(sorted(set(source_snapshot_ids))),
            source_snapshot_bindings=tuple(sorted(source_snapshot_bindings)),
            historical_approval_statuses=tuple(sorted(historical_statuses.items())),
            schema_versions=(dataset_schema_version,),
            transform_versions=("dataset-transform-v1",),
            policy_versions=("current-use-v1",),
            current_use_decisions=tuple(decisions),
            configuration_path=configuration_path,
            configuration_snapshot=configuration_snapshot,
            producing_run=run,
            producing_run_path=None,
            created_at=created_at,
        )
        try:
            result = build_dataset(request, records)
        except ApplicationError:
            raise
        except (OSError, TypeError, ValueError) as error:
            code = getattr(error, "code", None)
            if isinstance(code, str) and code.isupper():
                raise ApplicationError(code) from None
            raise ApplicationError("QUALITY_DATASET_BUILD_REJECTED") from None
        final_run = build_run_manifest(
            run_id=run_id,
            run_kind="dataset_build",
            stage="data",
            status="succeeded",
            git_commit=operation.git_commit,
            git_dirty=operation.git_dirty,
            git_worktree_sha256=operation.git_worktree_sha256,
            dependency_lock_hash=operation.dependency_lock_hash,
            configuration_path=configuration_path,
            configuration_snapshot=configuration_snapshot,
            inputs=tuple(run_inputs),
            schema_versions=(settings.schema_version, dataset_schema_version),
            transform_versions=("dataset-transform-v1",),
            policy_versions=("current-use-v1", settings.split_policy.version),
            artifacts=(
                *operation.artifacts,
                *(
                    RunArtifactReference(
                        path=item.path,
                        sha256=item.sha256,
                        kind="curated",
                    )
                    for item in result.output_artifacts
                ),
                RunArtifactReference(
                    path=result.manifest_artifact.path,
                    sha256=result.manifest_artifact.sha256,
                    kind="dataset_manifest",
                ),
            ),
            determinism=operation.determinism,
            created_at=created_at,
            started_at=created_at,
            finished_at=created_at,
        )
        ManifestFileWriter(self._runtime.artifact_root).write_run_manifest(
            final_run,
            manifest_path=f"runs/{run_id}/manifest.json",
            configuration_snapshot=configuration_snapshot,
            write_configuration=False,
        )
        return DatasetBuildResult(
            dataset_id=result.manifest.dataset_id,
            dataset_kind=result.manifest.dataset_kind,
            status="COMPLETE",
            manifest_path=result.manifest_artifact.path,
            manifest_sha256=result.manifest_artifact.sha256,
            output_paths=tuple(item.path for item in result.output_artifacts),
        )


def _dataset_schema_version(dataset_kind: str) -> str:
    versions = {
        "deck_completion": "deck-corpus.v1",
        "card_cooccurrence": "card-cooccurrence.v1",
        "tournament_outcomes": "tournament-corpus.v1",
        "combo": "combo-corpus.v1",
    }
    try:
        return versions[dataset_kind]
    except KeyError as error:
        raise ApplicationError("CONFIG_DATASET_KIND_INVALID") from error


__all__ = ["ConfiguredDatasetBuild"]
