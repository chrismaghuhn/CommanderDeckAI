from datetime import UTC, datetime

from commander_ai.config.current_use_policy import CurrentUseDecision
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.reports.dataset_audit import build_dataset_audit_report
from commander_ai.data_pipeline.reports.source_metrics import (
    DeckMetricRecord,
    ReportInputBinding,
    SourceMetricsInput,
)


def _decision(source_id: str) -> CurrentUseDecision:
    return CurrentUseDecision(
        source_id=source_id,
        status="ALLOWED",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        reason="fixture policy",
        effective_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def _deck(
    deck_id: str,
    source_id: str,
    *,
    complete: bool = True,
    resolved: bool = True,
    legal_status: str = "legal",
    mode: str | None = "casual",
    usable_outcome: bool = False,
    full_pod: bool = False,
    commander_ids: tuple[str, ...] = ("commander-a",),
    canonical_deck_id: str | None = None,
) -> DeckMetricRecord:
    return DeckMetricRecord(
        deck_id=deck_id,
        source_id=source_id,
        canonical_deck_id=canonical_deck_id or deck_id,
        commander_ids=commander_ids,
        card_ids=("card-a", "card-b"),
        observed_at=datetime(2024, 1, 1, tzinfo=UTC),
        complete_decklist=complete,
        resolution_complete=resolved,
        legal_status=legal_status,
        mode=mode,
        usable_outcome=usable_outcome,
        full_pod=full_pod,
        unresolved_cards=0 if resolved else 2,
    )


def _source(
    source_id: str,
    decks: tuple[DeckMetricRecord, ...],
    *,
    tournament_events: int = 0,
    complete_event_observations: int = 0,
    pods: int = 0,
    complete_pods: int = 0,
) -> SourceMetricsInput:
    return SourceMetricsInput(
        source_id=source_id,
        snapshot_id=f"{source_id}-snapshot",
        snapshot_date=datetime(2026, 8, 10, tzinfo=UTC),
        raw_bytes=100,
        source_record_count=len(decks),
        decks=decks,
        tournament_events=tournament_events,
        complete_event_observations=complete_event_observations,
        pods=pods,
        complete_pods=complete_pods,
        input_manifests=(
            ReportInputBinding(
                kind="normalized_snapshot_manifest",
                identifier=f"{source_id}-normalized",
                sha256="b" * 64,
            ),
        ),
        historical_approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        current_use=_decision(source_id),
    )


def test_dataset_audit_reports_training_and_performance_readiness() -> None:
    sources = (
        _source(
            "source-a",
            (
                _deck(
                    "deck-1",
                    "source-a",
                    usable_outcome=True,
                    full_pod=True,
                    canonical_deck_id="same-deck",
                    mode="casual",
                ),
                _deck("deck-2", "source-a", complete=False, resolved=False, legal_status="unknown"),
            ),
            tournament_events=2,
            complete_event_observations=2,
            pods=1,
        ),
        _source(
            "source-b",
            (
                _deck(
                    "deck-3",
                    "source-b",
                    usable_outcome=True,
                    canonical_deck_id="same-deck",
                    mode="competitive",
                    commander_ids=("commander-b",),
                ),
            ),
        ),
    )

    report = build_dataset_audit_report(
        sources,
        report_id="audit-1",
        reported_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    payload = report.as_dict()

    assert payload["counts"]["complete_commander_decks"] == 2
    assert payload["counts"]["usable_outcomes"] == 2
    assert payload["counts"]["full_pod_records"] == 1
    assert payload["counts"]["tournaments"] == 2
    assert payload["counts"]["pods"] == 1
    assert payload["counts"]["historical_legality_unknown"] == 1
    assert payload["source_duplication"]["cross_source_canonical_decks"] == 1
    assert payload["classification"]["casual"] == 1
    assert payload["classification"]["competitive"] == 1
    assert payload["missing_information"]["unresolved_cards"] == 2
    assert payload["suitability"]["deck_completion_training"] == "conditional"
    assert payload["suitability"]["performance_modeling"] == "suitable"
