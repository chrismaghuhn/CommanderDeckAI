"""Build source-quality reports from verified normalized snapshots."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.application.errors import ApplicationError
from commander_ai.application.ports.reporting import ReportResult
from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config import RuntimeConfig
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    read_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
)
from commander_ai.data_pipeline.reports.report_writer import ReportWriter
from commander_ai.data_pipeline.reports.source_metrics import (
    ReportInputBinding,
    SourceMetricsInput,
    build_source_metrics_report,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .operation_provenance import operation_context
from .registry_context import SourceRegistryProvider


class ConfiguredReport:
    """Publish a deterministic report after current-use and integrity checks."""

    def __init__(self, runtime: RuntimeConfig, registry_provider: SourceRegistryProvider) -> None:
        self._runtime = runtime
        self._registry_provider = registry_provider

    def build_report(self, selector: str) -> ReportResult:
        registry, _ = self._registry_provider.load()
        runtime = self._runtime
        manifests = _select_manifests(runtime.artifact_root, selector)
        if not manifests:
            raise ApplicationError("INTEGRITY_NORMALIZED_SNAPSHOT_NOT_FOUND")
        source_inputs: list[SourceMetricsInput] = []
        run_inputs: list[RunInputReference] = []
        policy = SourcePolicy(registry)
        for manifest_path in manifests:
            verified = read_normalized_snapshot_manifest(
                runtime.artifact_root,
                manifest_path,
                raw_root=runtime.data_root,
                run_root=runtime.artifact_root,
            )
            source_id = verified.manifest.source_id
            try:
                decision = policy.require_operation(source_id, PolicyOperation.REPORT)
            except SourcePolicyError as error:
                raise ApplicationError(error.code) from None
            entry = registry.lookup(source_id)
            source_manifest = verified.source_snapshot.manifest
            audit_rows = ParquetTableWriter(runtime.artifact_root).read_table(
                verified.manifest.audit_artifact_path
            )
            finding_counts = Counter(
                str(row["finding_code"])
                for row in audit_rows
                if isinstance(row.get("finding_code"), str)
            )
            binding = ReportInputBinding(
                kind="normalized_snapshot_manifest",
                identifier=verified.manifest.normalized_snapshot_id,
                sha256=_sha256(runtime.artifact_root / manifest_path),
            )
            source_inputs.append(
                SourceMetricsInput(
                    source_id=source_id,
                    snapshot_id=source_manifest.source_snapshot_id,
                    snapshot_date=source_manifest.completed_at or source_manifest.started_at,
                    raw_bytes=sum(item.bytes for item in source_manifest.objects),
                    source_record_count=verified.manifest.counts.get(
                        "input_records", verified.manifest.counts.get("normalized_records", 0)
                    ),
                    input_manifests=(binding,),
                    historical_approval_status=SourceApprovalStatus(
                        source_manifest.approval_status
                    ),
                    current_use=entry.current_use,
                    quarantined_records=verified.manifest.counts.get("quarantine_records", 0),
                    finding_counts=dict(sorted(finding_counts.items())),
                )
            )
            if decision.decision_reference is None or decision.decision_sha256 is None:
                raise ApplicationError("POLICY_DECISION_BINDING")
            run_inputs.extend(
                (
                    RunInputReference(
                        kind="normalized_snapshot_manifest",
                        id=verified.manifest.normalized_snapshot_id,
                        path=manifest_path,
                        sha256=binding.sha256,
                    ),
                    RunInputReference(
                        kind="current_use_decision",
                        id=decision.decision_reference,
                        sha256=decision.decision_sha256,
                    ),
                )
            )
        ordered_ids = tuple(
            item.snapshot_id for item in sorted(source_inputs, key=lambda x: x.snapshot_id)
        )
        report_id = f"source-quality-{_digest((selector, *ordered_ids))[:24]}"
        reported_at = max(item.snapshot_date for item in source_inputs).astimezone(UTC)
        report = build_source_metrics_report(
            source_inputs,
            report_id=report_id,
            reported_at=reported_at,
        )
        report_writer = ReportWriter(runtime.artifact_root)
        artifacts = report_writer.write_report(
            report,
            json_path=f"reports/{report_id}.json",
            markdown_path=f"reports/{report_id}.md",
        )
        operation = operation_context(runtime.artifact_root, f"report-{report_id}")
        config_snapshot = {"selector": selector, "normalized_snapshot_ids": list(ordered_ids)}
        run = build_run_manifest(
            run_id=f"report-{report_id}",
            run_kind="report",
            stage="data",
            status="succeeded",
            git_commit=operation.git_commit,
            git_dirty=operation.git_dirty,
            git_worktree_sha256=operation.git_worktree_sha256,
            dependency_lock_hash=operation.dependency_lock_hash,
            configuration_path=f"configs/reports/{report_id}.json",
            configuration_snapshot=config_snapshot,
            inputs=_unique_run_inputs(run_inputs),
            schema_versions=("source-quality-report.v1",),
            transform_versions=("report-v1",),
            policy_versions=("current-use-v1",),
            artifacts=(
                *operation.artifacts,
                RunArtifactReference(
                    path=artifacts.json.path,
                    sha256=artifacts.json.sha256,
                    kind="report",
                ),
                *(
                    (
                        RunArtifactReference(
                            path=artifacts.markdown.path,
                            sha256=artifacts.markdown.sha256,
                            kind="report_markdown",
                        ),
                    )
                    if artifacts.markdown is not None
                    else ()
                ),
            ),
            determinism=operation.determinism,
            created_at=reported_at,
            started_at=reported_at,
            finished_at=reported_at,
        )
        ManifestFileWriter(runtime.artifact_root).write_run_manifest(
            run,
            manifest_path=f"runs/report-{report_id}/manifest.json",
            configuration_snapshot=config_snapshot,
        )
        return ReportResult(
            selector=selector,
            status="COMPLETE",
            report_path=artifacts.json.path,
            report_sha256=artifacts.json.sha256,
            summary={"report_id": report_id, "sources": len(source_inputs)},
        )


def _select_manifests(root: Path, selector: str) -> tuple[str, ...]:
    normalized_root = root / "normalized"
    paths: list[str] = []
    if not normalized_root.is_dir() or normalized_root.is_symlink():
        return ()
    for path in normalized_root.rglob("manifest.json"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if selector == "all" or payload.get("source_id") == selector:
            paths.append(path.relative_to(root).as_posix())
    return tuple(sorted(paths))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(values: tuple[str, ...]) -> str:
    return sha256_hex(canonical_json_bytes(list(values)))


def _unique_run_inputs(values: list[RunInputReference]) -> tuple[RunInputReference, ...]:
    unique: dict[tuple[str, str], RunInputReference] = {}
    for value in values:
        key = (value.kind, value.id)
        previous = unique.get(key)
        if previous is not None and previous != value:
            raise ApplicationError("INTEGRITY_REPORT_INPUT_BINDING")
        unique[key] = value
    return tuple(unique[key] for key in sorted(unique))


__all__ = ["ConfiguredReport"]
