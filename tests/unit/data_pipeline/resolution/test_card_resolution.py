from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.adapters.sources.mtgjson.parser import MTGJSONMemberParser
from commander_ai.adapters.sources.mtgjson.settings import MTGJSONProduct
from commander_ai.adapters.sources.mtgjson.staging import MTGJSONStagingMapper
from commander_ai.adapters.storage.parquet_tables import (
    ParquetTableWriter,
    validate_parquet_table_rows,
)
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.data_pipeline.quality.resolution_reports import ResolutionReport
from commander_ai.data_pipeline.resolution.card_catalog import AliasCatalog, build_card_catalog
from commander_ai.data_pipeline.resolution.card_resolution import (
    CardResolutionInput,
    CardResolver,
)
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord
from commander_ai.domain.cards import CanonicalCard, CardResolutionCandidate
from commander_ai.domain.provenance import ProvenanceReference, SourceSnapshotRequest

PROJECT_ROOT = Path(__file__).resolve().parents[4]

ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
PRINTING_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PRINTING_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ATTEMPTED_AT = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _record(
    record_id: str, values: dict[str, object], *, record_type: str = "card"
) -> StagingRecord:
    locator = RawLocator(
        source_id="fixture",
        source_snapshot_id="fixture-snapshot",
        raw_object_id="cards.json",
        raw_object_path="objects/cards.json",
        location=JsonPointerLocator(pointer=f"/cards/{record_id}"),
    )
    return StagingRecord.from_dto(
        SourceRecordDTO(
            source_id="fixture",
            record_type=record_type,
            raw_locator=locator,
            original_source_values=values,
        ),
        staging_record_id=record_id,
        status="OBSERVED",
    )


def _card_values(
    *,
    name: str,
    oracle_id: str,
    printing_id: str,
    uuid: str,
    mtgjson_id: str,
    side: str | None = None,
) -> dict[str, object]:
    values: dict[str, object] = {
        "uuid": uuid,
        "name": name,
        "setCode": "FIX",
        "number": "1",
        "layout": "transform" if side else "normal",
        "manaCost": "{1}{U}",
        "manaValue": 2,
        "colors": ["U"],
        "colorIdentity": ["U"],
        "type": "Creature — Wizard",
        "types": ["Creature"],
        "subtypes": ["Wizard"],
        "oracleText": "Draw a card.",
        "keywords": ["Flying"],
        "legalities": {"commander": "Legal"},
        "identifiers": {
            "scryfallOracleId": oracle_id,
            "scryfallId": printing_id,
            "mtgjsonV4Id": mtgjson_id,
        },
    }
    if side is not None:
        values["side"] = side
        values["faceName"] = name
    return values


def _provenance(record: StagingRecord) -> tuple[ProvenanceReference, ...]:
    return (
        ProvenanceReference(
            source_id=record.source_id,
            source_snapshot_id=record.raw_locator.source_snapshot_id,
            source_object_id=record.raw_locator.raw_object_id,
            raw_sha256="0" * 64,
            retrieved_at=datetime(2026, 8, 11, tzinfo=UTC),
            adapter_version="fixture-adapter-v1",
            mapper_version="fixture-mapper-v1",
            approval_status="APPROVED_LOCAL",
        ),
    )


def _catalog(*records: StagingRecord):
    result = build_card_catalog(
        records,
        card_snapshot_id="cards-fixture-v1",
        provenance_for=_provenance,
        release_dates={"FIX": datetime(2026, 1, 1, tzinfo=UTC).date()},
        mapper_version="fixture-mapper-v1",
    )
    assert not result.quarantines
    return result.catalog


def _verified_snapshot(root: Path):
    writer = RawSnapshotStore(root).start_snapshot(
        source_id="fixture",
        snapshot_id="fixture-snapshot",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-adapter-v1",
        usage_status="historical-approved",
        started_at=ATTEMPTED_AT,
    )
    writer.add_request(
        SourceSnapshotRequest(
            request_id="request-1",
            sanitized_method="GET",
            sanitized_endpoint="https://fixture.invalid/cards.json",
            format="json",
        )
    )
    writer.write_object(raw_object_id="cards.json", request_id="request-1", chunks=[b"{}"])
    writer.finalize()
    return SnapshotVerifier(root).verify_complete_snapshot("fixture", "fixture-snapshot")


def _resolve(catalog, record: StagingRecord, value: str, **kwargs: object):
    return CardResolver(catalog).resolve(
        CardResolutionInput(record, value, **kwargs),
        attempted_at=ATTEMPTED_AT,
    )


