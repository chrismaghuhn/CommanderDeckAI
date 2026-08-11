"""Validate source locators against bytes in a verified raw snapshot."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from commander_ai.adapters.storage.archive_safety import (
    ArchiveLimits,
    ArchiveSafetyError,
    read_archive_member,
)
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot

from .raw_locators import (
    ByteRangeLocator,
    JsonPointerLocator,
    RawLocator,
    RawLocatorValidationError,
    RecordIndexLocator,
)


def validate_raw_locator_against_snapshot(
    locator: RawLocator,
    *,
    verified_snapshot: VerifiedSourceSnapshot,
    source_id: str | None = None,
    raw_sha256: str | None = None,
    archive_limits: ArchiveLimits | None = None,
) -> None:
    """Fail closed unless the exact member/document locator exists in evidence."""

    verified_snapshot.assert_consistent()
    manifest = verified_snapshot.manifest
    if locator.source_id != manifest.source_id:
        raise ValueError("raw locator source_id does not match verified snapshot")
    if source_id is not None and source_id != manifest.source_id:
        raise ValueError("raw locator source_id does not match verified snapshot")
    if locator.source_snapshot_id != manifest.source_snapshot_id:
        raise ValueError("raw locator source_snapshot_id does not match verified snapshot")
    reference = verified_snapshot.object_index.get(locator.raw_object_id)
    if reference is None:
        raise ValueError("raw locator raw_object_id is absent from verified snapshot")
    if locator.raw_object_path != reference.path:
        raise ValueError("raw locator path does not match verified source object")
    if raw_sha256 is not None and raw_sha256 != reference.sha256:
        raise ValueError("raw locator sha256 does not match verified source object")
    raw_path = _verified_object_path(verified_snapshot, locator.raw_object_id)
    if locator.archive_member is None:
        try:
            payload = raw_path.read_bytes()
        except OSError:
            raise ValueError("verified raw object cannot be read") from None
    else:
        try:
            payload = read_archive_member(
                raw_path,
                locator.archive_member,
                limits=archive_limits,
            )
        except ArchiveSafetyError as error:
            raise RawLocatorValidationError(
                f"archive member validation failed: {error.code.lower()}",
                code=error.code,
            ) from None
    if isinstance(locator.location, JsonPointerLocator):
        _validate_json_pointer(payload, locator.location.pointer)
    elif isinstance(locator.location, RecordIndexLocator):
        _validate_record_index(payload, locator.location.index, reference.logical_record_count)
    elif isinstance(locator.location, ByteRangeLocator) and locator.location.end > len(payload):
        raise ValueError("raw byte range is outside the verified source document")


def _verified_object_path(
    verified_snapshot: VerifiedSourceSnapshot, raw_object_id: str
) -> Path:
    reference = verified_snapshot.object_index[raw_object_id]
    path = verified_snapshot.object_paths[raw_object_id]
    try:
        digest = hashlib.sha256()
        actual_bytes = 0
        with path.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                actual_bytes += len(chunk)
                digest.update(chunk)
    except OSError:
        raise ValueError("verified raw object cannot be read") from None
    if (
        actual_bytes != reference.bytes
        or digest.hexdigest() != reference.sha256
    ):
        raise ValueError("verified raw object bytes do not match its manifest digest")
    return path


def _validate_json_pointer(payload: bytes, pointer: str) -> None:
    if not pointer:
        return
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("JSON pointer cannot be resolved in an invalid JSON document") from None
    current: object = document
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"JSON pointer {pointer} is missing")
            current = current[token]
        elif (
            isinstance(current, list)
            and token.isdigit()
            and (token == "0" or not token.startswith("0"))
        ):
            index = int(token)
            if index >= len(current):
                raise ValueError(f"JSON pointer {pointer} is missing")
            current = current[index]
        else:
            raise ValueError(f"JSON pointer {pointer} is missing")


def _validate_record_index(payload: bytes, index: int, expected_count: int | None) -> None:
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("record index cannot be resolved in an invalid JSON document") from None
    if not isinstance(document, list) or index >= len(document):
        raise ValueError("raw record index is outside the verified source document")
    if expected_count is not None and len(document) != expected_count:
        raise ValueError("verified record count does not match the source document")


__all__ = ["RawLocatorValidationError", "validate_raw_locator_against_snapshot"]
