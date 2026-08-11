"""Validate source locators against bytes in a verified raw snapshot."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from commander_ai.adapters.http.content_coding import (
    HttpContentCodingError,
    decode_entity_body,
)
from commander_ai.adapters.storage.archive_safety import (
    ArchiveLimits,
    ArchiveSafetyError,
    read_archive_member,
)
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot

from .raw_locators import (
    ByteRangeLocator,
    JsonObjectEntryLocator,
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
            raw_payload = raw_path.read_bytes()
        except OSError:
            raise ValueError("verified raw object cannot be read") from None
        try:
            payload = decode_entity_body(raw_payload, reference.content_encoding)
        except HttpContentCodingError as error:
            raise ValueError(error.code) from None
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
    elif isinstance(locator.location, JsonObjectEntryLocator):
        _validate_json_object_entry(payload, locator.location)
    elif isinstance(locator.location, RecordIndexLocator):
        _validate_record_index(payload, locator.location.index, reference.logical_record_count)
    elif isinstance(locator.location, ByteRangeLocator) and locator.location.end > len(payload):
        raise ValueError("raw byte range is outside the verified source document")


def _verified_object_path(verified_snapshot: VerifiedSourceSnapshot, raw_object_id: str) -> Path:
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
    if actual_bytes != reference.bytes or digest.hexdigest() != reference.sha256:
        raise ValueError("verified raw object bytes do not match its manifest digest")
    return path


def _validate_json_pointer(payload: bytes, pointer: str) -> None:
    if not pointer:
        return
    try:
        document = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("JSON pointer cannot be resolved in an invalid JSON document") from None
    _resolve_json_pointer(document, pointer)


def _validate_json_object_entry(payload: bytes, locator: JsonObjectEntryLocator) -> None:
    try:
        document = json.loads(
            payload.decode("utf-8"),
            object_pairs_hook=_pairs_without_duplicates,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, _DuplicateJSONKey):
        raise ValueError(
            "JSON object entry locator cannot be resolved in an invalid JSON document"
        ) from None
    parent = _resolve_json_pointer(document, locator.parent_pointer)
    if not isinstance(parent, dict):
        raise ValueError("JSON object entry parent pointer does not identify an object")
    entries = list(parent.items())
    if locator.entry_index >= len(entries):
        raise ValueError("JSON object entry index is outside the verified source document")
    key, value = entries[locator.entry_index]
    key_bytes = _malformed_key_bytes(key)
    if key_bytes is None:
        raise ValueError("JSON object entry does not identify a malformed object key")
    if (
        base64.b64encode(key_bytes).decode("ascii") != locator.key_base64
        or len(key_bytes) != locator.key_byte_length
        or hashlib.sha256(key_bytes).hexdigest() != locator.key_sha256
    ):
        raise ValueError("JSON object entry key metadata does not match the verified source")
    _resolve_json_pointer(value, locator.value_pointer)


def _resolve_json_pointer(document: object, pointer: str) -> object:
    if not pointer:
        return document
    current = document
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
    return current


def _malformed_key_bytes(value: object) -> bytes | None:
    if not isinstance(value, str) or not any(
        0xD800 <= ord(character) <= 0xDFFF for character in value
    ):
        return None
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")


class _DuplicateJSONKey(ValueError):
    pass


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(key)
        result[key] = value
    return result


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
