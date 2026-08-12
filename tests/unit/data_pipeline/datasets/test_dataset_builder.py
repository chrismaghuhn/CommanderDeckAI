import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.adapters.storage.parquet_tables import (
    ParquetTableWriter,
    validate_parquet_table_rows,
)
from commander_ai.config.current_use_policy import (
    CurrentUseDecision,
    current_use_decision_binding,
)
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.datasets.dataset_builder import (
    DatasetBuildRequest,
    build_dataset,
)
from commander_ai.data_pipeline.datasets.dataset_content import compute_dataset_content_sha256
from commander_ai.data_pipeline.datasets.dataset_inspection import inspect_dataset
from commander_ai.data_pipeline.datasets.dataset_rows import safe_payload
from commander_ai.data_pipeline.datasets.leakage_reports import build_leakage_report
from commander_ai.data_pipeline.decks.canonical_decks import (
    DeckOccurrence,
    DeckSourceReference,
    DeckStructureInput,
    canonical_deck_from_input,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
    configuration_snapshot_bytes,
    run_manifest_bytes,
)
from commander_ai.domain.dataset_contracts import DatasetInputReference
from commander_ai.domain.dataset_row_contracts import (
    CardCooccurrenceRow,
    ComboCorpusRow,
    DeckCorpusRow,
    TournamentCorpusRow,
)
from commander_ai.domain.decks import CardQuantity, CardZone, CommandZoneEntry
from commander_ai.domain.provenance import (
    NormalizedSnapshotManifest,
    ProvenanceReference,
    detached_manifest_sha256,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
ORACLE_C = "33333333-3333-4333-8333-333333333333"


def _occurrence() -> DeckOccurrence:
    observed_at = datetime(2024, 1, 1, tzinfo=UTC)
    source = DeckSourceReference(
        source_id="fixture",
        source_deck_id="deck-1",
        source_snapshot_id="snapshot-1",
        raw_object_id="response.json",
        raw_sha256="0" * 64,
        observed_at=observed_at,
    )
    provenance = (
        ProvenanceReference(
            source_id="fixture",
            source_snapshot_id="snapshot-1",
            source_object_id="response.json",
            raw_sha256="0" * 64,
            retrieved_at=observed_at,
            adapter_version="fixture-adapter-v1",
            mapper_version="fixture-deck-mapper-v1",
            approval_status="APPROVED_LOCAL",
        ),
    )
    result = canonical_deck_from_input(
        DeckStructureInput(
            source=source,
            command_zone=(CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),),
            card_zones=(
                CardZone(
                    zone="mainboard",
                    cards=(
                        CardQuantity(oracle_id=ORACLE_B, quantity=1),
                        CardQuantity(oracle_id=ORACLE_C, quantity=1),
                    ),
                ),
            ),
            provenance=provenance,
        )
    )
    return DeckOccurrence(deck=result.deck, source=source)


def _settings(
    *,
    dataset_id: str = "fixture-dataset",
    dataset_kind: str = "deck_completion",
    completion_constraints: bool = True,
) -> DatasetSettings:
    inputs = (
        {
            "require_complete_decklists": True,
            "legal_decks_only": True,
        }
        if completion_constraints
        else {}
    )
    return DatasetSettings.model_validate(
        {
            "dataset_id": dataset_id,
            "dataset_kind": dataset_kind,
            "inputs": inputs,
            "split_policy": {
                "strategy": "temporal_grouped",
                "version": "temporal-grouped-test-v1",
                "train_until": "2025-01-01T00:00:00Z",
                "validation_until": "2026-01-01T00:00:00Z",
            },
            "deduplication": {
                "exact_fingerprint": True,
                "group_revisions": False,
                "near_duplicate": {
                    "algorithm": "jaccard",
                    "version": "near-duplicate-test-v1",
                    "threshold": 0.92,
                },
            },
            "quality": {"fail_on_blocking_findings": True},
        }
    )


