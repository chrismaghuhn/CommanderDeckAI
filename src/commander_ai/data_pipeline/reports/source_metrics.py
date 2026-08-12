"""Deterministic quality metrics for one or more source snapshots."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Literal

from commander_ai.config.current_use_policy import (
    CurrentUseDecision,
    CurrentUsePolicy,
    PolicyOperation,
)
from commander_ai.config.source_settings import SourceApprovalStatus, normalize_source_id

_SHA256_LENGTH = 64
_MODE_ALIASES = {
    "casual": "casual",
    "cedh": "competitive",
    "competitive": "competitive",
    "tournament": "competitive",
}


@dataclass(frozen=True, slots=True)
class ReportInputBinding:
    """A portable, hash-bound input reference for a report artifact."""

    kind: str
    identifier: str
    sha256: str

    def __post_init__(self) -> None:
        if not self.kind.strip() or not self.identifier.strip():
            raise ValueError("report input kind and identifier must be non-empty")
        if len(self.sha256) != _SHA256_LENGTH or any(
            character not in "0123456789abcdef" for character in self.sha256
        ):
            raise ValueError("report input sha256 must be lowercase SHA-256")

    def as_dict(self) -> dict[str, str]:
        return {"kind": self.kind, "id": self.identifier, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class DeckMetricRecord:
    """Source-neutral measurements for one normalized deck observation."""

    deck_id: str
    source_id: str
    canonical_deck_id: str | None
    commander_ids: tuple[str, ...]
    card_ids: tuple[str, ...]
    observed_at: datetime | None
    complete_decklist: bool
    resolution_complete: bool
    legal_status: str
    quality_status: str = "unknown"
    mode: str | None = None
    usable_outcome: bool = False
    full_pod: bool = False
    unresolved_cards: int = 0

    def __post_init__(self) -> None:
        if not self.deck_id.strip():
            raise ValueError("deck_id must be non-empty")
        object.__setattr__(self, "source_id", normalize_source_id(self.source_id))
        if self.canonical_deck_id is not None and not self.canonical_deck_id.strip():
            raise ValueError("canonical_deck_id must be non-empty when supplied")
        for field_name in ("commander_ids", "card_ids"):
            values = tuple(
                dict.fromkeys(item.strip() for item in getattr(self, field_name) if item.strip())
            )
            object.__setattr__(self, field_name, values)
        if self.observed_at is not None and (
            self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None
        ):
            raise ValueError("observed_at must include a timezone")
        if not self.legal_status.strip():
            raise ValueError("legal_status must be non-empty")
        if not self.quality_status.strip():
            raise ValueError("quality_status must be non-empty")
        if self.mode is not None and not self.mode.strip():
            object.__setattr__(self, "mode", None)
        if self.unresolved_cards < 0:
            raise ValueError("unresolved_cards must be non-negative")


@dataclass(frozen=True, slots=True)
class SourceMetricsInput:
    """Measured, already-acquired source data supplied to a report builder."""

    source_id: str
    snapshot_id: str
    snapshot_date: datetime
    raw_bytes: int
    source_record_count: int
    decks: tuple[DeckMetricRecord, ...] = ()
    card_resolution_total: int = 0
    card_resolution_resolved: int = 0
    card_resolution_ambiguous: int = 0
    card_resolution_unresolved: int = 0
    exact_duplicate_decks: int = 0
    cross_source_overlap_decks: int = 0
    tournament_events: int = 0
    complete_event_observations: int = 0
    pods: int = 0
    complete_pods: int = 0
    quarantined_records: int = 0
    finding_counts: Mapping[str, int] = field(default_factory=dict)
    input_manifests: tuple[ReportInputBinding, ...] = ()
    historical_approval_status: SourceApprovalStatus = SourceApprovalStatus.PROPOSED
    current_use: CurrentUseDecision | None = None
    research_only: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", normalize_source_id(self.source_id))
        if not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be non-empty")
        if self.snapshot_date.tzinfo is None or self.snapshot_date.utcoffset() is None:
            raise ValueError("snapshot_date must include a timezone")
        for field_name in (
            "raw_bytes",
            "source_record_count",
            "card_resolution_total",
            "card_resolution_resolved",
            "card_resolution_ambiguous",
            "card_resolution_unresolved",
            "exact_duplicate_decks",
            "cross_source_overlap_decks",
            "tournament_events",
            "complete_event_observations",
            "pods",
            "complete_pods",
            "quarantined_records",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if self.card_resolution_resolved > self.card_resolution_total:
            raise ValueError("resolved card entries cannot exceed total entries")
        if self.complete_event_observations > self.source_record_count:
            raise ValueError("complete event observations cannot exceed source records")
        if self.complete_pods > self.pods:
            raise ValueError("complete pods cannot exceed pods")
        if (
            self.card_resolution_resolved
            + self.card_resolution_ambiguous
            + self.card_resolution_unresolved
            != self.card_resolution_total
        ):
            raise ValueError("card resolution counts must sum to total entries")
        if self.current_use is not None and self.current_use.source_id != self.source_id:
            raise ValueError("current-use decision source does not match source metrics")
        if any(deck.source_id != self.source_id for deck in self.decks):
            raise ValueError("deck metric source does not match source metrics")
        if not self.input_manifests:
            raise ValueError("source metrics require at least one input manifest")


@dataclass(frozen=True, slots=True)
class SourceMetricsReport:
    schema_version: Literal["source-quality-report.v1"]
    report_id: str
    reported_at: datetime
    input_manifests: tuple[ReportInputBinding, ...]
    sources: tuple[dict[str, object], ...]
    current_use: tuple[dict[str, object], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "report_id": self.report_id,
            "reported_at": _iso(self.reported_at),
            "input_manifests": [item.as_dict() for item in self.input_manifests],
            "sources": list(self.sources),
            "current_use": list(self.current_use),
        }


def build_source_metrics_report(
    inputs: Sequence[SourceMetricsInput],
    *,
    report_id: str,
    reported_at: datetime,
) -> SourceMetricsReport:
    """Build a stable report without acquiring or mutating source data."""

    if not report_id.strip():
        raise ValueError("report_id must be non-empty")
    _require_aware(reported_at, "reported_at")
    ordered_inputs = tuple(sorted(inputs, key=lambda item: (item.source_id, item.snapshot_id)))
    source_by_deck: dict[str, set[str]] = {}
    for source in ordered_inputs:
        for deck in source.decks:
            if deck.canonical_deck_id is not None:
                source_by_deck.setdefault(deck.canonical_deck_id, set()).add(source.source_id)
    cross_source_ids = {
        deck_id for deck_id, source_ids in source_by_deck.items() if len(source_ids) > 1
    }
    ordered = tuple(
        replace(
            source,
            exact_duplicate_decks=max(
                source.exact_duplicate_decks,
                len(
                    [
                        deck.canonical_deck_id
                        for deck in source.decks
                        if deck.canonical_deck_id is not None
                    ]
                )
                - len(
                    {
                        deck.canonical_deck_id
                        for deck in source.decks
                        if deck.canonical_deck_id is not None
                    }
                ),
            ),
            cross_source_overlap_decks=max(
                source.cross_source_overlap_decks,
                sum(
                    deck.canonical_deck_id in cross_source_ids
                    for deck in source.decks
                    if deck.canonical_deck_id is not None
                ),
            ),
        )
        for source in ordered_inputs
    )
    bindings = _unique_bindings(item for source in ordered for item in source.input_manifests)
    summaries: list[dict[str, object]] = []
    policy_rows: list[dict[str, object]] = []
    for source in ordered:
        policy = CurrentUsePolicy.check(
            source_id=source.source_id,
            historical_status=source.historical_approval_status,
            current_use=source.current_use,
            operation=PolicyOperation.REPORT,
        )
        summaries.append(_source_summary(source))
        policy_rows.append(
            {
                "source_id": source.source_id,
                "operation": policy.operation.value,
                "allowed": policy.allowed,
                "code": policy.code,
                "reason": policy.reason,
                "historical_status": policy.historical_status.value,
                "current_status": (
                    None if policy.current_status is None else policy.current_status.value
                ),
                "decision_reference": policy.decision_reference,
                "decision_sha256": policy.decision_sha256,
            }
        )
    return SourceMetricsReport(
        schema_version="source-quality-report.v1",
        report_id=report_id,
        reported_at=reported_at,
        input_manifests=bindings,
        sources=tuple(summaries),
        current_use=tuple(sorted(policy_rows, key=lambda item: str(item["source_id"]))),
    )


def _source_summary(source: SourceMetricsInput) -> dict[str, object]:
    decks = source.decks
    complete = sum(deck.complete_decklist for deck in decks)
    commander_decks = sum(bool(deck.commander_ids) for deck in decks)
    unique_commanders = sorted({commander for deck in decks for commander in deck.commander_ids})
    unique_cards = sorted({card for deck in decks for card in deck.card_ids})
    observed = sorted(deck.observed_at for deck in decks if deck.observed_at is not None)
    mode_counts = Counter(_mode_class(deck.mode) for deck in decks)
    legality_counts = Counter(deck.legal_status for deck in decks)
    quality_counts = Counter(deck.quality_status for deck in decks)
    resolution_rate = (
        source.card_resolution_resolved / source.card_resolution_total
        if source.card_resolution_total
        else None
    )
    return {
        "source_id": source.source_id,
        "snapshot_id": source.snapshot_id,
        "snapshot_date": _iso(source.snapshot_date),
        "raw_bytes": source.raw_bytes,
        "source_record_count": source.source_record_count,
        "commander_decks": commander_decks,
        "total_decks": len(decks),
        "complete_decklists": complete,
        "incomplete_decklists": len(decks) - complete,
        "unique_commanders": unique_commanders,
        "unique_cards": unique_cards,
        "date_range": _date_range(observed),
        "duplicates": {
            "exact_decks": source.exact_duplicate_decks,
            "cross_source_overlap_decks": source.cross_source_overlap_decks,
        },
        "tournaments": source.tournament_events,
        "event_observations": {
            "complete": source.complete_event_observations,
        },
        "resolution": {
            "total": source.card_resolution_total,
            "resolved": source.card_resolution_resolved,
            "ambiguous": source.card_resolution_ambiguous,
            "unresolved": source.card_resolution_unresolved,
            "success_rate": resolution_rate,
        },
        "missing_commander_count": len(decks) - commander_decks,
        "legality": {
            "by_status": dict(sorted(legality_counts.items())),
            "unknown": legality_counts.get("unknown", 0),
        },
        "legality_unknown_count": legality_counts.get("unknown", 0),
        "quality": {
            "by_status": dict(sorted(quality_counts.items())),
            "unknown": quality_counts.get("unknown", 0),
        },
        "quality_unknown_count": quality_counts.get("unknown", 0),
        "mode_availability": {
            "casual": mode_counts.get("casual", 0),
            "competitive": mode_counts.get("competitive", 0),
            "unknown": mode_counts.get("unknown", 0),
        },
        "outcomes": {"usable": sum(deck.usable_outcome for deck in decks)},
        "pods": {
            "total": source.pods,
            "complete": source.complete_pods,
            "full": sum(deck.full_pod for deck in decks),
        },
        "quarantined_records": source.quarantined_records,
        "finding_counts": dict(sorted(source.finding_counts.items())),
        "recommended_use": _recommended_use(source, complete, resolution_rate),
    }


def _recommended_use(
    source: SourceMetricsInput, complete: int, resolution_rate: float | None
) -> str:
    if source.research_only:
        return "research_only"
    usable_outcomes = sum(deck.usable_outcome for deck in source.decks)
    full_pods = sum(deck.full_pod for deck in source.decks)
    if usable_outcomes and full_pods:
        return "performance_modeling_candidate"
    if complete and resolution_rate == 1:
        return "deck_completion_training_candidate"
    if complete:
        return "deck_completion_training_conditional"
    return "audit_only"


def _unique_bindings(values: Iterable[ReportInputBinding]) -> tuple[ReportInputBinding, ...]:
    by_key: dict[tuple[str, str], ReportInputBinding] = {}
    for value in values:
        key = (value.kind, value.identifier)
        previous = by_key.get(key)
        if previous is not None and previous.sha256 != value.sha256:
            raise ValueError(f"report input binding conflict: {key}")
        by_key[key] = value
    return tuple(by_key[key] for key in sorted(by_key))


def _mode_class(mode: str | None) -> str:
    return _MODE_ALIASES.get(mode.strip().casefold(), "unknown") if mode else "unknown"


def _date_range(values: Sequence[datetime]) -> dict[str, str] | None:
    if not values:
        return None
    return {"from": _iso(values[0]), "until": _iso(values[-1])}


def _iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")


__all__ = [
    "DeckMetricRecord",
    "ReportInputBinding",
    "SourceMetricsInput",
    "SourceMetricsReport",
    "build_source_metrics_report",
]
