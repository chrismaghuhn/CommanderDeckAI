from __future__ import annotations

import base64
import hashlib
import io
import json
import stat
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
from commander_ai.adapters.storage.archive_safety import ArchiveLimits
from commander_ai.adapters.storage.parquet_tables import (
    ParquetTableWriter,
    validate_parquet_table_rows,
)
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.data_pipeline.provenance.rows import AuditRecord
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
    assert all(record.raw_locator.location.kind == "json_pointer" for record in result.records)
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


@pytest.mark.parametrize(
    ("field_name", "raw_scalar", "scalar_type", "expected_raw"),
    [
        ("manaValue", b"NaN", "non_finite_number", b"NaN"),
        ("manaValue", b"Infinity", "non_finite_number", b"Infinity"),
        ("manaValue", b"-Infinity", "non_finite_number", b"-Infinity"),
        ("name", b'"\\ud800"', "invalid_unicode_scalar", b'"\\ud800"'),
    ],
)
def test_malformed_json_scalars_are_retained_as_structural_staging_findings(
    tmp_path: Path,
    field_name: str,
    raw_scalar: bytes,
    scalar_type: str,
    expected_raw: bytes,
) -> None:
    if field_name == "name":
        card = b'{"uuid":"malformed-card","name":' + raw_scalar + b"}"
    else:
        card = (
            b'{"uuid":"malformed-card","name":"Malformed Card","'
            + field_name.encode("ascii")
            + b'":'
            + raw_scalar
            + b"}"
        )
    member = (
        b'{"meta":{},"data":{"BAD":{"code":"BAD","name":"Malformed Set","cards":[' + card + b"]}}}"
    )
    verified = _verified_snapshot(tmp_path, _zip_members({"AllPrintings.json": member}))

    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id="AllPrintings.json.zip",
        destination=tmp_path / "derived" / "malformed-scalars",
        product=MTGJSONProduct.ALL_PRINTINGS,
    )

    card_record = next(record for record in result.records if record.record_type == "card")
    assert card_record.dto is None
    assert card_record.finding_codes == ("parse.malformed_scalar",)
    envelope = card_record.source_values[field_name]
    assert envelope["encoding"] == "base64"
    assert envelope["scalar_type"] == scalar_type
    assert base64.b64decode(envelope["data"]) == expected_raw

    staging = MTGJSONStagingMapper().map_records((card_record,))
    row = staging[0]
    assert row.status == "STRUCTURAL_INVALID"
    assert row.finding_codes == ("parse.malformed_scalar",)
    assert row.has_canonical_identity is False
    row.model_dump(mode="json")

    audit = AuditRecord(
        audit_id="audit-malformed-scalar",
        entity_id=row.staging_record_id,
        stage="parse",
        finding_code="parse.malformed_scalar",
        raw_locator=row.raw_locator,
        details={"original_source_values": row.original_source_values},
    )
    writer = ParquetTableWriter(tmp_path / "artifacts")
    staging_artifact = writer.write_table(
        "staging",
        [row],
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
    )
    audit_artifact = writer.write_table(
        "audit",
        [audit],
        layer="audit",
        row_contract=AuditRecord,
        verified_snapshot=verified,
    )

    persisted_staging = writer.read_table(staging_artifact.path)
    assert persisted_staging == [row.model_dump(mode="json")]
    validate_parquet_table_rows(
        tmp_path / "artifacts" / audit_artifact.path,
        layer="audit",
        verified_snapshot=verified,
    )


def test_malformed_json_object_keys_are_retained_through_staging_audit_and_parquet(
    tmp_path: Path,
) -> None:
    malformed_key = b"\\ud800"
    card = (
        b'{"uuid":"malformed-key-card","name":"Malformed Key Card","'
        + malformed_key
        + b'":"retained"}'
    )
    member = (
        b'{"meta":{},"data":{"BAD":{"code":"BAD","name":"Malformed Set","cards":[' + card + b"]}}}"
    )
    verified = _verified_snapshot(tmp_path, _zip_members({"AllPrintings.json": member}))

    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id="AllPrintings.json.zip",
        destination=tmp_path / "derived" / "malformed-keys",
        product=MTGJSONProduct.ALL_PRINTINGS,
    )

    card_record = next(record for record in result.records if record.record_type == "card")
    assert card_record.dto is None
    assert card_record.finding_codes == ("parse.malformed_scalar",)
    object_envelope = card_record.source_values
    assert object_envelope["encoding"] == "json_object_entries"
    malformed_entry = next(
        entry for entry in object_envelope["entries"] if entry["key"].get("role") == "object_key"
    )
    key_envelope = malformed_entry["key"]
    assert key_envelope["scalar_type"] == "invalid_unicode_scalar"
    assert base64.b64decode(key_envelope["data"]) == b'"\\ud800"'

    staging = MTGJSONStagingMapper().map_records((card_record,))
    row = staging[0]
    assert row.status == "STRUCTURAL_INVALID"
    assert row.finding_codes == ("parse.malformed_scalar",)
    row_payload = row.model_dump(mode="json")
    assert row_payload["original_source_values"] == json.loads(
        json.dumps(object_envelope, sort_keys=True)
    )

    audit = AuditRecord(
        audit_id="audit-malformed-key",
        entity_id=row.staging_record_id,
        stage="parse",
        finding_code="parse.malformed_scalar",
        raw_locator=row.raw_locator,
        details={"original_source_values": row.original_source_values},
    )
    writer = ParquetTableWriter(tmp_path / "artifacts")
    staging_artifact = writer.write_table(
        "staging",
        [row],
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
    )
    audit_artifact = writer.write_table(
        "audit",
        [audit],
        layer="audit",
        row_contract=AuditRecord,
        verified_snapshot=verified,
    )

    assert writer.read_table(staging_artifact.path) == [row_payload]
    validate_parquet_table_rows(
        tmp_path / "artifacts" / audit_artifact.path,
        layer="audit",
        verified_snapshot=verified,
    )