def _request(settings: DatasetSettings, root: Path) -> DatasetBuildRequest:
    input_bytes = _normalized_input_bytes()
    input_path = root / "normalized/fixture/manifest.json"
    input_path.parent.mkdir(parents=True, exist_ok=True)
    input_path.write_bytes(input_bytes)
    configuration_snapshot = settings.model_dump(mode="json")
    configuration_path = root / "configs/datasets/fixture.json"
    configuration_path.parent.mkdir(parents=True, exist_ok=True)
    configuration_path.write_bytes(configuration_snapshot_bytes(configuration_snapshot))
    decision = CurrentUseDecision(
        source_id="fixture",
        status="ALLOWED",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        reason="fixture policy",
        effective_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    decision_reference, decision_sha256 = current_use_decision_binding(
        source_id=decision.source_id,
        historical_status=decision.approval_status or SourceApprovalStatus.PROPOSED,
        current_use=decision,
        operation="dataset_build",
    )
    run = build_run_manifest(
        run_id="fixture-run",
        run_kind="dataset_build",
        stage="data",
        status="succeeded",
        git_commit="abcdef1234567890abcdef1234567890abcdef12",
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/datasets/fixture.json",
        configuration_snapshot=configuration_snapshot,
        inputs=(
            RunInputReference(
                kind="normalized_snapshot_manifest",
                id="normalized-fixture",
                path="normalized/fixture/manifest.json",
                sha256=sha256_hex(input_bytes),
            ),
            RunInputReference(
                kind="current_use_decision",
                id=decision_reference,
                sha256=decision_sha256,
            ),
        ),
        schema_versions=("canonical-deck.v1",),
        transform_versions=("dataset-transform-v1",),
        policy_versions=("temporal-grouped-test-v1",),
        created_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 8, 11, 12, 1, tzinfo=UTC),
    )
    run_path = root / "runs/fixture-run.json"
    run_path.parent.mkdir(parents=True, exist_ok=True)
    run_path.write_bytes(run_manifest_bytes(run))
    return DatasetBuildRequest(
        settings=settings,
        input_manifests=(
            DatasetInputReference(
                kind="normalized_snapshot_manifest",
                id="normalized-fixture",
                path="normalized/fixture/manifest.json",
                sha256=sha256_hex(input_bytes),
            ),
        ),
        output_root=root,
        code_commit="abcdef1234567890abcdef1234567890abcdef12",
        dependency_lock_hash="b" * 64,
        source_snapshot_ids=("snapshot-1",),
        source_snapshot_bindings=(("fixture", "snapshot-1"),),
        ruleset_versions=("commander-2026-02-09",),
        card_snapshot_ids=("cards-fixture-v1",),
        schema_versions=("canonical-deck.v1",),
        current_use_decisions=(decision,),
        configuration_path="configs/datasets/fixture.json",
        configuration_snapshot=configuration_snapshot,
        producing_run=run,
        producing_run_path="runs/fixture-run.json",
        created_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )


def _normalized_input_bytes() -> bytes:
    manifest = NormalizedSnapshotManifest(
        normalized_snapshot_id="normalized-fixture",
        producing_run_id="fixture-run",
        input_source_snapshot_manifest_id="snapshot-1",
        input_source_snapshot_manifest_sha256="a" * 64,
        source_id="fixture",
        status="COMPLETE",
        normalized_schema_version="staging.v1",
        mapper_version="fixture-mapper-v1",
        transform_version="normalize-v1",
        normalized_artifact_path="normalized/staging.parquet",
        normalized_artifact_sha256="b" * 64,
        audit_artifact_path="audit/audit.parquet",
        audit_artifact_sha256="c" * 64,
        counts={"normalized_records": 0},
        provenance=(
            ProvenanceReference(
                source_id="fixture",
                source_snapshot_id="snapshot-1",
                source_object_id="response.json",
                raw_sha256="d" * 64,
                retrieved_at=datetime(2026, 8, 11, tzinfo=UTC),
                adapter_version="fixture-adapter-v1",
                approval_status="APPROVED_LOCAL",
            ),
        ),
        created_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        completed_at=datetime(2026, 8, 11, 12, 1, tzinfo=UTC),
        normalized_content_sha256="e" * 64,
    )
    return canonical_json_bytes(manifest.model_dump(mode="json"))


def _build(root: Path):
    request = _request(_settings(), root)
    result = build_dataset(request, [_record()])
    _publish_final_run(request, result)
    return result


def _assert_rows_match_schema(root: Path, artifact_path: str, schema_stem: str) -> None:
    schema = json.loads((PROJECT_ROOT / "schemas" / f"{schema_stem}.schema.json").read_text())
    rows = ParquetTableWriter(root).read_table(artifact_path)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for row in rows:
        errors = list(validator.iter_errors(row))
        assert errors == [], [error.message for error in errors]


def _publish_final_run(request: DatasetBuildRequest, result) -> None:
    from commander_ai.adapters.storage.manifest_files import ManifestFileWriter

    base = request.producing_run
    assert base is not None
    final_run = build_run_manifest(
        run_id=base.run_id,
        run_kind=base.run_kind,
        stage=base.stage,
        status="succeeded",
        git_commit=base.git_commit,
        git_dirty=base.git_dirty,
        git_worktree_sha256=base.git_worktree_sha256,
        dependency_lock_hash=base.environment.dependency_lock_hash,
        configuration_path=base.configuration.path,
        configuration_snapshot=request.configuration_snapshot,
        inputs=base.inputs,
        schema_versions=tuple(
            item.removeprefix("schema:")
            for item in base.feature_spec_versions
            if item.startswith("schema:")
        ),
        transform_versions=tuple(
            item.removeprefix("transform:")
            for item in base.feature_spec_versions
            if item.startswith("transform:")
        ),
        policy_versions=tuple(
            item.removeprefix("policy:")
            for item in base.feature_spec_versions
            if item.startswith("policy:")
        ),
        artifacts=(
            RunArtifactReference(
                path=result.output_artifacts[0].path,
                sha256=result.output_artifacts[0].sha256,
                kind="curated",
            ),
            *(
                RunArtifactReference(
                    path=item.path,
                    sha256=item.sha256,
                    kind=item.name,
                )
                for item in getattr(result, "report_artifacts", ())
            ),
            RunArtifactReference(
                path=result.manifest_artifact.path,
                sha256=result.manifest_artifact.sha256,
                kind="dataset_manifest",
            ),
        ),
        determinism=base.determinism,
        created_at=base.created_at,
        started_at=base.started_at,
        finished_at=base.finished_at,
    )
    ManifestFileWriter(request.output_root).write_run_manifest(
        final_run,
        manifest_path=f"runs/{base.run_id}/manifest.json",
        configuration_snapshot=request.configuration_snapshot,
        write_configuration=False,
    )


