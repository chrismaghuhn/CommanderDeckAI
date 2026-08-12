"""Build source-quality reports from verified normalized snapshots."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import replace
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.application.errors import ApplicationError
from commander_ai.application.ports.reporting import ReportResult
from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config import RuntimeConfig
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.provenance.canonical_snapshot_verifier import (
    read_canonical_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    read_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
)
from commander_ai.data_pipeline.reports.dataset_audit import build_dataset_audit_report
from commander_ai.data_pipeline.reports.report_writer import ReportWriter
from commander_ai.data_pipeline.reports.source_metrics import (
    ReportInputBinding,
    SourceMetricsInput,
    build_source_metrics_report,
)

from .operation_provenance import operation_context
from .registry_context import SourceRegistryProvider
from .report_assessment import reported_at as _reported_at
from .report_assessment import source_assessments as _source_assessments
from .report_metrics import canonical_metrics as _canonical_metrics
from .report_provenance import report_digest as _digest
from .report_provenance import sha256_path as _sha256
from .report_provenance import unique_run_inputs as _unique_run_inputs


class ConfiguredReport:
    """Publish a deterministic report after current-use and integrity checks."""

    def __init__(self, runtime: RuntimeConfig, registry_provider: SourceRegistryProvider) -> None:
        self._runtime = runtime
        self._registry_provider = registry_provider

    def build_report(self, selector: str) -> ReportResult:
        registry, _ = self._registry_provider.load()
        runtime = self._runtime
        manifests = _select_manifests(runtime.artifact_root, selector)
        if not manifests and selector != "all" and registry.get(selector) is None:
            raise ApplicationError("INTEGRITY_NORMALIZED_SNAPSHOT_NOT_FOUND")
        source_inputs: list[SourceMetricsInput] = []
        run_inputs: list[RunInputReference] = []
        policy = SourcePolicy(registry)
        for manifest_path in manifests:
            if manifest_path.startswith("canonical/"):
                verified_canonical = read_canonical_snapshot_manifest(
                    runtime.artifact_root,
                    manifest_path,
                    raw_root=runtime.data_root,
                    run_root=runtime.artifact_root,
                )
                source_id = verified_canonical.manifest.source_id
                normalized = verified_canonical.normalized_snapshot
                source_manifest = normalized.source_snapshot.manifest
                canonical_rows = ParquetTableWriter(runtime.artifact_root).read_table(
                    next(
                        item.path
                        for item in verified_canonical.manifest.artifacts
                        if item.artifact_kind == "canonical"
                    )
                )
                audit_rows = ParquetTableWriter(runtime.artifact_root).read_table(
                    next(
                        item.path
                        for item in verified_canonical.manifest.artifacts
                        if item.artifact_kind == "audit"
                    )
                )
                resolution_rows = ParquetTableWriter(runtime.artifact_root).read_table(
                    next(
                        item.path
                        for item in verified_canonical.manifest.artifacts
                        if item.artifact_kind == "resolution"
                    )
                )
                decks, resolution_counts, event_counts, pod_counts = _canonical_metrics(
                    canonical_rows, resolution_rows, source_id=source_id
                )
                snapshot_id = source_manifest.source_snapshot_id
                source_record_count = normalized.manifest.counts.get(
                    "input_records", normalized.manifest.counts.get("normalized_records", 0)
                )
                input_kind = "canonical_snapshot_manifest"
                input_id = verified_canonical.manifest.canonical_snapshot_id
                input_path = manifest_path
                quarantine_count = verified_canonical.manifest.counts.get("quarantine_records", 0)
            else:
                verified = read_normalized_snapshot_manifest(
                    runtime.artifact_root,
                    manifest_path,
                    raw_root=runtime.data_root,
                    run_root=runtime.artifact_root,
                )
                source_id = verified.manifest.source_id
                source_manifest = verified.source_snapshot.manifest
                audit_rows = ParquetTableWriter(runtime.artifact_root).read_table(
                    verified.manifest.audit_artifact_path
                )
                decks = ()
                resolution_counts = (0, 0, 0, 0)
                event_counts = (0, 0)
                pod_counts = (0, 0)
                snapshot_id = source_manifest.source_snapshot_id
                source_record_count = verified.manifest.counts.get(
                    "input_records", verified.manifest.counts.get("normalized_records", 0)
                )
                input_kind = "normalized_snapshot_manifest"
                input_id = verified.manifest.normalized_snapshot_id
                input_path = manifest_path
                quarantine_count = verified.manifest.counts.get("quarantine_records", 0)
            try:
                decision = policy.require_operation(source_id, PolicyOperation.REPORT)
            except SourcePolicyError as error:
                raise ApplicationError(error.code) from None
            entry = registry.lookup(source_id)
            finding_counts = Counter(
                str(row["finding_code"])
                for row in audit_rows
                if isinstance(row.get("finding_code"), str)
            )
            binding = ReportInputBinding(
                kind=input_kind,
                identifier=input_id,
                sha256=_sha256(runtime.artifact_root / input_path),
            )
            source_inputs.append(
                SourceMetricsInput(
                    source_id=source_id,
                    snapshot_id=snapshot_id,
                    snapshot_date=source_manifest.completed_at or source_manifest.started_at,
                    raw_bytes=sum(item.bytes for item in source_manifest.objects),
                    source_record_count=source_record_count,
                    decks=decks,
                    card_resolution_total=resolution_counts[0],
                    card_resolution_resolved=resolution_counts[1],
                    card_resolution_ambiguous=resolution_counts[2],
                    card_resolution_unresolved=resolution_counts[3],
                    tournament_events=event_counts[0],
                    complete_event_observations=event_counts[1],
                    pods=pod_counts[0],
                    complete_pods=pod_counts[1],
                    input_manifests=(binding,),
                    historical_approval_status=SourceApprovalStatus(
                        source_manifest.approval_status
                    ),
                    current_use=entry.current_use,
                    quarantined_records=quarantine_count,
                    finding_counts=dict(sorted(finding_counts.items())),
                )
            )
            if decision.decision_reference is None or decision.decision_sha256 is None:
                raise ApplicationError("POLICY_DECISION_BINDING")
            run_inputs.extend(
                (
                    RunInputReference(
                        kind=input_kind,
                        id=input_id,
                        path=input_path,
                        sha256=binding.sha256,
                    ),
                    RunInputReference(
                        kind="current_use_decision",
                        id=decision.decision_reference,
                        sha256=decision.decision_sha256,
                    ),
                )
            )
        measured_sources = {item.source_id for item in source_inputs}
        assessments = _source_assessments(registry, selector, measured_sources)
        ordered_ids = tuple(
            item.snapshot_id for item in sorted(source_inputs, key=lambda x: x.snapshot_id)
        )
        input_ids = tuple(
            sorted(
                f"{binding.kind}:{binding.identifier}:{binding.sha256}"
                for source in source_inputs
                for binding in source.input_manifests
            )
        )
        assessment_ids = tuple(
            f"{item.source_id}:{item.approval_status}:{item.current_use_status}:"
            f"{item.policy_code}:{item.decision_sha256 or ''}"
            for item in assessments
        )
        report_id = (
            f"source-quality-{_digest((selector, *ordered_ids, *input_ids, *assessment_ids))[:24]}"
        )
        reported_at = _reported_at(source_inputs, registry, selector)
        source_report = build_source_metrics_report(
            source_inputs,
            report_id=report_id,
            reported_at=reported_at,
        )
        if assessments:
            source_report = replace(
                source_report,
                sources=tuple(
                    (*source_report.sources, *(item.as_source_report() for item in assessments))
                ),
                current_use=tuple(
                    (*source_report.current_use, *(item.as_current_use() for item in assessments))
                ),
            )
        report_writer = ReportWriter(runtime.artifact_root)
        artifacts = report_writer.write_report(
            source_report,
            json_path=f"reports/{report_id}.json",
            markdown_path=f"reports/{report_id}.md",
        )
        audit_artifacts = None
        if selector == "all":
            audit_id = f"dataset-audit-{_digest((report_id, 'audit'))[:24]}"
            audit_report = build_dataset_audit_report(
                source_inputs,
                report_id=audit_id,
                reported_at=reported_at,
                source_assessments=assessments,
            )
            audit_artifacts = report_writer.write_report(
                audit_report,
                json_path=f"reports/{audit_id}.json",
                markdown_path=f"reports/{audit_id}.md",
            )
        operation = operation_context(runtime.artifact_root, f"report-{report_id}")
        config_snapshot = {
            "selector": selector,
            "source_snapshot_ids": list(ordered_ids),
            "input_manifest_ids": [
                item.identifier for source in source_inputs for item in source.input_manifests
            ],
            "assessment_sources": [
                {
                    "source_id": item.source_id,
                    "approval_status": item.approval_status,
                    "current_use_status": item.current_use_status,
                    "policy_code": item.policy_code,
                    "policy_allowed": item.policy_allowed,
                    "research_only": item.research_only,
                }
                for item in assessments
            ],
        }
        report_artifacts = [
            RunArtifactReference(
                path=artifacts.json.path,
                sha256=artifacts.json.sha256,
                kind="report",
            )
        ]
        if artifacts.markdown is not None:
            report_artifacts.append(
                RunArtifactReference(
                    path=artifacts.markdown.path,
                    sha256=artifacts.markdown.sha256,
                    kind="report_markdown",
                )
            )
        schema_versions = ["source-quality-report.v1"]
        transform_versions = ["report-v1"]
        if audit_artifacts is not None:
            schema_versions.append("dataset-audit-report.v1")
            transform_versions.append("dataset-audit-v1")
            report_artifacts.append(
                RunArtifactReference(
                    path=audit_artifacts.json.path,
                    sha256=audit_artifacts.json.sha256,
                    kind="dataset_audit_report",
                )
            )
            if audit_artifacts.markdown is not None:
                report_artifacts.append(
                    RunArtifactReference(
                        path=audit_artifacts.markdown.path,
                        sha256=audit_artifacts.markdown.sha256,
                        kind="dataset_audit_report_markdown",
                    )
                )
        for assessment in assessments:
            if assessment.decision_reference and assessment.decision_sha256:
                run_inputs.append(
                    RunInputReference(
                        kind="current_use_decision",
                        id=assessment.decision_reference,
                        sha256=assessment.decision_sha256,
                    )
                )
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
            schema_versions=tuple(schema_versions),
            transform_versions=tuple(transform_versions),
            policy_versions=("current-use-v1",),
            artifacts=(
                *operation.artifacts,
                *report_artifacts,
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
            summary={
                "report_id": report_id,
                "sources": len(source_inputs),
                "assessment_only_sources": len(assessments),
                **(
                    {
                        "audit_report_path": audit_artifacts.json.path,
                        "audit_report_sha256": audit_artifacts.json.sha256,
                        "audit_markdown_path": audit_artifacts.markdown.path
                        if audit_artifacts.markdown is not None
                        else None,
                    }
                    if audit_artifacts is not None
                    else {}
                ),
            },
        )


def _select_manifests(root: Path, selector: str) -> tuple[str, ...]:
    normalized = _manifest_index(root / "normalized", root, selector, "normalized_snapshot_id")
    canonical = _manifest_index(root / "canonical", root, selector, "input_normalized_snapshot_id")
    canonical_inputs = {item[1] for item in canonical}
    selected = [path for path, _ in canonical]
    selected.extend(path for path, snapshot_id in normalized if snapshot_id not in canonical_inputs)
    return tuple(sorted(selected))


def _manifest_index(
    directory: Path,
    root: Path,
    selector: str,
    identity_key: str,
) -> tuple[tuple[str, str], ...]:
    if not directory.is_dir() or directory.is_symlink():
        return ()
    values: list[tuple[str, str]] = []
    for path in directory.rglob("manifest.json"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        source_id = payload.get("source_id")
        identity = payload.get(identity_key)
        if (
            isinstance(source_id, str)
            and isinstance(identity, str)
            and (selector == "all" or source_id == selector)
        ):
            values.append((path.relative_to(root).as_posix(), identity))
    return tuple(sorted(values))
