from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from commander_ai.adapters.sources.commander_spellbook.api_models import (
    SpellbookCard,
    SpellbookVariant,
)
from commander_ai.adapters.sources.commander_spellbook.mapper import (
    CommanderSpellbookStagingMapper,
)
from commander_ai.adapters.sources.commander_spellbook.parser import (
    CommanderSpellbookParseError,
    CommanderSpellbookParser,
)
from commander_ai.adapters.storage.parquet_tables import (
    ParquetTableWriter,
    validate_parquet_table_rows,
)
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import (
    SnapshotIntegrityError,
    SnapshotVerifier,
)
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    validate_raw_locator_against_snapshot,
)
from commander_ai.data_pipeline.staging.records import StagingRecord

VARIANT = {
    "id": 101,
    "of": [{"id": 9001}],
    "includes": [{"id": 9002}],
    "uses": [
        {
            "card": {
                "id": 7,
                "name": "Fixture Ritual",
                "oracleId": "oracle-7",
                "colorIdentity": ["U"],
            },
            "quantity": 1,
            "mustBeCommander": True,
            "zoneLocations": ["command"],
            "futureUseField": {"condition": "untapped"},
        }
    ],
    "requires": [
        {
            "template": {"id": 12, "name": "Any mana"},
            "quantity": 1,
            "mustBeCommander": False,
        }
    ],
    "produces": [{"feature": {"id": 44, "name": "Infinite mana"}, "quantity": 1}],
    "colorIdentity": ["U", "G"],
    "easyPrerequisites": "A commander is on the battlefield.",
    "notablePrerequisites": ["A creature can tap for mana."],
    "results": [{"effect": "draw cards", "condition": "after the loop"}],
    "commanderCompatible": True,
    "status": "LEGAL",
    "sourceUrl": "https://backend.commanderspellbook.com/variants/101/",
    "futureVariantField": {"nested": ["retained", {"value": 2}]},
}

FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "commander_spellbook"

CARD = {
    "id": 7,
    "name": "Fixture Ritual",
    "oracleId": "oracle-7",
    "colorIdentity": ["U"],
    "typeLine": "Instant",
    "status": "ACTIVE",
    "futureCardField": {"introducedBy": "fixture", "values": [1, 2]},
}


def _verified_snapshot(
    tmp_path: Path,
    payload: bytes,
    *,
    source_id: str = "commander_spellbook",
    snapshot_id: str = "spellbook-fixture",
    raw_object_id: str = "variants-page-1.json",
    endpoint: str = "https://backend.commanderspellbook.com/api/variants/",
    source_object_id: str | None = None,
    logical_record_count: int | None = None,
):
    store = RawSnapshotStore(tmp_path)
    writer = store.start_snapshot(
        source_id=source_id,
        snapshot_id=snapshot_id,
        approval_status="APPROVED_LOCAL",
        adapter_version="commander-spellbook-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
        attribution_required=True,
        redistribution_status="not_approved",
    )
    writer.add_request(
        {
            "request_id": "spellbook-request",
            "sanitized_method": "GET",
            "sanitized_endpoint": endpoint,
            "format": "json",
            "sanitized_parameters": {"page": 1},
        }
    )
    writer.write_object(
        raw_object_id=raw_object_id,
        request_id="spellbook-request",
        chunks=[payload],
        content_type="application/json",
        source_object_id=source_object_id or raw_object_id.split("-page-", 1)[0],
        logical_record_count=logical_record_count,
    )
    writer.finalize()
    return SnapshotVerifier(tmp_path).verify_complete_snapshot(source_id, snapshot_id)


def _payload(*records: object, envelope: bool = True) -> bytes:
    if not envelope:
        value: object = list(records)
    else:
        value = {
            "count": len(records),
            "next": None,
            "previous": None,
            "results": list(records),
            "futurePageField": {"preserve": True},
        }
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def test_documented_variant_dto_preserves_combo_cards_requirements_results_and_unknown_fields(
    tmp_path: Path,
) -> None:
    verified = _verified_snapshot(tmp_path, _payload(VARIANT))

    result = CommanderSpellbookParser().parse_object(
        verified,
        raw_object_id="variants-page-1.json",
        contract="variants",
    )

    assert len(result.records) == 1
    record = result.records[0]
    assert record.finding_codes == ()
    assert isinstance(record.dto, SpellbookVariant)
    assert record.dto.id == 101
    assert record.dto.of[0].id == 9001
    assert record.dto.includes[0].id == 9002
    assert record.dto.uses[0].card is not None
    assert record.dto.uses[0].card.name == "Fixture Ritual"
    assert record.dto.requires[0].template is not None
    assert record.dto.requires[0].template.id == 12
    assert record.dto.produces[0].feature is not None
    assert record.dto.produces[0].feature.name == "Infinite mana"
    assert record.dto.color_identity == ("U", "G")
    assert record.dto.commander_compatible is True
    assert record.dto.status == "LEGAL"
    assert record.dto.model_extra["futureVariantField"]["nested"][0] == "retained"
    assert record.source_values["results"][0]["effect"] == "draw cards"
    assert record.raw_locator.location == JsonPointerLocator(pointer="/results/0")

    with pytest.raises(TypeError):
        record.dto.model_extra["futureVariantField"]["nested"] += ("blocked",)  # type: ignore[index]


