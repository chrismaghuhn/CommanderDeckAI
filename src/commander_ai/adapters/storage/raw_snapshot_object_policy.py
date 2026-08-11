"""Validation rules for raw-object checksum metadata."""

from __future__ import annotations


def valid_upstream_checksum(value: object) -> bool:
    return value is None or (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def consistent_checksum_status(status: object, upstream_sha256: str | None) -> bool:
    valid_statuses = {
        "verified",
        "mismatch",
        "not_provided",
        "not_checked",
        "not_applicable",
    }
    return (
        isinstance(status, str)
        and status in valid_statuses
        and not (upstream_sha256 is None and status in {"verified", "mismatch"})
    )


__all__ = ["consistent_checksum_status", "valid_upstream_checksum"]
