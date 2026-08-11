"""Immutable raw response storage with crash-safe snapshot finalization."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Literal, cast

from commander_ai.adapters.http.redaction import redact_request_parameters, sanitize_endpoint
from commander_ai.domain.provenance import (
    RawObjectReference,
    SourceSnapshotManifest,
    SourceSnapshotRequest,
    derive_request_parameters_summary,
)

from .canonical_json import canonical_json_bytes
from .digests import detached_manifest_sha256, snapshot_content_sha256
from .path_policy import (
    resolve_under_root,
    validate_portable_relative_path,
)
from .raw_snapshot_errors import ChecksumStatus, RawSnapshotError, SnapshotState
from .raw_snapshot_io import fsync_directory, publish_new, sha256_file, write_temp_file
from .raw_snapshot_objects import RawObjectWriter
from .raw_snapshot_store import RawSnapshotStore


@dataclass(frozen=True, slots=True)
class SnapshotCommit:
    """Paths and digest emitted after a snapshot reaches COMPLETE."""

    source_id: str
    source_snapshot_id: str
    manifest_path: Path
    detached_manifest_path: Path
    manifest_sha256: str


class RawSnapshotWriter:
    """Own one immutable snapshot lifecycle and its object/manifest journal."""

    def __init__(
        self,
        store: RawSnapshotStore,
        *,
        source_id: str,
        snapshot_id: str,
        approval_status: str,
        adapter_version: str,
        usage_status: str,
        attribution_required: bool,
        redistribution_status: Literal["not_approved", "derived_only", "approved"],
        started_at: datetime,
        terms_reference: str | None,
        pagination_state: Mapping[str, object] | None,
        max_object_bytes: int,
    ) -> None:
        self._store = store
        self.source_id = source_id
        self.snapshot_id = snapshot_id
        self.snapshot_dir = store.snapshot_dir(source_id, snapshot_id)
        self.objects_dir = self.snapshot_dir / "objects"
        self.manifest_path = self.snapshot_dir / "manifest.json"
        self.detached_manifest_path = self.snapshot_dir / "manifest.sha256"
        self.max_object_bytes = max_object_bytes
        self._approval_status = approval_status
        self._adapter_version = adapter_version
        self._usage_status = usage_status
        self._attribution_required = attribution_required
        self._redistribution_status = redistribution_status
        self._started_at = started_at
        self._terms_reference = terms_reference
        self._pagination_state = (
            None if pagination_state is None else redact_request_parameters(pagination_state)
        )
        self._requests: list[SourceSnapshotRequest] = []
        self._objects: list[RawObjectReference] = []
        self._open_object_ids: set[str] = set()
        self._state: SnapshotState = "INCOMPLETE"
        self._detached_digest: str | None = None
        self._complete_manifest_published = False
        self._manifest = self._build_manifest("INCOMPLETE", None)
        self._persist_manifest(self._manifest)

    @property
    def state(self) -> SnapshotState:
        return self._state

    @property
    def manifest(self) -> SourceSnapshotManifest:
        return self._manifest

    @property
    def detached_manifest_sha256(self) -> str | None:
        return self._detached_digest

    def add_request(self, request: SourceSnapshotRequest | Mapping[str, object]) -> None:
        self._ensure_incomplete()
        try:
            value = SourceSnapshotRequest.model_validate(request)
            sanitized_endpoint = sanitize_endpoint(value.sanitized_endpoint)
            if sanitized_endpoint == "[redacted-endpoint]":
                raise ValueError("request endpoint is not a safe HTTP URI")
            value = value.model_copy(
                update={
                    "sanitized_endpoint": sanitized_endpoint,
                    "sanitized_parameters": redact_request_parameters(value.sanitized_parameters),
                }
            )
        except (TypeError, ValueError) as error:
            self._fail("ACQ_REQUEST_INVALID", "request metadata is invalid")
            raise RawSnapshotError("ACQ_REQUEST_INVALID") from error
        if any(item.request_id == value.request_id for item in self._requests):
            self._fail("ACQ_REQUEST_COLLISION", "request ID is already registered")
            raise RawSnapshotError("ACQ_REQUEST_COLLISION")
        self._requests.append(value)
        self._persist_manifest(self._build_manifest("INCOMPLETE", None))

    def open_object(
        self,
        *,
        raw_object_id: str,
        request_id: str,
        content_type: str | None = None,
        retrieved_at: datetime | None = None,
        source_object_id: str | None = None,
        upstream_sha256: str | None = None,
        checksum_verification_status: ChecksumStatus = "not_checked",
        logical_record_count: int | None = None,
    ) -> RawObjectWriter:
        self._ensure_incomplete()
        self._validate_object_id(raw_object_id)
        if request_id not in {item.request_id for item in self._requests}:
            self._fail("ACQ_REQUEST_OBJECT_LINEAGE", "object references an unknown request")
            raise RawSnapshotError("ACQ_REQUEST_OBJECT_LINEAGE")
        if raw_object_id in self._open_object_ids or any(
            item.raw_object_id == raw_object_id for item in self._objects
        ):
            self._fail("ACQ_OBJECT_COLLISION", "raw object ID is already registered")
            raise RawSnapshotError("ACQ_OBJECT_COLLISION")
        if upstream_sha256 is not None and (
            len(upstream_sha256) != 64
            or any(char not in "0123456789abcdef" for char in upstream_sha256)
        ):
            self._fail("ACQ_CHECKSUM_INVALID", "upstream checksum is not lowercase SHA-256")
            raise RawSnapshotError("ACQ_CHECKSUM_INVALID")
        if logical_record_count is not None and logical_record_count < 0:
            self._fail("ACQ_OBJECT_METADATA_INVALID", "logical record count must be non-negative")
            raise RawSnapshotError("ACQ_OBJECT_METADATA_INVALID")
        final_path = resolve_under_root(
            self.snapshot_dir, validate_portable_relative_path(f"objects/{raw_object_id}")
        )
        if os.path.lexists(final_path):
            self._fail("ACQ_OBJECT_COLLISION", "final raw object path already exists")
            raise RawSnapshotError("ACQ_OBJECT_COLLISION")
        try:
            descriptor, temp_name = tempfile.mkstemp(prefix=".object-", dir=self.objects_dir)
        except OSError as error:
            self._fail(
                "ACQ_TEMP_CREATE_FAILED", "same-filesystem temporary object could not be created"
            )
            raise RawSnapshotError("ACQ_TEMP_CREATE_FAILED") from error
        temp_path = Path(temp_name)
        self._open_object_ids.add(raw_object_id)
        return RawObjectWriter(
            self,
            raw_object_id=raw_object_id,
            request_id=request_id,
            final_path=final_path,
            temp_path=temp_path,
            file_descriptor=descriptor,
            content_type=content_type,
            retrieved_at=retrieved_at or datetime.now(UTC),
            source_object_id=source_object_id,
            upstream_sha256=upstream_sha256,
            checksum_verification_status=checksum_verification_status,
            logical_record_count=logical_record_count,
        )

    def write_object(
        self,
        *,
        raw_object_id: str,
        request_id: str,
        chunks: Iterable[bytes] | BinaryIO,
        content_type: str | None = None,
        retrieved_at: datetime | None = None,
        source_object_id: str | None = None,
        upstream_sha256: str | None = None,
        checksum_verification_status: ChecksumStatus = "not_checked",
        logical_record_count: int | None = None,
    ) -> RawObjectReference:
        object_writer = self.open_object(
            raw_object_id=raw_object_id,
            request_id=request_id,
            content_type=content_type,
            retrieved_at=retrieved_at,
            source_object_id=source_object_id,
            upstream_sha256=upstream_sha256,
            checksum_verification_status=checksum_verification_status,
            logical_record_count=logical_record_count,
        )
        try:
            for chunk in self._iter_chunks(chunks):
                object_writer.write(chunk)
            return object_writer.finalize()
        except RawSnapshotError:
            if not object_writer._finished:
                object_writer._abort("ACQ_WRITE_FAILED", "raw object write failed")
            raise
        except (OSError, TypeError, ValueError) as error:
            object_writer._abort("ACQ_WRITE_FAILED", "raw object stream failed")
            raise RawSnapshotError("ACQ_WRITE_FAILED", "raw object stream failed") from error

    def finalize(self) -> SnapshotCommit:
        self._ensure_incomplete()
        if self._open_object_ids:
            raise RawSnapshotError("ACQ_OBJECTS_OPEN")
        try:
            for reference in self._objects:
                path = resolve_under_root(self.snapshot_dir, reference.path)
                if not path.is_file() or path.stat().st_size != reference.bytes:
                    raise RawSnapshotError("ACQ_OBJECT_INTEGRITY", "final object metadata mismatch")
                if sha256_file(path) != reference.sha256:
                    raise RawSnapshotError("ACQ_OBJECT_INTEGRITY", "final object digest mismatch")
            fsync_directory(self.objects_dir)
            completed_at = datetime.now(UTC)
            complete_manifest = self._build_manifest("COMPLETE", completed_at)
            manifest_payload = complete_manifest.model_dump(mode="json")
            manifest_bytes = canonical_json_bytes(manifest_payload)
            manifest_digest = detached_manifest_sha256(manifest_payload)
            manifest_temp = write_temp_file(self.snapshot_dir, ".manifest-", manifest_bytes)
            sidecar_temp = write_temp_file(
                self.snapshot_dir, ".manifest-digest-", f"{manifest_digest}\n".encode("ascii")
            )
            publish_new(sidecar_temp, self.detached_manifest_path)
            os.replace(manifest_temp, self.manifest_path)
            self._complete_manifest_published = True
            fsync_directory(self.snapshot_dir)
            self._manifest = complete_manifest
            self._detached_digest = manifest_digest
            self._state = "COMPLETE"
            return SnapshotCommit(
                source_id=self.source_id,
                source_snapshot_id=self.snapshot_id,
                manifest_path=self.manifest_path,
                detached_manifest_path=self.detached_manifest_path,
                manifest_sha256=manifest_digest,
            )
        except RawSnapshotError:
            self._fail("ACQ_FINALIZE_FAILED", "snapshot finalization failed")
            raise
        except (OSError, ValueError, TypeError) as error:
            self._fail("ACQ_FINALIZE_FAILED", "snapshot finalization failed")
            raise RawSnapshotError("ACQ_FINALIZE_FAILED") from error

    def _register_object(self, reference: RawObjectReference) -> None:
        if self._state != "INCOMPLETE" or self._complete_manifest_published:
            raise RawSnapshotError("ACQ_SNAPSHOT_FINALIZED")
        if any(item.path == reference.path for item in self._objects):
            raise RawSnapshotError("ACQ_OBJECT_PATH_COLLISION")
        self._objects.append(reference)
        self._persist_manifest(self._build_manifest("INCOMPLETE", None))

    def _publish_object(self, temp_path: Path, final_path: Path) -> None:
        try:
            publish_new(temp_path, final_path)
        except FileExistsError as error:
            raise RawSnapshotError("ACQ_OBJECT_COLLISION") from error
        except OSError as error:
            raise RawSnapshotError("ACQ_ATOMIC_FINALIZE_FAILED") from error

    def _persist_manifest(self, manifest: SourceSnapshotManifest) -> None:
        if self._complete_manifest_published or (
            self._state == "COMPLETE" and manifest.status != "COMPLETE"
        ):
            raise RawSnapshotError("ACQ_SNAPSHOT_FINALIZED")
        payload = canonical_json_bytes(manifest.model_dump(mode="json"))
        try:
            temp_path = write_temp_file(self.snapshot_dir, ".manifest-write-", payload)
            os.replace(temp_path, self.manifest_path)
            fsync_directory(self.snapshot_dir)
        except (OSError, TypeError, ValueError) as error:
            self._state = "FAILED"
            self._manifest = manifest.model_copy(update={"status": "FAILED", "completed_at": None})
            raise RawSnapshotError("ACQ_MANIFEST_WRITE_FAILED") from error
        self._manifest = manifest

    def _fail(self, code: str, detail: str) -> None:
        if self._state == "COMPLETE" or self._complete_manifest_published:
            return
        self._state = "FAILED"
        failed = self._build_manifest("FAILED", datetime.now(UTC))
        self._manifest = failed
        with suppress(RawSnapshotError):
            self._persist_manifest(failed)
        with suppress(FileNotFoundError, OSError):
            self.detached_manifest_path.unlink()

    def _build_manifest(
        self, status: SnapshotState, completed_at: datetime | None
    ) -> SourceSnapshotManifest:
        objects = tuple(self._objects)
        object_payloads = [item.model_dump(mode="json") for item in objects]
        return SourceSnapshotManifest(
            source_id=self.source_id,
            source_snapshot_id=self.snapshot_id,
            status=status,
            approval_status=cast(
                Literal["APPROVED_LOCAL", "APPROVED_REDISTRIBUTION"], self._approval_status
            ),
            adapter_version=self._adapter_version,
            started_at=self._started_at,
            completed_at=completed_at,
            terms_reference=self._terms_reference,
            usage_status=self._usage_status,
            request_parameters_redacted=derive_request_parameters_summary(self._requests),
            requests=tuple(self._requests),
            objects=objects,
            pagination_state=self._pagination_state,
            attribution_required=self._attribution_required,
            redistribution_status=self._redistribution_status,
            snapshot_content_sha256=snapshot_content_sha256(object_payloads),
        )

    def _ensure_incomplete(self) -> None:
        if self._state == "COMPLETE":
            raise RawSnapshotError("ACQ_SNAPSHOT_FINALIZED")
        if self._complete_manifest_published:
            raise RawSnapshotError("ACQ_SNAPSHOT_FINALIZING")
        if self._state == "FAILED":
            raise RawSnapshotError("ACQ_SNAPSHOT_FAILED")

    def _release_object_id(self, raw_object_id: str) -> None:
        self._open_object_ids.discard(raw_object_id)

    @staticmethod
    def _validate_object_id(raw_object_id: str) -> None:
        if (
            not isinstance(raw_object_id, str)
            or not raw_object_id
            or "/" in raw_object_id
            or "\\" in raw_object_id
        ):
            raise RawSnapshotError("ACQ_OBJECT_ID_INVALID")
        try:
            validate_portable_relative_path(f"objects/{raw_object_id}")
        except ValueError as error:
            raise RawSnapshotError("ACQ_OBJECT_ID_INVALID") from error

    @staticmethod
    def _iter_chunks(chunks: Iterable[bytes] | BinaryIO) -> Iterable[bytes]:
        read = getattr(chunks, "read", None)
        if callable(read):
            while True:
                chunk = read(1024 * 1024)
                if not chunk:
                    return
                yield chunk
            return
        yield from chunks


__all__ = [
    "RawObjectWriter",
    "RawSnapshotError",
    "RawSnapshotStore",
    "RawSnapshotWriter",
    "SnapshotCommit",
]
