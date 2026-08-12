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
    for segment in segments:
        device_stem = segment.rstrip(". ").split(".", maxsplit=1)[0].casefold()
        is_device_name = device_stem in {
            "con",
            "prn",
            "aux",
            "nul",
            "clock$",
            "conin$",
            "conout$",
        } or (
            len(device_stem) == 4
            and device_stem[:3] in {"com", "lpt"}
            and device_stem[3] in "123456789"
        )
        if (
            segment in {"", ".", ".."}
            or segment.startswith("~")
            or segment in _NON_RELOADABLE_ROOT_MARKERS
            or ":" in segment
            or segment.endswith((".", " "))
            or is_device_name
            or any(char in '<>"|?*' or ord(char) < 0x20 for char in segment)
        ):
            raise ValueError("path contains a platform-special or non-portable segment")
    return value


def normalize_portable_relative_path(value: str) -> str:
    """Validate and return the path without changing its portable spelling."""

    return validate_portable_relative_path(value)
