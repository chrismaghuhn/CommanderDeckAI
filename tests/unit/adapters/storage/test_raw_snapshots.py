from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commander_ai.adapters.storage import raw_snapshot_objects, raw_snapshots
from commander_ai.adapters.storage.digests import detached_manifest_sha256, snapshot_content_sha256
from commander_ai.domain.provenance import SourceSnapshotRequest


def _request(request_id: str = "request-1") -> SourceSnapshotRequest:
    return SourceSnapshotRequest(
        request_id=request_id,
        sanitized_method="GET",
        sanitized_endpoint="https://fixture.invalid/cards",
        format="json",
        sanitized_parameters={"page": 1},
    )


def _start(
    tmp_path: Path, snapshot_id: str = "fixture-snapshot"
) -> raw_snapshots.RawSnapshotWriter:
    writer = raw_snapshots.RawSnapshotStore(tmp_path).start_snapshot(
        source_id="fixture",
        snapshot_id=snapshot_id,
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-v1",
        usage_status="APPROVED_LOCAL",
        attribution_required=False,
        redistribution_status="not_approved",
        started_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    writer.add_request(_request())
    return writer


def test_streaming_object_uses_same_filesystem_temp_and_preserves_raw_bytes(
    tmp_path: Path,
) -> None:
    writer = _start(tmp_path)
    raw_bytes = b"\x1f\x8b\x00\xffcompressed-entity"

    object_writer = writer.open_object(
        raw_object_id="object-1",
        request_id="request-1",
        content_type="application/octet-stream",
    )
    assert object_writer.temp_path.parent == object_writer.final_path.parent
    assert not object_writer.final_path.exists()

    object_writer.write(raw_bytes[:4])
    object_writer.write(raw_bytes[4:])
    assert not object_writer.final_path.exists()
    reference = object_writer.finalize()

    assert object_writer.final_path.read_bytes() == raw_bytes
    assert reference.bytes == len(raw_bytes)
    assert reference.sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert not list(object_writer.final_path.parent.glob(".object-*"))

    commit = writer.finalize()
    assert writer.state == "COMPLETE"
    assert writer.manifest.status == "COMPLETE"
    assert (
        commit.manifest_path.read_bytes()
        == (tmp_path / "raw/fixture/fixture-snapshot/manifest.json").read_bytes()
    )
    assert (
        commit.detached_manifest_path.read_text(encoding="ascii").strip() == commit.manifest_sha256
    )


def test_finalize_rejects_open_object_writer_before_publishing_complete_manifest(
    tmp_path: Path,
) -> None:
    writer = _start(tmp_path)
    object_writer = writer.open_object(raw_object_id="object-1", request_id="request-1")

    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.finalize()

    assert error.value.code == "ACQ_OBJECTS_OPEN"
    assert writer.state == "INCOMPLETE"
    assert writer.manifest.status == "INCOMPLETE"
    assert writer.manifest_path.read_text(encoding="utf-8").find('"status":"INCOMPLETE"') >= 0

    object_writer.finalize()
    writer.finalize()
    assert writer.state == "COMPLETE"


def test_object_directory_is_flushed_before_complete_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = _start(tmp_path)
    writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"raw"])
    calls: list[Path] = []
    monkeypatch.setattr(raw_snapshots, "fsync_directory", calls.append)

    writer.finalize()

    assert writer.objects_dir in calls
    assert calls.index(writer.objects_dir) < calls.index(writer.snapshot_dir)


def test_request_metadata_is_redacted_again_at_snapshot_persistence_boundary(
    tmp_path: Path,
) -> None:
    writer = _start(tmp_path)
    writer.add_request(
        {
            "request_id": "request-2",
            "sanitized_method": "GET",
            "sanitized_endpoint": "https://fixture.invalid/cards?sig=url-secret",
            "format": "json",
            "sanitized_parameters": {
                "page": 2,
                "format": "json",
                "sig": "signature-secret",
                "signature": "signature-secret-2",
                "accessKey": "access-key-secret",
                "nested": {
                    "safe": "not-an-allowlisted-key",
                    "token": "nested-secret",
                },
            },
        }
    )

    persisted = writer.manifest.requests[-1]
    assert persisted.sanitized_endpoint == "https://fixture.invalid/cards"
    assert persisted.sanitized_parameters == {"format": "json", "page": 2}
    serialized = writer.manifest_path.read_text(encoding="utf-8")
    for secret in (
        "url-secret",
        "signature-secret",
        "signature-secret-2",
        "access-key-secret",
        "nested-secret",
    ):
        assert secret not in serialized
    for key in ("sig", "signature", "accessKey", "token"):
        assert f'"{key}"' not in serialized


def test_finalize_persists_distinct_snapshot_and_detached_manifest_digests(
    tmp_path: Path,
) -> None:
    writer = _start(tmp_path)
    writer.write_object(
        raw_object_id="object-1",
        request_id="request-1",
        chunks=[b"one"],
        retrieved_at=datetime(2026, 8, 11, 1, tzinfo=UTC),
    )
    writer.finalize()

    manifest_payload = writer.manifest.model_dump(mode="json")
    assert writer.manifest.snapshot_content_sha256 == snapshot_content_sha256(
        [manifest_payload["objects"][0]]  # type: ignore[index]
    )
    assert writer.detached_manifest_sha256 == detached_manifest_sha256(manifest_payload)
    assert writer.manifest.snapshot_content_sha256 != writer.detached_manifest_sha256