def _variant_run(
    request: DatasetBuildRequest,
    *,
    run_kind: str = "dataset_build",
    inputs: tuple[RunInputReference, ...] | None = None,
):
    run = request.producing_run
    assert run is not None
    return build_run_manifest(
        run_id=run.run_id,
        run_kind=run_kind,
        stage=run.stage,
        status="succeeded",
        git_commit=run.git_commit,
        git_dirty=run.git_dirty,
        dependency_lock_hash=run.environment.dependency_lock_hash,
        configuration_path=run.configuration.path,
        configuration_snapshot=request.configuration_snapshot,
        inputs=run.inputs if inputs is None else inputs,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
    )


def _use_variant_run(request: DatasetBuildRequest, run) -> DatasetBuildRequest:
    run_path = Path(request.output_root) / request.producing_run_path
    run_path.write_bytes(run_manifest_bytes(run))
    return replace(request, producing_run=run)


def _record(record_id: str = "record-1"):
    from commander_ai.data_pipeline.splitting.deck_completion_policy import DeckCompletionRecord

    return DeckCompletionRecord(
        record_id=record_id,
        occurrence=_occurrence(),
        observed_at=datetime(2024, 1, 1, tzinfo=UTC),
        payload={"player_name": "Alice", "nested": {"email": "alice@example.test"}},
        complete_decklist=True,
        resolution_complete=True,
        legal_status="legal",
        quality_status="accepted",
        legality_evaluation_record_id="legality-record-1",
        quality_evaluation_record_id="quality-record-1",
    )


def test_dataset_build_is_reproducible_and_manifest_binds_inputs_and_policy(tmp_path: Path) -> None:
    first = _build(tmp_path / "first")
    second = _build(tmp_path / "second")

    assert first.manifest.dataset_id == second.manifest.dataset_id
    assert first.manifest.dataset_content_sha256 == second.manifest.dataset_content_sha256
    assert first.manifest.manifest_sha256 == second.manifest.manifest_sha256
    assert any(item.id == "normalized-fixture" for item in first.manifest.input_manifests)
    assert first.manifest.split_policy_version == "temporal-grouped-test-v1"
    assert first.manifest.near_duplicate_version == "near-duplicate-test-v1"
    assert first.manifest.filters["deduplication"] == _settings().deduplication.model_dump(
        mode="json"
    )
    assert first.manifest.counts["eligible_records"] == 1
    assert first.manifest.ruleset_versions == ("commander-2026-02-09",)

    first_table = tmp_path / "first" / first.output_artifacts[0].path
    second_table = tmp_path / "second" / second.output_artifacts[0].path
    validate_parquet_table_rows(first_table, layer="curated", row_contract=DeckCorpusRow)
    _assert_rows_match_schema(tmp_path / "first", first.output_artifacts[0].path, "deck-corpus.v1")
    assert first_table.read_bytes() == second_table.read_bytes()
    first_manifest = tmp_path / "first" / first.manifest_artifact.path
    second_manifest = tmp_path / "second" / second.manifest_artifact.path
    assert first_manifest.read_bytes() == second_manifest.read_bytes()

    schema = json.loads((PROJECT_ROOT / "schemas" / "dataset-manifest.v2.schema.json").read_text())
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
            first.manifest.model_dump(mode="json", exclude_none=True)
        )
    )
    assert errors == []
    assert first.manifest.manifest_sha256 == detached_manifest_sha256(
        first.manifest.model_dump(mode="json", exclude_none=True)
    )


def test_legal_only_build_requires_an_authoritative_ruleset_binding(tmp_path: Path) -> None:
    request = _request(_settings(), tmp_path)

    with pytest.raises(ValueError, match="LEGAL_RULESET_BINDING_REQUIRED"):
        build_dataset(replace(request, ruleset_versions=()), [_record()])

    with pytest.raises(ValueError, match="LEGAL_RULESET_BINDING_INVALID"):
        build_dataset(replace(request, ruleset_versions=("unknown",)), [_record()])

    with pytest.raises(ValueError, match="LEGAL_RULESET_BINDING_INVALID"):
        build_dataset(replace(request, ruleset_versions=(" unknown ",)), [_record()])


