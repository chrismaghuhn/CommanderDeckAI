"""Application boundary for current-use and raw-snapshot normalization gates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from commander_ai.application.source_policy import SourcePolicyDecision
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.config.source_settings import normalize_source_id
from commander_ai.domain.provenance import SourceSnapshotManifest


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
    def check_operation(self, source_id: str, operation: str) -> SourcePolicyDecision:
        """Return the typed current-use decision for the requested operation."""


class RawSnapshotVerifierPort(Protocol):
    def verify_complete_snapshot(self, source_id: str, snapshot_id: str) -> VerifiedSourceSnapshot:
        """Return nominal evidence after verifying the manifest and every raw object."""


RawSnapshotInspectionPort = RawSnapshotVerifierPort


@dataclass(frozen=True, slots=True)
class VerifiedNormalizationInput:
    source_id: str
    source_snapshot_id: str
    manifest: SourceSnapshotManifest
    source_manifest_sha256: str
    verified_snapshot: VerifiedSourceSnapshot
    policy_decision: SourcePolicyDecision


class NormalizationCoordinator:
    """Authorize normalization only after independent current-use and integrity gates."""

    def __init__(self, policy: CurrentUseGatePort, verifier: RawSnapshotVerifierPort) -> None:
        self._policy = policy
        self._verifier = verifier

    def prepare(self, source_id: str, snapshot_id: str) -> VerifiedNormalizationInput:
        try:
            normalized_source_id = normalize_source_id(source_id)
        except ValueError:
            raise NormalizationRejected("POLICY_SOURCE_ID_INVALID") from None

        decision = self._policy.check_operation(normalized_source_id, PolicyOperation.NORMALIZE)
        if not isinstance(decision, SourcePolicyDecision):
            raise NormalizationRejected("POLICY_DECISION_INVALID")
        if (
            decision.source_id != normalized_source_id
            or decision.operation is not PolicyOperation.NORMALIZE
        ):
            raise NormalizationRejected("POLICY_DECISION_IDENTITY")
        if not decision.allowed:
            raise NormalizationRejected(decision.code)
        if not _has_valid_policy_binding(decision, normalized_source_id):
            raise NormalizationRejected("POLICY_DECISION_BINDING")

        verify_complete = getattr(self._verifier, "verify_complete_snapshot", None)
        if not callable(verify_complete):
            raise NormalizationRejected("INTEGRITY_VERIFIER_REQUIRED")
        try:
            verified = verify_complete(normalized_source_id, snapshot_id)
        except RawSnapshotVerificationError as error:
            raise NormalizationRejected(error.code) from None
        except (OSError, TypeError, ValueError):
            raise NormalizationRejected("INTEGRITY_VERIFICATION_EVIDENCE") from None
        if not isinstance(verified, VerifiedSourceSnapshot):
            raise NormalizationRejected("INTEGRITY_VERIFICATION_EVIDENCE")
        try:
            verified.assert_consistent()
        except (TypeError, ValueError):
            raise NormalizationRejected("INTEGRITY_VERIFICATION_EVIDENCE") from None
        if not _matches_requested_identity(verified, normalized_source_id, snapshot_id):
            raise NormalizationRejected("INTEGRITY_MANIFEST_IDENTITY")
        return VerifiedNormalizationInput(
            source_id=normalized_source_id,
            source_snapshot_id=snapshot_id,
            manifest=verified.manifest,
            source_manifest_sha256=verified.manifest_sha256,
            verified_snapshot=verified,
            policy_decision=decision,
        )


def _has_valid_policy_binding(decision: SourcePolicyDecision, source_id: str) -> bool:
    digest = decision.decision_sha256
    reference = decision.decision_reference
    return (
        isinstance(digest, str)
        and len(digest) == 64
        and all(character in "0123456789abcdef" for character in digest)
        and reference == f"current-use.v1:{source_id}:{digest[:32]}"
    )


def _matches_requested_identity(
    verified: VerifiedSourceSnapshot, source_id: str, snapshot_id: str
) -> bool:
    expected_parts = ("raw", source_id, snapshot_id)
    return (
        verified.manifest.source_id == source_id
        and verified.manifest.source_snapshot_id == snapshot_id
        and verified.snapshot_dir.parts[-3:] == expected_parts
        and verified.manifest_path == verified.snapshot_dir / "manifest.json"
    )


__all__ = [
    "CurrentUseGatePort",
    "NormalizationCoordinator",
    "NormalizationRejected",
    "RawSnapshotInspectionPort",
    "RawSnapshotVerificationError",
    "RawSnapshotVerifierPort",
    "VerifiedNormalizationInput",
]
