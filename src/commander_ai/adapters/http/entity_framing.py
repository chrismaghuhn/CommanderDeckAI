"""Validation for raw HTTP entity framing metadata."""

from __future__ import annotations


def parse_content_length(value: str | None) -> int | None:
    """Parse a single non-negative Content-Length value."""

    if value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("Content-Length is not an integer") from error
    if parsed < 0:
        raise ValueError("Content-Length cannot be negative")
    return parsed


__all__ = ["parse_content_length"]