def test_dataset_build_rejects_non_manifest_normalized_input(tmp_path: Path) -> None:
    request = _request(_settings(), tmp_path)
    path = tmp_path / "normalized/fixture/manifest.json"
    bad_bytes = b"not-a-normalized-manifest"
    path.write_bytes(bad_bytes)
    bad_hash = sha256_hex(bad_bytes)
    input_reference = DatasetInputReference(
        kind="normalized_snapshot_manifest",
        id="normalized-fixture",
        path="normalized/fixture/manifest.json",
        sha256=bad_hash,
    )
    assert request.producing_run is not None
    current_use_input = next(
        item for item in request.producing_run.inputs if item.kind == "current_use_decision"
    )
    run = _variant_run(
        request,
        inputs=(
            RunInputReference(
                kind=input_reference.kind,
                id=input_reference.id,
                path=input_reference.path,
                sha256=bad_hash,
            ),
            current_use_input,
        ),
    )
    request = replace(
        request,
        input_manifests=(input_reference,),
        producing_run=run,
    )
    request = _use_variant_run(request, run)

    with pytest.raises(ValueError, match="valid JSON"):
        build_dataset(request, [_record()])


def test_dataset_inspection_verifies_artifact_hashes_and_excludes_private_payload_keys(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)

    inspection = inspect_dataset(tmp_path, result.manifest.dataset_id)

    assert inspection.manifest.dataset_id == "fixture-dataset"
    rows = ParquetTableWriter(tmp_path).read_table(result.output_artifacts[0].path)
    row = rows[0]["values"]
    assert row["payload"] == {
        "player_name": "[EXCLUDED]",
        "nested": {"email": "[EXCLUDED]"},
    }


def test_curated_payload_masks_common_identifier_spellings() -> None:
    assert safe_payload(
        {
            "player_id": "p-1",
            "playerId": "p-2",
            "participant_id": "participant-1",
            "displayName": "Alice",
            "display_id": "display-1",
            "discord_id": "discord-1",
            "email_address": "alice@example.test",
            "player_full_name": "Alice Example",
            "player_display_name": "Alice Example",
            "nested": {
                "account_id": "account-1",
                "player": {"id": "player-1", "name": "Alice Example"},
            },
        }
    ) == {
        "player_id": "[EXCLUDED]",
        "playerId": "[EXCLUDED]",
        "participant_id": "[EXCLUDED]",
        "displayName": "[EXCLUDED]",
        "display_id": "[EXCLUDED]",
        "discord_id": "[EXCLUDED]",
        "email_address": "[EXCLUDED]",
        "player_full_name": "[EXCLUDED]",
        "player_display_name": "[EXCLUDED]",
        "nested": {
            "account_id": "[EXCLUDED]",
            "player": {"id": "[EXCLUDED]", "name": "[EXCLUDED]"},
        },
    }


def test_curated_payload_masks_additional_pii_key_shapes() -> None:
    assert safe_payload(
        {
            "full_name": "Alice Example",
            "postal_code": "12345",
            "ip_address": "192.0.2.1",
            "card_name": "Example Card",
            "deck_name": "Example Deck",
        }
    ) == {
        "full_name": "[EXCLUDED]",
        "postal_code": "[EXCLUDED]",
        "ip_address": "[EXCLUDED]",
        "card_name": "Example Card",
        "deck_name": "Example Deck",
    }


def test_curated_payload_masks_nested_opaque_participant_items() -> None:
    assert safe_payload({"items": [{"name": "Alice", "id": "player-1"}]}) == {
        "items": [{"name": "[EXCLUDED]", "id": "[EXCLUDED]"}]
    }


def test_dataset_inspection_rejects_manifest_id_mismatch(tmp_path: Path) -> None:
    result = _build(tmp_path)
    manifest_path = tmp_path / result.manifest_artifact.path
    payload = json.loads(manifest_path.read_bytes())
    payload["dataset_id"] = "different-dataset"
    payload["manifest_sha256"] = detached_manifest_sha256(payload)
    manifest_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(ValueError, match="manifest id"):
        inspect_dataset(tmp_path, result.manifest.dataset_id)


def test_dataset_inspection_rejects_declared_bytes_and_content_digest_mismatch(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)
    manifest_path = tmp_path / result.manifest_artifact.path
    payload = json.loads(manifest_path.read_bytes())
    payload["outputs"][0]["bytes"] += 1
    payload["manifest_sha256"] = detached_manifest_sha256(payload)
    manifest_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(ValueError, match="byte count"):
        inspect_dataset(tmp_path, result.manifest.dataset_id)

    second_root = tmp_path / "content"
    second = _build(second_root)
    second_manifest_path = second_root / second.manifest_artifact.path
    second_payload = json.loads(second_manifest_path.read_bytes())
    second_payload["dataset_content_sha256"] = "0" * 64
    second_payload["manifest_sha256"] = detached_manifest_sha256(second_payload)
    second_manifest_path.write_bytes(canonical_json_bytes(second_payload))

    with pytest.raises(ValueError, match="content digest"):
        inspect_dataset(second_root, second.manifest.dataset_id)


