from __future__ import annotations

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.data_pipeline.normalization.canonicalization import canonicalize_staging
from commander_ai.data_pipeline.normalization.canonicalization_events import (
    canonicalize_event_sources,
)
from commander_ai.data_pipeline.resolution.catalog_indexes import build_catalog_indexes
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord
from commander_ai.domain.cards import CanonicalCard
from commander_ai.domain.provenance import ProvenanceReference, SourceSnapshotManifest

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


def test_event_decklist_resolves_to_canonical_deck_and_observation() -> None:
    provenance = ProvenanceReference(
        source_id="fixture",
        source_snapshot_id="fixture-card-snapshot",
        source_object_id="cards.json",
        raw_sha256="0" * 64,
        retrieved_at="2026-08-10T18:00:30Z",
        adapter_version="fixture-card-adapter-v1",
        mapper_version="fixture-card-mapper-v1",
        approval_status="APPROVED_LOCAL",
    )
    catalog = build_catalog_indexes(
        cards=(
            CanonicalCard(
                card_snapshot_id="cards-fixture-v1",
                oracle_id="11111111-1111-4111-8111-111111111111",
                name="Fixture Commander",
                normalized_name="fixture commander",
                layout="normal",
                mana_value=2,
                colors=("U",),
                color_identity=("U",),
                types=("Creature",),
                legalities={"commander": "legal"},
                provenance=(provenance,),
            ),
            CanonicalCard(
                card_snapshot_id="cards-fixture-v1",
                oracle_id="22222222-2222-4222-8222-222222222222",
                name="Fixture Card A",
                normalized_name="fixture card a",
                layout="normal",
                mana_value=1,
                legalities={"commander": "legal"},
                provenance=(provenance,),
            ),
        ),
        faces=(),
        printings=(),
        source_records=(),
    )
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
            "deck_id": "event-deck-1",
            "deckObj": {
                "commander": ["Fixture Commander"],
                "cards": [{"name": "Fixture Card A", "quantity": 1}],
            },
            "place": 1,
            "wins": 1,
            "losses": 0,
            "draws": 0,
        },
        "/standing",
    )

    result = canonicalize_event_sources(
        [event, standing], source_manifest=_manifest(), card_catalog=catalog
    )

    assert {item.record_type for item in result.records} == {
        "canonical_deck",
        "event_deck_observation",
    }
    deck = next(item for item in result.records if item.record_type == "canonical_deck")
    observation = next(
        item for item in result.records if item.record_type == "event_deck_observation"
    )
    assert deck.source_record_id == "event-deck-1"
    assert observation.payload["canonical_deck_id"] == deck.payload["canonical_deck_id"]
    assert len(result.resolutions) == 2
    assert len(result.resolution_attempts) == 2
    assert not result.quarantines


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

    result = canonicalize_event_sources(
        [event, standing],
        source_manifest=_manifest(),
        allow_source_opaque_participant_id=True,
    )

    assert len(result.records) == 1
    observation = result.records[0].payload
    assert observation["canonical_deck_id"] == "a" * 64
    assert observation["participant_reference"]["scope"] == "source"  # type: ignore[index]
    assert "player-1" in observation["participant_reference"]["reference_id"]  # type: ignore[index]
    assert all("display_name" not in str(item.model_dump()) for item in result.records)


def test_nested_deck_object_id_is_used_but_top_level_standing_id_is_not() -> None:
    from commander_ai.data_pipeline.normalization.event_deck_canonicalization import (
        _deck_values,
        _source_deck_id,
    )

    record = _record("standing", {"id": "standing-1"}, "/standing")
    values = {"id": "standing-1", "deckObj": {"id": "deck-42"}}

    nested_values = _deck_values(values)

    assert _source_deck_id(values, record) == record.staging_record_id
    assert _source_deck_id(nested_values, record, allow_generic_id=True) == "deck-42"


