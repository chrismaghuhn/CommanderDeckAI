"""Assessment-only source status rows for report operations."""

from __future__ import annotations

from datetime import UTC, datetime

from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config.current_use_policy import CurrentUsePolicy, PolicyOperation
from commander_ai.config.source_registry import SourceRegistry
from commander_ai.data_pipeline.reports.source_assessments import SourceAssessment
from commander_ai.data_pipeline.reports.source_metrics import SourceMetricsInput


def source_assessments(
    registry: SourceRegistry,
    selector: str,
    measured_sources: set[str],
) -> tuple[SourceAssessment, ...]:
    entries = (
        registry.entries
        if selector == "all"
        else tuple(entry for entry in registry.entries if entry.source_id == selector)
    )
    assessments: list[SourceAssessment] = []
    for entry in entries:
        if entry.source_id in measured_sources:
            continue
        decision = CurrentUsePolicy.check(
            source_id=entry.source_id,
            historical_status=entry.historical_approval.approval_status,
            current_use=entry.current_use,
            operation=PolicyOperation.AUDIT_INSPECT,
        )
        assessments.append(
            SourceAssessment(
                source_id=entry.source_id,
                approval_status=entry.historical_approval.approval_status.value,
                current_use_status=(
                    None if decision.current_status is None else decision.current_status.value
                ),
                policy_code=decision.code,
                policy_allowed=decision.allowed,
                research_only=(
                    entry.historical_approval.approval_status
                    not in SourcePolicy.LOCAL_SYNC_ALLOWLIST
                ),
                reason=decision.reason,
                decision_reference=decision.decision_reference,
                decision_sha256=decision.decision_sha256,
            )
        )
    return tuple(sorted(assessments, key=lambda item: item.source_id))


def reported_at(
    sources: list[SourceMetricsInput], registry: SourceRegistry, selector: str
) -> datetime:
    values = [item.snapshot_date for item in sources]
    entries = (
        registry.entries
        if selector == "all"
        else tuple(entry for entry in registry.entries if entry.source_id == selector)
    )
    for entry in entries:
        values.extend(
            (entry.historical_approval.reviewed_at, entry.historical_approval.effective_at)
        )
        if entry.current_use is not None:
            values.append(entry.current_use.effective_at)
    return max(values, default=datetime(1970, 1, 1, tzinfo=UTC))


__all__ = ["reported_at", "source_assessments"]
