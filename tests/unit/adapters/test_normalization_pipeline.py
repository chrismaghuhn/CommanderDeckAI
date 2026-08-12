from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from shutil import copytree
from types import SimpleNamespace

import pytest

from commander_ai.adapters.normalization_pipeline import SourceNormalizationPipeline
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.application.source_policy import SourcePolicyDecision
from commander_ai.config.current_use_policy import CurrentUseStatus, PolicyOperation
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings
from commander_ai.data_pipeline.provenance.normalized_snapshot_verifier import (
    read_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.run_manifests import verify_run_manifest
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord
from commander_ai.domain.provenance import SourceSnapshotRequest

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
RUN_ID = "normalize-fixture-snapshot-1"
MANIFEST_PATH = "normalized/fixture/snapshot-1/manifest.json"
RUN_PATH = f"runs/{RUN_ID}/manifest.json"


def test_normalize_final_run_binds_manifest_and_hash(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "commander_ai.adapters.normalization_pipeline.publish_canonical_snapshot",
        lambda *_args, **_kwargs: None,
    )

    result, _ = _publish_fixture(tmp_path)

    run = verify_run_manifest(tmp_path, RUN_PATH, external_input_root=tmp_path)
    manifest_outputs = [
        item for item in run.artifacts if item.kind == "normalized_snapshot_manifest"
    ]
    assert len(manifest_outputs) == 1
    assert manifest_outputs[0].path == result.manifest_path == MANIFEST_PATH
    assert manifest_outputs[0].sha256 == result.manifest_sha256
    assert run.schema_version == "run-manifest.v1"
    assert "schema:normalized-snapshot-manifest.v1" in run.feature_spec_versions

    verified = read_normalized_snapshot_manifest(tmp_path, MANIFEST_PATH)
    assert verified.producing_run.run_id == RUN_ID


def test_normalize_rebuild_keeps_manifest_and_run_outputs_deterministic(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        "commander_ai.adapters.normalization_pipeline.publish_canonical_snapshot",
        lambda *_args, **_kwargs: None,
    )

    first, first_root = _publish_fixture(tmp_path / "first")
    second_root = tmp_path / "second"
    second_root.mkdir()
    copytree(first_root / "raw", second_root / "raw")
    second, _ = _publish_fixture(second_root, acquire=False)

    assert first.source_snapshot_id == second.source_snapshot_id == "snapshot-1"
    assert first.normalized_snapshot_id == second.normalized_snapshot_id
    assert first.manifest_sha256 == second.manifest_sha256
    assert (first_root / MANIFEST_PATH).read_bytes() == (second_root / MANIFEST_PATH).read_bytes()
    assert (first_root / RUN_PATH).read_bytes() == (second_root / RUN_PATH).read_bytes()


def test_normalize_failure_before_final_run_is_not_consumable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "commander_ai.adapters.normalization_pipeline.publish_canonical_snapshot",
        lambda *_args, **_kwargs: None,
    )

    def fail_final_run(*_args, **_kwargs):
        raise RuntimeError("fixture final run failure")

    monkeypatch.setattr(
        "commander_ai.adapters.storage.manifest_files.ManifestFileWriter.write_run_manifest",
        fail_final_run,
    )

    with pytest.raises(RuntimeError, match="fixture final run failure"):
        _publish_fixture(tmp_path)

    assert (tmp_path / MANIFEST_PATH).is_file()
    assert not (tmp_path / RUN_PATH).exists()
    with pytest.raises((FileNotFoundError, ValueError)):
        read_normalized_snapshot_manifest(tmp_path, MANIFEST_PATH)


def _publish_fixture(root: Path, *, acquire: bool = True):
    root.mkdir(parents=True, exist_ok=True)
    if acquire:
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
                sanitized_endpoint="https://fixture.invalid/data",
                format="json",
            )
        )
        writer.write_object(
            raw_object_id="object-1",
            request_id="fixture-request-1",
            chunks=[b"[{}]"],
            retrieved_at=NOW,
            logical_record_count=1,
        )
        writer.finalize()
    verified = SnapshotVerifier(root).verify_complete_snapshot("fixture", "snapshot-1")

    source_settings = SourceSettings(
        source_id="fixture",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        review_path="docs/03-data/source-reviews/fixture.md",
    )
    entry = SourceRegistryEntry(
        source_id="fixture",
        settings=source_settings,
        historical_approval=HistoricalApprovalMetadata(
            source_id="fixture",
            approval_status=SourceApprovalStatus.APPROVED_LOCAL,
            review_path=source_settings.review_path,
            reviewed_at=NOW,
            effective_at=NOW,
            reason="offline fixture",
        ),
    )
    prepared = SimpleNamespace(
        source_id="fixture",
        source_snapshot_id="snapshot-1",
        manifest=verified.manifest,
        source_manifest_sha256=verified.manifest_sha256,
        verified_snapshot=verified,
        policy_decision=SourcePolicyDecision(
            source_id="fixture",
            operation=PolicyOperation.NORMALIZE,
            allowed=True,
            code="POLICY_OPERATION_ALLOWED",
            reason="offline fixture",
            historical_status=SourceApprovalStatus.APPROVED_LOCAL,
            current_status=CurrentUseStatus.ALLOWED,
            decision_reference="current-use.v1:fixture:" + "a" * 32,
            decision_sha256="a" * 64,
        ),
    )
    locator = RawLocator(
        source_id="fixture",
        source_snapshot_id="snapshot-1",
        raw_object_id="object-1",
        raw_object_path="objects/object-1",
        location=JsonPointerLocator(pointer="/0"),
    )
    staging = StagingRecord.from_dto(
        SourceRecordDTO(
            source_id="fixture",
            record_type="deck",
            raw_locator=locator,
            original_source_values={"record_id": "fixture-record"},
        ),
        staging_record_id="staging-fixture-record",
        status="OBSERVED",
    )
    pipeline = SourceNormalizationPipeline(
        root,
        root,
        SourceRegistry(entries=(entry,)),
    )
    result = pipeline._publish(
        prepared,
        entry,
        staging=(staging,),
        audits=(),
        quarantine=(),
        mapper_version="fixture-mapper-v1",
    )
    return result, root
