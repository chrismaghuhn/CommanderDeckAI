from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from shutil import copytree

from commander_ai.adapters.data_pipeline import LocalDatasetInspector, VerifiedNormalizedSnapshot
from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.adapters.storage.raw_snapshot_io import sha256_file
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.config import RuntimeConfig, load_dataset_settings
from commander_ai.config.current_use_policy import (
    CurrentUseDecision,
    current_use_decision_binding,
)
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.datasets.dataset_builder import (
    DatasetBuildRequest,
    DatasetProjectionRecord,
    build_dataset,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_contracts import (
    NormalizedTableArtifact,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_manifests import (
    build_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    read_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
    configuration_snapshot_bytes,
)
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.data_pipeline.reports.report_writer import ReportWriter
from commander_ai.data_pipeline.reports.source_metrics import (
    ReportInputBinding,
    SourceMetricsInput,
    build_source_metrics_report,
)
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord
from commander_ai.domain.dataset_contracts import DatasetInputReference
from commander_ai.domain.provenance import SourceSnapshotRequest

NOW = datetime(2024, 8, 12, 12, 0, tzinfo=UTC)
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_offline_data_foundation_workflow_is_rebuildable(tmp_path: Path) -> None:
    runtime = RuntimeConfig(data_root=tmp_path, artifact_root=tmp_path)
    verified = _acquire_fixture_snapshot(tmp_path)
    assert verified.manifest.status == "COMPLETE"
    assert SnapshotVerifier(tmp_path).verify_complete_snapshot("fixture", "snapshot-1")

    normalized_id, normalized_path = _normalize_fixture(tmp_path, verified)
    validated = VerifiedNormalizedSnapshot(runtime, require_current_use=False).validate_snapshot(
        normalized_id
    )
    assert validated.status == "VALID"
    assert "normalized/staging.parquet" in validated.artifact_paths

    report_path, report_hash = _build_report(tmp_path, normalized_id, normalized_path)
    assert report_path.is_file()
    assert sha256_file(report_path) == report_hash

    dataset_id = _build_dataset(tmp_path, normalized_id, normalized_path)
    inspected = LocalDatasetInspector(runtime).inspect_dataset(dataset_id)
    assert inspected.dataset_id == dataset_id
    assert inspected.counts["eligible_records"] == 1
    assert inspected.output_rows == (("combo_corpus", 1),)

    first_hashes = _artifact_hashes(tmp_path)
    second_root = tmp_path / "repeat"
    second_root.mkdir()
    copytree(tmp_path / "raw", second_root / "raw")
    verified_repeat = SnapshotVerifier(second_root).verify_complete_snapshot(
        "fixture", "snapshot-1"
    )
    normalized_repeat_id, normalized_repeat_path = _normalize_fixture(second_root, verified_repeat)
    _build_report(second_root, normalized_repeat_id, normalized_repeat_path)
    _build_dataset(second_root, normalized_repeat_id, normalized_repeat_path)
    VerifiedNormalizedSnapshot(
        RuntimeConfig(data_root=second_root, artifact_root=second_root),
        require_current_use=False,
    ).validate_snapshot(normalized_repeat_id)
    assert first_hashes == _artifact_hashes(second_root)


def _acquire_fixture_snapshot(root: Path):
    response = PROJECT_ROOT / "tests/fixtures/data_foundation/source-response.json"
    writer = RawSnapshotStore(root).start_snapshot(
        source_id="fixture",
        snapshot_id="snapshot-1",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-adapter-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
        started_at=NOW,
    )
    writer.add_request(
        SourceSnapshotRequest(
            request_id="fixture-request-1",
            sanitized_method="GET",
            sanitized_endpoint="https://fixture.invalid/decks",
            format="json",
        )
    )
    payload = response.read_bytes()
    writer.write_object(
        raw_object_id="response.json",
        request_id="fixture-request-1",
        chunks=[payload],
        retrieved_at=NOW,
        logical_record_count=1,
    )
    writer.finalize()
    return SnapshotVerifier(root).verify_complete_snapshot("fixture", "snapshot-1")


def _current_use() -> CurrentUseDecision:
    return CurrentUseDecision(
        source_id="fixture",
        status="ALLOWED",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        reason="offline fixture",
        effective_at=NOW,
    )


def _policy_binding(operation: str) -> tuple[str, str]:
    decision = _current_use()
    return current_use_decision_binding(
        source_id="fixture",
        historical_status=SourceApprovalStatus.APPROVED_LOCAL,
        current_use=decision,
        operation=operation,
    )


def _normalize_fixture(root: Path, verified) -> tuple[str, str]:
    locator = RawLocator(
        source_id="fixture",
        source_snapshot_id="snapshot-1",
        raw_object_id="response.json",
        raw_object_path="objects/response.json",
        location=JsonPointerLocator(pointer="/0"),
    )
    staging = StagingRecord.from_dto(
        SourceRecordDTO(
            source_id="fixture",
            record_type="deck",
            raw_locator=locator,
            original_source_values={"record_id": "fixture-record", "value": 1},
        ),
        staging_record_id="staging-fixture-record",
        status="OBSERVED",
    )
    audit = AuditRecord(
        audit_id="audit-fixture-record",
        entity_id=staging.staging_record_id,
        stage="quality",
        finding_code="quality.fixture_observed",
    )
    parquet = ParquetTableWriter(root)
    normalized = parquet.write_table(
        "staging",
        [staging],
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
    )
    audit_artifact = parquet.write_table(
        "audit",
        [audit],
        layer="audit",
        row_contract=AuditRecord,
        verified_snapshot=verified,
    )
    quarantine_artifact = parquet.write_table(
        "quarantine",
        [],
        layer="quarantine",
        row_contract=QuarantineRecord,
        verified_snapshot=verified,
    )
    artifacts = tuple(
        NormalizedTableArtifact(
            table_name=item.table_name,
            layer=item.layer,
            path=item.path,
            sha256=item.sha256,
            rows=item.rows,
            bytes=item.bytes,
        )
        for item in (normalized, audit_artifact, quarantine_artifact)
    )
    decision_reference, decision_hash = _policy_binding("normalize")
    run = build_run_manifest(
        run_id="normalize-fixture-run",
        run_kind="normalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/normalize/fixture.json",
        configuration_snapshot={"source_id": "fixture", "mapper": "fixture-mapper-v1"},
        inputs=(
            RunInputReference(
                kind="source_snapshot_manifest",
                id="snapshot-1",
                path="raw/fixture/snapshot-1/manifest.json",
                sha256=verified.manifest_sha256,
            ),
            RunInputReference(
                kind="current_use_decision",
                id=decision_reference,
                sha256=decision_hash,
            ),
        ),
        schema_versions=("staging.v1",),
        mapper_versions=("fixture-mapper-v1",),
        transform_versions=("normalize-v1",),
        policy_versions=("current-use-v1",),
        artifacts=tuple(
            RunArtifactReference(path=item.path, sha256=item.sha256, kind=item.layer)
            for item in artifacts
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    ManifestFileWriter(root).write_run_manifest(
        run,
        manifest_path="runs/normalize-fixture-run/manifest.json",
        configuration_snapshot={"source_id": "fixture", "mapper": "fixture-mapper-v1"},
    )
    build = build_normalized_snapshot_manifest(
        producing_run=run,
        verified_snapshot=verified,
        table_artifacts=artifacts,
        normalized_schema_version="staging.v1",
        mapper_version="fixture-mapper-v1",
        transform_version="normalize-v1",
        policy_version="current-use-v1",
        counts={
            "input_records": 1,
            "normalized_records": 1,
            "audit_records": 1,
            "quarantine_records": 0,
        },
        started_at=NOW,
        created_at=NOW,
        completed_at=NOW,
    )
    manifest_path = "normalized/fixture/snapshot-1/manifest.json"
    ManifestFileWriter(root).write_normalized_manifest(build, manifest_path=manifest_path)
    read_normalized_snapshot_manifest(root, manifest_path)
    return build.manifest.normalized_snapshot_id, manifest_path


def _build_report(root: Path, normalized_id: str, normalized_path: str) -> tuple[Path, str]:
    normalized_file = root / normalized_path
    binding = ReportInputBinding(
        kind="normalized_snapshot_manifest",
        identifier=normalized_id,
        sha256=sha256_file(normalized_file),
    )
    report = build_source_metrics_report(
        [
            SourceMetricsInput(
                source_id="fixture",
                snapshot_id="snapshot-1",
                snapshot_date=NOW,
                raw_bytes=(root / "raw/fixture/snapshot-1/objects/response.json").stat().st_size,
                source_record_count=1,
                input_manifests=(binding,),
                historical_approval_status=SourceApprovalStatus.APPROVED_LOCAL,
                current_use=_current_use(),
            )
        ],
        report_id="fixture-report",
        reported_at=NOW,
    )
    artifact = ReportWriter(root).write_report(
        report,
        json_path="reports/fixture-report.json",
        markdown_path="reports/fixture-report.md",
    )
    return root / artifact.json.path, artifact.json.sha256


def _build_dataset(root: Path, normalized_id: str, normalized_path: str) -> str:
    fixture_config = PROJECT_ROOT / "tests/fixtures/data_foundation/dataset-combo.yaml"
    settings = load_dataset_settings(fixture_config)
    configuration_snapshot = settings.model_dump(mode="json")
    configuration_path = "configs/datasets/fixture-combo.json"
    normalized_hash = sha256_file(root / normalized_path)
    decision = _current_use()
    decision_reference, decision_hash = _policy_binding("dataset_build")
    run = build_run_manifest(
        run_id="dataset-fixture-run",
        run_kind="dataset_build",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path=configuration_path,
        configuration_snapshot=configuration_snapshot,
        inputs=(
            RunInputReference(
                kind="normalized_snapshot_manifest",
                id=normalized_id,
                path=normalized_path,
                sha256=normalized_hash,
            ),
            RunInputReference(
                kind="current_use_decision",
                id=decision_reference,
                sha256=decision_hash,
            ),
        ),
        schema_versions=("combo-corpus.v1",),
        transform_versions=("dataset-transform-v1",),
        policy_versions=("fixture-split-v1",),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    ManifestFileWriter(root).write_json(
        configuration_path,
        configuration_snapshot_bytes(configuration_snapshot),
    )
    request = DatasetBuildRequest(
        settings=settings,
        input_manifests=(
            DatasetInputReference(
                kind="normalized_snapshot_manifest",
                id=normalized_id,
                path=normalized_path,
                sha256=normalized_hash,
            ),
        ),
        output_root=root,
        input_root=root,
        code_commit="a" * 40,
        dependency_lock_hash="b" * 64,
        source_snapshot_ids=("snapshot-1",),
        source_snapshot_bindings=(("fixture", "snapshot-1"),),
        schema_versions=("combo-corpus.v1",),
        current_use_decisions=(decision,),
        configuration_path=configuration_path,
        configuration_snapshot=configuration_snapshot,
        producing_run=run,
        producing_run_path=None,
        created_at=NOW,
    )
    result = build_dataset(
        request,
        [
            DatasetProjectionRecord(
                record_id="combo-record-1",
                observed_at=datetime(2024, 8, 1, tzinfo=UTC),
                payload={"player": {"name": "not-curated"}, "cards": ["fixture-card"]},
                source_id="fixture",
                source_snapshot_id="snapshot-1",
            )
        ],
    )
    final_run = build_run_manifest(
        run_id=run.run_id,
        run_kind=run.run_kind,
        stage=run.stage,
        status="succeeded",
        git_commit=run.git_commit,
        git_dirty=run.git_dirty,
        git_worktree_sha256=run.git_worktree_sha256,
        dependency_lock_hash=run.environment.dependency_lock_hash,
        configuration_path=run.configuration.path,
        configuration_snapshot=configuration_snapshot,
        inputs=run.inputs,
        schema_versions=("combo-corpus.v1",),
        transform_versions=("dataset-transform-v1",),
        policy_versions=("fixture-split-v1",),
        artifacts=(
            RunArtifactReference(
                path=result.output_artifacts[0].path,
                sha256=result.output_artifacts[0].sha256,
                kind="curated",
            ),
            RunArtifactReference(
                path=result.manifest_artifact.path,
                sha256=result.manifest_artifact.sha256,
                kind="dataset_manifest",
            ),
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    ManifestFileWriter(root).write_run_manifest(
        final_run,
        manifest_path="runs/dataset-fixture-run/manifest.json",
        configuration_snapshot=configuration_snapshot,
        write_configuration=False,
    )
    return result.manifest.dataset_id


def _artifact_hashes(root: Path) -> dict[str, str]:
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink() and path.name != "manifest.sha256"
    )
    return {
        path.relative_to(root).as_posix(): sha256_file(path)
        for path in paths
        if not path.relative_to(root).as_posix().startswith("repeat/")
    }
