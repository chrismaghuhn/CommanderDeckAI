"""Lossless JSON scalar handling for malformed MTGJSON source values."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

MalformedScalarKind = Literal["non_finite_number", "invalid_unicode_scalar"]
MalformedScalarEncoding = Literal["ascii", "json_escaped"]


@dataclass(frozen=True, slots=True)
class MalformedJSONScalar:
    """A source JSON lexeme that cannot enter canonical semantics."""

    kind: MalformedScalarKind
    raw_bytes: bytes
    encoding: MalformedScalarEncoding


def malformed_json_constant(token: str) -> MalformedJSONScalar:
    """Retain a JSON decoder constant instead of converting it to a float."""

    return MalformedJSONScalar(
        kind="non_finite_number",
        raw_bytes=token.encode("ascii"),
        encoding="ascii",
    )


def sanitize_json_scalars(value: object) -> object:
    """Replace malformed scalars while preserving all other source values."""

    if isinstance(value, MalformedJSONScalar):
        return value
    if isinstance(value, float) and not math.isfinite(value):
        return malformed_json_constant(_constant_token(value))
    if isinstance(value, str):
        return _sanitize_text(value)
    if isinstance(value, Mapping):
        return {key: sanitize_json_scalars(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_json_scalars(item) for item in value]
    return value


def find_malformed_scalars(
    value: object, path: str = ""
) -> tuple[tuple[str, MalformedJSONScalar], ...]:
    """Return malformed scalar locations in deterministic traversal order."""

    if isinstance(value, MalformedJSONScalar):
        return ((path or "$", value),)
    if isinstance(value, Mapping):
        findings: list[tuple[str, MalformedJSONScalar]] = []
        for key, item in value.items():
            key_text = str(key)
            child_path = f"{path}/{_escape_pointer(key_text)}"
            findings.extend(find_malformed_scalars(item, child_path))
        return tuple(findings)
    if isinstance(value, (list, tuple)):
        findings = []
        for index, item in enumerate(value):
            findings.extend(find_malformed_scalars(item, f"{path}/{index}"))
        return tuple(findings)
    return ()


def scalar_envelope(value: MalformedJSONScalar) -> dict[str, object]:
    """Return a deterministic JSON-safe representation of one malformed lexeme."""

    return {
        "encoding": "base64",
        "data": base64.b64encode(value.raw_bytes).decode("ascii"),
        "representation": value.encoding,
        "scalar_type": value.kind,
        "byte_length": len(value.raw_bytes),
        "sha256": hashlib.sha256(value.raw_bytes).hexdigest(),
    }


def _sanitize_text(value: str) -> str | MalformedJSONScalar:
    if not any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        return value
    normalized: list[str] = []
    index = 0
    while index < len(value):
        codepoint = ord(value[index])
        if 0xD800 <= codepoint <= 0xDBFF:
            if index + 1 < len(value) and 0xDC00 <= ord(value[index + 1]) <= 0xDFFF:
                pair = 0x10000 + ((codepoint - 0xD800) << 10) + (ord(value[index + 1]) - 0xDC00)
                normalized.append(chr(pair))
                index += 2
                continue
            return _invalid_unicode_scalar(value)
        if 0xDC00 <= codepoint <= 0xDFFF:
            return _invalid_unicode_scalar(value)
        normalized.append(value[index])
        index += 1
    return "".join(normalized)


def _invalid_unicode_scalar(value: str) -> MalformedJSONScalar:
    escaped = json.dumps(value, ensure_ascii=True, separators=(",", ":"))
    return MalformedJSONScalar(
        kind="invalid_unicode_scalar",
        raw_bytes=escaped.encode("ascii"),
        encoding="json_escaped",
    )


def _constant_token(value: float) -> str:
    if math.isnan(value):
        return "NaN"
    return "-Infinity" if value < 0 else "Infinity"


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


__all__ = [
    "MalformedJSONScalar",
    "find_malformed_scalars",
    "malformed_json_constant",
    "sanitize_json_scalars",
    "scalar_envelope",
]
