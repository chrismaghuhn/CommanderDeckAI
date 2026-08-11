"""CLI-facing adapters for verified normalized and dataset artifacts."""

from __future__ import annotations

from pathlib import Path

from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.application.errors import ApplicationError
from commander_ai.application.ports.data_pipeline import NormalizeResult, ValidateResult
from commander_ai.application.ports.dataset_store import (
    DatasetBuildResult,
    DatasetInspectionResult,
)
from commander_ai.application.ports.reporting import ReportResult
from commander_ai.config import RuntimeConfig
from commander_ai.data_pipeline.datasets.dataset_inspection import inspect_dataset
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    read_normalized_snapshot_manifest,
)
from commander_ai.domain.path_policy import validate_portable_relative_path


class VerifiedSnapshotNormalizer:
    """Verify the raw boundary before handing control to a future mapper composition."""

    def __init__(self, runtime: RuntimeConfig) -> None:
        self._runtime = runtime

    def normalize_snapshot(self, snapshot_id: str) -> NormalizeResult:
        source_id = _find_unique_source(self._runtime.data_root, snapshot_id)
        verification = SnapshotVerifier(self._runtime.data_root).inspect(source_id, snapshot_id)
        if not verification.consumable:
            raise ApplicationError(verification.issue_codes[0] or "INTEGRITY_SNAPSHOT_INVALID")
        raise ApplicationError("CONFIG_NORMALIZATION_PIPELINE_NOT_CONFIGURED")


class VerifiedNormalizedSnapshot:
    """Resolve and verify normalized-snapshot-manifest.v1/v2 artifacts."""

    def __init__(self, runtime: RuntimeConfig) -> None:
        self._runtime = runtime

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
        finding_counts = {"findings": len(manifest.finding_codes)}
        finding_counts["quarantine"] = len(manifest.quarantine_references)
        return ValidateResult(
            normalized_snapshot_id=manifest.normalized_snapshot_id,
            status="VALID",
            finding_counts=finding_counts,
            artifact_paths=tuple(item.path for item in verified.table_artifacts),
        )


class UnconfiguredReport:
    def build_report(self, selector: str) -> ReportResult:
        raise ApplicationError("CONFIG_REPORT_PIPELINE_NOT_CONFIGURED")


class UnconfiguredDatasetBuild:
    def build_dataset(self, config_path: str) -> DatasetBuildResult:
        raise ApplicationError("CONFIG_DATASET_PIPELINE_NOT_CONFIGURED")


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
            if (
                path.parent.name == normalized_snapshot_id
                and path.is_file()
                and not path.is_symlink()
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
    "UnconfiguredDatasetBuild",
    "UnconfiguredReport",
    "VerifiedNormalizedSnapshot",
    "VerifiedSnapshotNormalizer",
]
