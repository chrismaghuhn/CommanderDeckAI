"""Source-neutral portable path validation and root containment."""

from __future__ import annotations

import os
from pathlib import Path

__all__ = [
    "normalize_portable_relative_path",
    "resolve_under_root",
    "to_portable_relative_path",
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
        segment in {"", ".", ".."} or segment in _NON_RELOADABLE_ROOT_MARKERS
        for segment in segments
    ):
        raise ValueError("path must not contain empty, '.', '..', or root-marker segments")
    return value


def normalize_portable_relative_path(value: str) -> str:
    """Validate and return the path without changing its portable spelling."""

    return validate_portable_relative_path(value)


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


def _require_below_root(candidate: Path, root: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError("path escapes its configured root") from error
    if relative == Path("."):
        raise ValueError("path must identify an artifact below its configured root")


def resolve_under_root(root: Path | str, relative_path: str) -> Path:
    """Resolve a portable relative path while rejecting symlink escapes."""

    portable = validate_portable_relative_path(relative_path)
    resolved_root = _resolved_root(root)
    candidate = _resolved(resolved_root.joinpath(*portable.split("/")))
    _require_below_root(candidate, resolved_root)
    return candidate


def to_portable_relative_path(path: Path | str, root: Path | str) -> str:
    """Return a normalized POSIX path after root-containment verification."""

    path_value = os.fspath(path)
    if not isinstance(path_value, str):
        raise TypeError("filesystem paths must be strings or Path values")

    resolved_root = _resolved_root(root)
    candidate = Path(path_value)
    if not candidate.is_absolute():
        portable = validate_portable_relative_path(path_value)
        candidate = resolved_root.joinpath(*portable.split("/"))
    resolved_candidate = _resolved(candidate)
    _require_below_root(resolved_candidate, resolved_root)
    relative = resolved_candidate.relative_to(resolved_root).as_posix()
    return normalize_portable_relative_path(relative)
