from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.application.normalize_snapshot import (
    NormalizationCoordinator,
    NormalizationRejected,
    RawSnapshotVerificationError,
)
from commander_ai.application.source_policy import SourcePolicyDecision
from commander_ai.config.current_use_policy import CurrentUseStatus, PolicyOperation
from commander_ai.domain.provenance import SourceSnapshotRequest


@dataclass(frozen=True)
class Inspection:
    status: str
    consumable: bool
    issue_codes: tuple[str, ...]
    manifest: Any = None


class Policy:
    def __init__(
        self,
        allowed: bool,
        code: str = "POLICY_CURRENT_USE_BLOCKED",
        *,
        bound: bool = True,
    ) -> None:
        self.allowed = allowed
        self.code = code
        self.bound = bound
        self.calls = 0

    def check_operation(self, source_id: str, operation: str) -> SourcePolicyDecision:
        self.calls += 1
        return SourcePolicyDecision(
            source_id=source_id,
            operation=PolicyOperation.normalize(operation),
            allowed=self.allowed,
            code=self.code,
            reason="fixture policy decision",
            historical_status=None,
            current_status=CurrentUseStatus.ALLOWED if self.allowed else None,
            decision_reference=(
                f"current-use.v1:{source_id}:" + "a" * 32 if self.bound and self.allowed else None
            ),
            decision_sha256="a" * 64 if self.bound and self.allowed else None,
        )


class Verifier:
    def __init__(self, result: object | None = None, error: str | None = None) -> None:
        self.result = result
        self.error = error
        self.calls = 0

    def verify_complete_snapshot(self, source_id: str, snapshot_id: str) -> object:
        self.calls += 1
        if self.error is not None:
            raise RawSnapshotVerificationError(self.error)
        return self.result


class InspectOnlyVerifier:
    def __init__(self, inspection: Inspection) -> None:
        self.inspection = inspection
        self.calls = 0

    def inspect(self, source_id: str, snapshot_id: str) -> Inspection:
        self.calls += 1
        return self.inspection


def test_normalize_rejects_incomplete_snapshot_before_parsing() -> None:
    verifier = Verifier(error="INTEGRITY_SNAPSHOT_NOT_COMPLETE")
    coordinator = NormalizationCoordinator(Policy(True), verifier)

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "INTEGRITY_SNAPSHOT_NOT_COMPLETE"
    assert verifier.calls == 1


def test_normalize_rejects_complete_snapshot_with_integrity_failure() -> None:
    verifier = Verifier(error="INTEGRITY_OBJECT_HASH_MISMATCH")
    coordinator = NormalizationCoordinator(Policy(True), verifier)

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "INTEGRITY_OBJECT_HASH_MISMATCH"


def test_normalize_checks_current_use_separately_from_historical_snapshot_status() -> None:
    policy = Policy(False)
    verifier = InspectOnlyVerifier(Inspection("COMPLETE", True, (), manifest="ignored"))
    coordinator = NormalizationCoordinator(policy, verifier)

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "POLICY_CURRENT_USE_BLOCKED"
    assert verifier.calls == 0


def test_normalize_rejects_an_unbound_allowed_policy_decision() -> None:
    coordinator = NormalizationCoordinator(
        Policy(True, code="POLICY_CURRENT_USE_ALLOWED", bound=False),
        Verifier(result=object()),
    )

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "POLICY_DECISION_BINDING"


def test_normalize_rejects_legacy_inspection_even_when_consumable() -> None:
    verifier = InspectOnlyVerifier(Inspection("COMPLETE", True, (), manifest=object()))
    coordinator = NormalizationCoordinator(Policy(True), verifier)

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "INTEGRITY_VERIFIER_REQUIRED"
    assert verifier.calls == 0


def test_normalize_rejects_an_arbitrary_verifier_result() -> None:
    coordinator = NormalizationCoordinator(Policy(True), Verifier(result=object()))

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "INTEGRITY_VERIFICATION_EVIDENCE"


def test_normalize_uses_full_raw_snapshot_verifier_before_parsing(tmp_path: Any) -> None:
    started_at = datetime(2026, 8, 11, tzinfo=UTC)
    writer = RawSnapshotStore(tmp_path).start_snapshot(
        source_id="fixture",
        snapshot_id="snapshot-1",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-v1",
        usage_status="APPROVED_LOCAL",
        started_at=started_at,
    )
    request = SourceSnapshotRequest(
        request_id="request-1",
        sanitized_method="GET",
        sanitized_endpoint="https://fixture.invalid/data",
        format="json",
    )
    writer.add_request(request)
    writer.write_object(
        raw_object_id="object-1",
        request_id="request-1",
        chunks=[b"{}"],
    )
    writer.finalize()

    verifier = SnapshotVerifier(tmp_path)
    coordinator = NormalizationCoordinator(Policy(True), verifier)
    assert coordinator.prepare("fixture", "snapshot-1").manifest.status == "COMPLETE"

    object_path = tmp_path / "raw/fixture/snapshot-1/objects/object-1"
    object_path.write_bytes(b"corrupt")
    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")
    assert error.value.code == "INTEGRITY_OBJECT_SIZE_MISMATCH"
