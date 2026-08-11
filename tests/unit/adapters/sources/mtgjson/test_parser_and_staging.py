from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from commander_ai.adapters.sources.mtgjson.dto import (
    MTGJSONCard,
    MTGJSONCardFace,
    MTGJSONDeckProduct,
)
from commander_ai.adapters.sources.mtgjson.parser import MTGJSONParseError, MTGJSONParser
from commander_ai.adapters.sources.mtgjson.settings import MTGJSONProduct
from commander_ai.adapters.sources.mtgjson.staging import MTGJSONStagingMapper
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    RawLocator,
    RecordIndexLocator,
    validate_raw_locator_against_snapshot,
)
from commander_ai.data_pipeline.staging.records import StagingRecord

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "mtgjson"


def _zip_members(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()


def _verified_snapshot(
    tmp_path: Path,
    archive_bytes: bytes,
    *,
    source_id: str = "mtgjson",
    raw_object_id: str = "AllPrintings.json.zip",
    source_object_id: str = "AllPrintings",
    logical_record_count: int | None = None,
):
    store = RawSnapshotStore(tmp_path)
    writer = store.start_snapshot(
        source_id=source_id,
        snapshot_id="mtgjson-fixture",
        approval_status="APPROVED_LOCAL",
        adapter_version="mtgjson-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
        attribution_required=True,
        redistribution_status="derived_only",
    )
    writer.add_request(
        {
            "request_id": "archive-request",
            "sanitized_method": "GET",
            "sanitized_endpoint": f"https://fixture.invalid/api/v5/{raw_object_id}",
            "format": "binary",
            "sanitized_parameters": {},
        }
    )
    writer.write_object(
        raw_object_id=raw_object_id,
        request_id="archive-request",
        chunks=[archive_bytes],
        content_type="application/zip",
        source_object_id=source_object_id,
        logical_record_count=logical_record_count,
    )
    writer.finalize()
    return SnapshotVerifier(tmp_path).verify_complete_snapshot(source_id, "mtgjson-fixture")


def test_parser_preserves_cards_printings_faces_and_required_source_fields(tmp_path: Path) -> None:
    archive = _zip_members({"AllPrintings.json": (FIXTURES / "all_printings.json").read_bytes()})
    verified = _verified_snapshot(tmp_path, archive)

    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id="AllPrintings.json.zip",
        destination=tmp_path / "derived" / "all-printings",
        product=MTGJSONProduct.ALL_PRINTINGS,
    )

    cards = [record for record in result.records if record.record_type == "card"]
    faces = [record for record in result.records if record.record_type == "card_face"]
    assert len(cards) == 5
    assert len(faces) == 2

    normal = next(record.dto for record in cards if record.dto.uuid == "normal-printing-1")
    assert isinstance(normal, MTGJSONCard)
    assert normal.mana_cost == "{2}{U}"
    assert normal.mana_value == 3
    assert normal.color_identity == ("U",)
    assert normal.types == ("Creature",)
    assert normal.subtypes == ("Wizard",)
    assert normal.oracle_text == "Draw a card."
    assert normal.keywords == ("Flying",)
    assert normal.identifiers["scryfallId"] == "scryfall-normal"
    assert normal.legalities["commander"] == "Legal"

    dfc = next(record.dto for record in cards if record.dto.uuid == "dfc-front")
    assert isinstance(dfc, MTGJSONCard)
    assert dfc.other_face_ids == ("dfc-back",)
    assert dfc.card_parts == ("Taskbound", "Task Unbound")
    assert dfc.rules_text == "Vigilance"

    face_dtos = [record.dto for record in faces]
    assert all(isinstance(face, MTGJSONCardFace) for face in face_dtos)
    assert {face.face_name for face in face_dtos} == {"Taskbound", "Task Unbound"}
    assert {face.side for face in face_dtos} == {"a", "b"}
    assert len({record.raw_locator.exact_locator for record in result.records}) == len(
        result.records
    )
    staging = MTGJSONStagingMapper().map_records(result.records)
    artifact = ParquetTableWriter(tmp_path / "artifacts").write_table(
        "cards",
        staging,
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
    )
    assert artifact.rows == len(staging)
    face_pointers = {
        record.dto.uuid: record.raw_locator.location.pointer
        for record in faces
        if record.dto is not None
    }
    assert face_pointers["dfc-front"].endswith("/faceName")
    assert face_pointers["dfc-back"].endswith("/faceName")

    split = next(record.dto for record in cards if record.dto.uuid == "split-printing")
    assert isinstance(split, MTGJSONCard)
    assert split.layout == "split"
    assert split.card_parts == ("Search", "Find")
    assert split.rules_text.startswith("Draw a card.")

    normal_printings = [record for record in cards if record.dto.name == "Test Adept"]
    assert {record.dto.uuid for record in normal_printings} == {
        "normal-printing-1",
        "normal-printing-2",
    }
    assert verified.object_paths["AllPrintings.json.zip"].read_bytes() == archive
    assert result.extracted_root != verified.object_paths["AllPrintings.json.zip"]
    assert (result.extracted_root / "AllPrintings.json").is_file()


