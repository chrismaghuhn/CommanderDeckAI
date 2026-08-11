from __future__ import annotations

from datetime import UTC, datetime

import pytest

from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config.current_use_policy import CurrentUseDecision
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings

EFFECTIVE_AT = datetime(2026, 8, 10, tzinfo=UTC)


def registry_for(
    approval_status: SourceApprovalStatus,
    *,
    current_status: str = "ALLOWED",
    current_approval_status: SourceApprovalStatus | None = None,
) -> SourceRegistry:
    settings = SourceSettings(
        source_id="Example-Source",
        approval_status=approval_status,
        review_path="docs/03-data/source-reviews/example.md",
        endpoints=("https://example.com/api",),
        host_allowlist=("example.com",),
    )
    historical = HistoricalApprovalMetadata(
        source_id="example_source",
        approval_status=approval_status,
        review_path="docs/03-data/source-reviews/example.md",
        reviewed_at=EFFECTIVE_AT,
        effective_at=EFFECTIVE_AT,
        reason="fixture review record",
    )
    current = CurrentUseDecision(
        source_id="example_source",
        status=current_status,
        approval_status=current_approval_status or approval_status,
        reason="fixture current-use decision",
        effective_at=EFFECTIVE_AT,
    )
    return SourceRegistry(
        entries=(
            SourceRegistryEntry(
                source_id="example_source",
                settings=settings,
                historical_approval=historical,
                current_use=current,
            ),
        )
    )


@pytest.mark.parametrize(
    "status",
    [SourceApprovalStatus.APPROVED_LOCAL, SourceApprovalStatus.APPROVED_REDISTRIBUTION],
)
def test_local_sync_allows_exactly_the_two_approved_statuses(
    status: SourceApprovalStatus,
) -> None:
    assert SourcePolicy(registry_for(status)).local_sync_allowed("EXAMPLE-SOURCE")


@pytest.mark.parametrize(
    "status",
    [
        SourceApprovalStatus.PROPOSED,
        SourceApprovalStatus.REVIEWED,
        SourceApprovalStatus.REJECTED,
        SourceApprovalStatus.PAUSED,
    ],
)
def test_local_sync_blocks_every_non_allowlisted_status(status: SourceApprovalStatus) -> None:
    assert not SourcePolicy(registry_for(status)).local_sync_allowed("example_source")


def test_public_export_requires_current_and_historical_redistribution_approval() -> None:
    policy = SourcePolicy(
        registry_for(
            SourceApprovalStatus.APPROVED_REDISTRIBUTION,
            current_approval_status=SourceApprovalStatus.APPROVED_REDISTRIBUTION,
        )
    )
    assert policy.public_export_allowed("example_source")

    local_only = SourcePolicy(registry_for(SourceApprovalStatus.APPROVED_LOCAL))
    assert not local_only.public_export_allowed("example_source")


@pytest.mark.parametrize("blocked_status", ["REJECTED", "PAUSED", "TAKEDOWN", "PROHIBITED"])
def test_historical_approval_cannot_override_current_block(
    blocked_status: str,
) -> None:
    policy = SourcePolicy(
        registry_for(
            SourceApprovalStatus.APPROVED_LOCAL,
            current_status=blocked_status,
        )
    )

    decision = policy.check_operation("example_source", "normalize")

    assert not decision.allowed
    assert decision.code == "POLICY_CURRENT_USE_BLOCKED"


@pytest.mark.parametrize("operation", ["normalize", "validate", "report", "dataset_build"])
def test_processing_operations_require_a_current_use_decision(operation: str) -> None:
    registry = registry_for(SourceApprovalStatus.APPROVED_LOCAL)
    entry = registry.lookup("example_source")
    entry_without_decision = entry.model_copy(update={"current_use": None})
    policy = SourcePolicy(SourceRegistry(entries=(entry_without_decision,)))

    decision = policy.check_operation("example_source", operation)

    assert not decision.allowed
    assert decision.code == "POLICY_CURRENT_USE_REQUIRED"


def test_source_adapter_configuration_is_gated_by_explicit_review_record() -> None:
    adapter_configuration = SourcePolicy(
        registry_for(SourceApprovalStatus.APPROVED_LOCAL)
    ).adapter_configuration("example_source")

    assert adapter_configuration.source.source_id == "example_source"
    assert adapter_configuration.historical_approval.review_path.endswith("example.md")

    settings = SourceSettings(
        source_id="example_source",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
    )
    historical = HistoricalApprovalMetadata(
        source_id="example_source",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        review_path="docs/03-data/source-reviews/example.md",
        reviewed_at=EFFECTIVE_AT,
        effective_at=EFFECTIVE_AT,
        reason="fixture review record",
    )
    with pytest.raises(ValueError):
        SourcePolicy(
            SourceRegistry(
                entries=(
                    SourceRegistryEntry(
                        source_id="example_source",
                        settings=settings,
                        historical_approval=historical,
                    ),
                )
            )
        ).adapter_configuration("example_source")


@pytest.mark.parametrize(
    "status",
    [
        SourceApprovalStatus.PROPOSED,
        SourceApprovalStatus.REJECTED,
        SourceApprovalStatus.PAUSED,
    ],
)
def test_source_adapter_configuration_requires_local_acquisition_approval(
    status: SourceApprovalStatus,
) -> None:
    with pytest.raises(SourcePolicyError) as error:
        SourcePolicy(registry_for(status)).adapter_configuration("example_source")

    assert error.value.code == "POLICY_SOURCE_NOT_APPROVED"


def test_source_adapter_configuration_requires_current_use_allowance() -> None:
    policy = SourcePolicy(
        registry_for(SourceApprovalStatus.APPROVED_LOCAL, current_status="REJECTED")
    )

    with pytest.raises(SourcePolicyError) as error:
        policy.adapter_configuration("example_source")

    assert error.value.code == "POLICY_CURRENT_USE_BLOCKED"


@pytest.mark.parametrize(
    "status",
    [
        SourceApprovalStatus.PROPOSED,
        SourceApprovalStatus.REVIEWED,
        SourceApprovalStatus.REJECTED,
        SourceApprovalStatus.PAUSED,
    ],
)
def test_audit_inspect_can_inspect_historically_blocked_snapshots(
    status: SourceApprovalStatus,
) -> None:
    policy = SourcePolicy(registry_for(status, current_status="REJECTED"))

    decision = policy.check_operation("example_source", "audit_inspect")

    assert decision.allowed
    assert decision.code == "POLICY_AUDIT_ONLY_ALLOWED"
    assert decision.operation.value == "audit_inspect"
    assert not policy.operation_allowed("example_source", "normalize")
    assert not policy.operation_allowed("example_source", "public_export")


def test_audit_inspect_can_inspect_currently_blocked_approved_snapshot() -> None:
    policy = SourcePolicy(
        registry_for(SourceApprovalStatus.APPROVED_LOCAL, current_status="TAKEDOWN")
    )

    decision = policy.check_operation("example_source", "audit_inspect")

    assert decision.allowed
    assert decision.code == "POLICY_AUDIT_ONLY_ALLOWED"
    assert not policy.operation_allowed("example_source", "report")