def test_source_identifier_resolution_preserves_value_and_provenance_versions() -> None:
    record = _record(
        "one",
        _card_values(
            name="Test Adept",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="mtgjson-printing-a",
            mtgjson_id="mtgjson-a",
        ),
    )
    result = _resolve(_catalog(record), record, "Test Adept", requested_quantity=2)

    assert result.resolution.status == "resolved"
    assert result.resolution.method == "source_identifier"
    assert result.resolution.original_value == "Test Adept"
    assert result.resolution.canonical_oracle_id == ORACLE_A
    assert result.resolution.canonical_printing_id == PRINTING_A
    assert result.resolution.resolver_version == "card-resolver-v1"
    assert result.resolution.normalization_policy_version.startswith("unicode_")
    assert len(result.resolution.alias_catalog_sha256) == 64
    assert result.attempt.original_source_value["requested_quantity"] == 2  # type: ignore[index]
    assert result.quarantine is None


def test_printing_and_mtgjson_identifiers_resolve_without_name_guessing() -> None:
    first = _record(
        "one",
        _card_values(
            name="Test Adept",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="mtgjson-printing-a",
            mtgjson_id="mtgjson-a",
        ),
    )
    catalog = _catalog(first)

    printing_values = dict(first.original_source_values)
    printing_values["uuid"] = "unknown-source-uuid"
    printing_record = _record("printing", printing_values)
    printing_result = _resolve(catalog, printing_record, "wrong display text")
    assert printing_result.resolution.method == "exact_identifier"
    assert printing_result.resolution.canonical_printing_id == PRINTING_A

    mtgjson_values = dict(first.original_source_values)
    mtgjson_values["uuid"] = "unknown-source-uuid"
    mtgjson_values["identifiers"] = {"mtgjsonV4Id": "mtgjson-a"}
    mtgjson_record = _record("mtgjson", mtgjson_values)
    mtgjson_result = _resolve(catalog, mtgjson_record, "also wrong")
    assert mtgjson_result.resolution.method == "exact_identifier"
    assert mtgjson_result.resolution.canonical_oracle_id == ORACLE_A


def test_exact_unicode_name_and_documented_alias_are_deterministic() -> None:
    record = _record(
        "one",
        _card_values(
            name="Café Adept",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="unknown-source-uuid",
            mtgjson_id="unknown-mtgjson-id",
        ),
    )
    catalog = _catalog(record)
    name_values = dict(record.original_source_values)
    name_values["name"] = "other"
    name_values["uuid"] = "not-in-catalog"
    name_values["identifiers"] = {}
    name_record = _record("name", name_values)
    exact_record = _resolve(catalog, name_record, "CAFE\u0301 ADEPT")
    assert exact_record.resolution.method == "exact_name"

    alias = AliasCatalog.create(
        "aliases-fixture-v1",
        {"The Adept": (CardResolutionCandidate(oracle_id=ORACLE_A),)},
    )
    alias_result = CardResolver(catalog, alias_catalog=alias).resolve(
        CardResolutionInput(name_record, "The Adept"), attempted_at=ATTEMPTED_AT
    )
    assert alias_result.resolution.method == "alias"
    assert alias_result.resolution.alias_catalog_version == "aliases-fixture-v1"


def test_ambiguous_and_unresolved_values_are_quarantined_without_fuzzy_matching() -> None:
    first = _record(
        "one",
        _card_values(
            name="Shared Name",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="uuid-a",
            mtgjson_id="id-a",
        ),
    )
    second = _record(
        "two",
        _card_values(
            name="Shared Name",
            oracle_id=ORACLE_B,
            printing_id=PRINTING_B,
            uuid="uuid-b",
            mtgjson_id="id-b",
        ),
    )
    catalog = _catalog(first, second)

    ambiguous = _resolve(catalog, _record("ambiguous", {"name": "Shared Name"}), "Shared Name")
    assert ambiguous.resolution.status == "ambiguous"
    assert ambiguous.resolution.finding_code == "resolution.ambiguous_name"
    assert ambiguous.quarantine is not None
    assert len(ambiguous.attempt.candidate_canonical_ids) == 2

    unresolved = _resolve(catalog, _record("missing", {"name": "Shared Nam"}), "Shared Nam")
    assert unresolved.resolution.status == "unresolved"
    assert unresolved.resolution.finding_code == "resolution.unresolved_name"
    assert unresolved.quarantine is not None


def test_faces_and_catalog_hash_are_stable_across_rebuilds() -> None:
    record = _record(
        "front",
        _card_values(
            name="Front Face",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="face-front",
            mtgjson_id="id-front",
            side="a",
        ),
    )
    back = _record(
        "back",
        _card_values(
            name="Back Face",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="face-back",
            mtgjson_id="id-back",
            side="b",
        ),
        record_type="card_face",
    )
    # A source card row supplies the canonical card; the face row preserves the back face.
    catalog = _catalog(record, back)
    rebuilt = _catalog(back, record)
    assert catalog.catalog_snapshot_id == rebuilt.catalog_snapshot_id
    assert {face.face_id for face in catalog.faces} == {"face-front", "face-back"}
    back_result = _resolve(catalog, _record("lookup", {"name": "Back Face"}), "Back Face")
    assert back_result.resolution.method == "split_face"
    assert back_result.resolution.canonical_face_id == "face-back"