def test_empty_outer_deck_id_does_not_shadow_nested_identity() -> None:
    from commander_ai.data_pipeline.normalization.event_deck_canonicalization import (
        _deck_values,
        _source_deck_id,
    )

    record = _record("standing", {"deck_id": None}, "/standing")
    values = {"deck_id": None, "name": "standing-name", "deckObj": {"id": "deck-42"}}

    nested_values = _deck_values(values)

    assert _source_deck_id(nested_values, record, allow_generic_id=True) == "deck-42"


def test_inline_standing_name_is_not_used_as_source_deck_identity() -> None:
    from commander_ai.data_pipeline.normalization.event_deck_canonicalization import (
        _source_deck_id,
    )

    record = _record("standing", {"name": "player-name"}, "/standing")

    assert _source_deck_id({"name": "player-name"}, record) == record.staging_record_id


def test_boolean_deck_id_alias_does_not_shadow_nested_identity() -> None:
    from commander_ai.data_pipeline.normalization.event_deck_canonicalization import (
        _deck_values,
        _source_deck_id,
    )

    record = _record("standing", {"deck_id": False}, "/standing")
    values = {"deck_id": False, "deckObj": {"id": "deck-42"}}

    assert _source_deck_id(_deck_values(values), record, allow_generic_id=True) == "deck-42"


def test_source_opaque_participant_ids_require_an_explicit_identity_policy() -> None:
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

    assert result.records[0].payload["participant_reference"] is None
    assert "quality.participant_source_id_not_retained" in result.finding_codes


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


def _topdeck_table_records(
    players: object,
    *,
    table_values: dict[str, object] | None = None,
) -> tuple[StagingRecord, StagingRecord, StagingRecord]:
    event = _record(
        "event",
        {"TID": "event-1", "format": "EDH", "startDate": "2026-08-10T18:00:00Z"},
        "/event",
        source_id="topdeck",
    )
    round_record = _record(
        "round",
        {"round": 1},
        "/event/rounds/0",
        source_id="topdeck",
    )
    values = {
        "tableId": "table-1",
        "status": "complete",
        "players": players,
    }
    values.update(table_values or {})
    table = _record(
        "table",
        values,
        "/event/rounds/0/tables/0",
        source_id="topdeck",
    )
    return event, round_record, table


def _four_topdeck_players() -> list[dict[str, object]]:
    labels = ("winner", "second", "third", "fourth")
    return [
        {
            "player_id": f"opaque-player-{seat}",
            "name": f"Participant {seat}",
            "handle": f"handle-{seat}",
            "seat": seat,
            "canonical_deck_id": f"{seat:x}" * 64,
            "result": labels[seat - 1],
        }
        for seat in range(1, 5)
    ]


def test_topdeck_frozen_table_players_produce_one_four_player_pod() -> None:
    event, round_record, table = _topdeck_table_records(_four_topdeck_players())
    manifest = _manifest().model_copy(update={"source_id": "topdeck"})

    result = canonicalize_event_sources(
        [event, round_record, table],
        source_manifest=manifest,
        allow_source_opaque_participant_id=True,
    )

    assert len(result.records) == 4
    assert {item.record_type for item in result.records} == {"pod_entry"}
    assert {item.payload["seat"] for item in result.records} == {1, 2, 3, 4}
    assert {item.payload["pod_id"] for item in result.records} == {"pod:topdeck:table-1"}
    assert {item.payload["event_id"] for item in result.records} == {"event:topdeck:event-1"}
    assert all(
        "Participant" not in json.dumps(item.payload) and "handle-" not in json.dumps(item.payload)
        for item in result.records
    )
    assert all(
        item.payload["participant_reference"]["scope"] == "source"  # type: ignore[index]
        and str(item.payload["participant_reference"]["reference_id"]).startswith(
            "participant:topdeck:"
        )  # type: ignore[index]
        for item in result.records
    )
    assert all(item.raw_locator == table.raw_locator for item in result.records)
    assert all(
        item.provenance[0].source_object_id == table.raw_locator.raw_object_id
        for item in result.records
    )
    assert result.pod_index.complete_pod_ids == ("pod:topdeck:table-1",)
    assert result.pod_index.complete_event_deck_keys == tuple(
        ("event:topdeck:event-1", f"{seat:x}" * 64) for seat in range(1, 5)
    )
    canonical_result = canonicalize_staging(
        [event, round_record, table],
        source_manifest=manifest,
    )
    assert canonical_result.pod_index == result.pod_index
    schema = json.loads(
        (ROOT / "schemas" / "canonical-record.v1.schema.json").read_text(encoding="utf-8")
    )
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    assert all(
        not list(validator.iter_errors(item.model_dump(mode="json"))) for item in result.records
    )


