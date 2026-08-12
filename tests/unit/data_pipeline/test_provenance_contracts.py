from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.data_pipeline.provenance.normalized_snapshot_manifests import (
    NormalizedTableArtifact,
    build_normalized_snapshot_manifest,
    normalized_snapshot_manifest_bytes,
    validate_normalized_snapshot_manifest,
    validate_normalized_snapshot_manifest_bytes,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunEnvironment,
    RunInputReference,
    build_run_manifest,
    configuration_snapshot_bytes,
    run_manifest_bytes,
    validate_run_manifest_bytes,
)
from commander_ai.domain.provenance import (
    NormalizedSnapshotManifest,
    SourceSnapshotRequest,
)

NOW = datetime(2026, 8, 10, 10, 0, tzinfo=UTC)
POLICY_REFERENCE = "current-use.v1:fixture:" + "a" * 32
POLICY_SHA256 = "a" * 64


def verified_snapshot(tmp_path: Path):
    manifest_path = tmp_path / "raw/fixture/fixture-snapshot/manifest.json"
    if not manifest_path.exists():
        writer = RawSnapshotStore(tmp_path).start_snapshot(
            source_id="fixture",
            snapshot_id="fixture-snapshot",
            approval_status="APPROVED_LOCAL",
            adapter_version="fixture-v1",
            usage_status="historical-approved",
            started_at=NOW,
        )
        writer.add_request(
            SourceSnapshotRequest(
                request_id="request-1",
                sanitized_method="GET",
                sanitized_endpoint="https://fixture.invalid/decks",
                format="json",
            )
        )
        writer.write_object(
            raw_object_id="object-1",
            request_id="request-1",
            chunks=[b"raw"],
        )
        writer.finalize()
    return SnapshotVerifier(tmp_path).verify_complete_snapshot("fixture", "fixture-snapshot")


def table_artifacts(quarantine_rows: int = 1) -> tuple[NormalizedTableArtifact, ...]:
    return (
        NormalizedTableArtifact(
            table_name="staging",
            layer="normalized",
            path="normalized/staging.parquet",
            sha256="d" * 64,
            rows=1,
            bytes=100,
        ),
        NormalizedTableArtifact(
            table_name="audit",
            layer="audit",
            path="normalized/audit.parquet",
            sha256="f" * 64,
            rows=1,
            bytes=100,
        ),
        NormalizedTableArtifact(
            table_name="quarantine",
            layer="quarantine",
            path="normalized/quarantine.parquet",
            sha256="1" * 64,
            rows=quarantine_rows,
            bytes=100,
        ),
    )


