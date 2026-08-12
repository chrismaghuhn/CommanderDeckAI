from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commander_ai.adapters.http.transport import HttpTransport, HttpTransportError
from commander_ai.adapters.storage import raw_snapshot_objects, raw_snapshots
from commander_ai.adapters.storage.digests import detached_manifest_sha256, snapshot_content_sha256
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
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
    tmp_path: Path,
    snapshot_id: str = "fixture-snapshot",
    terms_reference: str | None = None,
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
        terms_reference=terms_reference,
    )
    writer.add_request(_request())
    return writer


def test_writer_rejects_hidden_snapshot_id_like_verifier(tmp_path: Path) -> None:
    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        _start(tmp_path, snapshot_id=".valid-snapshot")

    assert error.value.code == "ACQ_SNAPSHOT_ID_INVALID"


def test_writer_rejects_explicit_empty_snapshot_id_instead_of_generating_one(
    tmp_path: Path,
) -> None:
    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        _start(tmp_path, snapshot_id="")

    assert error.value.code == "ACQ_SNAPSHOT_ID_INVALID"


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


def test_invalid_object_metadata_cannot_publish_an_unregistered_raw_blob(tmp_path: Path) -> None:
    writer = _start(tmp_path)

    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.write_object(
            raw_object_id="object-1",
            request_id="request-1",
            chunks=[b"raw"],
            content_encoding="gzip;invalid",
        )

    assert error.value.code == "ACQ_OBJECT_FINALIZE_FAILED"
    assert writer.state == "FAILED"
    assert writer.manifest.objects == ()
    assert not (writer.objects_dir / "object-1").exists()
    assert not list(writer.objects_dir.glob(".object-*"))


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


def test_all_request_metadata_is_redacted_at_the_persistence_boundary(
    tmp_path: Path,
) -> None:
    writer = _start(
        tmp_path,
        terms_reference="https://terms.invalid/policy?token=terms-secret",
    )
    writer.add_request(
        {
            "request_id": "request-2",
            "sanitized_method": "GET",
            "sanitized_endpoint": "https://fixture.invalid/cards",
            "api_version": "v1?api_key=api-secret",
            "format": "json?token=format-secret",
            "sanitized_parameters": {
                "fields": {"page": 2, "token": "nested-secret"},
                "page": 1,
            },
        }
    )

    persisted = writer.manifest.requests[-1]
    assert persisted.api_version is None
    assert persisted.format == "[redacted]"
    assert persisted.sanitized_parameters == {"fields": {"page": 2}, "page": 1}
    assert writer.manifest.terms_reference == "https://terms.invalid/policy"
    serialized = writer.manifest_path.read_text(encoding="utf-8")
    for secret in ("terms-secret", "api-secret", "format-secret", "nested-secret"):
        assert secret not in serialized


def test_writer_normalizes_manifest_method_before_complete_verification(
    tmp_path: Path,
) -> None:
    writer = _start(tmp_path)
    writer.add_request(
        {
            "request_id": "request-2",
            "sanitized_method": "get",
            "sanitized_endpoint": "https://fixture.invalid/cards",
            "format": "json",
            "sanitized_parameters": {},
        }
    )
    writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"raw"])

    writer.finalize()

    assert writer.manifest.requests[-1].sanitized_method == "GET"
    assert SnapshotVerifier(tmp_path).inspect("fixture", writer.snapshot_id).consumable is True


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


def test_http_body_failure_aborts_object_writer_and_closes_snapshot_state(
    tmp_path: Path,
) -> None:
    writer = _start(tmp_path)

    class FailingBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise httpx.ReadError("body-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=FailingBody(), request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    transport = HttpTransport(
        allowed_hosts={"fixture.invalid"},
        client=client,
        rate_limit_per_minute=None,
        user_agent="CommanderDeckAI/Test-1.0",
    )
    response = transport.request("GET", "https://fixture.invalid/body")
    try:
        with pytest.raises(HttpTransportError) as error:
            writer.write_object(
                raw_object_id="object-1",
                request_id="request-1",
                chunks=response.iter_raw(),
            )
    finally:
        transport.close()

    assert error.value.code == "HTTP_ENTITY_STREAM_FAILED"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert writer.state == "FAILED"
    assert writer.manifest.status == "FAILED"
    assert not writer._open_object_ids
    assert not (writer.objects_dir / "object-1").exists()
    assert not list(writer.objects_dir.glob(".object-*"))


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


def test_verified_checksum_requires_an_upstream_checksum_and_comparison(
    tmp_path: Path,
) -> None:
    writer = _start(tmp_path)

    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.write_object(
            raw_object_id="object-1",
            request_id="request-1",
            chunks=[b"raw"],
            checksum_verification_status="verified",
        )

    assert error.value.code == "ACQ_CHECKSUM_STATUS_INVALID"
    assert writer.state == "FAILED"
    assert writer.manifest.status == "FAILED"
    assert not (writer.objects_dir / "object-1").exists()
    assert not list(writer.objects_dir.glob(".object-*"))


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


def test_snapshot_directory_durability_failure_cannot_leave_consumable_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    writer = _start(tmp_path)
    writer.write_object(raw_object_id="object-1", request_id="request-1", chunks=[b"raw"])
    calls: list[Path] = []

    def fail_snapshot_directory(directory: Path) -> None:
        calls.append(directory)
        if directory == writer.snapshot_dir:
            raise OSError("directory durability failure")

    monkeypatch.setattr(raw_snapshots, "fsync_directory", fail_snapshot_directory)
    with pytest.raises(raw_snapshots.RawSnapshotError) as error:
        writer.finalize()

    assert error.value.code == "ACQ_FINALIZE_FAILED"
    assert calls == [writer.objects_dir, writer.snapshot_dir, writer.snapshot_dir]
    assert writer.state == "FAILED"
    loaded = raw_snapshots.RawSnapshotStore(tmp_path).load_manifest("fixture", writer.snapshot_id)
    assert loaded.status == "FAILED"
    inspection = SnapshotVerifier(tmp_path).inspect("fixture", writer.snapshot_id)
    assert inspection.consumable is False
    assert inspection.status == "FAILED"


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
