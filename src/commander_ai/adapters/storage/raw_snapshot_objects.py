"""Incremental raw-object streaming for the immutable snapshot writer."""

from __future__ import annotations

import hashlib
import os
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from commander_ai.domain.provenance import RawObjectReference

from .path_policy import to_portable_relative_path
from .raw_snapshot_errors import ChecksumStatus, RawSnapshotError


class _RawObjectOwner(Protocol):
    max_object_bytes: int
    snapshot_dir: Path

    def _publish_object(self, temp_path: Path, final_path: Path) -> None: ...

    def _register_object(self, reference: RawObjectReference) -> None: ...

    def _release_object_id(self, raw_object_id: str) -> None: ...

    def _fail(self, code: str, detail: str) -> None: ...


class RawObjectWriter:
    """Keep one response temp file unpublished until fsync and hash completion."""

    def __init__(
        self,
        owner: _RawObjectOwner,
        *,
        raw_object_id: str,
        request_id: str,
        final_path: Path,
        temp_path: Path,
        file_descriptor: int,
        content_type: str | None,
        retrieved_at: datetime,
        source_object_id: str | None,
        upstream_sha256: str | None,
        checksum_verification_status: ChecksumStatus,
        logical_record_count: int | None,
    ) -> None:
        self._owner = owner
        self.raw_object_id = raw_object_id
        self.request_id = request_id
        self.final_path = final_path
        self.temp_path = temp_path
        self._fd = file_descriptor
        self._content_type = content_type
        self._retrieved_at = retrieved_at
        self._source_object_id = source_object_id
        self._upstream_sha256 = upstream_sha256
        self._checksum_status = checksum_verification_status
        self._logical_record_count = logical_record_count
        self._digest = hashlib.sha256()
        self._byte_count = 0
        self._finished = False
        self._reference: RawObjectReference | None = None

    def write(self, chunk: bytes | bytearray | memoryview) -> None:
        if self._finished:
            raise RawSnapshotError("ACQ_OBJECT_FINALIZED", "raw object writer is already closed")
        if not isinstance(chunk, (bytes, bytearray, memoryview)):
            self._abort("ACQ_WRITE_FAILED", "raw response chunks must be bytes")
            raise RawSnapshotError("ACQ_WRITE_FAILED", "raw response chunks must be bytes")
        data = bytes(chunk)
        if self._byte_count + len(data) > self._owner.max_object_bytes:
            self._abort("ACQ_OBJECT_SIZE_LIMIT", "raw object exceeds the configured byte limit")
            raise RawSnapshotError("ACQ_OBJECT_SIZE_LIMIT")
        try:
            view = memoryview(data)
            while view:
                written = os.write(self._fd, view)
                if written <= 0:
                    raise OSError("raw object write made no progress")
                view = view[written:]
        except OSError as error:
            self._abort("ACQ_WRITE_FAILED", "raw object write failed")
            raise RawSnapshotError("ACQ_WRITE_FAILED", "raw object write failed") from error
        self._digest.update(data)
        self._byte_count += len(data)

    def finalize(self) -> RawObjectReference:
        if self._finished:
            if self._reference is None:
                raise RawSnapshotError("ACQ_OBJECT_FINALIZED", "raw object has no reference")
            return self._reference
        digest = self._digest.hexdigest()
        try:
            os.fsync(self._fd)
            os.close(self._fd)
            self._fd = -1
            self._owner._publish_object(self.temp_path, self.final_path)
            checksum_status: ChecksumStatus = self._checksum_status
            if self._upstream_sha256 is not None:
                checksum_status = "verified" if digest == self._upstream_sha256 else "mismatch"
            reference = RawObjectReference(
                raw_object_id=self.raw_object_id,
                request_id=self.request_id,
                retrieved_at=self._retrieved_at,
                path=to_portable_relative_path(self.final_path, self._owner.snapshot_dir),
                bytes=self._byte_count,
                content_type=self._content_type,
                sha256=digest,
                source_object_id=self._source_object_id,
                upstream_sha256=self._upstream_sha256,
                checksum_verification_status=checksum_status,
                logical_record_count=self._logical_record_count,
            )
            self._owner._register_object(reference)
            self._reference = reference
            self._finished = True
            self._owner._release_object_id(self.raw_object_id)
            if checksum_status == "mismatch":
                self._owner._fail("ACQ_UPSTREAM_CHECKSUM_MISMATCH", "upstream checksum mismatch")
                raise RawSnapshotError("ACQ_UPSTREAM_CHECKSUM_MISMATCH")
            return reference
        except RawSnapshotError:
            self._cleanup_temp()
            self._finished = True
            self._owner._release_object_id(self.raw_object_id)
            raise
        except (OSError, ValueError) as error:
            self._cleanup_temp()
            self._finished = True
            self._owner._release_object_id(self.raw_object_id)
            self._owner._fail("ACQ_OBJECT_FINALIZE_FAILED", "raw object finalization failed")
            raise RawSnapshotError("ACQ_OBJECT_FINALIZE_FAILED") from error

    def abort(self) -> None:
        if not self._finished:
            self._abort("ACQ_OBJECT_ABORTED", "raw object write was aborted")

    def __enter__(self) -> RawObjectWriter:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> Literal[False]:
        if exc_type is not None:
            self._abort("ACQ_WRITE_FAILED", "raw object context exited with an error")
            return False
        self.finalize()
        return False

    def _abort(self, code: str, detail: str) -> None:
        self._cleanup_temp()
        self._finished = True
        self._owner._release_object_id(self.raw_object_id)
        self._owner._fail(code, detail)

    def _cleanup_temp(self) -> None:
        if self._fd >= 0:
            with suppress(OSError):
                os.close(self._fd)
            self._fd = -1
        with suppress(FileNotFoundError, OSError):
            self.temp_path.unlink()


__all__ = ["RawObjectWriter"]