def run_manifest(
    verified: object,
    artifacts: tuple[NormalizedTableArtifact, ...] | None = None,
):
    source = verified.manifest
    selected_artifacts = artifacts or table_artifacts()
    return build_run_manifest(
        run_id="normalize-run-1",
        run_kind="normalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/normalize.json",
        configuration_snapshot={
            "source": "fixture",
            "api_key": "do-not-persist",
            "nested": {"cookie": "session-secret", "limit": 10},
        },
        inputs=(
            RunInputReference(
                kind="source_snapshot_manifest",
                id=source.source_snapshot_id,
                path="raw/fixture/fixture-snapshot/manifest.json",
                sha256=verified.manifest_sha256,
            ),
            RunInputReference(
                kind="current_use_decision",
                id=POLICY_REFERENCE,
                sha256=POLICY_SHA256,
            ),
        ),
        schema_versions=("staging.v1",),
        mapper_versions=("fixture-mapper-v1",),
        transform_versions=("normalize-v1",),
        policy_versions=("current-use-v1",),
        ruleset_snapshot_ids=("commander-2026-02-09",),
        random_seeds=(1729,),
        artifacts=tuple(
            RunArtifactReference(path=item.path, sha256=item.sha256, kind=item.layer)
            for item in selected_artifacts
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )


def build_result(
    tmp_path: Path,
    counts: dict[str, int] | None = None,
    source_hash: str | None = None,
    *,
    quarantine_rows: int = 1,
    quarantine_references: tuple[dict[str, str], ...] | None = None,
):
    verified = verified_snapshot(tmp_path)
    artifacts = table_artifacts(quarantine_rows)
    run = run_manifest(verified, artifacts)
    return build_normalized_snapshot_manifest(
        producing_run=run,
        table_artifacts=artifacts,
        normalized_schema_version="staging.v1",
        mapper_version="fixture-mapper-v1",
        transform_version="normalize-v1",
        policy_version="current-use-v1",
        counts=counts
        or {
            "input_records": 1,
            "staging_records": 1,
            "normalized_records": 1,
            "audit_records": 1,
            "quarantine_records": 1,
        },
        finding_codes=("parse.json.invalid", "resolution.ambiguous"),
        quarantine_references=quarantine_references
        or (
            {
                "quarantine_id": "q-1",
                "reason_code": "parse.json.invalid",
                "path": "normalized/quarantine.parquet",
                "record_locator": "/0",
            },
        ),
        started_at=NOW,
        created_at=NOW,
        completed_at=NOW,
        verified_snapshot=verified,
        source_manifest_sha256=source_hash,
    )


def test_normalized_manifest_is_v1_with_stable_id_digest_and_all_bindings(
    tmp_path: Path,
) -> None:
    first = build_result(tmp_path)
    second = build_result(tmp_path)

    assert first.manifest.schema_version == "normalized-snapshot-manifest.v1"
    assert first.manifest.normalized_snapshot_id == second.manifest.normalized_snapshot_id
    assert first.manifest.normalized_content_sha256 == second.manifest.normalized_content_sha256
    assert {artifact.layer for artifact in first.table_artifacts} == {
        "normalized",
        "audit",
        "quarantine",
    }
    assert first.manifest.producing_run_id == "normalize-run-1"
    assert first.manifest.input_source_snapshot_manifest_id == "fixture-snapshot"
    assert first.manifest.counts["quarantine_records"] == 1
    assert first.manifest.quarantine_references[0].path == "normalized/quarantine.parquet"

    payload = json.loads(normalized_snapshot_manifest_bytes(first))
    assert payload["schema_version"] == "normalized-snapshot-manifest.v1"
    assert "artifacts" not in payload

    schema_path = (
        Path(__file__).resolve().parents[3]
        / "schemas"
        / "normalized-snapshot-manifest.v1.schema.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert not list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload)
    )


def test_quarantine_references_are_canonically_sorted(tmp_path: Path) -> None:
    result = build_result(
        tmp_path,
        counts={
            "normalized_records": 1,
            "audit_records": 1,
            "quarantine_records": 2,
        },
        quarantine_rows=2,
        quarantine_references=(
            {
                "quarantine_id": "q-2",
                "reason_code": "parse.json.invalid",
                "path": "normalized/quarantine.parquet",
                "record_locator": "/1",
            },
            {
                "quarantine_id": "q-1",
                "reason_code": "parse.json.invalid",
                "path": "normalized/quarantine.parquet",
                "record_locator": "/0",
            },
        ),
    )

    assert [item.quarantine_id for item in result.manifest.quarantine_references] == ["q-1", "q-2"]


def test_normalized_manifest_rejects_mismatched_table_content(tmp_path: Path) -> None:
    result = build_result(tmp_path)
    changed = tuple(
        artifact.model_copy(update={"sha256": "2" * 64})
        if artifact.layer == "quarantine"
        else artifact
        for artifact in result.table_artifacts
    )

    with pytest.raises(ValueError, match=r"artifact bindings|content digest"):
        validate_normalized_snapshot_manifest(
            result.manifest,
            changed,
            producing_run=run_manifest(verified_snapshot(tmp_path), changed),
        )


def test_normalized_manifest_rejects_row_count_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="count"):
        build_result(
            tmp_path,
            counts={
                "normalized_records": 1,
                "audit_records": 1,
                "quarantine_records": 2,
            },
        )


def test_normalized_manifest_requires_exact_quarantine_output_locators(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="quarantine reference"):
        build_result(
            tmp_path,
            quarantine_references=(
                {
                    "quarantine_id": "q-1",
                    "reason_code": "parse.json.invalid",
                    "path": "normalized/quarantine.parquet",
                },
            ),
        )


