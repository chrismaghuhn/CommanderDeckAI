from __future__ import annotations

from datetime import UTC, datetime

from commander_ai.data_pipeline.quality.resolution_reports import ResolutionReport
from commander_ai.data_pipeline.resolution.card_catalog import AliasCatalog, build_card_catalog
from commander_ai.data_pipeline.resolution.card_resolution import CardResolutionInput, CardResolver
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord
from commander_ai.domain.cards import CardResolutionCandidate
from commander_ai.domain.provenance import ProvenanceReference

ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
PRINTING_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PRINTING_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
ATTEMPTED_AT = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _record(record_id: str, values: dict[str, object]) -> StagingRecord:
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
            record_type="card",
            raw_locator=locator,
            original_source_values=values,
        ),
        staging_record_id=record_id,
        status="OBSERVED",
    )


def _card_values(
    *, name: str, oracle_id: str, printing_id: str, uuid: str, mtgjson_id: str
) -> dict[str, object]:
    return {
        "uuid": uuid,
        "name": name,
        "setCode": "FIX",
        "number": "1",
        "layout": "normal",
        "manaValue": 2,
        "colors": ["U"],
        "colorIdentity": ["U"],
        "type": "Creature — Wizard",
        "types": ["Creature"],
        "subtypes": ["Wizard"],
        "keywords": ["Flying"],
        "legalities": {"commander": "Legal"},
        "identifiers": {
            "scryfallOracleId": oracle_id,
            "scryfallId": printing_id,
            "mtgjsonV4Id": mtgjson_id,
        },
    }


