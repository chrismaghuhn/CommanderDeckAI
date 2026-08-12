"""Filesystem-aware policy for portable storage artifact paths."""

from __future__ import annotations

import os
from collections.abc import Sequence
from pathlib import Path

from commander_ai.domain.path_policy import (
    normalize_portable_relative_path as _normalize_portable_relative_path,
)
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

    portable = validate_portable_relative_path(relative_path)
    _reject_symlink_components(root, portable.split("/"))
    resolved_root = _resolved_root(root)
    candidate = _resolved(resolved_root.joinpath(*portable.split("/")))
    _require_below_root(candidate, resolved_root)
    return candidate


def to_portable_relative_path(path: Path | str, root: Path | str) -> str:
    """Convert a contained filesystem path to a normalized POSIX relative path."""

    path_value = os.fspath(path)
    if not isinstance(path_value, str):
        raise TypeError("filesystem paths must be strings or Path values")

    raw_root = _absolute_without_resolving(root)
    _reject_symlink_components(raw_root, ())
    resolved_root = _resolved_root(root)
    candidate = Path(path_value)
    if not candidate.is_absolute():
        portable = validate_portable_relative_path(path_value)
        _reject_symlink_components(raw_root, portable.split("/"))
        candidate = raw_root.joinpath(*portable.split("/"))
    else:
        if any(part in {".", ".."} for part in candidate.parts):
            raise ValueError("filesystem paths must not contain dot segments")
        raw_candidate = _absolute_without_resolving(candidate)
        try:
            raw_relative = raw_candidate.relative_to(raw_root)
        except ValueError as error:
            raise ValueError("path escapes its configured root") from error
        _reject_symlink_components(raw_root, raw_relative.parts)
        candidate = raw_candidate
    resolved_candidate = _resolved(candidate)
    _require_below_root(resolved_candidate, resolved_root)
    relative = resolved_candidate.relative_to(resolved_root).as_posix()
    return normalize_portable_relative_path(relative)


_NON_RELOADABLE_ROOT_MARKERS = frozenset({"<external-root>", "<repository-root>"})


def _resolved(path: Path) -> Path:
    try:
        return path.expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as error:
        raise ValueError("path cannot be resolved safely") from error


def _resolved_root(root: Path | str) -> Path:
    root_value = os.fspath(root)
    if not isinstance(root_value, str):
        raise TypeError("filesystem roots must be strings or Path values")
    if root_value in _NON_RELOADABLE_ROOT_MARKERS:
        raise ValueError("portable snapshot root markers are not filesystem roots")
    return _resolved(Path(root_value))


def _absolute_without_resolving(path: Path | str) -> Path:
    return Path(os.path.abspath(os.fspath(Path(path).expanduser())))


def _reject_symlink_components(root: Path | str, relative_parts: Sequence[str]) -> None:
    current = _absolute_without_resolving(root)
    parts = current.parts
    prefix = Path(parts[0])
    for part in parts[1:]:
        prefix /= part
        if prefix.is_symlink():
            raise ValueError("configured root cannot traverse a symlink")
    for part in relative_parts:
        current /= part
        if current.is_symlink():
            raise ValueError("artifact path cannot traverse a symlink")


def _require_below_root(candidate: Path, root: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("path escapes its configured root") from error
    if relative == Path("."):
        raise ValueError("path must identify an artifact below its configured root")
