from datetime import UTC, datetime

import pytest

from commander_ai.config.current_use_policy import CurrentUseDecision, CurrentUseStatus
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.reports.source_metrics import (
    DeckMetricRecord,
    ReportInputBinding,
    SourceMetricsInput,
    build_source_metrics_report,
)

ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
ORACLE_C = "33333333-3333-4333-8333-333333333333"


def _decision(
    source_id: str, status: CurrentUseStatus = CurrentUseStatus.ALLOWED
) -> CurrentUseDecision:
    return CurrentUseDecision(
        source_id=source_id,
        status=status,
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        reason="fixture policy",
        effective_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def _deck(
    deck_id: str,
    *,
    source_id: str = "fixture",
    commander_ids: tuple[str, ...] = (ORACLE_A,),
    card_ids: tuple[str, ...] = (ORACLE_B, ORACLE_C),
    observed_at: datetime | None = None,
    complete: bool = True,
    resolved: bool = True,
    legal_status: str = "legal",
    mode: str | None = "casual",
    usable_outcome: bool = False,
    full_pod: bool = False,
    unresolved_cards: int = 0,
    canonical_deck_id: str | None = None,
) -> DeckMetricRecord:
    return DeckMetricRecord(
        deck_id=deck_id,
        source_id=source_id,
        canonical_deck_id=canonical_deck_id or deck_id,
        commander_ids=commander_ids,
        card_ids=card_ids,
        observed_at=observed_at,
        complete_decklist=complete,
        resolution_complete=resolved,
        legal_status=legal_status,
        mode=mode,
        usable_outcome=usable_outcome,
        full_pod=full_pod,
        unresolved_cards=unresolved_cards,
    )


def _input(
    *,
    source_id: str = "fixture",
    snapshot_id: str = "snapshot-1",
    decks: tuple[DeckMetricRecord, ...] = (),
    research_only: bool = False,
    current_use: CurrentUseDecision | None = None,
    exact_duplicate_decks: int = 2,
    cross_source_overlap_decks: int = 1,
) -> SourceMetricsInput:
    return SourceMetricsInput(
        source_id=source_id,
        snapshot_id=snapshot_id,
        snapshot_date=datetime(2026, 8, 10, tzinfo=UTC),
        raw_bytes=1234,
        source_record_count=10,
        decks=decks,
        card_resolution_total=3,
        card_resolution_resolved=2,
        card_resolution_ambiguous=0,
        card_resolution_unresolved=1,
        exact_duplicate_decks=exact_duplicate_decks,
        cross_source_overlap_decks=cross_source_overlap_decks,
        quarantined_records=1,
        input_manifests=(
            ReportInputBinding(
                kind="source_snapshot_manifest",
                identifier=snapshot_id,
                sha256="a" * 64,
            ),
        ),
        historical_approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        current_use=current_use,
        research_only=research_only,
    )


def test_source_report_is_deterministic_and_exposes_missingness() -> None:
    decks = (
        _deck(
            "deck-1",
            observed_at=datetime(2024, 1, 1, tzinfo=UTC),
            usable_outcome=True,
            full_pod=True,
        ),
        _deck(
            "deck-2",
            commander_ids=(),
            card_ids=(ORACLE_C,),
            observed_at=datetime(2025, 1, 1, tzinfo=UTC),
            complete=False,
            resolved=False,
            legal_status="unknown",
            mode=None,
            unresolved_cards=2,
        ),
        _deck(
            "deck-3",
            commander_ids=(ORACLE_A,),
            card_ids=(ORACLE_B,),
            observed_at=datetime(2026, 1, 1, tzinfo=UTC),
            mode="cedh",
            canonical_deck_id="deck-1",
        ),
    )
    source = _input(decks=decks, current_use=_decision("fixture"))

    first = build_source_metrics_report(
        [source], report_id="source-report-1", reported_at=datetime(2026, 8, 11, tzinfo=UTC)
    )
    second = build_source_metrics_report(
        [_input(decks=tuple(reversed(decks)), current_use=_decision("fixture"))],
        report_id="source-report-1",
        reported_at=datetime(2026, 8, 11, tzinfo=UTC),
    )

    assert first.as_dict() == second.as_dict()
    summary = first.as_dict()["sources"][0]
    assert summary["raw_bytes"] == 1234
    assert summary["source_record_count"] == 10
    assert summary["commander_decks"] == 2
    assert summary["complete_decklists"] == 2
    assert summary["incomplete_decklists"] == 1
    assert summary["unique_commanders"] == [ORACLE_A]
    assert summary["unique_cards"] == [ORACLE_B, ORACLE_C]
    assert summary["missing_commander_count"] == 1
    assert summary["legality_unknown_count"] == 1
    assert summary["date_range"] == {
        "from": "2024-01-01T00:00:00Z",
        "until": "2026-01-01T00:00:00Z",
    }
    assert summary["resolution"]["success_rate"] == 2 / 3
    assert first.as_dict()["current_use"][0]["allowed"] is True


def test_research_only_or_blocked_sources_are_reported_without_acquisition() -> None:
    report = build_source_metrics_report(
        [
            _input(
                source_id="edhrec",
                snapshot_id="assessment-only",
                research_only=True,
                current_use=CurrentUseDecision(
                    source_id="edhrec",
                    status=CurrentUseStatus.PAUSED,
                    approval_status=SourceApprovalStatus.PAUSED,
                    reason="assessment only",
                    effective_at=datetime(2026, 8, 11, tzinfo=UTC),
                ),
            )
        ],
        report_id="blocked-report",
        reported_at=datetime(2026, 8, 11, tzinfo=UTC),
    )

    source = report.as_dict()["sources"][0]
    assert source["recommended_use"] == "research_only"
    assert report.as_dict()["current_use"][0]["allowed"] is False
    assert report.as_dict()["current_use"][0]["code"] == "POLICY_CURRENT_USE_BLOCKED"


def test_source_metrics_reject_inconsistent_card_resolution_counts() -> None:
    with pytest.raises(ValueError, match="sum to total"):
        _input(
            current_use=_decision("fixture"),
        ).__class__(
            source_id="fixture",
            snapshot_id="snapshot-1",
            snapshot_date=datetime(2026, 8, 10, tzinfo=UTC),
            raw_bytes=1234,
            source_record_count=10,
            card_resolution_total=3,
            card_resolution_resolved=2,
            card_resolution_ambiguous=0,
            card_resolution_unresolved=0,
            input_manifests=(
                ReportInputBinding(
                    kind="source_snapshot_manifest",
                    identifier="snapshot-1",
                    sha256="a" * 64,
                ),
            ),
            historical_approval_status=SourceApprovalStatus.APPROVED_LOCAL,
            current_use=_decision("fixture"),
        )


def test_source_report_exposes_event_and_pod_coverage() -> None:
    source = SourceMetricsInput(
        source_id="fixture",
        snapshot_id="snapshot-1",
        snapshot_date=datetime(2026, 8, 10, tzinfo=UTC),
        raw_bytes=10,
        source_record_count=4,
        tournament_events=2,
        complete_event_observations=3,
        pods=1,
        complete_pods=0,
        input_manifests=(
            ReportInputBinding(
                kind="canonical_snapshot_manifest",
                identifier="canonical-1",
                sha256="c" * 64,
            ),
        ),
        historical_approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        current_use=_decision("fixture"),
    )

    summary = build_source_metrics_report(
        [source], report_id="coverage-report", reported_at=datetime(2026, 8, 11, tzinfo=UTC)
    ).as_dict()["sources"][0]

    assert summary["tournaments"] == 2
    assert summary["event_observations"]["complete"] == 3
    assert summary["pods"]["total"] == 1
    assert summary["pods"]["complete"] == 0


def test_source_report_derives_exact_and_cross_source_overlap_counts() -> None:
    first = _input(
        source_id="source-a",
        snapshot_id="a-snapshot",
        decks=(_deck("a-1", source_id="source-a", canonical_deck_id="same"),),
        current_use=_decision("source-a"),
        exact_duplicate_decks=0,
        cross_source_overlap_decks=0,
    )
    second = _input(
        source_id="source-b",
        snapshot_id="b-snapshot",
        decks=(_deck("b-1", source_id="source-b", canonical_deck_id="same"),),
        current_use=_decision("source-b"),
        exact_duplicate_decks=0,
        cross_source_overlap_decks=0,
    )

    report = build_source_metrics_report(
        [first, second],
        report_id="overlap-report",
        reported_at=datetime(2026, 8, 11, tzinfo=UTC),
    )

    summaries = {item["source_id"]: item for item in report.as_dict()["sources"]}
    assert summaries["source_a"]["duplicates"] == {
        "exact_decks": 0,
        "cross_source_overlap_decks": 1,
    }
