from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

import pytest

from commander_ai.adapters.sources.topdeck.parser import TopDeckParser
from commander_ai.adapters.sources.topdeck.settings import TopDeckSettings
from commander_ai.adapters.sources.topdeck.staging import TopDeckStagingMapper
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotIntegrityError, SnapshotVerifier
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator
from commander_ai.domain.serialization import canonical_json_bytes

FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "topdeck"


def _settings() -> TopDeckSettings:
    return TopDeckSettings.from_source_settings(
        SourceSettings(
            source_id="topdeck",
            approval_status=SourceApprovalStatus.APPROVED_LOCAL,
            endpoints=("https://topdeck.gg",),
            host_allowlist=("topdeck.gg",),
            api_key_env="TOPDECK_API_KEY",
            filters={"game": "Magic: The Gathering", "formats": ["EDH"]},
        )
    )


def _fixture() -> bytes:
    return (FIXTURE_ROOT / "valid_tournaments.json").read_bytes()


def _verified_snapshot(
    tmp_path: Path,
    raw: bytes,
    *,
    content_encoding: str | None = None,
    snapshot_id: str = "topdeck-parser-fixture",
):
    settings = _settings()
    request_parameters = settings.request_parameters()
    store = RawSnapshotStore(tmp_path)
    writer = store.start_snapshot(
        source_id="topdeck",
        snapshot_id=snapshot_id,
        approval_status="APPROVED_LOCAL",
        adapter_version="topdeck-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
    )
    writer.add_request(
        {
            "request_id": "topdeck-tournaments-v2",
            "sanitized_method": "POST",
            "sanitized_endpoint": settings.endpoint,
            "api_version": "v2",
            "format": "json",
            "request_body_sha256": hashlib.sha256(
                canonical_json_bytes(request_parameters)
            ).hexdigest(),
            "sanitized_parameters": request_parameters,
        }
    )
    writer.write_object(
        raw_object_id="tournaments-v2.json",
        request_id="topdeck-tournaments-v2",
        chunks=[raw],
        content_type="application/json",
        content_encoding=content_encoding,
        source_object_id="tournaments-v2",
    )
    writer.finalize()
    return SnapshotVerifier(tmp_path).verify_complete_snapshot("topdeck", snapshot_id)


def test_parser_preserves_event_deck_standing_round_table_and_all_players(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture())
    records = TopDeckParser(_settings()).parse_object(verified)

    event = next(item for item in records if item.record_type == "event")
    assert event.raw_locator.location == JsonPointerLocator(pointer="/0")
    assert event.dto.event_id == "fixture-event-1"
    assert event.dto.format == "EDH"
    assert event.dto.event_at.isoformat() == "2026-08-10T18:00:00+00:00"

    standing = next(item for item in records if item.record_type == "standing")
    assert standing.dto.player_id == "fixture-player-1"
    assert standing.dto.wins == 3
    assert standing.dto.losses == 0
    assert standing.dto.draws == 0
    assert standing.dto.place == 1

    deck = next(item for item in records if item.record_type == "deck")
    assert deck.raw_locator.location == JsonPointerLocator(pointer="/0/standings/0/deckObj")
    assert deck.source_values["cards"][0]["name"] == "Fixture Card A"

    table = next(item for item in records if item.record_type == "table")
    assert table.dto.winner_id == "fixture-player-1"
    assert len(table.source_values["players"]) == 4
    assert table.source_values["players"][0]["player_id"] == "fixture-player-1"
    assert sum(item.record_type == "table_player" for item in records) == 4
    assert not any(item.record_type in {"staff", "attendee"} for item in records)
    assert all("canonical_deck_id" not in item.model_dump(mode="json") for item in records)
    assert all(
        "not-for-curated@example.invalid" not in json.dumps(item.model_dump(mode="json"))
        for item in records
    )


def test_parser_preserves_opaque_id_and_name_for_later_participant_resolution(
    tmp_path: Path,
) -> None:
    payload = [
        {
            "TID": "fixture-event-named",
            "format": "EDH",
            "rounds": [
                {
                    "round": 1,
                    "tables": [
                        {
                            "tableId": "fixture-table-named",
                            "players": [
                                {
                                    "player_id": "opaque-player-1",
                                    "name": "Player Name",
                                    "handle": "player-handle",
                                    "seat": 1,
                                    "result": "winner",
                                }
                            ],
                            "status": "complete",
                        }
                    ],
                }
            ],
        }
    ]
    verified = _verified_snapshot(tmp_path, json.dumps(payload).encode("utf-8"))

    table = next(
        item
        for item in TopDeckParser(_settings()).parse_object(verified)
        if item.record_type == "table"
    )

    player = table.source_values["players"][0]
    assert player["player_id"] == "opaque-player-1"
    assert player["name"] == "Player Name"
    assert player["handle"] == "player-handle"