def test_normalized_manifest_rejects_noncanonical_serialization(tmp_path: Path) -> None:
    canonical = normalized_snapshot_manifest_bytes(build_result(tmp_path))
    pretty = json.dumps(json.loads(canonical), ensure_ascii=False, indent=2).encode("utf-8")

    with pytest.raises(ValueError, match="canonical"):
        validate_normalized_snapshot_manifest_bytes(pretty)


def test_normalized_manifest_rejects_noncanonical_reference_order(tmp_path: Path) -> None:
    result = build_result(
        tmp_path,
        counts={
            "normalized_records": 1,
            "audit_records": 1,
            "quarantine_records": 2,
        },
        quarantine_rows=2,
        quarantine_references=(
            {
                "quarantine_id": "q-1",
                "reason_code": "parse.json.invalid",
                "path": "normalized/quarantine.parquet",
                "record_locator": "/0",
            },
            {
                "quarantine_id": "q-2",
                "reason_code": "parse.json.invalid",
                "path": "normalized/quarantine.parquet",
                "record_locator": "/1",
            },
        ),
    )
    payload = result.manifest.model_dump(mode="json")
    payload["quarantine_references"] = list(reversed(payload["quarantine_references"]))

    with pytest.raises(ValueError, match="sorted"):
        NormalizedSnapshotManifest.model_validate(payload)


def test_normalized_manifest_rejects_sensible_time_and_failed_status_violations(
    tmp_path: Path,
) -> None:
    payload = build_result(tmp_path).manifest.model_dump(mode="json")
    payload["created_at"] = "2026-08-10T10:00:00Z"
    payload["started_at"] = "2026-08-10T10:00:01Z"
    with pytest.raises(ValueError, match="started_at"):
        NormalizedSnapshotManifest.model_validate(payload)

    payload = build_result(tmp_path).manifest.model_dump(mode="json")
    payload["status"] = "FAILED"
    payload["completed_at"] = None
    with pytest.raises(ValueError, match="FAILED"):
        NormalizedSnapshotManifest.model_validate(payload)


def test_normalized_manifest_bytes_verify_content_with_context(tmp_path: Path) -> None:
    result = build_result(tmp_path)
    payload = json.loads(normalized_snapshot_manifest_bytes(result))
    payload["normalized_content_sha256"] = "0" * 64
    modified = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    with pytest.raises(ValueError, match="content digest"):
        validate_normalized_snapshot_manifest_bytes(
            modified,
            table_artifacts=result.table_artifacts,
            producing_run=run_manifest(verified_snapshot(tmp_path)),
        )


def test_normalized_manifest_rejects_boolean_only_integrity_claim(tmp_path: Path) -> None:
    verified = verified_snapshot(tmp_path)
    run = run_manifest(verified)
    with pytest.raises(ValueError, match="verified raw snapshot evidence"):
        build_normalized_snapshot_manifest(
            producing_run=run,
            table_artifacts=table_artifacts(),
            normalized_schema_version="staging.v1",
            mapper_version="fixture-mapper-v1",
            transform_version="normalize-v1",
            policy_version="current-use-v1",
            counts={"normalized_records": 0, "audit_records": 0, "quarantine_records": 0},
            started_at=NOW,
            created_at=NOW,
            completed_at=NOW,
            raw_snapshot_verified=True,
        )


def test_normalized_manifest_rejects_a_caller_supplied_source_hash(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="source manifest hash"):
        build_result(tmp_path, source_hash="c" * 64)


def test_normalized_manifest_rejects_fabricated_verifier_evidence(tmp_path: Path) -> None:
    verified = verified_snapshot(tmp_path)
    run = run_manifest(verified)
    with pytest.raises(ValueError, match="verified raw snapshot evidence"):
        build_normalized_snapshot_manifest(
            producing_run=run,
            table_artifacts=table_artifacts(),
            normalized_schema_version="staging.v1",
            mapper_version="fixture-mapper-v1",
            transform_version="normalize-v1",
            policy_version="current-use-v1",
            counts={"normalized_records": 0, "audit_records": 0, "quarantine_records": 0},
            started_at=NOW,
            created_at=NOW,
            completed_at=NOW,
            verified_snapshot=object(),
        )