def test_dataset_inspection_verifies_optional_report_outputs_and_counts(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)
    manifest_path = tmp_path / result.manifest_artifact.path
    payload = json.loads(manifest_path.read_bytes())
    payload["quality_report"] = {
        "name": "quality-report",
        "path": "datasets/fixture-dataset/reports/quality.json",
        "sha256": "a" * 64,
        "rows": 0,
        "bytes": 1,
    }
    payload["manifest_sha256"] = detached_manifest_sha256(payload)
    manifest_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(FileNotFoundError, match=r"quality\.json"):
        inspect_dataset(tmp_path, result.manifest.dataset_id)

    second_root = tmp_path / "counts"
    second = _build(second_root)
    second_manifest_path = second_root / second.manifest_artifact.path
    second_payload = json.loads(second_manifest_path.read_bytes())
    second_payload["counts"]["output_rows"] += 1
    second_payload["manifest_sha256"] = detached_manifest_sha256(second_payload)
    second_manifest_path.write_bytes(canonical_json_bytes(second_payload))

    with pytest.raises(ValueError, match="output row count"):
        inspect_dataset(second_root, second.manifest.dataset_id)

    third_root = tmp_path / "split-counts"
    third = _build(third_root)
    third_manifest_path = third_root / third.manifest_artifact.path
    third_payload = json.loads(third_manifest_path.read_bytes())
    third_payload["counts"]["train"] += 1
    third_payload["manifest_sha256"] = detached_manifest_sha256(third_payload)
    third_manifest_path.write_bytes(canonical_json_bytes(third_payload))

    with pytest.raises(ValueError, match="train count"):
        inspect_dataset(third_root, third.manifest.dataset_id)


def test_configured_leakage_report_is_published_and_verified(tmp_path: Path) -> None:
    settings = DatasetSettings.model_validate(
        {
            **_settings().model_dump(mode="python"),
            "quality": {
                "fail_on_blocking_findings": True,
                "emit_leakage_report": True,
            },
        }
    )
    request = _request(settings, tmp_path)
    result = build_dataset(request, [_record()])
    _publish_final_run(request, result)

    assert result.manifest.leakage_report is not None
    assert result.report_artifacts[0].name == "leakage_report"
    report_path = tmp_path / result.report_artifacts[0].path
    report = json.loads(report_path.read_bytes())
    assert report["schema_version"] == "dataset-leakage-report.v1"
    assert report["status"] == "PASS"
    report_schema = json.loads(
        (PROJECT_ROOT / "schemas" / "dataset-leakage-report.v1.schema.json").read_text()
    )
    assert (
        list(
            Draft202012Validator(report_schema, format_checker=FormatChecker()).iter_errors(report)
        )
        == []
    )
    assert inspect_dataset(tmp_path, result.manifest.dataset_id).manifest.leakage_report is not None


def test_dataset_inspection_rejects_cross_split_group_even_after_rehashing(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)
    rows = ParquetTableWriter(tmp_path).read_table(result.output_artifacts[0].path)
    first = dict(rows[0])
    second = dict(rows[0])
    first_values = dict(first["values"])
    second_values = dict(second["values"])
    first["curated_id"] = "fixture-dataset:record-train"
    second["curated_id"] = "fixture-dataset:record-test"
    first_values.update(record_id="record-train", split="train", group_ids=["tampered-group"])
    second_values.update(record_id="record-test", split="test", group_ids=["tampered-group"])
    first["values"] = first_values
    second["values"] = second_values
    tampered_rows = [DeckCorpusRow.model_validate(first), DeckCorpusRow.model_validate(second)]
    artifact = ParquetTableWriter(tmp_path).write_table(
        "deck_corpus",
        tampered_rows,
        relative_path="datasets/fixture-dataset/tampered.parquet",
        schema_version="deck-corpus.v1",
        layer="curated",
        row_contract=DeckCorpusRow,
    )
    manifest_path = tmp_path / result.manifest_artifact.path
    payload = json.loads(manifest_path.read_bytes())
    payload["outputs"] = [
        {
            "name": "deck_corpus",
            "path": artifact.path,
            "sha256": artifact.sha256,
            "rows": artifact.rows,
            "bytes": artifact.bytes,
        }
    ]
    payload["counts"].update(
        train=1,
        validation=0,
        test=1,
        eligible_records=2,
        input_records=2,
        output_rows=2,
    )
    payload["dataset_content_sha256"] = compute_dataset_content_sha256(
        dataset_id=result.manifest.dataset_id,
        dataset_kind=result.manifest.dataset_kind,
        table_name="deck_corpus",
        rows=[row.model_dump(mode="json") for row in tampered_rows],
    )
    payload["manifest_sha256"] = detached_manifest_sha256(payload)
    manifest_path.write_bytes(canonical_json_bytes(payload))

    with pytest.raises(ValueError, match="cross-split leakage"):
        inspect_dataset(tmp_path, result.manifest.dataset_id)