def test_staging_keeps_source_tables_and_audit_findings_without_canonical_observations(
    tmp_path: Path,
) -> None:
    verified = _verified_snapshot(tmp_path, _fixture())
    parser = TopDeckParser(_settings())
    records = parser.parse_object(verified)
    mapper = TopDeckStagingMapper(_settings())

    staging = mapper.map_records(records, verified_snapshot=verified)
    audits = mapper.map_audit_records(records, verified_snapshot=verified)

    assert len(staging) == len(records)
    assert all(row.layer == "staging" for row in staging)
    assert all(row.has_canonical_identity is False for row in staging)
    assert any(row.record_type == "table" for row in staging)
    assert audits == ()


def test_ambiguous_table_result_is_preserved_as_a_parse_finding(tmp_path: Path) -> None:
    payload = [
        {
            "TID": "fixture-event-ambiguous",
            "format": "EDH",
            "rounds": [{"round": 1, "tables": [{"players": [{"id": "p1"}, {"id": "p2"}]}]}],
        }
    ]
    verified = _verified_snapshot(tmp_path, json.dumps(payload).encode("utf-8"))
    records = TopDeckParser(_settings()).parse_object(verified)
    table = next(item for item in records if item.record_type == "table")
    assert table.finding_codes == ("parse.topdeck_ambiguous_result_semantics",)

    audits = TopDeckStagingMapper(_settings()).map_audit_records(
        (table,), verified_snapshot=verified
    )
    assert audits[0].stage == "parse"
    assert audits[0].finding_code == "parse.topdeck_ambiguous_result_semantics"


def test_compressed_raw_entity_is_decoded_only_after_raw_verification(tmp_path: Path) -> None:
    raw = _fixture()
    encoded = gzip.compress(raw)
    verified = _verified_snapshot(tmp_path, encoded, content_encoding="gzip")
    records = TopDeckParser(_settings()).parse_object(verified)
    assert (
        next(item for item in records if item.record_type == "event").dto.event_id
        == "fixture-event-1"
    )
    assert verified.object_paths["tournaments-v2.json"].read_bytes() == encoded


def test_invalid_json_remains_auditable_and_is_not_curated(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, b'{"broken":')
    records = TopDeckParser(_settings()).parse_object(verified)
    assert len(records) == 1
    assert records[0].record_type == "response"
    assert records[0].finding_codes == ("parse.topdeck_invalid_json",)
    row = TopDeckStagingMapper(_settings()).map_records(records, verified_snapshot=verified)[0]
    assert row.status == "PARSE_FAILED"
    assert row.has_canonical_identity is False


def test_staging_rejects_forged_source_values(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture())
    records = TopDeckParser(_settings()).parse_object(verified)
    forged = records[0].model_copy(update={"source_values": {"TID": "forged"}})
    with pytest.raises(ValueError, match="does not match verified source"):
        TopDeckStagingMapper(_settings()).map_records((forged,), verified_snapshot=verified)


def test_parser_requires_complete_verified_snapshot(tmp_path: Path) -> None:
    store = RawSnapshotStore(tmp_path)
    writer = store.start_snapshot(
        source_id="topdeck",
        snapshot_id="incomplete",
        approval_status="APPROVED_LOCAL",
        adapter_version="topdeck-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
    )
    writer.add_request(
        {
            "request_id": "request",
            "sanitized_method": "POST",
            "sanitized_endpoint": "https://topdeck.gg/api/v2/tournaments",
            "api_version": "v2",
            "format": "json",
            "request_body_sha256": "0" * 64,
        }
    )
    writer.write_object(
        raw_object_id="tournaments-v2.json",
        request_id="request",
        chunks=[_fixture()],
        source_object_id="tournaments-v2",
    )
    with pytest.raises(SnapshotIntegrityError) as error:
        SnapshotVerifier(tmp_path).verify_complete_snapshot("topdeck", "incomplete")
    assert error.value.code == "INTEGRITY_SNAPSHOT_NOT_COMPLETE"