def test_parser_preserves_deck_product_commander_and_precon_metadata(tmp_path: Path) -> None:
    archive = _zip_members(
        {"decks/TST-commander.json": (FIXTURES / "deck_product.json").read_bytes()}
    )
    verified = _verified_snapshot(
        tmp_path,
        archive,
        raw_object_id="AllDeckFiles.json.zip",
        source_object_id="AllDeckFiles",
    )

    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id="AllDeckFiles.json.zip",
        destination=tmp_path / "derived" / "decks",
        product=MTGJSONProduct.ALL_DECK_FILES,
    )

    products = [record.dto for record in result.records if record.record_type == "deck_product"]
    assert len(products) == 1
    product = products[0]
    assert isinstance(product, MTGJSONDeckProduct)
    assert product.commander[0]["name"] == "Test Adept"
    assert product.source_products[0]["productType"] == "precon"
    assert product.partner["name"] == "Partner Fixture"
    assert product.background["name"] == "Background Fixture"
    assert result.records[0].raw_locator.archive_member == "decks/TST-commander.json"


def test_malformed_records_are_retained_with_namespaced_findings_and_exact_locators(
    tmp_path: Path,
) -> None:
    payload = {
        "meta": {"version": "fixture"},
        "data": {
            "BAD": {
                "code": "BAD",
                "name": "Malformed Set",
                "cards": [{"name": "No UUID", "oracleText": "retained"}, "not an object"],
            }
        },
    }
    archive = _zip_members({"AllPrintings.json": json.dumps(payload).encode("utf-8")})
    verified = _verified_snapshot(tmp_path, archive)
    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id="AllPrintings.json.zip",
        destination=tmp_path / "derived" / "malformed",
        product=MTGJSONProduct.ALL_PRINTINGS,
    )

    malformed = [record for record in result.records if record.record_type == "card"]
    assert len(malformed) == 2
    assert malformed[0].source_values["name"] == "No UUID"
    assert malformed[0].finding_codes == ("parse.missing_required_field",)
    assert malformed[0].raw_locator.archive_member == "AllPrintings.json"
    assert malformed[0].raw_locator.location.pointer == "/data/BAD/cards/0"
    assert malformed[0].raw_locator.source_id == "mtgjson"
    assert malformed[0].raw_locator.raw_object_id == "AllPrintings.json.zip"
    assert malformed[0].raw_locator.raw_object_path == "objects/AllPrintings.json.zip"
    assert malformed[1].finding_codes == ("parse.record_not_object",)
    assert malformed[1].raw_locator.location.pointer == "/data/BAD/cards/1"

    staging = MTGJSONStagingMapper().map_records(result.records)
    assert len({row.staging_record_id for row in staging}) == len(staging)
    invalid = [row for row in staging if row.record_type == "card" and row.status != "OBSERVED"]
    assert {row.status for row in invalid} == {"STRUCTURAL_INVALID", "PARSE_FAILED"}
    assert all(row.raw_locator.source_snapshot_id == "mtgjson-fixture" for row in invalid)
    assert all(row.finding_codes for row in invalid)


def test_parser_rejects_member_bytes_that_do_not_match_verified_archive(
    tmp_path: Path,
) -> None:
    archive = _zip_members({"AllPrintings.json": b'{"meta":{},"data":{}}'})
    verified = _verified_snapshot(tmp_path, archive)

    with pytest.raises(MTGJSONParseError) as error:
        MTGJSONParser().parse_member(
            verified_snapshot=verified,
            raw_object_id="AllPrintings.json.zip",
            archive_member="AllPrintings.json",
            member_bytes=b'{"meta":{},"data":{"evil":true}}',
            product=MTGJSONProduct.ALL_PRINTINGS,
        )

    assert error.value.code == "INTEGRITY_ARCHIVE_MEMBER_MISMATCH"