def test_dataset_inspection_rejects_rows_outside_the_declared_typed_contract(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)
    malformed = {
        "curated_id": "fixture-dataset:record-1",
        "layer": "curated",
        "values": {"record_id": "record-1", "split": "train"},
    }
    malformed_path = tmp_path / "datasets/fixture-dataset/malformed.parquet"
    malformed_path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(
        pa.Table.from_arrays(
            [pa.array([canonical_json_bytes(malformed).decode("utf-8")], type=pa.string())],
            names=["row_json"],
        ),
        malformed_path,
    )
    payload = json.loads((tmp_path / result.manifest_artifact.path).read_bytes())
    malformed_bytes = malformed_path.read_bytes()
    payload["outputs"] = [
        {
            "name": "deck_corpus",
            "path": "datasets/fixture-dataset/malformed.parquet",
            "sha256": sha256_hex(malformed_bytes),
            "rows": 1,
            "bytes": len(malformed_bytes),
        }
    ]
    payload["dataset_content_sha256"] = compute_dataset_content_sha256(
        dataset_id=result.manifest.dataset_id,
        dataset_kind=result.manifest.dataset_kind,
        table_name="deck_corpus",
        rows=[malformed],
    )
    payload["manifest_sha256"] = detached_manifest_sha256(payload)
    (tmp_path / result.manifest_artifact.path).write_bytes(canonical_json_bytes(payload))

    with pytest.raises(ValueError, match="typed layer contract"):
        inspect_dataset(tmp_path, result.manifest.dataset_id)


def test_leakage_report_tracks_event_groups_separately_from_deck_groups(tmp_path: Path) -> None:
    manifest = _build(tmp_path).manifest
    rows = (
        {"values": {"split": "train", "event_id": "event-1", "group_ids": ["event:event-1"]}},
        {"values": {"split": "test", "event_id": "event-1", "group_ids": ["event:event-1"]}},
    )

    report = build_leakage_report(manifest, (("tournament_corpus", rows),))

    assert report["cross_split_group_ids"] == ["event:event-1"]
    assert report["cross_split_event_ids"] == ["event-1"]
    assert report["status"] == "FAIL"


def test_dataset_filters_are_applied_and_counted(tmp_path: Path) -> None:
    settings = DatasetSettings.model_validate(
        {
            **_settings().model_dump(mode="python"),
            "filters": {"source_ids": ["other-source"]},
        }
    )

    result = build_dataset(_request(settings, tmp_path), [_record()])

    assert result.manifest.counts["excluded_records"] == 1
    assert result.manifest.exclusions[0].code == "policy.dataset_source_excluded"
    assert result.manifest.counts["output_rows"] == 0


def test_dataset_exclusion_count_sums_records_sharing_a_code(tmp_path: Path) -> None:
    settings = DatasetSettings.model_validate(
        {
            **_settings().model_dump(mode="python"),
            "filters": {"source_ids": ["other-source"]},
        }
    )

    result = build_dataset(_request(settings, tmp_path), [_record("record-1"), _record("record-2")])

    assert result.manifest.counts["excluded_records"] == 2
    assert result.manifest.exclusions[0].count == 2


def test_dataset_build_blocks_current_use_and_missing_inputs(tmp_path: Path) -> None:
    blocked = CurrentUseDecision(
        source_id="fixture",
        status="PAUSED",
        approval_status=SourceApprovalStatus.PAUSED,
        reason="takedown review",
        effective_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="POLICY_CURRENT_USE_BLOCKED"):
        build_dataset(
            replace(_request(_settings(), tmp_path), current_use_decisions=(blocked,)),
            [_record()],
        )

    valid_root = tmp_path / "valid"
    missing_request = _request(_settings(), valid_root)
    (valid_root / "normalized/fixture/manifest.json").unlink()
    with pytest.raises(FileNotFoundError, match=r"normalized/fixture/manifest\.json"):
        build_dataset(replace(missing_request, input_root=valid_root), [_record()])


def test_dataset_build_rejects_invalid_filter_interval(tmp_path: Path) -> None:
    settings = DatasetSettings.model_validate(
        {
            **_settings().model_dump(mode="python"),
            "filters": {
                "observed_from": "2026-01-01T00:00:00Z",
                "observed_until": "2025-01-01T00:00:00Z",
            },
        }
    )

    with pytest.raises(ValueError, match="observed_until"):
        build_dataset(_request(settings, tmp_path), [_record()])


def test_dataset_split_cutoffs_reject_mixed_naive_and_aware_datetimes() -> None:
    with pytest.raises(ValueError, match="train_until"):
        DatasetSettings.model_validate(
            {
                "dataset_id": "mixed-timezones",
                "split_policy": {
                    "train_until": datetime(2025, 1, 1),
                    "validation_until": datetime(2026, 1, 1, tzinfo=UTC),
                },
            }
        )


