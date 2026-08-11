from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from commander_ai.adapters.sources.mtgjson.dto import (
    MTGJSONCard,
    MTGJSONCardFace,
    MTGJSONDeckProduct,
)
from commander_ai.adapters.sources.mtgjson.parser import MTGJSONParser
from commander_ai.adapters.sources.mtgjson.settings import MTGJSONProduct
from commander_ai.adapters.sources.mtgjson.staging import MTGJSONStagingMapper
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "mtgjson"


def _zip_members(members: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return output.getvalue()


def _verified_snapshot(tmp_path: Path, archive_bytes: bytes):
    store = RawSnapshotStore(tmp_path)
    writer = store.start_snapshot(
        source_id="mtgjson",
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
            "sanitized_endpoint": "https://fixture.invalid/api/v5/AllPrintings.zip",
            "format": "binary",
            "sanitized_parameters": {},
        }
    )
    writer.write_object(
        raw_object_id="AllPrintings.zip",
        request_id="archive-request",
        chunks=[archive_bytes],
        content_type="application/zip",
        source_object_id="AllPrintings",
    )
    writer.finalize()
    return SnapshotVerifier(tmp_path).verify_complete_snapshot("mtgjson", "mtgjson-fixture")


def test_parser_preserves_cards_printings_faces_and_required_source_fields(tmp_path: Path) -> None:
    archive = _zip_members({"AllPrintings.json": (FIXTURES / "all_printings.json").read_bytes()})
    verified = _verified_snapshot(tmp_path, archive)

    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id="AllPrintings.zip",
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
    assert verified.object_paths["AllPrintings.zip"].read_bytes() == archive
    assert result.extracted_root != verified.object_paths["AllPrintings.zip"]
    assert (result.extracted_root / "AllPrintings.json").is_file()


def test_parser_preserves_deck_product_commander_and_precon_metadata(tmp_path: Path) -> None:
    archive = _zip_members(
        {"decks/TST-commander.json": (FIXTURES / "deck_product.json").read_bytes()}
    )
    verified = _verified_snapshot(tmp_path, archive)

    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id="AllPrintings.zip",
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
        raw_object_id="AllPrintings.zip",
        destination=tmp_path / "derived" / "malformed",
        product=MTGJSONProduct.ALL_PRINTINGS,
    )

    malformed = [record for record in result.records if record.record_type == "card"]
    assert len(malformed) == 2
    assert malformed[0].source_values["name"] == "No UUID"
    assert malformed[0].finding_codes == ("parse.missing_required_field",)
    assert malformed[0].raw_locator.archive_member == "AllPrintings.json"
    assert malformed[0].raw_locator.location.pointer == "/data/BAD/cards/0"
    assert malformed[0].raw_locator.raw_object_id == "AllPrintings.zip"
    assert malformed[0].raw_locator.raw_object_path == "objects/AllPrintings.zip"
    assert malformed[1].finding_codes == ("parse.record_not_object",)
    assert malformed[1].raw_locator.location.pointer == "/data/BAD/cards/1"

    staging = MTGJSONStagingMapper().map_records(result.records)
    invalid = [row for row in staging if row.record_type == "card" and row.status != "OBSERVED"]
    assert {row.status for row in invalid} == {"STRUCTURAL_INVALID", "PARSE_FAILED"}
    assert all(row.raw_locator.source_snapshot_id == "mtgjson-fixture" for row in invalid)
    assert all(row.finding_codes for row in invalid)
