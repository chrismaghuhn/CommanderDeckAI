"""Canonical JSON serialization for persisted artifact metadata."""

from __future__ import annotations

from commander_ai.domain.serialization import canonical_json_bytes as _canonical_json_bytes

__all__ = ["canonical_json_bytes"]


def canonical_json_bytes(value: object) -> bytes:
    """Return exact UTF-8 bytes under the repository canonical JSON contract."""

    return _canonical_json_bytes(value)