@pytest.mark.parametrize(
    ("product", "raw_object_id", "source_object_id", "member_name", "record_type"),
    [
        (
            MTGJSONProduct.ALL_PRINTINGS,
            "AllPrintings.json.zip",
            "AllPrintings",
            "AllPrintings.json",
            "set",
        ),
        (
            MTGJSONProduct.ALL_DECK_FILES,
            "AllDeckFiles.json.zip",
            "AllDeckFiles",
            "AllDeckFiles.json",
            "deck_product",
        ),
    ],
)
def test_malformed_record_identity_uses_a_reconstructable_entry_locator(
    tmp_path: Path,
    product: MTGJSONProduct,
    raw_object_id: str,
    source_object_id: str,
    member_name: str,
    record_type: str,
) -> None:
    malformed_key = b"\\ud800"
    if product is MTGJSONProduct.ALL_PRINTINGS:
        value = (
            b'{"code":"BAD","name":"Malformed Set","cards":['
            b'{"uuid":"nested-card","name":"Nested Card"}]}'
        )
    else:
        value = (
            b'{"code":"BAD","name":"Malformed Deck","mainBoard":[],"sideBoard":[],"type":"precon"}'
        )
    member = b'{"meta":{},"data":{"' + malformed_key + b'":' + value + b"}}"
    archive = _zip_members({member_name: member})
    verified = _verified_snapshot(
        tmp_path,
        archive,
        raw_object_id=raw_object_id,
        source_object_id=source_object_id,
    )

    result = MTGJSONParser().parse_archive(
        verified,
        raw_object_id=raw_object_id,
        destination=tmp_path / "derived" / product.value,
        product=product,
    )
    record = next(item for item in result.records if item.record_type == record_type)

    assert record.dto is None
    assert record.finding_codes == ("parse.malformed_scalar",)
    location = record.raw_locator.location
    assert location.kind == "json_object_entry"
    assert location.parent_pointer == "/data"
    assert location.entry_index == 0
    assert location.key_base64 == base64.b64encode(b'"\\ud800"').decode("ascii")
    assert location.key_byte_length == len(b'"\\ud800"')
    assert location.key_sha256 == hashlib.sha256(b'"\\ud800"').hexdigest()

    locator_text = record.raw_locator.exact_locator
    assert all(not 0xD800 <= ord(character) <= 0xDFFF for character in locator_text)
    locator_text.encode("utf-8")
    validate_raw_locator_against_snapshot(record.raw_locator, verified_snapshot=verified)
    with pytest.raises(ValueError, match="outside"):
        validate_raw_locator_against_snapshot(
            record.raw_locator.model_copy(
                update={"location": location.model_copy(update={"entry_index": 1})}
            ),
            verified_snapshot=verified,
        )
    with pytest.raises(ValueError, match="sha256"):
        location.model_copy(update={"key_sha256": "0" * 64})

    if product is MTGJSONProduct.ALL_PRINTINGS:
        nested_card = next(item for item in result.records if item.record_type == "card")
        assert nested_card.raw_locator.location.kind == "json_object_entry"
        assert nested_card.raw_locator.location.value_pointer == "/cards/0"
        validate_raw_locator_against_snapshot(nested_card.raw_locator, verified_snapshot=verified)

    source_values = record.source_values
    assert source_values["encoding"] == "json_object_entries"
    assert source_values["entry_count"] == 1
    entry = source_values["entries"][0]
    assert entry["key"]["role"] == "object_key"
    assert entry["key"]["data"] == location.key_base64
    assert entry["value"]["code"] == "BAD"
    assert (
        source_values["sha256"]
        == hashlib.sha256(
            json.dumps(
                {"entries": source_values["entries"]}, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()
    )

    staging = MTGJSONStagingMapper().map_records((record,))
    row = staging[0]
    assert row.status == "STRUCTURAL_INVALID"
    assert row.finding_codes == ("parse.malformed_scalar",)
    row_payload = row.model_dump(mode="json")
    json.dumps(row_payload, ensure_ascii=False).encode("utf-8")

    audit = AuditRecord(
        audit_id="audit-malformed-identity",
        entity_id=row.staging_record_id,
        stage="parse",
        finding_code="parse.malformed_scalar",
        raw_locator=row.raw_locator,
        details={"original_source_values": row.original_source_values},
    )
    writer = ParquetTableWriter(tmp_path / "artifacts")
    staging_artifact = writer.write_table(
        "staging",
        [row],
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
    )
    audit_artifact = writer.write_table(
        "audit",
        [audit],
        layer="audit",
        row_contract=AuditRecord,
        verified_snapshot=verified,
    )

    assert writer.read_table(staging_artifact.path) == [row_payload]
    validate_parquet_table_rows(
        tmp_path / "artifacts" / staging_artifact.path,
        layer="normalized",
        verified_snapshot=verified,
    )
    validate_parquet_table_rows(
        tmp_path / "artifacts" / audit_artifact.path,
        layer="audit",
        verified_snapshot=verified,
    )

    repeat = MTGJSONParser().parse_archive(
        verified,
        raw_object_id=raw_object_id,
        destination=tmp_path / "derived" / f"{product.value}-repeat",
        product=product,
    )
    repeat_record = next(item for item in repeat.records if item.record_type == record_type)
    repeat_row = MTGJSONStagingMapper().map_records((repeat_record,))[0]
    assert repeat_record.raw_locator.exact_locator == locator_text
    assert repeat_record.source_values["sha256"] == source_values["sha256"]
    assert repeat_row.staging_record_id == row.staging_record_id


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


def test_locator_validation_rejects_a_compression_bomb_with_shared_security_code(
    tmp_path: Path,
) -> None:
    archive = _zip_members({"records.json": b"a" * 100_000})
    verified = _verified_snapshot(tmp_path, archive)
    candidate = RawLocator(
        source_id="mtgjson",
        source_snapshot_id="mtgjson-fixture",
        raw_object_id="AllPrintings.json.zip",
        raw_object_path="objects/AllPrintings.json.zip",
        archive_member="records.json",
        location=JsonPointerLocator(pointer=""),
    )

    with pytest.raises(ValueError) as error:
        validate_raw_locator_against_snapshot(candidate, verified_snapshot=verified)

    assert getattr(error.value, "code", None) == "SECURITY_ARCHIVE_RATIO_LIMIT"


@pytest.mark.parametrize(
    ("limits", "expected_code"),
    [
        (ArchiveLimits(max_file_bytes=32), "SECURITY_ARCHIVE_FILE_LIMIT"),
        (ArchiveLimits(max_compression_ratio=2.0), "SECURITY_ARCHIVE_RATIO_LIMIT"),
    ],
)
def test_locator_validation_applies_configured_archive_member_limits(
    tmp_path: Path,
    limits: ArchiveLimits,
    expected_code: str,
) -> None:
    archive = _zip_members({"records.json": b"a" * 100_000})
    verified = _verified_snapshot(tmp_path, archive)
    candidate = RawLocator(
        source_id="mtgjson",
        source_snapshot_id="mtgjson-fixture",
        raw_object_id="AllPrintings.json.zip",
        raw_object_path="objects/AllPrintings.json.zip",
        archive_member="records.json",
        location=JsonPointerLocator(pointer=""),
    )

    with pytest.raises(ValueError) as error:
        validate_raw_locator_against_snapshot(
            candidate,
            verified_snapshot=verified,
            archive_limits=limits,
        )

    assert getattr(error.value, "code", None) == expected_code


def test_locator_validation_rejects_a_symlink_archive_member_with_shared_security_code(
    tmp_path: Path,
) -> None:
    output = io.BytesIO()
    info = zipfile.ZipInfo("records.json")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(info, "outside")
    verified = _verified_snapshot(tmp_path, output.getvalue())
    candidate = RawLocator(
        source_id="mtgjson",
        source_snapshot_id="mtgjson-fixture",
        raw_object_id="AllPrintings.json.zip",
        raw_object_path="objects/AllPrintings.json.zip",
        archive_member="records.json",
        location=JsonPointerLocator(pointer=""),
    )

    with pytest.raises(ValueError) as error:
        validate_raw_locator_against_snapshot(candidate, verified_snapshot=verified)

    assert getattr(error.value, "code", None) == "SECURITY_ARCHIVE_LINK"


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
