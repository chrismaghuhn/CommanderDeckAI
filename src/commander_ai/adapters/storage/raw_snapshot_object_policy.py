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


def checksum_metadata_code(status: object, upstream_sha256: str | None) -> str | None:
    """Classify persisted checksum metadata before any object is consumed."""

    if status in {"verified", "mismatch"} and (
        upstream_sha256 is None or not valid_upstream_checksum(upstream_sha256)
    ):
        return "INTEGRITY_CHECKSUM_PROVENANCE"
    return None


def checksum_integrity_code(
    status: object, upstream_sha256: str | None, local_sha256: str
) -> str | None:
    """Classify checksum status against the freshly computed local digest."""

    metadata_code = checksum_metadata_code(status, upstream_sha256)
    if metadata_code is not None:
        return metadata_code
    if status == "verified" and upstream_sha256 != local_sha256:
        return "INTEGRITY_UPSTREAM_CHECKSUM_MISMATCH"
    if status == "mismatch":
        return "INTEGRITY_UPSTREAM_CHECKSUM_MISMATCH"
    return None


__all__ = [
    "checksum_integrity_code",
    "checksum_metadata_code",
    "consistent_checksum_status",
    "valid_upstream_checksum",
]
