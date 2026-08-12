"""Digest domains for raw objects, snapshot contents, and detached manifests."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from typing import Protocol, cast

from commander_ai.domain.provenance import DETACHED_MANIFEST_DIGEST_FIELD
from commander_ai.domain.provenance import detached_manifest_sha256 as _detached_manifest_sha256
from commander_ai.domain.serialization import sha256_hex

from .canonical_json import canonical_json_bytes

__all__ = [
    "DETACHED_MANIFEST_DIGEST_FIELD",
    "detached_manifest_sha256",
    "raw_object_sha256",
    "snapshot_content_bytes",
    "snapshot_content_payload",
    "snapshot_content_sha256",
]

_READ_CHUNK_BYTES = 1024 * 1024
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")


class _BinaryReader(Protocol):
    def read(self, size: int = -1, /) -> bytes: ...


def raw_object_sha256(raw: object) -> str:
    """Hash exact bytes, accepting bytes-like values or a binary reader."""

    if isinstance(raw, (bytes, bytearray, memoryview)):
        return sha256_hex(bytes(raw))

    read = getattr(raw, "read", None)
    if not callable(read):
        raise TypeError("raw object input must be bytes or a binary reader")

    reader = cast(_BinaryReader, raw)
    digest = hashlib.sha256()
    while True:
        chunk = reader.read(_READ_CHUNK_BYTES)
        if not isinstance(chunk, bytes):
            raise TypeError("binary readers must return bytes")
        if not chunk:
            return digest.hexdigest()
        digest.update(chunk)


def _snapshot_entry(raw_object: Mapping[str, object]) -> dict[str, object]:
    try:
        raw_object_id = raw_object["raw_object_id"]
        byte_count = raw_object["bytes"]
        sha256 = raw_object["sha256"]
    except KeyError as error:
        raise ValueError("snapshot object metadata is missing a required field") from error

    if not isinstance(raw_object_id, str) or not raw_object_id:
        raise ValueError("raw_object_id must be a non-empty string")
    if type(byte_count) is not int or byte_count < 0:
        raise ValueError("bytes must be a non-negative integer")
    if not isinstance(sha256, str) or _SHA256_PATTERN.fullmatch(sha256) is None:
        raise ValueError("sha256 must be lowercase hexadecimal SHA-256")

    return {"bytes": byte_count, "raw_object_id": raw_object_id, "sha256": sha256}


def snapshot_content_payload(
    objects: Iterable[Mapping[str, object]],
) -> dict[str, list[dict[str, object]]]:
    """Build the exact ordered object-hash document for a snapshot."""

    entries = [_snapshot_entry(raw_object) for raw_object in objects]
    object_ids = [entry["raw_object_id"] for entry in entries]
    if len(object_ids) != len(set(object_ids)):
        raise ValueError("snapshot objects must have unique raw_object_id values")
    entries.sort(key=lambda entry: cast(str, entry["raw_object_id"]))
    return {"objects": entries}


def snapshot_content_bytes(objects: Iterable[Mapping[str, object]]) -> bytes:
    """Return canonical bytes of the ordered snapshot object-hash document."""

    return canonical_json_bytes(snapshot_content_payload(objects))


def snapshot_content_sha256(objects: Iterable[Mapping[str, object]]) -> str:
    """Hash only object IDs, sizes, and exact raw-object SHA-256 values."""

    return sha256_hex(snapshot_content_bytes(objects))


def detached_manifest_sha256(manifest: Mapping[str, object]) -> str:
    """Hash a manifest after omitting only its documented detached digest field."""

    return _detached_manifest_sha256(manifest)
