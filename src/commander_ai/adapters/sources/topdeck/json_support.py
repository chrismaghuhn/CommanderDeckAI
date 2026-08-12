"""Strict JSON decoding and lossless source-value safety for TopDeck."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass


class DuplicateJSONKey(ValueError):
    """The raw JSON object contains a duplicate key."""


@dataclass(frozen=True, slots=True)
class MalformedJSONScalar:
    """Marker for a JSON-compatible but non-standard numeric scalar."""

    token: str


def decode_json(raw_bytes: bytes) -> object:
    """Decode UTF-8 JSON while retaining duplicate/non-finite findings."""

    return json.loads(
        raw_bytes.decode("utf-8"),
        object_pairs_hook=_pairs_without_duplicates,
        parse_constant=MalformedJSONScalar,
    )


def contains_malformed_value(value: object) -> bool:
    if isinstance(value, MalformedJSONScalar):
        return True
    if isinstance(value, Mapping):
        return any(contains_malformed_value(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_malformed_value(item) for item in value)
    return False


def json_safe_source_value(value: object) -> object:
    """Convert parser-only markers and bytes into deterministic JSON values."""

    if isinstance(value, MalformedJSONScalar):
        raw = value.token.encode("ascii")
        return {
            "encoding": "base64",
            "data": base64.b64encode(raw).decode("ascii"),
            "byte_length": len(raw),
            "scalar_type": "non_finite_number",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {
            "encoding": "base64",
            "data": base64.b64encode(raw).decode("ascii"),
            "byte_length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raw = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        return {
            "encoding": "base64",
            "data": base64.b64encode(raw).decode("ascii"),
            "byte_length": len(raw),
            "scalar_type": "invalid_unicode_scalar",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if isinstance(value, Mapping):
        return {str(key): json_safe_source_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_source_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_safe_source_value(item) for item in sorted(value, key=str)]
    return value


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKey(key)
        result[key] = value
    return result


__all__ = [
    "DuplicateJSONKey",
    "MalformedJSONScalar",
    "contains_malformed_value",
    "decode_json",
    "json_safe_source_value",
]
