from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from commander_ai.adapters.reporting import ConfiguredReport, _canonical_metrics
from commander_ai.config.runtime import RuntimeConfig
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings
from commander_ai.data_pipeline.provenance.run_manifests import validate_run_manifest_bytes
from commander_ai.domain.observations import PodEntry

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _pod_record(
    source_record_id: str,
    pod_id: str,
    canonical_deck_id: str,
    seat: int,
    raw_object_id: str,
) -> dict[str, object]:
    result = _canonical_record("pod_entry", "canonical-deck.v1.json", raw_object_id)
    payload = PodEntry(
        pod_id=pod_id,
        event_id="event-001",
        round_number=1,
        seat=seat,
        canonical_deck_id=canonical_deck_id,
        result="win" if seat == 1 else "loss",
        provenance=tuple(result["provenance"]),  # type: ignore[arg-type]
    )
    result["source_record_id"] = source_record_id
    result["payload"] = payload.model_dump(mode="json")
    return result


def _canonical_record(record_type: str, payload_name: str, raw_object_id: str) -> dict[str, object]:
    envelope = json.loads(
        (PROJECT_ROOT / "examples" / "canonical-record.v1.json").read_text(encoding="utf-8")
    )
    payload = json.loads((PROJECT_ROOT / "examples" / payload_name).read_text(encoding="utf-8"))
    result = copy.deepcopy(envelope)
    result["record_type"] = record_type
    result["source_record_id"] = f"source-{record_type}"
    result["raw_locator"]["raw_object_id"] = raw_object_id  # type: ignore[index]
    result["payload"] = payload
    result["provenance"][0]["source_object_id"] = raw_object_id  # type: ignore[index]
    return result


def test_canonical_metrics_join_event_outcomes_to_structural_decks() -> None:
    rows = [
        _canonical_record("canonical_deck", "canonical-deck.v1.json", "deck-001"),
        _canonical_record("event_deck_observation", "event-deck-observation.v1.json", "event-001"),
    ]

    decks, resolution_counts, event_counts, pod_counts = _canonical_metrics(
        rows, [], source_id="fixture"
    )

    assert len(decks) == 1
    assert decks[0].usable_outcome is True
    assert resolution_counts == (0, 0, 0, 0)
    assert event_counts == (1, 1)
    assert pod_counts == (0, 0)


def test_canonical_metrics_counts_repeated_structural_outcome_once() -> None:
    first_deck = _canonical_record("canonical_deck", "canonical-deck.v1.json", "deck-z")
    first_deck["source_record_id"] = "source-deck-z"
    second_deck = _canonical_record("canonical_deck", "canonical-deck.v1.json", "deck-a")
    second_deck["source_record_id"] = "source-deck-a"
    first_observation = _canonical_record(
        "event_deck_observation", "event-deck-observation.v1.json", "event-z"
    )
    second_observation = _canonical_record(
        "event_deck_observation", "event-deck-observation.v1.json", "event-a"
    )

    decks, _, _, _ = _canonical_metrics(
        [first_deck, second_deck, first_observation, second_observation],
        [],
        source_id="fixture",
    )

    assert [item.deck_id for item in decks if item.usable_outcome] == ["source-deck-a"]
    assert sum(item.usable_outcome for item in decks) == 1


def test_canonical_metrics_counts_complete_pods_and_full_pod_decks() -> None:
    deck_id = "a15de215dbd5b7f2295fb2d1836519dd0c4b27ec7e40cf140cbd205641f44625"
    rows = [
        _canonical_record("canonical_deck", "canonical-deck.v1.json", "deck-001"),
        _pod_record("pod-001-seat-1", "pod-001", deck_id, 1, "pod-001-seat-1"),
        _pod_record("pod-001-seat-2", "pod-001", deck_id, 2, "pod-001-seat-2"),
    ]
    decks, _, _, pod_counts = _canonical_metrics(rows, [], source_id="fixture")

    assert pod_counts == (1, 1)
    assert decks[0].full_pod is True


def test_all_report_publishes_source_and_dataset_audit_artifacts_without_acquisition(
    tmp_path: Path,
) -> None:
    now = datetime(2026, 8, 11, tzinfo=UTC)
    historical = HistoricalApprovalMetadata(
        source_id="edhrec",
        approval_status=SourceApprovalStatus.PAUSED,
        review_path="docs/03-data/source-reviews/edhrec.md",
        reviewed_at=now,
        effective_at=now,
        reason="assessment-only fixture",
    )
    entry = SourceRegistryEntry(
        source_id="edhrec",
        settings=SourceSettings(
            source_id="edhrec",
            approval_status=SourceApprovalStatus.PAUSED,
            review_path=historical.review_path,
        ),
        historical_approval=historical,
        current_use=None,
    )

    class Provider:
        def load(self) -> tuple[SourceRegistry, Path]:
            return SourceRegistry(entries=(entry,)), Path("configs/sources/fixture.yaml")

    result = ConfiguredReport(
        RuntimeConfig(data_root=tmp_path, artifact_root=tmp_path), Provider()
    ).build_report("all")

    assert result.status == "COMPLETE"
    assert result.summary["audit_report_path"]
    audit_path = tmp_path / str(result.summary["audit_report_path"])
    assert audit_path.is_file()
    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["counts"]["total_decks"] == 0
    assert any(
        row["source_id"] == "edhrec" and row["assessment_only"] for row in audit["source_reports"]
    )

    run_path = tmp_path / f"runs/report-{result.summary['report_id']}/manifest.json"
    run = validate_run_manifest_bytes(run_path.read_bytes())
    artifact_paths = {artifact.path for artifact in run.artifacts}
    assert str(result.report_path) in artifact_paths
    assert str(result.summary["audit_report_path"]) in artifact_paths
    assert str(result.summary["audit_markdown_path"]) in artifact_paths
