from __future__ import annotations

import copy
import json
from pathlib import Path

from commander_ai.adapters.reporting import _canonical_metrics

PROJECT_ROOT = Path(__file__).resolve().parents[3]


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