def _provenance(record: StagingRecord) -> tuple[ProvenanceReference, ...]:
    return (
        ProvenanceReference(
            source_id=record.source_id,
            source_snapshot_id=record.raw_locator.source_snapshot_id,
            source_object_id=record.raw_locator.raw_object_id,
            raw_sha256="0" * 64,
            retrieved_at=ATTEMPTED_AT,
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


def test_direct_identifier_aliases_are_considered_and_conflicts_stop_resolution() -> None:
    values = _card_values(
        name="Direct IDs",
        oracle_id=ORACLE_A,
        printing_id=PRINTING_A,
        uuid="direct-uuid",
        mtgjson_id="direct-mtgjson",
    )
    values["identifiers"] = {}
    values.update(
        {
            "oracleId": ORACLE_A,
            "scryfallId": PRINTING_A,
            "mtgjsonV4Id": "direct-mtgjson",
        }
    )
    base = _record(
        "direct-base",
        _card_values(
            name="Direct IDs",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="base-uuid",
            mtgjson_id="base-mtgjson",
        ),
    )
    record = _record("direct", values)
    result = CardResolver(_catalog(base)).resolve(
        CardResolutionInput(record, "not the name"), attempted_at=ATTEMPTED_AT
    )
    assert result.resolution.status == "resolved"
    assert result.resolution.method == "exact_identifier"

    second = _record(
        "second",
        _card_values(
            name="Other",
            oracle_id=ORACLE_B,
            printing_id=PRINTING_B,
            uuid="uuid-b",
            mtgjson_id="id-b",
        ),
    )
    catalog = _catalog(record, second)
    conflicting_values = {"uuid": "uuid-b", "identifiers": {"scryfallId": PRINTING_A}}
    conflicting = _record("conflicting", conflicting_values)
    conflict_result = CardResolver(catalog).resolve(
        CardResolutionInput(conflicting, "ignored"), attempted_at=ATTEMPTED_AT
    )
    assert conflict_result.resolution.status == "ambiguous"
    assert conflict_result.resolution.finding_code == "resolution.conflicting_identifiers"
    assert conflict_result.quarantine is not None


def test_catalog_mapping_quarantines_contradictory_canonical_identifiers() -> None:
    values = _card_values(
        name="Contradictory IDs",
        oracle_id=ORACLE_A,
        printing_id=PRINTING_A,
        uuid="contradictory-uuid",
        mtgjson_id="contradictory-mtgjson",
    )
    values["oracleId"] = ORACLE_B
    result = build_card_catalog(
        (_record("contradictory", values),),
        card_snapshot_id="cards-fixture-v1",
        provenance_for=_provenance,
        mapper_version="fixture-mapper-v1",
    )
    assert not result.catalog.cards
    assert any(
        item.reason_code == "quality.conflicting_canonical_identifiers"
        for item in result.quarantines
    )


def test_alias_normalization_merges_collisions_and_rejects_stale_targets() -> None:
    record = _record(
        "alias-source",
        _card_values(
            name="Alias Target",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="alias-uuid",
            mtgjson_id="alias-id",
        ),
    )
    catalog = _catalog(record)
    second_record = _record(
        "alias-second",
        _card_values(
            name="Second Alias Target",
            oracle_id=ORACLE_B,
            printing_id=PRINTING_B,
            uuid="alias-second-uuid",
            mtgjson_id="alias-second-id",
        ),
    )
    catalog_with_both = _catalog(record, second_record)
    first = AliasCatalog.create(
        "aliases-v1",
        {
            "CAFÉ": (CardResolutionCandidate(oracle_id=ORACLE_A),),
            "CAFE\u0301": (CardResolutionCandidate(oracle_id=ORACLE_B),),
        },
    )
    second = AliasCatalog.create(
        "aliases-v1",
        {
            "CAFE\u0301": (CardResolutionCandidate(oracle_id=ORACLE_B),),
            "CAFÉ": (CardResolutionCandidate(oracle_id=ORACLE_A),),
        },
    )
    assert first.sha256 == second.sha256
    assert len(first.aliases["café"]) == 2

    ambiguous = CardResolver(catalog_with_both, alias_catalog=first).resolve(
        CardResolutionInput(_record("alias", {"name": "Alias?"}), "CAFÉ"),
        attempted_at=ATTEMPTED_AT,
    )
    assert ambiguous.resolution.status == "ambiguous"

    stale = AliasCatalog.create(
        "aliases-stale-v1",
        {"Old Name": (CardResolutionCandidate(oracle_id=ORACLE_B),)},
    )
    stale_result = CardResolver(catalog, alias_catalog=stale).resolve(
        CardResolutionInput(_record("stale", {"name": "Old Name"}), "Old Name"),
        attempted_at=ATTEMPTED_AT,
    )
    assert stale_result.resolution.status == "unresolved"
    assert stale_result.resolution.finding_code == "resolution.alias_target_unresolved"
    assert stale_result.quarantine is not None

    foreign_printing = AliasCatalog.create(
        "aliases-foreign-printing-v1",
        {
            "Foreign Printing": (
                CardResolutionCandidate(oracle_id=ORACLE_A, printing_id=PRINTING_B),
            )
        },
    )
    foreign_result = CardResolver(catalog_with_both, alias_catalog=foreign_printing).resolve(
        CardResolutionInput(
            _record("foreign-printing", {"name": "Foreign Printing"}), "Foreign Printing"
        ),
        attempted_at=ATTEMPTED_AT,
    )
    assert foreign_result.resolution.status == "unresolved"
    assert foreign_result.resolution.finding_code == "resolution.alias_target_unresolved"


def test_split_parts_become_distinct_faces_and_keep_printing_relationships() -> None:
    values = _card_values(
        name="Search // Find",
        oracle_id=ORACLE_A,
        printing_id=PRINTING_A,
        uuid="split-source",
        mtgjson_id="split-id",
    )
    values["cardParts"] = ["Search", "Find"]
    record = _record("split", values)
    result = build_card_catalog(
        (record,),
        card_snapshot_id="cards-fixture-v1",
        provenance_for=_provenance,
        release_dates={"FIX": datetime(2026, 1, 1, tzinfo=UTC).date()},
        mapper_version="fixture-mapper-v1",
    )
    assert not result.quarantines
    assert result.provenance_rows
    assert all(row.raw_locator == record.raw_locator for row in result.provenance_rows)
    assert {face.name for face in result.catalog.faces} == {"Search", "Find"}
    assert result.catalog.printings[0].face_ids == (
        "split-source#part-0",
        "split-source#part-1",
    )
    lookup = CardResolver(result.catalog).resolve(
        CardResolutionInput(_record("split-lookup", {"name": "Find"}), "Find"),
        attempted_at=ATTEMPTED_AT,
    )
    assert lookup.resolution.method == "split_face"
    assert lookup.resolution.canonical_face_id == "split-source#part-1"


def test_multiple_source_rows_merge_all_faces_into_one_printing() -> None:
    front_values = _card_values(
        name="Front Face",
        oracle_id=ORACLE_A,
        printing_id=PRINTING_A,
        uuid="front-face",
        mtgjson_id="front-id",
    )
    front_values.update({"faceName": "Front Face", "side": "a", "layout": "transform"})
    back_values = _card_values(
        name="Back Face",
        oracle_id=ORACLE_A,
        printing_id=PRINTING_A,
        uuid="back-face",
        mtgjson_id="back-id",
    )
    back_values.update({"faceName": "Back Face", "side": "b", "layout": "transform"})
    result = build_card_catalog(
        (_record("front", front_values), _record("back", back_values)),
        card_snapshot_id="cards-fixture-v1",
        provenance_for=_provenance,
        release_dates={"FIX": datetime(2026, 1, 1, tzinfo=UTC).date()},
        mapper_version="fixture-mapper-v1",
    )
    assert not result.quarantines
    assert result.catalog.printings[0].face_ids == ("back-face", "front-face")


def test_conflicting_card_and_face_names_are_ambiguous() -> None:
    card = _record(
        "name-card",
        _card_values(
            name="Shared Name",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="shared-card",
            mtgjson_id="shared-card-id",
        ),
    )
    face_values = _card_values(
        name="Other Card",
        oracle_id=ORACLE_B,
        printing_id=PRINTING_B,
        uuid="other-card",
        mtgjson_id="other-card-id",
    )
    face_values.update({"faceName": "Shared Name", "side": "b", "layout": "transform"})
    catalog = _catalog(card, _record("name-face", face_values))
    result = CardResolver(catalog).resolve(
        CardResolutionInput(_record("name-lookup", {"name": "Shared Name"}), "Shared Name"),
        attempted_at=ATTEMPTED_AT,
    )
    assert result.resolution.status == "ambiguous"
    assert result.resolution.finding_code == "resolution.ambiguous_name"


def test_malformed_collections_and_printing_failures_are_retained() -> None:
    malformed_values = _card_values(
        name="Malformed",
        oracle_id=ORACLE_A,
        printing_id=PRINTING_A,
        uuid="malformed",
        mtgjson_id="malformed-id",
    )
    malformed_values["types"] = ["Creature", 7]
    malformed = _record("malformed", malformed_values)
    malformed_result = build_card_catalog(
        (malformed,),
        card_snapshot_id="cards-fixture-v1",
        provenance_for=_provenance,
        mapper_version="fixture-mapper-v1",
    )
    assert malformed_result.quarantines[0].reason_code == "quality.invalid_card_collection"

    incomplete_values = _card_values(
        name="Incomplete Printing",
        oracle_id=ORACLE_A,
        printing_id=PRINTING_A,
        uuid="incomplete",
        mtgjson_id="incomplete-id",
    )
    incomplete_values.pop("setCode")
    incomplete = _record("incomplete", incomplete_values)
    incomplete_result = build_card_catalog(
        (incomplete,),
        card_snapshot_id="cards-fixture-v1",
        provenance_for=_provenance,
        release_dates={"FIX": datetime(2026, 1, 1, tzinfo=UTC).date()},
        mapper_version="fixture-mapper-v1",
    )
    assert any(
        item.reason_code == "quality.incomplete_printing" for item in incomplete_result.quarantines
    )
    resolution = CardResolver(incomplete_result.catalog).resolve(
        CardResolutionInput(incomplete, "ignored"), attempted_at=ATTEMPTED_AT
    )
    assert resolution.resolution.status == "resolved"
    assert resolution.resolution.canonical_printing_id is None


def test_resolution_report_does_not_count_ambiguous_exact_attempts_as_matches() -> None:
    first = _record(
        "report-a",
        _card_values(
            name="Report Name",
            oracle_id=ORACLE_A,
            printing_id=PRINTING_A,
            uuid="report-a-uuid",
            mtgjson_id="report-a-id",
        ),
    )
    second = _record(
        "report-b",
        _card_values(
            name="Report Name",
            oracle_id=ORACLE_B,
            printing_id=PRINTING_B,
            uuid="report-b-uuid",
            mtgjson_id="report-b-id",
        ),
    )
    catalog = _catalog(first, second)
    ambiguous = CardResolver(catalog).resolve(
        CardResolutionInput(_record("report-lookup", {"name": "Report Name"}), "Report Name"),
        attempted_at=ATTEMPTED_AT,
    )
    report = ResolutionReport.from_results((ambiguous,))
    assert report.ambiguous_entries == 1
    assert report.exact_matches == 0
