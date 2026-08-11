"""Strict JSON decoding and JSON-safe source values for Spicerack."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass


class DuplicateJSONKey(ValueError):
    """A source object contained a duplicate key."""


@dataclass(frozen=True, slots=True)
class MalformedJSONScalar:
    token: str


def decode_json(raw_bytes: bytes) -> object:
    return json.loads(
        raw_bytes.decode("utf-8"),
        object_pairs_hook=_pairs_without_duplicates,
        parse_constant=MalformedJSONScalar,
    )


def json_safe_source_value(value: object) -> object:
    if isinstance(value, MalformedJSONScalar):
        raw = value.token.encode("ascii")
        return _encoded(raw, scalar_type="non_finite_number")
    if isinstance(value, (bytes, bytearray, memoryview)):
        return _encoded(bytes(value))
    if isinstance(value, str) and any(0xD800 <= ord(char) <= 0xDFFF for char in value):
        raw = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        return _encoded(raw, scalar_type="invalid_unicode_scalar")
    if isinstance(value, Mapping):
        return {str(key): json_safe_source_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_source_value(item) for item in value]
    return value


def contains_malformed_json_scalar(value: object) -> bool:
    """Return whether a preserved source projection contains a malformed scalar."""

    if isinstance(value, Mapping):
        scalar_type = value.get("scalar_type")
        if scalar_type in {"non_finite_number", "invalid_unicode_scalar"}:
            return True
        return any(contains_malformed_json_scalar(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(contains_malformed_json_scalar(item) for item in value)
    return False


def _encoded(raw: bytes, *, scalar_type: str | None = None) -> dict[str, object]:
    result: dict[str, object] = {
        "encoding": "base64",
        "data": base64.b64encode(raw).decode("ascii"),
        "byte_length": len(raw),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if scalar_type is not None:
        result["scalar_type"] = scalar_type
    return result


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
    "contains_malformed_json_scalar",
    "decode_json",
    "json_safe_source_value",
]
