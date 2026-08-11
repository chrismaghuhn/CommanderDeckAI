"""Application boundary for current-use and raw-snapshot normalization gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from commander_ai.domain.provenance import detached_manifest_sha256


class NormalizationRejected(ValueError):
    """Safe rejection with a stable policy or integrity code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RawSnapshotVerificationError(RuntimeError):
    """Port-level failure returned by an immutable raw-snapshot verifier."""

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
    source_manifest_sha256: str | None = None
    verified_snapshot: object | None = None


class NormalizationCoordinator:
    """Authorize normalization only after independent current-use and integrity gates."""

    def __init__(self, policy: CurrentUseGatePort, verifier: RawSnapshotInspectionPort) -> None:
        self._policy = policy
        self._verifier = verifier

    def prepare(self, source_id: str, snapshot_id: str) -> VerifiedNormalizationInput:
        decision = self._policy.check_operation(source_id, "normalize")
        if not decision.allowed:
            raise NormalizationRejected(decision.code)

        verify_complete = getattr(self._verifier, "verify_complete_snapshot", None)
        if callable(verify_complete):
            try:
                verified = verify_complete(source_id, snapshot_id)
            except RawSnapshotVerificationError as error:
                raise NormalizationRejected(error.code) from None
            if not _matches_requested_identity(verified.manifest, source_id, snapshot_id):
                raise NormalizationRejected("INTEGRITY_MANIFEST_IDENTITY")
            return VerifiedNormalizationInput(
                source_id=source_id,
                source_snapshot_id=snapshot_id,
                manifest=verified.manifest,
                source_manifest_sha256=verified.manifest_sha256,
                verified_snapshot=verified,
            )

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
        if not _matches_requested_identity(inspection.manifest, source_id, snapshot_id):
            raise NormalizationRejected("INTEGRITY_MANIFEST_IDENTITY")
        manifest_hash = getattr(inspection, "manifest_sha256", None)
        if manifest_hash is None:
            try:
                manifest_hash = detached_manifest_sha256(
                    inspection.manifest.model_dump(mode="json")
                )
            except (AttributeError, TypeError, ValueError):
                manifest_hash = None
        return VerifiedNormalizationInput(
            source_id=source_id,
            source_snapshot_id=snapshot_id,
            manifest=inspection.manifest,
            source_manifest_sha256=manifest_hash,
        )


def _matches_requested_identity(manifest: object, source_id: str, snapshot_id: str) -> bool:
    return (
        getattr(manifest, "source_id", None) == source_id
        and getattr(manifest, "source_snapshot_id", None) == snapshot_id
    )


__all__ = [
    "CurrentUseGatePort",
    "NormalizationCoordinator",
    "NormalizationRejected",
    "RawSnapshotInspectionPort",
    "RawSnapshotVerificationError",
    "VerifiedNormalizationInput",
]
