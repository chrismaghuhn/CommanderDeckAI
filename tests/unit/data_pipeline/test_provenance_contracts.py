from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.adapters.storage.digests import snapshot_content_sha256
from commander_ai.adapters.storage.snapshot_verifier import VerifiedSnapshot
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
    RawObjectReference,
    SourceSnapshotManifest,
    SourceSnapshotRequest,
    derive_request_parameters_summary,
    detached_manifest_sha256,
)

NOW = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)


def run_manifest() -> object:
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
                id="fixture-snapshot",
                path="raw/fixture/fixture-snapshot/manifest.json",
                sha256=detached_manifest_sha256(source_manifest().model_dump(mode="json")),
            ),
        ),
        schema_versions=("staging.v1",),
        mapper_versions=("fixture-mapper-v1",),
        transform_versions=("normalize-v1",),
        policy_versions=("current-use-v1",),
        ruleset_snapshot_ids=("commander-2026-02-09",),
        random_seeds=(1729,),
        artifacts=(
            RunArtifactReference(
                path="normalized/staging.parquet", sha256="d" * 64, kind="normalized"
            ),
            RunArtifactReference(
                path="normalized/audit.parquet", sha256="f" * 64, kind="audit"
            ),
            RunArtifactReference(
                path="normalized/quarantine.parquet", sha256="1" * 64, kind="quarantine"
            ),
        ),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )


def source_manifest() -> SourceSnapshotManifest:
    request = SourceSnapshotRequest(
        request_id="request-1",
        sanitized_method="GET",
        sanitized_endpoint="https://fixture.invalid/decks",
        format="json",
        sanitized_parameters={},
    )
    raw_object = RawObjectReference(
        raw_object_id="object-1",
        request_id="request-1",
        retrieved_at=NOW,
        path="objects/object-1.json",
        bytes=3,
        sha256="e" * 64,
        checksum_verification_status="not_checked",
    )
    return SourceSnapshotManifest(
        source_id="fixture",
        source_snapshot_id="fixture-snapshot",
        status="COMPLETE",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-v1",
        started_at=NOW,
        completed_at=NOW,
        usage_status="historical-approved",
        request_parameters_redacted=derive_request_parameters_summary((request,)),
        requests=(request,),
        objects=(raw_object,),
        attribution_required=False,
        redistribution_status="derived_only",
        snapshot_content_sha256=snapshot_content_sha256((raw_object.model_dump(mode="json"),)),
    )


def table_artifacts() -> tuple[NormalizedTableArtifact, ...]:
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
            rows=1,
            bytes=100,
        ),
    )


def verified_snapshot(manifest: SourceSnapshotManifest | None = None) -> VerifiedSnapshot:
    selected = manifest or source_manifest()
    return VerifiedSnapshot(
        manifest=selected,
        snapshot_dir=Path("raw/fixture/fixture-snapshot"),
        object_paths={"object-1": Path("raw/fixture/fixture-snapshot/objects/object-1.json")},
        record_count=1,
        manifest_sha256=detached_manifest_sha256(selected.model_dump(mode="json")),
        manifest_path=Path("raw/fixture/fixture-snapshot/manifest.json"),
    )


def build_result(
    counts: dict[str, int] | None = None,
    source_hash: str | None = None,
) -> object:
    return build_normalized_snapshot_manifest(
        source_manifest=source_manifest(),
        source_manifest_sha256=(
            source_hash
            if source_hash is not None
            else detached_manifest_sha256(source_manifest().model_dump(mode="json"))
        ),
        producing_run=run_manifest(),
        table_artifacts=table_artifacts(),
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
        quarantine_references=(
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
        verified_snapshot=verified_snapshot(),
    )


def test_normalized_manifest_has_stable_id_digest_and_all_table_bindings() -> None:
    first = build_result()
    second = build_result()

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
    assert payload["schema_version"] == "normalized-snapshot-manifest.v2"
    assert {artifact["layer"] for artifact in payload["artifacts"]} == {
        "normalized",
        "audit",
        "quarantine",
    }
    assert "api_key" not in run_manifest_bytes(run_manifest()).decode("utf-8")

    schema = json.loads(
        (
            Path(__file__).resolve().parents[3]
            / "schemas"
            / "normalized-snapshot-manifest.v2.schema.json"
        ).read_text(encoding="utf-8")
    )
    assert not list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload)
    )


