"""Application boundary for current-use and raw-snapshot normalization gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class NormalizationRejected(ValueError):
    """Safe rejection with a stable policy or integrity code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CurrentUseGatePort(Protocol):
    def check_operation(self, source_id: str, operation: str) -> Any:
        """Return an object with ``allowed`` and safe ``code`` attributes."""


class RawSnapshotInspectionPort(Protocol):
    def inspect(self, source_id: str, snapshot_id: str) -> Any:
        """Return a complete integrity inspection, not only manifest status."""


@dataclass(frozen=True, slots=True)
class VerifiedNormalizationInput:
    source_id: str
    source_snapshot_id: str
    manifest: object


class NormalizationCoordinator:
    """Authorize normalization only after independent current-use and integrity gates."""

    def __init__(self, policy: CurrentUseGatePort, verifier: RawSnapshotInspectionPort) -> None:
        self._policy = policy
        self._verifier = verifier

    def prepare(self, source_id: str, snapshot_id: str) -> VerifiedNormalizationInput:
        decision = self._policy.check_operation(source_id, "normalize")
        if not decision.allowed:
            raise NormalizationRejected(decision.code)
        inspection = self._verifier.inspect(source_id, snapshot_id)
        if inspection.status != "COMPLETE":
            code = (
                inspection.issue_codes[0]
                if inspection.issue_codes
                else "INTEGRITY_SNAPSHOT_NOT_COMPLETE"
            )
            raise NormalizationRejected(code)
        if not inspection.consumable or inspection.manifest is None:
            code = inspection.issue_codes[0] if inspection.issue_codes else "INTEGRITY_UNKNOWN"
            raise NormalizationRejected(code)
        return VerifiedNormalizationInput(
            source_id=source_id,
            source_snapshot_id=snapshot_id,
            manifest=inspection.manifest,
        )


__all__ = [
    "CurrentUseGatePort",
    "NormalizationCoordinator",
    "NormalizationRejected",
    "RawSnapshotInspectionPort",
    "VerifiedNormalizationInput",
]
