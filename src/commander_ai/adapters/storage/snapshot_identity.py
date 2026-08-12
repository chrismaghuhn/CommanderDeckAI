"""Shared validation for source and snapshot directory components."""

from __future__ import annotations

from .path_policy import validate_portable_relative_path


def validate_snapshot_component(value: object) -> str:
    """Require one non-hidden portable path component for snapshot storage."""

    if (
        not isinstance(value, str)
        or not value
        or value.startswith(".")
        or "/" in value
        or "\\" in value
    ):
        raise ValueError("snapshot identifiers must be single portable path components")
    try:
        validate_portable_relative_path(f"component/{value}")
    except ValueError as error:
        raise ValueError("snapshot identifiers must be single portable path components") from error
    return value


def is_safe_snapshot_component(value: object) -> bool:
    try:
        validate_snapshot_component(value)
    except ValueError:
        return False
    return True


__all__ = ["is_safe_snapshot_component", "validate_snapshot_component"]
