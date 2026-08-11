"""Shared error and lifecycle types for raw snapshot storage."""

from __future__ import annotations

from typing import Literal

SnapshotState = Literal["INCOMPLETE", "COMPLETE", "FAILED"]
ChecksumStatus = Literal["verified", "mismatch", "not_provided", "not_checked", "not_applicable"]


class RawSnapshotError(RuntimeError):
    """Safe acquisition failure carrying a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        message = code if not detail else f"{code}: {detail}"
        super().__init__(message)


__all__ = ["ChecksumStatus", "RawSnapshotError", "SnapshotState"]