def test_resolution_report_exposes_success_and_failure_counts() -> None:
    record = _record(
        "one",
        _card_values(
            name="Test Adept",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="uuid-a",
            mtgjson_id="id-a",
        ),
    )
    catalog = _catalog(record)
    results = (
        _resolve(catalog, record, "Test Adept"),
        _resolve(catalog, _record("missing", {"name": "Missing"}), "Missing"),
    )
    report = ResolutionReport.from_results(results)
    assert report.total_entries == 2
    assert report.resolved_entries == 1
    assert report.exact_matches == 1
    assert report.failure_count == 1
    assert report.as_dict()["unresolved_entries"] == 1


def test_mtgjson_staging_path_produces_schema_valid_canonical_records() -> None:
    def locator(location: object) -> RawLocator:
        assert isinstance(location, str)
        return RawLocator(
            source_id="mtgjson",
            source_snapshot_id="mtgjson-fixture",
            raw_object_id="AllPrintings.json.zip",
            raw_object_path="objects/AllPrintings.json.zip",
            archive_member="AllPrintings.json",
            location=JsonPointerLocator(pointer=location),
        )

    parsed = MTGJSONMemberParser(locator).parse(
        {
            "data": {
                "FIX": {
                    "code": "FIX",
                    "name": "Fixture Set",
                    "releaseDate": "2026-01-01",
                    "cards": [
                        _card_values(
                            name="Task Card",
                            oracle_id=ORACLE_A,
                            printing_id=PRINTING_A,
                            uuid="mtgjson-task-card",
                            mtgjson_id="mtgjson-task-card",
                        )
                    ],
                }
            }
        },
        product=MTGJSONProduct.ALL_PRINTINGS,
    )
    staging = MTGJSONStagingMapper().map_records(parsed)
    result = build_card_catalog(
        staging,
        card_snapshot_id="cards-mtgjson-fixture-v1",
        provenance_for=lambda record: _provenance(record),
        release_dates={"FIX": datetime(2026, 1, 1, tzinfo=UTC).date()},
        mapper_version="fixture-mapper-v1",
    )

    assert not result.quarantines
    contracts = {
        "card.v1": result.catalog.cards,
        "card-face.v1": result.catalog.faces,
        "printing.v1": result.catalog.printings,
    }
    for stem, records in contracts.items():
        schema = json.loads(
            (PROJECT_ROOT / "schemas" / f"{stem}.schema.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for record in records:
            assert not list(validator.iter_errors(record.model_dump(mode="json")))


def test_canonical_card_records_have_a_curated_parquet_persistence_path(tmp_path: Path) -> None:
    record = _record(
        "persisted",
        _card_values(
            name="Persisted Card",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="persisted-uuid",
            mtgjson_id="persisted-id",
        ),
    )
    catalog = _catalog(record)
    verified = _verified_snapshot(tmp_path / "snapshot")
    raw_sha256 = verified.manifest.objects[0].sha256
    cards = tuple(
        card.model_copy(
            update={
                "provenance": tuple(
                    reference.model_copy(update={"raw_sha256": raw_sha256})
                    for reference in card.provenance
                )
            }
        )
        for card in catalog.cards
    )
    writer = ParquetTableWriter(tmp_path)
    with pytest.raises(ValueError, match="verified raw snapshot"):
        writer.write_table(
            "cards-without-evidence",
            cards,
            layer="curated",
            schema_version="card.v1",
            row_contract=CanonicalCard,
        )
    invalid_cards = tuple(
        card.model_copy(
            update={
                "provenance": tuple(
                    reference.model_copy(update={"raw_sha256": "a" * 64})
                    for reference in card.provenance
                )
            }
        )
        for card in cards
    )
    with pytest.raises(ValueError, match="sha256"):
        writer.write_table(
            "cards-with-invalid-evidence",
            invalid_cards,
            layer="curated",
            schema_version="card.v1",
            row_contract=CanonicalCard,
            verified_snapshot=verified,
        )
    artifact = writer.write_table(
        "cards",
        cards,
        layer="curated",
        schema_version="card.v1",
        row_contract=CanonicalCard,
        verified_snapshot=verified,
    )

    validate_parquet_table_rows(
        artifact_path := tmp_path / artifact.path,
        layer="curated",
        verified_snapshot=verified,
    )
    assert writer.read_table(artifact.path)[0]["oracle_id"] == ORACLE_A
    assert artifact_path.is_file()