def test_documented_card_dto_and_distinct_variants_are_not_collapsed(tmp_path: Path) -> None:
    card_verified = _verified_snapshot(
        tmp_path / "card",
        _payload(CARD),
        raw_object_id="cards-page-1.json",
        endpoint="https://backend.commanderspellbook.com/api/cards/",
    )
    card_result = CommanderSpellbookParser().parse_object(
        card_verified,
        raw_object_id="cards-page-1.json",
        contract="cards",
    )
    assert isinstance(card_result.records[0].dto, SpellbookCard)
    assert card_result.records[0].dto.model_extra["futureCardField"]["values"] == (1, 2)

    variants = [
        {**VARIANT, "id": 101, "description": "first"},
        {**VARIANT, "id": 102, "description": "second", "of": [{"id": 9001}]},
    ]
    variant_verified = _verified_snapshot(
        tmp_path / "variants",
        _payload(*variants),
    )
    parsed = CommanderSpellbookParser().parse_object(
        variant_verified,
        raw_object_id="variants-page-1.json",
        contract="variants",
    )
    rows = CommanderSpellbookStagingMapper().map_records(
        parsed.records, verified_snapshot=variant_verified
    )

    assert [record.dto.id for record in parsed.records] == [101, 102]
    assert len({row.staging_record_id for row in rows}) == 2
    assert len({row.raw_locator.exact_locator for row in rows}) == 2
    assert [row.original_source_values["description"] for row in rows] == ["first", "second"]


def test_malformed_records_remain_staging_auditable_and_parquet_persistable(tmp_path: Path) -> None:
    malformed = {
        **VARIANT,
        "id": 103,
        "uses": "not-a-list",
    }
    missing_required = {"status": "LEGAL", "uses": [], "requires": [], "produces": []}
    verified = _verified_snapshot(
        tmp_path,
        _payload(VARIANT, missing_required, "not-an-object", malformed),
    )

    parsed = CommanderSpellbookParser().parse_object(
        verified,
        raw_object_id="variants-page-1.json",
        contract="variants",
    )
    rows = CommanderSpellbookStagingMapper().map_records(parsed.records, verified_snapshot=verified)
    audits = CommanderSpellbookStagingMapper().map_audit_records(
        parsed.records, verified_snapshot=verified
    )

    assert [record.finding_codes for record in parsed.records] == [
        (),
        ("parse.missing_required_field",),
        ("parse.record_not_object",),
        ("parse.invalid_record_shape",),
    ]
    assert {row.status for row in rows} == {"OBSERVED", "STRUCTURAL_INVALID", "PARSE_FAILED"}
    assert all(row.has_canonical_identity is False for row in rows)
    assert len(audits) == 3
    assert all(item.stage == "parse" for item in audits)
    assert all(item.raw_locator is not None for item in audits)

    writer = ParquetTableWriter(tmp_path / "artifacts")
    staging_artifact = writer.write_table(
        "commander_spellbook_staging",
        rows,
        layer="staging",
        row_contract=StagingRecord,
        verified_snapshot=verified,
    )
    audit_artifact = writer.write_table(
        "commander_spellbook_audit",
        audits,
        layer="audit",
        row_contract=AuditRecord,
        verified_snapshot=verified,
    )
    assert writer.read_table(staging_artifact.path) == [row.model_dump(mode="json") for row in rows]
    validate_parquet_table_rows(
        tmp_path / "artifacts" / staging_artifact.path,
        layer="staging",
        verified_snapshot=verified,
    )
    validate_parquet_table_rows(
        tmp_path / "artifacts" / audit_artifact.path,
        layer="audit",
        verified_snapshot=verified,
    )


