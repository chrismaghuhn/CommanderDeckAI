from __future__ import annotations

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

from commander_ai.adapters.dataset_building import _dataset_records
from commander_ai.adapters.reporting import _canonical_metrics
from commander_ai.data_pipeline.splitting.deck_completion_policy import (
    DeckCompletionPolicy,
    build_deck_completion_splits,
)
from commander_ai.data_pipeline.splitting.group_promotion import TemporalCutoffs

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _canonical_record(record_type: str, payload_name: str, raw_object_id: str) -> dict[str, object]:
    envelope = json.loads(
        (PROJECT_ROOT / "examples" / "canonical-record.v1.json").read_text(encoding="utf-8")
    )
    payload = json.loads((PROJECT_ROOT / "examples" / payload_name).read_text(encoding="utf-8"))
    result = copy.deepcopy(envelope)
    result["record_type"] = record_type
    result["source_record_id"] = "deck-001"
    result["raw_locator"]["raw_object_id"] = raw_object_id  # type: ignore[index]
    result["payload"] = payload
    result["payload"]["provenance"] = copy.deepcopy(result["provenance"])  # type: ignore[index]
    result["provenance"][0]["source_object_id"] = raw_object_id  # type: ignore[index]
    return result


def test_dataset_records_join_evaluations_and_missing_legality_is_unknown() -> None:
    deck = _canonical_record("canonical_deck", "canonical-deck.v1.json", "deck-001")
    legality = _canonical_record(
        "deck_legality_evaluation", "deck-legality-evaluation.v1.json", "deck-001"
    )
    quality = _canonical_record(
        "deck_quality_evaluation", "deck-quality-evaluation.v1.json", "deck-001"
    )

    records = _dataset_records(
        "deck_completion",
        [deck, legality, quality],
        source_id="fixture",
        source_snapshot_id="fixture-2026-08-10-v2",
    )
    assert len(records) == 1
    assert records[0].legal_status == "legal"
    assert records[0].quality_status == "accepted"

    missing = _dataset_records(
        "deck_completion",
        [deck],
        source_id="fixture",
        source_snapshot_id="fixture-2026-08-10-v2",
    )[0]
    assert missing.legal_status == "unknown"
    assert missing.quality_status == "unknown"
    missing_legality = _dataset_records(
        "deck_completion",
        [deck, quality],
        source_id="fixture",
        source_snapshot_id="fixture-2026-08-10-v2",
    )[0]
    assert missing_legality.legal_status == "unknown"
    assert missing_legality.quality_status == "accepted"
    split = build_deck_completion_splits(
        (missing_legality,),
        DeckCompletionPolicy(
            cutoffs=TemporalCutoffs(
                train_until=datetime(2025, 1, 1, tzinfo=UTC),
                validation_until=datetime(2026, 1, 1, tzinfo=UTC),
            ),
            legal_decks_only=True,
        ),
    )
    assert split.assignments == ()
    assert split.exclusions[0].code == "legality.deck_not_eligible"


def test_report_metrics_read_legality_and_quality_evaluations() -> None:
    rows = [
        _canonical_record("canonical_deck", "canonical-deck.v1.json", "deck-001"),
        _canonical_record(
            "deck_legality_evaluation", "deck-legality-evaluation.v1.json", "deck-001"
        ),
        _canonical_record("deck_quality_evaluation", "deck-quality-evaluation.v1.json", "deck-001"),
    ]

    decks, _, _, _ = _canonical_metrics(rows, [], source_id="fixture")

    assert len(decks) == 1
    assert decks[0].legal_status == "legal"
    assert decks[0].quality_status == "accepted"
