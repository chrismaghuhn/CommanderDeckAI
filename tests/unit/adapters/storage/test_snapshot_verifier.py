from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commander_ai.adapters.storage import raw_snapshots
from commander_ai.adapters.storage.canonical_json import canonical_json_bytes
from commander_ai.adapters.storage.digests import detached_manifest_sha256
from commander_ai.adapters.storage.snapshot_verifier import (
    SnapshotIntegrityError,
    SnapshotVerifier,
    verify_complete_snapshot,
)
from commander_ai.domain.provenance import SourceSnapshotRequest


def _complete_snapshot(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    writer = raw_snapshots.RawSnapshotStore(tmp_path).start_snapshot(
        source_id="fixture",
        snapshot_id="fixture-snapshot",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-v1",
        usage_status="APPROVED_LOCAL",
        started_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    writer.add_request(
        SourceSnapshotRequest(
            request_id="request-1",
            sanitized_method="GET",
            sanitized_endpoint="https://fixture.invalid/cards",
            format="json",
            sanitized_parameters={"page": 1},
        )
    )
    writer.write_object(
        raw_object_id="object-1",
        request_id="request-1",
        chunks=[b"exact raw bytes"],
        content_type="application/octet-stream",
    )
    writer.finalize()
    manifest_path = tmp_path / "raw/fixture/fixture-snapshot/manifest.json"
    return manifest_path, json.loads(manifest_path.read_text(encoding="utf-8"))


def _rewrite_manifest(
    manifest_path: Path, payload: dict[str, object], *, sidecar: bool = True
) -> None:
    manifest_path.write_bytes(canonical_json_bytes(payload))
    if sidecar:
        manifest_path.with_name("manifest.sha256").write_text(
            detached_manifest_sha256(payload) + "\n", encoding="ascii"
        )


@pytest.mark.parametrize(
    ("status", "expected_code"),
    [
        ("INCOMPLETE", "INTEGRITY_SNAPSHOT_NOT_COMPLETE"),
        ("FAILED", "INTEGRITY_SNAPSHOT_NOT_COMPLETE"),
    ],
)
def test_non_complete_snapshot_is_rejected_before_consumption(
    tmp_path: Path, status: str, expected_code: str
) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    payload["status"] = status
    payload["completed_at"] = None
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == expected_code


def test_verifier_returns_only_verified_manifest_and_paths(tmp_path: Path) -> None:
    _manifest_path, payload = _complete_snapshot(tmp_path)

    verified = verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")

    assert verified.manifest.status == "COMPLETE"
    assert verified.manifest_sha256 == detached_manifest_sha256(payload)
    assert verified.object_paths["object-1"].read_bytes() == b"exact raw bytes"
    assert verified.record_count == 0


def test_store_rejects_manifest_identity_mismatch_with_requested_snapshot_path(
    tmp_path: Path,
) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    payload["source_id"] = "other-source"
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        raw_snapshots.RawSnapshotStore(tmp_path).load_manifest("fixture", "fixture-snapshot")

    assert error.value.code == "ACQ_MANIFEST_IDENTITY"


def test_verifier_rejects_manifest_identity_mismatch_with_requested_snapshot_path(
    tmp_path: Path,
) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    payload["source_snapshot_id"] = "other-snapshot"
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")

    assert error.value.code == "INTEGRITY_MANIFEST_IDENTITY"


def test_duplicate_object_paths_are_rejected_even_for_distinct_object_ids(
    tmp_path: Path,
) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    objects = copy.deepcopy(payload["objects"])
    assert isinstance(objects, list)
    duplicate = copy.deepcopy(objects[0])
    duplicate["raw_object_id"] = "object-2"  # type: ignore[index]
    objects.append(duplicate)
    payload["objects"] = objects
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")

    assert error.value.code == "INTEGRITY_DUPLICATE_OBJECT_PATH"


@pytest.mark.parametrize(
    "field_mutation",
    [
        lambda payload: payload["requests"][0].update(  # type: ignore[index]
            {"sanitized_endpoint": "not-a-uri"}
        ),
        lambda payload: payload.update({"terms_reference": "not-a-uri"}),
    ],
)
def test_verifier_rejects_invalid_v2_uri_semantics(tmp_path: Path, field_mutation: object) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    if field_mutation is not None:
        field_mutation(payload)  # type: ignore[operator]
    if payload["requests"][0]["sanitized_endpoint"] == "not-a-uri":  # type: ignore[index]
        payload["request_parameters_redacted"]["endpoints"] = ["not-a-uri"]  # type: ignore[index]
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")

    assert error.value.code == "INTEGRITY_MANIFEST_FORMAT"


def test_verifier_classifies_request_summary_mismatch_as_manifest_format(
    tmp_path: Path,
) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    payload["request_parameters_redacted"]["methods"] = ["POST"]  # type: ignore[index]
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")

    assert error.value.code == "INTEGRITY_MANIFEST_FORMAT"


def test_verifier_rejects_unsanitized_pagination_metadata(tmp_path: Path) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    payload["pagination_state"] = {"page": 2, "token": "pagination-secret"}
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")

    assert error.value.code == "INTEGRITY_MANIFEST_FORMAT"


def test_verifier_rejects_object_symlink_before_resolving_containment(
    tmp_path: Path,
) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    object_dir = tmp_path / "raw/fixture/fixture-snapshot/objects"
    symlink_path = object_dir / "link"
    try:
        symlink_path.symlink_to(object_dir / "object-1")
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error}")
    payload["objects"][0]["path"] = "objects/link"  # type: ignore[index]
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")

    assert error.value.code == "INTEGRITY_OBJECT_PATH"


def test_missing_object_is_rejected(tmp_path: Path) -> None:
    _manifest_path, _payload = _complete_snapshot(tmp_path)
    (tmp_path / "raw/fixture/fixture-snapshot/objects/object-1").unlink()

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_OBJECT_MISSING"


def test_wrong_size_is_rejected_before_hash_acceptance(tmp_path: Path) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    objects = copy.deepcopy(payload["objects"])
    assert isinstance(objects, list)
    objects[0]["bytes"] = 999  # type: ignore[index]
    payload["objects"] = objects
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_OBJECT_SIZE_MISMATCH"


def test_object_hash_mismatch_is_rejected(tmp_path: Path) -> None:
    _manifest_path, _payload = _complete_snapshot(tmp_path)
    object_path = tmp_path / "raw/fixture/fixture-snapshot/objects/object-1"
    object_path.write_bytes(b"x" * len(b"exact raw bytes"))

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_OBJECT_HASH_MISMATCH"


def test_duplicate_object_ids_are_rejected_with_stable_code(tmp_path: Path) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    objects = copy.deepcopy(payload["objects"])
    assert isinstance(objects, list)
    objects.append(copy.deepcopy(objects[0]))
    payload["objects"] = objects
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_DUPLICATE_OBJECT_ID"


def test_duplicate_request_ids_are_rejected_with_stable_code(tmp_path: Path) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    requests = copy.deepcopy(payload["requests"])
    assert isinstance(requests, list)
    requests.append(copy.deepcopy(requests[0]))
    payload["requests"] = requests
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_DUPLICATE_REQUEST_ID"


def test_malformed_manifest_is_rejected_without_parsing_objects(tmp_path: Path) -> None:
    manifest_path, _payload = _complete_snapshot(tmp_path)
    manifest_path.write_bytes(b"{not-json")

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_MANIFEST_INVALID"


def test_request_object_lineage_error_is_rejected(tmp_path: Path) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    objects = copy.deepcopy(payload["objects"])
    assert isinstance(objects, list)
    objects[0]["request_id"] = "unknown-request"  # type: ignore[index]
    payload["objects"] = objects
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_REQUEST_OBJECT_LINEAGE"


def test_wrong_snapshot_content_digest_is_rejected(tmp_path: Path) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    payload["snapshot_content_sha256"] = "0" * 64
    _rewrite_manifest(manifest_path, payload)

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_SNAPSHOT_CONTENT_DIGEST"


def test_wrong_detached_manifest_digest_is_rejected(tmp_path: Path) -> None:
    manifest_path, _payload = _complete_snapshot(tmp_path)
    manifest_path.with_name("manifest.sha256").write_text("0" * 64 + "\n", encoding="ascii")

    with pytest.raises(SnapshotIntegrityError) as error:
        verify_complete_snapshot(tmp_path, "fixture", "fixture-snapshot")
    assert error.value.code == "INTEGRITY_MANIFEST_DIGEST"


def test_inspection_reports_recovery_state_without_emitting_records(tmp_path: Path) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    payload["status"] = "FAILED"
    payload["completed_at"] = None
    _rewrite_manifest(manifest_path, payload)

    inspection = SnapshotVerifier(tmp_path).inspect("fixture", "fixture-snapshot")

    assert inspection.consumable is False
    assert inspection.status == "FAILED"
    assert "INTEGRITY_SNAPSHOT_NOT_COMPLETE" in inspection.issue_codes
    assert inspection.record_count == 0


def test_corrupt_snapshot_inspection_never_reports_partial_record_count(tmp_path: Path) -> None:
    manifest_path, payload = _complete_snapshot(tmp_path)
    objects = copy.deepcopy(payload["objects"])
    assert isinstance(objects, list)
    objects[0]["logical_record_count"] = 12  # type: ignore[index]
    payload["objects"] = objects
    _rewrite_manifest(manifest_path, payload)
    (tmp_path / "raw/fixture/fixture-snapshot/objects/object-1").write_bytes(b"corrupt")

    inspection = SnapshotVerifier(tmp_path).inspect("fixture", "fixture-snapshot")

    assert inspection.consumable is False
    assert inspection.issue_codes == ("INTEGRITY_OBJECT_SIZE_MISMATCH",)
    assert inspection.record_count == 0