def test_parser_rejects_a_verified_snapshot_from_a_different_source(tmp_path: Path) -> None:
    archive = _zip_members({"AllPrintings.json": b'{"meta":{},"data":{}}'})
    verified = _verified_snapshot(tmp_path, archive, source_id="other-source")

    with pytest.raises(MTGJSONParseError) as error:
        MTGJSONParser().parse_archive(
            verified,
            raw_object_id="AllPrintings.json.zip",
            destination=tmp_path / "derived" / "wrong-source",
            product=MTGJSONProduct.ALL_PRINTINGS,
        )

    assert error.value.code == "INTEGRITY_SOURCE_MISMATCH"


def test_parser_binds_product_to_verified_raw_object_identity(tmp_path: Path) -> None:
    archive = _zip_members({"AllPrintings.json": b'{"meta":{},"data":{}}'})
    verified = _verified_snapshot(
        tmp_path,
        archive,
        source_object_id="AllDeckFiles",
    )

    with pytest.raises(MTGJSONParseError) as error:
        MTGJSONParser().parse_archive(
            verified,
            raw_object_id="AllPrintings.json.zip",
            destination=tmp_path / "derived" / "wrong-product",
            product=MTGJSONProduct.ALL_PRINTINGS,
        )

    assert error.value.code == "INTEGRITY_PRODUCT_MISMATCH"


def test_locator_validation_rejects_missing_member_pointer_and_record_index(
    tmp_path: Path,
) -> None:
    archive = _zip_members({"records.json": b'[{"name":"one"}]'})
    verified = _verified_snapshot(
        tmp_path,
        archive,
        raw_object_id="AllPrintings.json.zip",
        source_object_id="AllPrintings",
        logical_record_count=1,
    )

    def locator(*, member: str, location: object) -> RawLocator:
        return RawLocator(
            source_id="mtgjson",
            source_snapshot_id="mtgjson-fixture",
            raw_object_id="AllPrintings.json.zip",
            raw_object_path="objects/AllPrintings.json.zip",
            archive_member=member,
            location=location,
        )

    cases = (
        (locator(member="missing.json", location=JsonPointerLocator(pointer="")), "member"),
        (
            locator(member="records.json", location=JsonPointerLocator(pointer="/missing")),
            "pointer",
        ),
        (locator(member="records.json", location=RecordIndexLocator(index=1)), "record index"),
    )
    for candidate, message in cases:
        with pytest.raises(ValueError, match=message):
            validate_raw_locator_against_snapshot(candidate, verified_snapshot=verified)


def test_invalid_member_bytes_are_json_safe_and_persistable_in_staging(tmp_path: Path) -> None:
    archive = _zip_members({"AllPrintings.json": b"\xff\xee\x00"})
    verified = _verified_snapshot(tmp_path, archive)
    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id="AllPrintings.json.zip",
        destination=tmp_path / "derived" / "invalid-bytes",
        product=MTGJSONProduct.ALL_PRINTINGS,
    )

    staging = MTGJSONStagingMapper().map_records(result.records)
    encoded = staging[0].original_source_values
    assert encoded["encoding"] == "base64"
    assert encoded["byte_length"] == 3
    assert encoded["sha256"]
    artifact = ParquetTableWriter(tmp_path / "artifacts").write_table(
        "staging",
        staging,
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
    )

    persisted = ParquetTableWriter(tmp_path / "artifacts").read_table(artifact.path)
    assert persisted[0]["original_source_values"]["data"] == "/+4A"


def test_mtgjson_dto_keeps_forward_fields_but_freezes_nested_values() -> None:
    card = MTGJSONCard.model_validate(
        {
            "uuid": "future-card",
            "name": "Future Card",
            "futureField": {"values": [1, 2]},
        }
    )

    future_field = card.model_extra["futureField"]
    assert card.model_dump(mode="json")["futureField"] == {"values": [1, 2]}
    with pytest.raises(TypeError):
        future_field["values"] = (3,)  # type: ignore[index]
