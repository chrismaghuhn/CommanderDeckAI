"""CLI-facing adapters for verified normalized and dataset artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.application.errors import ApplicationError
from commander_ai.application.ports.data_pipeline import NormalizeResult, ValidateResult
from commander_ai.application.ports.dataset_store import DatasetInspectionResult
from commander_ai.application.source_policy import (
    SourcePolicy,
    SourcePolicyDecision,
    SourcePolicyError,
)
from commander_ai.config import RuntimeConfig
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.config.yaml_loader import serialize_config
from commander_ai.data_pipeline.datasets.dataset_inspection import inspect_dataset
from commander_ai.data_pipeline.provenance.normalized_snapshot_contracts import (
    NormalizedSnapshotManifestV2,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    read_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunInputReference,
    build_run_manifest,
)
from commander_ai.domain.path_policy import validate_portable_relative_path
from commander_ai.domain.provenance import NormalizedSnapshotManifest
from commander_ai.domain.serialization import sha256_hex

from .normalization_pipeline import SourceNormalizationPipeline
from .operation_provenance import operation_context
from .registry_context import SourceRegistryProvider


class VerifiedSnapshotNormalizer:
    """Verify the raw boundary before handing control to a future mapper composition."""

    def __init__(
        self,
        runtime: RuntimeConfig,
        registry_provider: SourceRegistryProvider | None = None,
    ) -> None:
        self._runtime = runtime
        self._registry_provider = registry_provider

    def normalize_snapshot(self, snapshot_id: str) -> NormalizeResult:
        if self._registry_provider is None:
            source_id = _find_unique_source(self._runtime.data_root, snapshot_id)
            from commander_ai.adapters.storage.snapshot_verifier import (
                SnapshotIntegrityError,
                SnapshotVerifier,
            )

            try:
                SnapshotVerifier(self._runtime.data_root).verify_complete_snapshot(
                    source_id, snapshot_id
                )
            except SnapshotIntegrityError as error:
                raise ApplicationError(error.code) from None
            raise ApplicationError("POLICY_SOURCE_REGISTRY_REQUIRED")
        registry, _ = self._registry_provider.load()
        pipeline = SourceNormalizationPipeline(
            self._runtime.data_root,
            self._runtime.artifact_root,
            registry,
        )
        return pipeline.normalize_snapshot(snapshot_id)


class VerifiedNormalizedSnapshot:
    """Resolve and verify normalized-snapshot-manifest.v1/v2 artifacts."""

    def __init__(
        self,
        runtime: RuntimeConfig,
        registry_provider: SourceRegistryProvider | None = None,
        *,
        require_current_use: bool = True,
    ) -> None:
        self._runtime = runtime
        self._registry_provider = registry_provider
        self._require_current_use = require_current_use

    def validate_snapshot(self, normalized_snapshot_id: str) -> ValidateResult:
        manifest_path = _find_normalized_manifest(
            self._runtime.artifact_root, normalized_snapshot_id
        )
        try:
            verified = read_normalized_snapshot_manifest(
                self._runtime.artifact_root,
                manifest_path,
                raw_root=self._runtime.data_root,
                run_root=self._runtime.artifact_root,
            )
        except (OSError, TypeError, ValueError) as error:
            raise ApplicationError("INTEGRITY_NORMALIZED_SNAPSHOT_INVALID") from error
        manifest = verified.manifest
        decision: SourcePolicyDecision | None = None
        if self._require_current_use:
            if self._registry_provider is None:
                raise ApplicationError("POLICY_SOURCE_REGISTRY_REQUIRED")
            registry, _ = self._registry_provider.load()
            try:
                decision = SourcePolicy(registry).require_operation(
                    manifest.source_id, PolicyOperation.VALIDATE
                )
            except SourcePolicyError as error:
                raise ApplicationError(error.code) from None
        finding_counts = {"findings": len(manifest.finding_codes)}
        finding_counts["quarantine"] = len(manifest.quarantine_references)
        if (
            self._require_current_use
            and decision is not None
            and (decision.decision_reference is None or decision.decision_sha256 is None)
        ):
            raise ApplicationError("POLICY_DECISION_BINDING")
        self._write_validation_run(manifest, manifest_path, decision)
        return ValidateResult(
            normalized_snapshot_id=manifest.normalized_snapshot_id,
            status="VALID",
            finding_counts=finding_counts,
            artifact_paths=tuple(item.path for item in verified.table_artifacts),
        )

    def _write_validation_run(
        self,
        manifest: NormalizedSnapshotManifest | NormalizedSnapshotManifestV2,
        manifest_path: str,
        decision: SourcePolicyDecision | None,
    ) -> None:
        normalized_id = manifest.normalized_snapshot_id
        run_id = f"validate-{normalized_id}"
        operation = operation_context(self._runtime.artifact_root, run_id)
        config_snapshot = {
            "normalized_snapshot_id": normalized_id,
            "source_id": manifest.source_id,
            "current_use_required": self._require_current_use,
        }
        inputs = [
            RunInputReference(
                kind="normalized_snapshot_manifest",
                id=normalized_id,
                path=manifest_path,
                sha256=sha256_hex((self._runtime.artifact_root / manifest_path).read_bytes()),
            )
        ]
        if decision is not None:
            if decision.decision_reference is None or decision.decision_sha256 is None:
                raise ApplicationError("POLICY_DECISION_BINDING")
            inputs.append(
                RunInputReference(
                    kind="current_use_decision",
                    id=decision.decision_reference,
                    sha256=decision.decision_sha256,
                )
            )
        now = manifest.created_at
        run = build_run_manifest(
            run_id=run_id,
            run_kind="validate",
            stage="data",
            status="succeeded",
            git_commit=operation.git_commit,
            git_dirty=operation.git_dirty,
            git_worktree_sha256=operation.git_worktree_sha256,
            dependency_lock_hash=operation.dependency_lock_hash,
            configuration_path=f"configs/validation/{normalized_id}.json",
            configuration_snapshot=serialize_config(config_snapshot),
            inputs=tuple(inputs),
            schema_versions=(manifest.schema_version,),
            transform_versions=("validate-v1",),
            policy_versions=(("current-use-v1",) if self._require_current_use else ()),
            artifacts=operation.artifacts,
            determinism=operation.determinism,
            created_at=now,
            started_at=now,
            finished_at=now,
        )
        ManifestFileWriter(self._runtime.artifact_root).write_run_manifest(
            run,
            manifest_path=f"runs/{run_id}/manifest.json",
            configuration_snapshot=serialize_config(config_snapshot),
        )


class LocalDatasetInspector:
    def __init__(self, runtime: RuntimeConfig) -> None:
        self._runtime = runtime

    def inspect_dataset(self, dataset_id: str) -> DatasetInspectionResult:
        inspection = inspect_dataset(self._runtime.artifact_root, dataset_id)
        return DatasetInspectionResult(
            dataset_id=inspection.manifest.dataset_id,
            dataset_kind=inspection.manifest.dataset_kind,
            manifest_sha256=inspection.manifest.manifest_sha256,
            counts=dict(inspection.manifest.counts),
            output_rows=inspection.output_rows,
        )


def _find_unique_source(root: Path, snapshot_id: str) -> str:
    _validate_component(snapshot_id, "INTEGRITY_SNAPSHOT_ID_INVALID")
    raw_root = root / "raw"
    matches: list[str] = []
    if raw_root.is_dir() and not raw_root.is_symlink():
        for source_root in raw_root.iterdir():
            candidate = source_root / snapshot_id / "manifest.json"
            if candidate.is_file() and not candidate.is_symlink():
                matches.append(source_root.name)
    if not matches:
        raise ApplicationError("INTEGRITY_SNAPSHOT_NOT_FOUND")
    if len(matches) != 1:
        raise ApplicationError("CONFIG_SNAPSHOT_ID_AMBIGUOUS")
    return matches[0]


def _find_normalized_manifest(root: Path, normalized_snapshot_id: str) -> str:
    _validate_component(normalized_snapshot_id, "INTEGRITY_NORMALIZED_SNAPSHOT_ID_INVALID")
    matches: list[str] = []
    normalized_root = root / "normalized"
    if normalized_root.is_dir() and not normalized_root.is_symlink():
        for path in normalized_root.rglob("manifest.json"):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError):
                continue
            if (
                isinstance(payload, dict)
                and payload.get("normalized_snapshot_id") == normalized_snapshot_id
            ):
                matches.append(path.relative_to(root).as_posix())
    if not matches:
        raise ApplicationError("INTEGRITY_NORMALIZED_SNAPSHOT_NOT_FOUND")
    if len(matches) != 1:
        raise ApplicationError("CONFIG_NORMALIZED_SNAPSHOT_ID_AMBIGUOUS")
    return matches[0]


def _validate_component(value: str, code: str) -> None:
    try:
        portable = validate_portable_relative_path(f"component/{value}")
    except (TypeError, ValueError):
        raise ApplicationError(code) from None
    if portable.count("/") != 1 or portable.endswith("/"):
        raise ApplicationError(code)


__all__ = [
    "LocalDatasetInspector",
    "VerifiedNormalizedSnapshot",
    "VerifiedSnapshotNormalizer",
]
