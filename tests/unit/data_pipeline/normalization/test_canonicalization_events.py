from __future__ import annotations

import json
from pathlib import Path

from commander_ai.data_pipeline.normalization.canonicalization_events import (
    canonicalize_event_sources,
)
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord
from commander_ai.domain.provenance import SourceSnapshotManifest

ROOT = Path(__file__).resolve().parents[4]


def _manifest() -> SourceSnapshotManifest:
    payload = json.loads(
        (ROOT / "examples/source-snapshot-manifest.v2.json").read_text(encoding="utf-8")
    )
    return SourceSnapshotManifest.model_validate(payload)


def _record(
    record_type: str,
    values: dict[str, object],
    pointer: str,
    *,
    source_id: str = "fixture",
) -> StagingRecord:
    locator = RawLocator(
        source_id=source_id,
        source_snapshot_id="fixture-2026-08-10-v2",
        raw_object_id="object-001",
        raw_object_path="objects/object-001.json",
        location=JsonPointerLocator(pointer=pointer),
    )
    return StagingRecord.from_dto(
        SourceRecordDTO(
            source_id=source_id,
            record_type=record_type,
            raw_locator=locator,
            original_source_values=values,
        ),
        staging_record_id=f"staging-{record_type}-{pointer.replace('/', '-')}",
        status="OBSERVED",
    )


def test_event_observation_requires_an_explicit_canonical_deck_id() -> None:
    event = _record(
        "event",
        {"TID": "event-1", "format": "EDH", "startDate": "2026-08-10T18:00:00Z"},
        "/event",
    )
    standing = _record(
        "standing",
        {
            "event_id": "event-1",
            "player_id": "player-1",
            "wins": 3,
            "losses": 0,
            "draws": 0,
            "place": 1,
            "record": "3-0-0",
        },
        "/standing",
    )

    result = canonicalize_event_sources([event, standing], source_manifest=_manifest())

    assert not result.records
    assert "quality.canonical_deck_missing" in result.finding_codes
    assert len(result.quarantines) == 1


def test_event_observation_preserves_explicit_deck_and_minimized_participant() -> None:
    event = _record(
        "event",
        {"TID": "event-1", "format": "EDH", "startDate": "2026-08-10T18:00:00Z"},
        "/event",
    )
    standing = _record(
        "standing",
        {
            "event_id": "event-1",
            "player_id": "player-1",
            "canonical_deck_id": "a" * 64,
            "wins": 3,
            "losses": 0,
            "draws": 0,
            "place": 1,
            "record": "3-0-0",
        },
        "/standing",
    )

    result = canonicalize_event_sources([event, standing], source_manifest=_manifest())

    assert len(result.records) == 1
    observation = result.records[0].payload
    assert observation["canonical_deck_id"] == "a" * 64
    assert observation["participant_reference"]["scope"] == "source"  # type: ignore[index]
    assert "player-1" in observation["participant_reference"]["reference_id"]  # type: ignore[index]
    assert all("display_name" not in str(item.model_dump()) for item in result.records)


def test_topdeck_style_table_without_context_is_quarantined_not_flattened() -> None:
    table = _record(
        "table",
        {"players": [{"player_id": "p1"}, {"player_id": "p2"}]},
        "/table",
        source_id="topdeck",
    )

    result = canonicalize_event_sources(
        [table], source_manifest=_manifest().model_copy(update={"source_id": "topdeck"})
    )

    assert not result.records
    assert result.finding_codes == ("quality.pod_context_missing",)
    assert len(result.quarantines) == 1