def test_topdeck_name_only_players_use_event_scoped_references_without_raw_names() -> None:
    players = _four_topdeck_players()
    for player in players:
        player.pop("player_id")
    event, round_record, table = _topdeck_table_records(players)

    result = canonicalize_event_sources(
        [event, round_record, table],
        source_manifest=_manifest().model_copy(update={"source_id": "topdeck"}),
    )

    assert len(result.records) == 4
    references = [item.payload["participant_reference"] for item in result.records]
    assert all(reference["scope"] == "event" for reference in references)  # type: ignore[index]
    assert all(
        str(reference["reference_id"]).startswith("event:")  # type: ignore[index]
        for reference in references
    )
    payload_text = json.dumps([item.payload for item in result.records])
    assert all(player["name"] not in payload_text for player in players)
    assert all(player["handle"] not in payload_text for player in players)


@pytest.mark.parametrize("pod_result", ["unknown", "bye"])
def test_topdeck_non_outcome_results_do_not_mark_pod_complete(pod_result: str) -> None:
    players = _four_topdeck_players()
    for player in players:
        player["result"] = pod_result
    event, round_record, table = _topdeck_table_records(players)

    result = canonicalize_event_sources(
        [event, round_record, table],
        source_manifest=_manifest().model_copy(update={"source_id": "topdeck"}),
    )

    assert len(result.records) == 4
    assert result.pod_index.complete_pod_ids == ()
    assert result.pod_index.complete_event_deck_keys == ()


@pytest.mark.parametrize(
    ("table_values", "players", "finding"),
    [
        (
            {"status": "complete"},
            [
                {
                    "player_id": "opaque-player-1",
                    "seat": 1,
                    "canonical_deck_id": "1" * 64,
                    "result": "win",
                },
                {
                    "player_id": "opaque-player-2",
                    "seat": 1,
                    "canonical_deck_id": "2" * 64,
                    "result": "loss",
                },
            ],
            "quality.pod_seat_duplicate",
        ),
        (
            {"status": "complete"},
            [
                {"player_id": "opaque-player-1", "seat": 1, "result": "win"},
                {
                    "player_id": "opaque-player-2",
                    "seat": 2,
                    "canonical_deck_id": "2" * 64,
                    "result": "loss",
                },
            ],
            "quality.pod_deck_unresolved",
        ),
        (
            {"status": None},
            _four_topdeck_players(),
            "quality.pod_status_unknown",
        ),
        (
            {"tableId": "table-1", "status": "complete"},
            _four_topdeck_players()[:1],
            "quality.pod_not_multiplayer",
        ),
        (
            {"round": 0},
            _four_topdeck_players(),
            "quality.pod_context_missing",
        ),
        (
            {"tableId": None},
            _four_topdeck_players(),
            "quality.pod_context_missing",
        ),
    ],
)
def test_topdeck_incomplete_table_is_quarantined(
    table_values: dict[str, object], players: object, finding: str
) -> None:
    event, round_record, table = _topdeck_table_records(players, table_values=table_values)

    result = canonicalize_event_sources(
        [event, round_record, table],
        source_manifest=_manifest().model_copy(update={"source_id": "topdeck"}),
    )

    assert not result.records
    assert finding in result.finding_codes
    assert len(result.quarantines) == 1


def test_topdeck_ambiguous_player_result_is_quarantined_without_guessing() -> None:
    players = _four_topdeck_players()
    players[2]["result"] = "mystery-result"
    event, round_record, table = _topdeck_table_records(players)

    result = canonicalize_event_sources(
        [event, round_record, table],
        source_manifest=_manifest().model_copy(update={"source_id": "topdeck"}),
    )

    assert not result.records
    assert "quality.pod_result_ambiguous" in result.finding_codes