def test_invalid_json_is_lossless_and_has_an_exact_page_locator(tmp_path: Path) -> None:
    raw = b'{"results":[{"id":101},'
    verified = _verified_snapshot(tmp_path, raw)

    result = CommanderSpellbookParser().parse_object(
        verified,
        raw_object_id="variants-page-1.json",
        contract="variants",
    )
    record = result.records[0]
    assert record.finding_codes == ("parse.invalid_json",)
    assert record.raw_locator.location == JsonPointerLocator(pointer="")
    assert record.source_values["encoding"] == "base64"
    assert base64.b64decode(record.source_values["data"]) == raw

    row = CommanderSpellbookStagingMapper().map_records(result.records, verified_snapshot=verified)[
        0
    ]
    assert row.status == "PARSE_FAILED"
    assert row.raw_locator.source_snapshot_id == "spellbook-fixture"
    assert row.raw_locator.raw_object_id == "variants-page-1.json"
    assert row.original_source_values["sha256"]
    row.model_dump(mode="json")


def test_locators_bind_source_snapshot_object_and_exact_json_identity(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _payload(VARIANT))
    records = (
        CommanderSpellbookParser()
        .parse_object(
            verified,
            raw_object_id="variants-page-1.json",
            contract="variants",
        )
        .records
    )
    row = CommanderSpellbookStagingMapper().map_records(records, verified_snapshot=verified)[0]

    validate_raw_locator_against_snapshot(row.raw_locator, verified_snapshot=verified)
    assert row.raw_locator.source_id == "commander_spellbook"
    assert row.raw_locator.source_snapshot_id == verified.manifest.source_snapshot_id
    assert row.raw_locator.raw_object_path == "objects/variants-page-1.json"

    with pytest.raises(ValueError):
        validate_raw_locator_against_snapshot(
            row.raw_locator.model_copy(update={"source_snapshot_id": "other-snapshot"}),
            verified_snapshot=verified,
        )
    with pytest.raises(ValueError):
        validate_raw_locator_against_snapshot(
            row.raw_locator.model_copy(update={"raw_object_id": "cards-page-1.json"}),
            verified_snapshot=verified,
        )


def test_parser_rejects_tampered_or_incomplete_snapshot_evidence(tmp_path: Path) -> None:
    raw = _payload(VARIANT)
    verified = _verified_snapshot(tmp_path / "tamper", raw)
    verified.object_paths["variants-page-1.json"].write_bytes(raw + b"tampered")
    with pytest.raises(CommanderSpellbookParseError) as error:
        CommanderSpellbookParser().parse_object(
            verified,
            raw_object_id="variants-page-1.json",
            contract="variants",
        )
    assert error.value.code == "INTEGRITY_OBJECT_SIZE_MISMATCH"

    store = RawSnapshotStore(tmp_path / "incomplete")
    writer = store.start_snapshot(
        source_id="commander_spellbook",
        snapshot_id="incomplete",
        approval_status="APPROVED_LOCAL",
        adapter_version="commander-spellbook-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
    )
    writer.add_request(
        {
            "request_id": "request",
            "sanitized_method": "GET",
            "sanitized_endpoint": "https://backend.commanderspellbook.com/api/variants/",
            "format": "json",
        }
    )
    writer.write_object(raw_object_id="variants.json", request_id="request", chunks=[raw])
    with pytest.raises(SnapshotIntegrityError) as error:
        SnapshotVerifier(tmp_path / "incomplete").verify_complete_snapshot(
            "commander_spellbook", "incomplete"
        )
    assert error.value.code == "INTEGRITY_SNAPSHOT_NOT_COMPLETE"


def test_public_bytes_and_payload_entry_points_reject_fabricated_provenance() -> None:
    parser = CommanderSpellbookParser()

    with pytest.raises(TypeError):
        parser.parse_bytes(
            b"{}",
            source_id="commander_spellbook",
            source_snapshot_id="fabricated",
            raw_object_id="variants-page-1.json",
            raw_object_path="objects/variants-page-1.json",
            contract="variants",
        )
    with pytest.raises(TypeError):
        parser.parse_payload(
            {},
            source_id="commander_spellbook",
            source_snapshot_id="fabricated",
            raw_object_id="variants-page-1.json",
            raw_object_path="objects/variants-page-1.json",
            contract="variants",
        )