def test_normalized_manifest_rejects_mismatched_table_content() -> None:
    result = build_result()
    changed = tuple(
        artifact.model_copy(update={"sha256": "2" * 64})
        if artifact.layer == "quarantine"
        else artifact
        for artifact in result.table_artifacts
    )

    with pytest.raises(ValueError, match=r"artifact bindings|content digest"):
        validate_normalized_snapshot_manifest(result.manifest, changed)


def test_normalized_manifest_rejects_row_count_mismatch() -> None:
    with pytest.raises(ValueError, match="count"):
        build_result(
            counts={
                "input_records": 1,
                "staging_records": 1,
                "audit_records": 1,
                "quarantine_records": 2,
            }
        )


def test_normalized_manifest_rejects_noncanonical_serialization() -> None:
    import json as json_module

    canonical = normalized_snapshot_manifest_bytes(build_result())
    pretty = json_module.dumps(json_module.loads(canonical), ensure_ascii=False, indent=2).encode(
        "utf-8"
    )

    with pytest.raises(ValueError, match="canonical"):
        validate_normalized_snapshot_manifest_bytes(pretty)


def test_normalized_manifest_bytes_are_semantically_verified_not_only_parsed() -> None:
    payload = json.loads(normalized_snapshot_manifest_bytes(build_result()))
    payload["normalized_content_sha256"] = "0" * 64
    modified = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")

    with pytest.raises(ValueError, match="content digest"):
        validate_normalized_snapshot_manifest_bytes(modified)


def test_normalized_manifest_rejects_boolean_only_integrity_claim() -> None:
    with pytest.raises(ValueError, match="verified raw snapshot evidence"):
        build_normalized_snapshot_manifest(
            source_manifest=source_manifest(),
            source_manifest_sha256="c" * 64,
            producing_run=run_manifest(),
            table_artifacts=table_artifacts(),
            normalized_schema_version="staging.v1",
            mapper_version="fixture-mapper-v1",
            transform_version="normalize-v1",
            policy_version="current-use-v1",
            counts={"input_records": 0},
            started_at=NOW,
            created_at=NOW,
            completed_at=NOW,
            raw_snapshot_verified=True,
        )


def test_normalized_manifest_rejects_a_caller_supplied_source_hash() -> None:
    with pytest.raises(ValueError, match="source manifest hash"):
        build_result(source_hash="c" * 64)


@pytest.mark.parametrize("status", ["INCOMPLETE", "FAILED"])
def test_normalized_manifest_rejects_unusable_raw_snapshot(status: str) -> None:
    manifest = source_manifest().model_copy(update={"status": status, "completed_at": None})
    with pytest.raises(ValueError, match="raw snapshot"):
        build_normalized_snapshot_manifest(
            source_manifest=manifest,
            source_manifest_sha256=detached_manifest_sha256(manifest.model_dump(mode="json")),
            producing_run=run_manifest(),
            table_artifacts=table_artifacts(),
            normalized_schema_version="staging.v1",
            mapper_version="fixture-mapper-v1",
            transform_version="normalize-v1",
            policy_version="current-use-v1",
            counts={"input_records": 0},
            started_at=NOW,
            created_at=NOW,
            completed_at=NOW,
            verified_snapshot=verified_snapshot(manifest),
        )


def test_run_manifest_is_secret_free_and_binds_required_provenance() -> None:
    payload = json.loads(run_manifest_bytes(run_manifest()))

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


def test_run_manifest_rejects_noncanonical_serialization() -> None:
    import json as json_module

    canonical = run_manifest_bytes(run_manifest())
    pretty = json_module.dumps(json_module.loads(canonical), ensure_ascii=False, indent=2).encode(
        "utf-8"
    )

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

    manifest = build_run_manifest(
        run_id="run-warning-redaction",
        run_kind="normalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/run-warning.json",
        configuration_snapshot={"source": "fixture"},
        warnings=("https://example.invalid/log?state=warning-secret",),
        tools=(("tool", "https://example.invalid/tool?token=tool-secret"),),
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    serialized = run_manifest_bytes(manifest)
    assert b"warning-secret" not in serialized
    assert b"tool-secret" not in serialized
