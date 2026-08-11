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
)
from commander_ai.domain.provenance import SourceSnapshotRequest


@dataclass(frozen=True)
class Inspection:
    status: str
    consumable: bool
    issue_codes: tuple[str, ...]
    manifest: Any = None


def verified_manifest(source_id: str = "fixture", snapshot_id: str = "snapshot-1") -> Any:
    return type(
        "Manifest",
        (),
        {"source_id": source_id, "source_snapshot_id": snapshot_id},
    )()


class Policy:
    def __init__(self, allowed: bool, code: str = "POLICY_CURRENT_USE_BLOCKED") -> None:
        self.allowed = allowed
        self.code = code
        self.calls = 0

    def check_operation(self, source_id: str, operation: str) -> Any:
        self.calls += 1
        return type("Decision", (), {"allowed": self.allowed, "code": self.code})()


class Verifier:
    def __init__(self, inspection: Inspection) -> None:
        self.inspection = inspection
        self.calls = 0

    def inspect(self, source_id: str, snapshot_id: str) -> Inspection:
        self.calls += 1
        return self.inspection


def test_normalize_rejects_incomplete_snapshot_before_parsing() -> None:
    verifier = Verifier(Inspection("INCOMPLETE", False, ("INTEGRITY_SNAPSHOT_NOT_COMPLETE",)))
    coordinator = NormalizationCoordinator(Policy(True), verifier)

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "INTEGRITY_SNAPSHOT_NOT_COMPLETE"
    assert verifier.calls == 1


def test_normalize_rejects_complete_snapshot_with_integrity_failure() -> None:
    verifier = Verifier(Inspection("COMPLETE", False, ("INTEGRITY_OBJECT_HASH_MISMATCH",)))
    coordinator = NormalizationCoordinator(Policy(True), verifier)

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "INTEGRITY_OBJECT_HASH_MISMATCH"


def test_normalize_checks_current_use_separately_from_historical_snapshot_status() -> None:
    policy = Policy(False)
    verifier = Verifier(Inspection("COMPLETE", True, (), manifest="verified"))
    coordinator = NormalizationCoordinator(policy, verifier)

    with pytest.raises(NormalizationRejected) as error:
        coordinator.prepare("fixture", "snapshot-1")

    assert error.value.code == "POLICY_CURRENT_USE_BLOCKED"
    assert verifier.calls == 0


def test_normalize_returns_verified_manifest_only_after_both_gates() -> None:
    manifest = verified_manifest()
    verifier = Verifier(Inspection("COMPLETE", True, (), manifest=manifest))
    result = NormalizationCoordinator(Policy(True), verifier).prepare("fixture", "snapshot-1")

    assert result.manifest == manifest


def test_normalize_rejects_a_verified_manifest_with_the_wrong_requested_identity() -> None:
    manifest = type(
        "Manifest",
        (),
        {"source_id": "other-source", "source_snapshot_id": "snapshot-1"},
    )()
    verifier = Verifier(Inspection("COMPLETE", True, (), manifest=manifest))

    with pytest.raises(NormalizationRejected) as error:
        NormalizationCoordinator(Policy(True), verifier).prepare("fixture", "snapshot-1")

    assert error.value.code == "INTEGRITY_MANIFEST_IDENTITY"


def test_normalize_does_not_accept_consumable_without_manifest_identity() -> None:
    verifier = Verifier(Inspection("COMPLETE", True, (), manifest="verified"))

    with pytest.raises(NormalizationRejected) as error:
        NormalizationCoordinator(Policy(True), verifier).prepare("fixture", "snapshot-1")

    assert error.value.code == "INTEGRITY_MANIFEST_IDENTITY"


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
