"""Lossless JSON decoding helpers for the reviewed Spellbook response shape."""

from __future__ import annotations

import json
from collections.abc import Mapping

from .api_models import MalformedJSONScalar


class DuplicateJSONKey(ValueError):
    """Signal a duplicate key without accepting a lossy last-value parse."""


def decode_json(raw_bytes: bytes) -> object:
    return json.loads(
        raw_bytes.decode("utf-8"),
        object_pairs_hook=_pairs_without_duplicates,
        parse_constant=lambda token: MalformedJSONScalar(token),
    )


def decode_pagination_json(raw_bytes: bytes) -> object:
    return json.loads(
        raw_bytes.decode("utf-8"),
        object_pairs_hook=_pairs_without_duplicates,
        parse_constant=_reject_non_finite,
    )


def contains_malformed_value(value: object) -> bool:
    if isinstance(value, MalformedJSONScalar):
        return True
    if isinstance(value, str):
        return any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    if isinstance(value, Mapping):
        return any(
            contains_malformed_value(key) or contains_malformed_value(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(contains_malformed_value(item) for item in value)
    return False


def valid_pagination_envelope(payload: object) -> bool:
    """Return whether a decoded page has the documented structural envelope."""

    if not isinstance(payload, Mapping) or not {
        "count",
        "next",
        "previous",
        "results",
    }.issubset(payload):
        return False
    count = payload["count"]
    return (
        isinstance(count, int)
        and not isinstance(count, bool)
        and count >= 0
        and isinstance(payload["results"], list)
        and (payload["next"] is None or isinstance(payload["next"], str))
        and (payload["previous"] is None or isinstance(payload["previous"], str))
    )


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateJSONKey(key)
        result[key] = value
    return result


def _reject_non_finite(token: str) -> object:
    raise ValueError(f"non-finite JSON constant is not valid pagination JSON: {token}")
