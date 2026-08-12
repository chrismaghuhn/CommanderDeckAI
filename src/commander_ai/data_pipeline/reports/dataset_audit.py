"""Conservative, source-aware audit of the usable Commander dataset."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from commander_ai.config.current_use_policy import CurrentUsePolicy, PolicyOperation

from .source_metrics import (
    DeckMetricRecord,
    ReportInputBinding,
    SourceMetricsInput,
    build_source_metrics_report,
)


@dataclass(frozen=True, slots=True)
class DatasetAuditReport:
    schema_version: Literal["dataset-audit-report.v1"]
    report_id: str
    reported_at: datetime
    input_manifests: tuple[ReportInputBinding, ...]
    counts: dict[str, int]
    classification: dict[str, int]
    outcomes: dict[str, int]
    pods: dict[str, int]
    commander_distribution: dict[str, object]
    source_duplication: dict[str, int]
    resolution: dict[str, int]
    date_range: dict[str, str] | None
    historical_legality: dict[str, int]
    missing_information: dict[str, int]
    suitability: dict[str, str]
    source_reports: tuple[dict[str, object], ...]
    current_use: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "reported_at": _iso(self.reported_at),
            "input_manifests": [item.as_dict() for item in self.input_manifests],
            "counts": self.counts,
            "classification": self.classification,
            "outcomes": self.outcomes,
            "pods": self.pods,
            "commander_distribution": self.commander_distribution,
            "source_duplication": self.source_duplication,
            "resolution": self.resolution,
            "date_range": self.date_range,
            "historical_legality": self.historical_legality,
            "missing_information": self.missing_information,
            "suitability": self.suitability,
            "source_reports": list(self.source_reports),
            "current_use": list(self.current_use),
        }


def build_dataset_audit_report(
    sources: Sequence[SourceMetricsInput],
    *,
    report_id: str,
    reported_at: datetime,
) -> DatasetAuditReport:
    """Summarize measured coverage without treating missing data as negative evidence."""

    if not report_id.strip():
        raise ValueError("report_id must be non-empty")
    _require_aware(reported_at, "reported_at")
    ordered_sources = tuple(sorted(sources, key=lambda item: (item.source_id, item.snapshot_id)))
    source_report = build_source_metrics_report(
        ordered_sources,
        report_id=f"{report_id}:sources",
        reported_at=reported_at,
    )
    decks = tuple(deck for source in ordered_sources for deck in source.decks)
    complete_commander_decks = sum(
        deck.complete_decklist and bool(deck.commander_ids) for deck in decks
    )
    mode_counts = Counter(
        _mode_class(deck.mode) for deck in decks if deck.complete_decklist and deck.commander_ids
    )
    observed = sorted(deck.observed_at for deck in decks if deck.observed_at is not None)
    commanders = Counter(commander for deck in decks for commander in deck.commander_ids)
    canonical_sources: dict[str, set[str]] = defaultdict(set)
    for deck in decks:
        if deck.canonical_deck_id is not None:
            canonical_sources[deck.canonical_deck_id].add(deck.source_id)
    duplicate_groups = [sources for sources in canonical_sources.values() if len(sources) > 1]
    allowed_sources = _allowed_sources(ordered_sources)
    eligible = tuple(deck for deck in decks if deck.source_id in allowed_sources)
    unresolved_cards = sum(deck.unresolved_cards for deck in decks)
    unknown_legality = sum(deck.legal_status == "unknown" for deck in decks)
    incomplete = sum(not deck.complete_decklist for deck in decks)
    missing_commander = sum(not deck.commander_ids for deck in decks)
    missing_observed_at = sum(deck.observed_at is None for deck in decks)
    missing_mode = sum(deck.mode is None for deck in decks)
    usable_outcomes = sum(deck.usable_outcome for deck in decks)
    full_pods = sum(deck.full_pod for deck in decks)
    tournament_events = sum(source.tournament_events for source in ordered_sources)
    complete_event_observations = sum(
        source.complete_event_observations for source in ordered_sources
    )
    pod_count = sum(source.pods for source in ordered_sources)
    complete_pod_count = sum(source.complete_pods for source in ordered_sources)
    return DatasetAuditReport(
        schema_version="dataset-audit-report.v1",
        report_id=report_id,
        reported_at=reported_at,
        input_manifests=source_report.input_manifests,
        counts={
            "total_decks": len(decks),
            "complete_decklists": sum(deck.complete_decklist for deck in decks),
            "complete_commander_decks": complete_commander_decks,
            "unique_commanders": len(commanders),
            "unique_cards": len({card for deck in decks for card in deck.card_ids}),
            "historical_legality_unknown": unknown_legality,
            "unresolved_card_records": sum(not deck.resolution_complete for deck in decks),
            "usable_outcomes": usable_outcomes,
            "full_pod_records": full_pods,
            "tournaments": tournament_events,
            "event_observations": complete_event_observations,
            "pods": pod_count,
        },
        classification={
            "casual": mode_counts.get("casual", 0),
            "competitive": mode_counts.get("competitive", 0),
            "unknown": mode_counts.get("unknown", 0),
        },
        outcomes={"usable": usable_outcomes},
        pods={
            "total": pod_count,
            "complete": complete_pod_count,
            "full": full_pods,
        },
        commander_distribution={
            "unique": len(commanders),
            "dominant": _top_commanders(commanders),
            "long_tail_singletons": sum(count == 1 for count in commanders.values()),
        },
        source_duplication={
            "cross_source_canonical_decks": len(duplicate_groups),
            "cross_source_deck_records": sum(
                sum(deck.canonical_deck_id == canonical_id for deck in decks)
                for canonical_id, source_ids in canonical_sources.items()
                if len(source_ids) > 1
            ),
        },
        resolution={
            "resolved_decks": sum(deck.resolution_complete for deck in decks),
            "unresolved_decks": sum(not deck.resolution_complete for deck in decks),
            "unresolved_cards": unresolved_cards,
        },
        date_range=_date_range(observed),
        historical_legality={
            "known": len(decks) - unknown_legality,
            "unknown": unknown_legality,
        },
        missing_information={
            "missing_commander": missing_commander,
            "missing_observed_at": missing_observed_at,
            "missing_mode": missing_mode,
            "incomplete_decklist": incomplete,
            "unresolved_cards": unresolved_cards,
            "unknown_legality": unknown_legality,
        },
        suitability={
            "deck_completion_training": _deck_training_suitability(eligible, unresolved_cards),
            "performance_modeling": _performance_suitability(eligible),
            "research_only_sources": str(sum(source.research_only for source in ordered_sources)),
        },
        source_reports=source_report.sources,
        current_use=source_report.current_use,
    )


def _allowed_sources(sources: Sequence[SourceMetricsInput]) -> set[str]:
    allowed: set[str] = set()
    for source in sources:
        result = CurrentUsePolicy.check(
            source_id=source.source_id,
            historical_status=source.historical_approval_status,
            current_use=source.current_use,
            operation=PolicyOperation.DATASET_BUILD,
        )
        if result.allowed and not source.research_only:
            allowed.add(source.source_id)
    return allowed


def _deck_training_suitability(decks: Sequence[DeckMetricRecord], unresolved_cards: int) -> str:
    complete = sum(deck.complete_decklist and bool(deck.commander_ids) for deck in decks)
    if complete == 0:
        return "not_suitable"
    if unresolved_cards or any(not deck.resolution_complete for deck in decks):
        return "conditional"
    return "suitable"


def _performance_suitability(decks: Sequence[DeckMetricRecord]) -> str:
    outcomes = sum(deck.usable_outcome for deck in decks)
    pods = sum(deck.full_pod for deck in decks)
    if outcomes and pods:
        return "suitable"
    if outcomes:
        return "conditional"
    return "not_suitable"


def _top_commanders(counts: Counter[str]) -> list[dict[str, object]]:
    return [
        {"commander_id": commander, "count": count}
        for commander, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:10]
    ]


def _mode_class(mode: str | None) -> str:
    if mode is None:
        return "unknown"
    normalized = mode.strip().casefold()
    return (
        "casual"
        if normalized == "casual"
        else "competitive"
        if normalized in {"cedh", "competitive", "tournament"}
        else "unknown"
    )


def _date_range(values: Sequence[datetime]) -> dict[str, str] | None:
    if not values:
        return None
    return {"from": _iso(values[0]), "until": _iso(values[-1])}


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


__all__ = ["DatasetAuditReport", "build_dataset_audit_report"]