def test_snapshot_and_object_collisions_never_overwrite_immutable_bytes(tmp_path: Path) -> None:
    writer = _start(tmp_path)
    writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"first"])
    writer.finalize()
    object_path = tmp_path / "raw/fixture/fixture-snapshot/objects/object-1"
    original_manifest = (tmp_path / "raw/fixture/fixture-snapshot/manifest.json").read_bytes()

    with pytest.raises(raw_snapshots.RawSnapshotError) as snapshot_error:
        raw_snapshots.RawSnapshotStore(tmp_path).start_snapshot(
            source_id="fixture",
            snapshot_id="fixture-snapshot",
            approval_status="APPROVED_LOCAL",
            adapter_version="fixture-v1",
            usage_status="APPROVED_LOCAL",
            started_at=datetime(2026, 8, 11, tzinfo=UTC),
        )
    assert snapshot_error.value.code == "ACQ_SNAPSHOT_COLLISION"

    with pytest.raises(raw_snapshots.RawSnapshotError) as object_error:
        writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"second"])
    assert object_error.value.code == "ACQ_SNAPSHOT_FINALIZED"
    assert object_path.read_bytes() == b"first"
    assert (
        tmp_path / "raw/fixture/fixture-snapshot/manifest.json"
    ).read_bytes() == original_manifest


def test_duplicate_object_id_fails_an_incomplete_snapshot_without_overwrite(tmp_path: Path) -> None:
    writer = _start(tmp_path)
    writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"first"])

    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"second"])

    assert error.value.code == "ACQ_OBJECT_COLLISION"
    assert writer.state == "FAILED"
    assert (tmp_path / "raw/fixture/fixture-snapshot/objects/object-1").read_bytes() == b"first"


def test_abandoned_snapshot_is_incomplete_and_not_consumable(tmp_path: Path) -> None:
    writer = _start(tmp_path)
    writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"raw"])

    loaded = raw_snapshots.RawSnapshotStore(tmp_path).load_manifest("fixture", writer.snapshot_id)
    assert loaded.status == "INCOMPLETE"
    assert writer.state == "INCOMPLETE"
    assert (tmp_path / "raw/fixture/fixture-snapshot/objects/object-1").exists()
    assert writer.manifest_path.exists()


def test_stream_failure_leaves_failed_snapshot_without_partial_final_object(tmp_path: Path) -> None:
    writer = _start(tmp_path)

    def failing_chunks() -> object:
        yield b"partial"
        raise OSError("simulated disk failure")

    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.write_object(
            raw_object_id="object-1",
            request_id="request-1",
            chunks=failing_chunks(),  # type: ignore[arg-type]
        )

    assert error.value.code == "ACQ_WRITE_FAILED"
    assert writer.state == "FAILED"
    assert writer.manifest.status == "FAILED"
    assert not (tmp_path / "raw/fixture/fixture-snapshot/objects/object-1").exists()
    assert not list((tmp_path / "raw/fixture/fixture-snapshot/objects").glob(".object-*"))


def test_upstream_checksum_mismatch_keeps_local_digest_distinct_and_fails_snapshot(
    tmp_path: Path,
) -> None:
    writer = _start(tmp_path)
    raw_bytes = b"authoritative compressed bytes"

    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.write_object(
            raw_object_id="object-1",
            request_id="request-1",
            chunks=[raw_bytes],
            upstream_sha256="0" * 64,
        )

    assert error.value.code == "ACQ_UPSTREAM_CHECKSUM_MISMATCH"
    assert writer.state == "FAILED"
    assert writer.manifest.objects[0].sha256 == hashlib.sha256(raw_bytes).hexdigest()
    assert writer.manifest.objects[0].upstream_sha256 == "0" * 64
    assert writer.manifest.objects[0].checksum_verification_status == "mismatch"
    assert (tmp_path / "raw/fixture/fixture-snapshot/objects/object-1").read_bytes() == raw_bytes


def test_finalize_replace_failure_cannot_publish_complete_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = _start(tmp_path)
    writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"raw"])
    original_replace = raw_snapshots.os.replace

    def fail_replace(source: str | bytes | Path, destination: str | bytes | Path) -> None:
        del source, destination
        raise OSError("simulated manifest replace failure")

    monkeypatch.setattr(raw_snapshots.os, "replace", fail_replace)
    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.finalize()

    assert error.value.code == "ACQ_FINALIZE_FAILED"
    assert writer.state == "FAILED"
    monkeypatch.setattr(raw_snapshots.os, "replace", original_replace)
    assert (
        raw_snapshots.RawSnapshotStore(tmp_path).load_manifest("fixture", writer.snapshot_id).status
        == "INCOMPLETE"
    )


def test_object_fsync_failure_leaves_no_final_object_or_temp_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = _start(tmp_path)

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("simulated fsync failure")

    monkeypatch.setattr(raw_snapshot_objects.os, "fsync", fail_fsync)
    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"raw"])

    assert error.value.code == "ACQ_OBJECT_FINALIZE_FAILED"
    assert writer.state == "FAILED"
    object_dir = tmp_path / "raw/fixture/fixture-snapshot/objects"
    assert not (object_dir / "object-1").exists()
    assert not list(object_dir.glob(".object-*"))


def test_write_system_failure_is_namespaced_and_non_consumable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = _start(tmp_path)

    def fail_write(fd: int, data: bytes | bytearray) -> int:
        del fd, data
        raise OSError("simulated write failure")

    monkeypatch.setattr(raw_snapshots.os, "write", fail_write)
    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"raw"])

    assert error.value.code == "ACQ_WRITE_FAILED"
    assert writer.manifest.status == "FAILED"


def test_raw_snapshot_error_detail_is_sanitized_before_exposure() -> None:
    error = raw_snapshots.RawSnapshotError(
        "ACQ_FAILURE",
        "https://fixture.invalid/path?signature=secret Authorization: Bearer header-secret",
    )

    assert "secret" not in str(error)
    assert "header-secret" not in str(error)
