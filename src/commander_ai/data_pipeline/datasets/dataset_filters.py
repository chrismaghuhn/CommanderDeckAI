"""Dataset-owned filters and explicit rejection of unsupported selectors."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from commander_ai.config.current_use_policy import (
    CurrentUseDecision,
    CurrentUsePolicy,
    PolicyOperation,
)
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.config.source_settings import SourceApprovalStatus, normalize_source_id
from commander_ai.data_pipeline.splitting.deck_completion_policy import (
    CompletionExclusion,
    DeckCompletionRecord,
)


def validate_selector_configuration(settings: DatasetSettings, kind: str) -> None:
    """Reject selectors whose record type cannot apply them deterministically."""

    if settings.split_policy.strategy != "temporal_grouped":
        raise ValueError(f"{kind} dataset split strategy is not implemented")
    if settings.split_policy.group_keys or settings.split_policy.extra_segments:
        raise ValueError(f"{kind} dataset split grouping options are not implemented")
    if settings.inclusions or settings.exclusions:
        raise ValueError(
            f"{kind} dataset inclusion/exclusion selectors are not supported by this builder"
        )
    if (
        kind in {"deck_completion", "card_cooccurrence"}
        and settings.inputs.require_complete_pod_result
    ):
        raise ValueError(f"{kind} datasets do not support pod-result completeness filters")
    if kind in {"tournament_outcomes", "combo"} and (
        settings.inputs.require_approved_sources
        or settings.inputs.require_complete_decklists
        or settings.inputs.legal_decks_only
        or (kind == "combo" and settings.inputs.require_complete_pod_result)
        or settings.source_ids
        or settings.inputs.modes
        or settings.filters.modes
        or settings.filters.legal_statuses
        or settings.filters.quality_statuses
        or settings.filters.observed_from is not None
        or settings.filters.observed_until is not None
    ):
        raise ValueError(f"{kind} dataset source/mode/status filters require source-aware records")


def filter_completion_records(
    settings: DatasetSettings,
    records: tuple[DeckCompletionRecord, ...],
    current_use_decisions: Mapping[str, CurrentUseDecision],
) -> tuple[tuple[DeckCompletionRecord, ...], tuple[CompletionExclusion, ...]]:
    """Apply source, mode, status, date, and approval filters before splitting."""

    observed_from = _parse_filter_datetime(settings.filters.observed_from, "observed_from")
    observed_until = _parse_filter_datetime(settings.filters.observed_until, "observed_until")
    if observed_from is not None and observed_until is not None and observed_until <= observed_from:
        raise ValueError("dataset filter observed_until must follow observed_from")
    source_ids = set(settings.source_ids)
    modes = {_normalize_mode(mode) for mode in (settings.filters.modes or settings.inputs.modes)}
    legal_statuses = set(settings.filters.legal_statuses)
    quality_statuses = set(settings.filters.quality_statuses)
    selected: list[DeckCompletionRecord] = []
    exclusions: list[CompletionExclusion] = []
    for record in sorted(records, key=lambda item: item.record_id):
        code = _completion_filter_code(
            record,
            source_ids=source_ids,
            modes=modes,
            legal_statuses=legal_statuses,
            quality_statuses=quality_statuses,
            current_use_decisions=current_use_decisions,
            observed_from=observed_from,
            observed_until=observed_until,
            require_approved_sources=settings.inputs.require_approved_sources,
        )
        if code is None:
            selected.append(record)
        else:
            exclusions.append(CompletionExclusion(record.record_id, code))
    return tuple(selected), tuple(exclusions)


def validate_current_use_decisions(
    decisions: tuple[CurrentUseDecision, ...],
    source_snapshot_ids: tuple[str, ...],
    *,
    required_source_ids: tuple[str, ...] = (),
    require_decision: bool = False,
    historical_statuses: Mapping[str, SourceApprovalStatus] | None = None,
) -> dict[str, CurrentUseDecision]:
    """Require and evaluate current-use decisions before dataset publication."""

    by_source: dict[str, CurrentUseDecision] = {}
    historical_by_source = {
        normalize_source_id(source_id): status
        for source_id, status in (historical_statuses or {}).items()
    }
    for decision in decisions:
        source_id = normalize_source_id(decision.source_id)
        if source_id in by_source:
            raise ValueError(f"duplicate current-use decision for source: {source_id}")
        historical_status = historical_by_source.get(source_id, decision.approval_status)
        if historical_status is None:
            raise ValueError(
                "POLICY_HISTORICAL_APPROVAL_REQUIRED: dataset build requires source history"
            )
        result = CurrentUsePolicy.check(
            source_id=source_id,
            historical_status=historical_status,
            current_use=decision,
            operation=PolicyOperation.DATASET_BUILD,
        )
        if not result.allowed:
            raise ValueError(f"{result.code}: dataset build blocked for source {source_id}")
        if historical_status not in {
            SourceApprovalStatus.APPROVED_LOCAL,
            SourceApprovalStatus.APPROVED_REDISTRIBUTION,
        }:
            raise ValueError(
                "POLICY_SOURCE_NOT_APPROVED: dataset build requires an approved source snapshot"
            )
        by_source[source_id] = decision
    normalized_required = {
        normalize_source_id(source_id) for source_id in required_source_ids if source_id.strip()
    }
    missing_sources = sorted(normalized_required - by_source.keys())
    if missing_sources:
        raise ValueError(
            "POLICY_CURRENT_USE_REQUIRED: missing source decisions for "
            + ", ".join(missing_sources)
        )
    if (source_snapshot_ids or require_decision) and not by_source:
        raise ValueError("dataset build requires current-use decisions for source inputs")
    return by_source


def _completion_filter_code(
    record: DeckCompletionRecord,
    *,
    source_ids: set[str],
    modes: set[str],
    legal_statuses: set[str],
    quality_statuses: set[str],
    current_use_decisions: Mapping[str, CurrentUseDecision],
    observed_from: datetime | None,
    observed_until: datetime | None,
    require_approved_sources: bool,
) -> str | None:
    source_id = normalize_source_id(record.occurrence.source.source_id)
    if source_ids and source_id not in source_ids:
        return "policy.dataset_source_excluded"
    if source_id not in current_use_decisions:
        return "policy.current_use_required"
    if modes and _normalize_mode(record.mode) not in modes:
        return "policy.dataset_mode_excluded"
    if legal_statuses and record.legal_status.casefold() not in legal_statuses:
        return "legality.dataset_status_excluded"
    if quality_statuses and record.quality_status.casefold() not in quality_statuses:
        return "quality.dataset_status_excluded"
    if observed_from is not None and record.observed_at < observed_from:
        return "quality.dataset_observed_before"
    if observed_until is not None and record.observed_at >= observed_until:
        return "quality.dataset_observed_after"
    if require_approved_sources and not _has_approved_provenance(record):
        return "policy.source_approval_missing"
    return None


def _has_approved_provenance(record: DeckCompletionRecord) -> bool:
    source = record.occurrence.source
    return any(
        normalize_source_id(reference.source_id) == normalize_source_id(source.source_id)
        and reference.source_snapshot_id == source.source_snapshot_id
        and reference.source_object_id == source.raw_object_id
        and reference.approval_status in {"APPROVED_LOCAL", "APPROVED_REDISTRIBUTION"}
        for reference in record.occurrence.deck.provenance
    )


def _parse_filter_datetime(value: str | None, field_name: str) -> datetime | None:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"dataset filter {field_name} must be an ISO-8601 datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"dataset filter {field_name} must include a timezone")
    return parsed


def _normalize_mode(value: str | None) -> str:
    if value is None:
        return "unknown"
    normalized = value.strip().casefold()
    return "competitive" if normalized == "cedh" else normalized or "unknown"


__all__ = [
    "filter_completion_records",
    "validate_current_use_decisions",
    "validate_selector_configuration",
]
