"""Shared error and lifecycle types for raw snapshot storage."""

from __future__ import annotations

from typing import Literal

from commander_ai.adapters.http.redaction import redact_error_text

SnapshotState = Literal["INCOMPLETE", "COMPLETE", "FAILED"]
ChecksumStatus = Literal["verified", "mismatch", "not_provided", "not_checked", "not_applicable"]


class RawSnapshotError(RuntimeError):
    """Safe acquisition failure carrying a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        safe_detail = redact_error_text(detail)
        message = code if not safe_detail else f"{code}: {safe_detail}"
        super().__init__(message)


__all__ = ["ChecksumStatus", "RawSnapshotError", "SnapshotState"]