def test_normalized_manifest_rejects_unusable_raw_snapshot(tmp_path: Path) -> None:
    verified = verified_snapshot(tmp_path)
    incomplete = verified.manifest.model_copy(update={"status": "INCOMPLETE", "completed_at": None})
    run = run_manifest(verified)
    with pytest.raises(ValueError, match=r"verified source|raw snapshot"):
        build_normalized_snapshot_manifest(
            producing_run=run,
            table_artifacts=table_artifacts(),
            normalized_schema_version="staging.v1",
            mapper_version="fixture-mapper-v1",
            transform_version="normalize-v1",
            policy_version="current-use-v1",
            counts={"normalized_records": 0, "audit_records": 0, "quarantine_records": 0},
            started_at=NOW,
            created_at=NOW,
            completed_at=NOW,
            source_manifest=incomplete,
            verified_snapshot=verified,
        )


def test_run_manifest_is_secret_free_and_binds_required_provenance(tmp_path: Path) -> None:
    manifest = run_manifest(verified_snapshot(tmp_path))
    payload = json.loads(run_manifest_bytes(manifest))

    assert payload["environment"]["dependency_lock_hash"] == "b" * 64
    assert "schema:staging.v1" in payload["feature_spec_versions"]
    assert "mapper:fixture-mapper-v1" in payload["feature_spec_versions"]
    assert "transform:normalize-v1" in payload["feature_spec_versions"]
    assert "policy:current-use-v1" in payload["feature_spec_versions"]
    assert payload["ruleset_versions"] == ["commander-2026-02-09"]
    assert payload["random_seeds"] == [1729]
    serialized = json.dumps(payload, sort_keys=True)
    assert "do-not-persist" not in serialized
    assert "session-secret" not in serialized
    assert "current_use_decision" in serialized

    schema = json.loads(
        (Path(__file__).resolve().parents[3] / "schemas" / "run-manifest.v1.schema.json").read_text(
            encoding="utf-8"
        )
    )
    assert not list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload)
    )


def test_run_manifest_rejects_nonportable_artifact_paths() -> None:
    with pytest.raises(ValueError):
        RunArtifactReference(path="C:\\escape.parquet", sha256="a" * 64, kind="staging")


def test_run_inputs_bind_pathful_file_objects_and_redact_secret_identifiers() -> None:
    with pytest.raises(ValueError, match="path"):
        RunInputReference(kind="raw_object", id="object-1", sha256="a" * 64)

    redacted = RunInputReference(
        kind="raw_object",
        id="token=secret-value",
        path="raw/fixture/object-1",
        sha256="a" * 64,
    )
    serialized = json.dumps(redacted.model_dump(mode="json"), sort_keys=True)
    assert "secret-value" not in serialized
    assert "[REDACTED]" in serialized


def test_run_manifest_rejects_duplicate_and_unknown_json_members(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="duplicate"):
        validate_run_manifest_bytes(
            b'{"schema_version":"run-manifest.v1","schema_version":"run-manifest.v1"}'
        )

    payload = json.loads(run_manifest_bytes(run_manifest(verified_snapshot(tmp_path))))
    payload["unknown"] = True
    with pytest.raises(ValueError):
        validate_run_manifest_bytes(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )


def test_run_manifest_rejects_noncanonical_serialization(tmp_path: Path) -> None:
    canonical = run_manifest_bytes(run_manifest(verified_snapshot(tmp_path)))
    pretty = json.dumps(json.loads(canonical), ensure_ascii=False, indent=2).encode("utf-8")

    with pytest.raises(ValueError, match="canonical"):
        validate_run_manifest_bytes(pretty)


def test_run_environment_rejects_extra_tool_fields() -> None:
    with pytest.raises(ValueError):
        RunEnvironment.model_validate(
            {
                "python_version": "3.12",
                "platform": "fixture",
                "dependency_lock_hash": "b" * 64,
                "tools": [{"name": "uv", "version": "1", "token": "secret"}],
            }
        )


def test_run_metadata_and_config_remove_secret_query_values() -> None:
    snapshot = configuration_snapshot_bytes(
        {
            "endpoint": "https://example.invalid/check?state=secret-query&safe=1",
            "nested": {"authorization": "Bearer header-secret"},
        }
    )
    assert b"secret-query" not in snapshot
    assert b"safe=1" not in snapshot