def test_verified_compatibility_entry_points_bind_bytes_and_payload_to_object(
    tmp_path: Path,
) -> None:
    raw = _fixture("valid_page.json")
    verified = _verified_snapshot(tmp_path, raw)
    parser = CommanderSpellbookParser()

    parsed_from_bytes = parser.parse_bytes(
        raw,
        verified_snapshot=verified,
        raw_object_id="variants-page-1.json",
        contract="variants",
    )
    parsed_from_payload = parser.parse_payload(
        json.loads(raw),
        verified_snapshot=verified,
        raw_object_id="variants-page-1.json",
        contract="variants",
    )
    assert parsed_from_bytes.records[0].raw_locator == parsed_from_payload.records[0].raw_locator

    with pytest.raises(CommanderSpellbookParseError) as byte_error:
        parser.parse_bytes(
            raw + b"tampered",
            verified_snapshot=verified,
            raw_object_id="variants-page-1.json",
            contract="variants",
        )
    assert byte_error.value.code == "INTEGRITY_OBJECT_BYTES_MISMATCH"

    with pytest.raises(CommanderSpellbookParseError) as payload_error:
        parser.parse_payload(
            {"count": 0, "next": None, "previous": None, "results": []},
            verified_snapshot=verified,
            raw_object_id="variants-page-1.json",
            contract="variants",
        )
    assert payload_error.value.code == "INTEGRITY_PAYLOAD_MISMATCH"


def test_parser_rejects_foreign_source_product_and_request_evidence(tmp_path: Path) -> None:
    parser = CommanderSpellbookParser()
    foreign_source = _verified_snapshot(
        tmp_path / "foreign-source",
        _fixture("source_identity_settings_binding.json"),
        source_id="other_source",
    )
    with pytest.raises(CommanderSpellbookParseError) as source_error:
        parser.parse_object(
            foreign_source,
            raw_object_id="variants-page-1.json",
            contract="variants",
        )
    assert source_error.value.code == "INTEGRITY_SOURCE_MISMATCH"

    foreign_product = _verified_snapshot(
        tmp_path / "foreign-product",
        _fixture("source_identity_settings_binding.json"),
        raw_object_id="variants-page-1.json",
        source_object_id="cards",
    )
    with pytest.raises(CommanderSpellbookParseError) as product_error:
        parser.parse_object(
            foreign_product,
            raw_object_id="variants-page-1.json",
            contract="variants",
        )
    assert product_error.value.code == "INTEGRITY_PRODUCT_MISMATCH"

    foreign_request = _verified_snapshot(
        tmp_path / "foreign-request",
        _fixture("source_identity_settings_binding.json"),
        endpoint="https://backend.commanderspellbook.com/api/cards/",
    )
    with pytest.raises(CommanderSpellbookParseError) as request_error:
        parser.parse_object(
            foreign_request,
            raw_object_id="variants-page-1.json",
            contract="variants",
        )
    assert request_error.value.code == "INTEGRITY_REQUEST_MISMATCH"


def test_staging_entry_points_require_verified_snapshot_evidence(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture("valid_page.json"))
    parsed = CommanderSpellbookParser().parse_object(
        verified,
        raw_object_id="variants-page-1.json",
        contract="variants",
    )
    mapper = CommanderSpellbookStagingMapper()

    with pytest.raises(TypeError):
        mapper.map_records(parsed.records)
    with pytest.raises(TypeError):
        mapper.map_audit_records(parsed.records)
    with pytest.raises(TypeError):
        mapper.staging_record_id(parsed.records[0])

    foreign = _verified_snapshot(
        tmp_path / "foreign",
        _fixture("valid_page.json"),
        snapshot_id="foreign-snapshot",
    )
    with pytest.raises(ValueError):
        mapper.map_records(parsed.records, verified_snapshot=foreign)


def test_strict_scalar_failure_remains_auditable_in_staging(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture("strict_scalar_failure.json"))
    parsed = CommanderSpellbookParser().parse_object(
        verified,
        raw_object_id="variants-page-1.json",
        contract="variants",
    )

    record = parsed.records[0]
    assert record.finding_codes == ("parse.invalid_record_shape",)
    assert record.source_values["uses"][0]["quantity"] == "1"
    assert record.source_values["uses"][0]["mustBeCommander"] == 1
    assert record.source_values["commanderCompatible"] == "false"
    row = CommanderSpellbookStagingMapper().map_records(parsed.records, verified_snapshot=verified)[
        0
    ]
    assert row.status == "STRUCTURAL_INVALID"
    audits = CommanderSpellbookStagingMapper().map_audit_records(
        parsed.records, verified_snapshot=verified
    )
    assert len(audits) == 1
    assert audits[0].details["source_values"]["uses"][0]["quantity"] == "1"
    assert audits[0].details["source_values"]["uses"][0]["mustBeCommander"] == 1