def test_dataset_build_closes_run_config_and_input_bindings(tmp_path: Path) -> None:
    request = _request(_settings(), tmp_path)
    wrong_kind = _use_variant_run(
        request,
        _variant_run(request, run_kind="normalize"),
    )
    with pytest.raises(ValueError, match="dataset_build run"):
        build_dataset(wrong_kind, [_record()])

    changed_config = replace(request, configuration_snapshot={"dataset_id": "changed"})
    with pytest.raises(ValueError, match="configuration binding"):
        build_dataset(changed_config, [_record()])

    missing_input = _use_variant_run(request, _variant_run(request, inputs=()))
    with pytest.raises(ValueError, match="input binding"):
        build_dataset(missing_input, [_record()])


def test_dataset_build_rejects_forged_current_use_input_reference(tmp_path: Path) -> None:
    request = _request(_settings(), tmp_path)
    forged = DatasetInputReference(
        kind="current_use_decision",
        id="current-use.v1:forged",
        sha256="a" * 64,
    )
    with pytest.raises(ValueError, match="unbound current-use"):
        build_dataset(
            replace(request, input_manifests=(*request.input_manifests, forged)),
            [_record()],
        )


def test_dataset_build_rejects_unapproved_history_and_unimplemented_split_strategy(
    tmp_path: Path,
) -> None:
    request = _request(_settings(), tmp_path)
    proposed = request.current_use_decisions[0].model_copy(
        update={"approval_status": SourceApprovalStatus.PROPOSED}
    )
    with pytest.raises(ValueError, match="POLICY_SOURCE_NOT_APPROVED"):
        build_dataset(replace(request, current_use_decisions=(proposed,)), [_record()])

    settings = DatasetSettings.model_validate(
        {
            **_settings().model_dump(mode="python"),
            "split_policy": {
                **_settings().split_policy.model_dump(mode="python"),
                "strategy": "random",
            },
        }
    )
    with pytest.raises(ValueError, match="split strategy"):
        build_dataset(_request(settings, tmp_path / "strategy"), [_record()])


def test_tournament_and_combo_builds_require_current_use_decisions(tmp_path: Path) -> None:
    from commander_ai.data_pipeline.datasets.dataset_builder import DatasetProjectionRecord
    from commander_ai.data_pipeline.splitting.tournament_policy import TournamentRecord

    tournament_settings = _settings(
        dataset_id="missing-tournament-policy",
        dataset_kind="tournament_outcomes",
        completion_constraints=False,
    )
    tournament_request = replace(
        _request(tournament_settings, tmp_path / "tournament"), current_use_decisions=()
    )
    tournament_record = TournamentRecord(
        record_id="entry-1",
        event_id="event-1",
        observed_at=datetime(2024, 1, 1, tzinfo=UTC),
        canonical_deck_id="deck-a",
        payload={},
    )
    with pytest.raises(ValueError, match="current-use decisions"):
        build_dataset(tournament_request, [tournament_record])

    combo_settings = _settings(
        dataset_id="missing-combo-policy",
        dataset_kind="combo",
        completion_constraints=False,
    )
    combo_request = replace(_request(combo_settings, tmp_path / "combo"), current_use_decisions=())
    with pytest.raises(ValueError, match="current-use decisions"):
        build_dataset(
            combo_request,
            [
                DatasetProjectionRecord(
                    record_id="combo-1",
                    observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                    payload={},
                    source_id="fixture",
                    source_snapshot_id="snapshot-1",
                )
            ],
        )


def test_failed_manifest_publication_removes_unpublished_parquet(tmp_path: Path) -> None:
    run = build_run_manifest(
        run_id="failed-run",
        run_kind="dataset_build",
        stage="data",
        status="failed",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/dataset.json",
        configuration_snapshot={"dataset_id": "fixture-dataset"},
        created_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 8, 11, 12, 1, tzinfo=UTC),
    )
    request = _request(_settings(), tmp_path)
    request = replace(
        request,
        producing_run=run,
        producing_run_path="runs/failed-run.json",
    )

    with pytest.raises(ValueError, match="succeeded producing run"):
        build_dataset(request, [_record()])
    assert not (tmp_path / "datasets/fixture-dataset/deck_corpus.parquet").exists()


def test_dataset_builder_rejects_forged_producing_run_digest(tmp_path: Path) -> None:
    run = build_run_manifest(
        run_id="successful-run",
        run_kind="dataset_build",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/dataset.json",
        configuration_snapshot={"dataset_id": "fixture-dataset"},
        created_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        started_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
        finished_at=datetime(2026, 8, 11, 12, 1, tzinfo=UTC),
    )
    request = replace(
        _request(_settings(), tmp_path),
        producing_run=run.model_copy(update={"sha256": "0" * 64}),
        producing_run_path="runs/successful-run.json",
    )

    with pytest.raises(ValueError, match="verified producing run"):
        build_dataset(request, [_record()])


