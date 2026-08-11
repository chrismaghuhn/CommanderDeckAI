"""Storage-facing exports for the shared portable path policy."""

from __future__ import annotations

from pathlib import Path

from commander_ai.domain.path_policy import (
    normalize_portable_relative_path as _normalize_portable_relative_path,
)
from commander_ai.domain.path_policy import resolve_under_root as _resolve_under_root
from commander_ai.domain.path_policy import to_portable_relative_path as _to_portable_relative_path
from commander_ai.domain.path_policy import (
    validate_portable_relative_path as _validate_portable_relative_path,
)

__all__ = [
    "normalize_portable_relative_path",
    "resolve_under_root",
    "to_portable_relative_path",
    "validate_portable_relative_path",
]


def validate_portable_relative_path(value: str) -> str:
    """Validate a persisted path using the shared source-neutral policy."""

    return _validate_portable_relative_path(value)


def normalize_portable_relative_path(value: str) -> str:
    """Return a validated POSIX relative path without changing its spelling."""

    return _normalize_portable_relative_path(value)


def resolve_under_root(root: Path | str, relative_path: str) -> Path:
    """Resolve a persisted path under a configured root without symlink escape."""

    return _resolve_under_root(root, relative_path)


def to_portable_relative_path(path: Path | str, root: Path | str) -> str:
    """Convert a contained filesystem path to a normalized POSIX relative path."""

    return _to_portable_relative_path(path, root)
