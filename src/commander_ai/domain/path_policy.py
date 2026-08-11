"""Source-neutral validation for persisted portable path strings."""

from __future__ import annotations

__all__ = [
    "normalize_portable_relative_path",
    "validate_portable_relative_path",
]

_NON_RELOADABLE_ROOT_MARKERS = frozenset({"<external-root>", "<repository-root>"})


def validate_portable_relative_path(value: str) -> str:
    """Require a nonempty root-relative POSIX path with no host syntax."""

    if not isinstance(value, str):
        raise TypeError("path must be a string")
    if (
        not value
        or value.startswith("/")
        or value.startswith("~")
        or "\\" in value
        or "\x00" in value
        or (
            len(value) >= 2
            and value[0] in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            and value[1] == ":"
        )
    ):
        raise ValueError("path must be a portable root-relative POSIX path")

    segments = value.split("/")
    if any(
        segment in {"", ".", ".."}
        or segment.startswith("~")
        or segment in _NON_RELOADABLE_ROOT_MARKERS
        for segment in segments
    ):
        raise ValueError("path must not contain empty, '.', '..', tilde, or root-marker segments")
    return value


def normalize_portable_relative_path(value: str) -> str:
    """Validate and return the path without changing its portable spelling."""

    return validate_portable_relative_path(value)