def test_card_cooccurrence_projection_emits_commander_and_card_relations(tmp_path: Path) -> None:
    from commander_ai.data_pipeline.splitting.deck_completion_policy import DeckCompletionRecord

    settings = _settings(dataset_id="fixture-cooccurrence", dataset_kind="card_cooccurrence")
    request = _request(settings, tmp_path)
    result = build_dataset(
        request,
        [
            DeckCompletionRecord(
                record_id="deck-1",
                occurrence=_occurrence(),
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                payload={},
                legal_status="legal",
                quality_status="accepted",
                legality_evaluation_record_id="legality-deck-1",
                quality_evaluation_record_id="quality-deck-1",
            )
        ],
    )

    rows = ParquetTableWriter(tmp_path).read_table(result.output_artifacts[0].path)
    validate_parquet_table_rows(
        tmp_path / result.output_artifacts[0].path,
        layer="curated",
        row_contract=CardCooccurrenceRow,
    )
    _assert_rows_match_schema(tmp_path, result.output_artifacts[0].path, "card-cooccurrence.v1")
    relations = {row["values"]["relation_type"] for row in rows}
    assert relations == {"commander_card", "card_card"}
    assert len(rows) == 3
    assert result.manifest.counts["output_rows"] == 3


def test_tournament_and_combo_builders_publish_separate_task_artifacts(tmp_path: Path) -> None:
    from commander_ai.data_pipeline.datasets.dataset_builder import DatasetProjectionRecord
    from commander_ai.data_pipeline.splitting.tournament_policy import TournamentRecord

    tournament_settings = _settings(
        dataset_id="fixture-tournament",
        dataset_kind="tournament_outcomes",
        completion_constraints=False,
    )
    tournament = build_dataset(
        _request(tournament_settings, tmp_path),
        [
            TournamentRecord(
                record_id="entry-1",
                event_id="event-1",
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                canonical_deck_id="deck-a",
                payload={"standing": 1},
                source_id="fixture",
                source_snapshot_id="snapshot-1",
            )
        ],
    )
    assert tournament.output_artifacts[0].name == "tournament_corpus"
    validate_parquet_table_rows(
        tmp_path / tournament.output_artifacts[0].path,
        layer="curated",
        row_contract=TournamentCorpusRow,
    )
    _assert_rows_match_schema(tmp_path, tournament.output_artifacts[0].path, "tournament-corpus.v1")

    combo_settings = _settings(
        dataset_id="fixture-combo",
        dataset_kind="combo",
        completion_constraints=False,
    )
    combo = build_dataset(
        _request(combo_settings, tmp_path),
        [
            DatasetProjectionRecord(
                record_id="combo-1",
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                payload={"cards": [ORACLE_A, ORACLE_B], "result": "infinite"},
                source_id="fixture",
                source_snapshot_id="snapshot-1",
            )
        ],
    )
    assert combo.output_artifacts[0].name == "combo_corpus"
    validate_parquet_table_rows(
        tmp_path / combo.output_artifacts[0].path,
        layer="curated",
        row_contract=ComboCorpusRow,
    )
    _assert_rows_match_schema(tmp_path, combo.output_artifacts[0].path, "combo-corpus.v1")


def test_event_grouped_tournament_strategy_applies_complete_record_filters(
    tmp_path: Path,
) -> None:
    from commander_ai.data_pipeline.splitting.tournament_policy import TournamentRecord

    base = _settings(
        dataset_id="fixture-event-grouped-tournament",
        dataset_kind="tournament_outcomes",
        completion_constraints=False,
    )
    split_policy = base.split_policy.model_dump(mode="python")
    split_policy.pop("group_keys")
    split_policy.update(strategy="temporal_event_grouped", group_key="event_id")
    settings = DatasetSettings.model_validate(
        {
            **base.model_dump(mode="python"),
            "inputs": {
                "require_complete_decklists": True,
                "require_complete_pod_result": True,
            },
            "split_policy": split_policy,
        }
    )
    result = build_dataset(
        _request(settings, tmp_path),
        [
            TournamentRecord(
                record_id="entry-1",
                event_id="event-1",
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                canonical_deck_id="a" * 64,
                payload={},
                complete_event=True,
                complete_decklist=True,
                source_id="fixture",
                source_snapshot_id="snapshot-1",
            )
        ],
    )

    assert result.output_artifacts[0].name == "tournament_corpus"
    assert result.manifest.counts["eligible_records"] == 1


def test_observation_datasets_require_record_source_binding(tmp_path: Path) -> None:
    from commander_ai.data_pipeline.datasets.dataset_builder import DatasetProjectionRecord

    settings = _settings(
        dataset_id="missing-observation-provenance",
        dataset_kind="combo",
        completion_constraints=False,
    )
    record = DatasetProjectionRecord(
        record_id="combo-1",
        observed_at=datetime(2024, 1, 1, tzinfo=UTC),
        payload={},
    )

    with pytest.raises(ValueError, match="source provenance"):
        build_dataset(_request(settings, tmp_path), [record])
