from __future__ import annotations

from datetime import UTC, datetime

import pytest

from commander_ai.data_pipeline.provenance.rows import (
    AuditRecord,
    AuditRows,
    ProvenanceRow,
    ResolutionAttempt,
)
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.quality.quarantine import quarantine_record
from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    RawLocator,
)
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord


def raw_locator() -> RawLocator:
    return RawLocator(
        source_id="fixture",
        source_snapshot_id="fixture-snapshot",
        raw_object_id="object-1",
        raw_object_path="objects/object-1.json",
        location=JsonPointerLocator(pointer="/decks/0"),
    )


def test_staging_record_retains_exact_locator_and_original_source_values() -> None:
    dto = SourceRecordDTO(
        source_id="fixture",
        record_type="deck",
        raw_locator=raw_locator(),
        original_source_values={"name": "Unchanged", "quantity": "not-an-int"},
    )

    record = StagingRecord.from_dto(
        dto,
        staging_record_id="staging-1",
        status="STRUCTURAL_INVALID",
        finding_codes=("parse.structural.invalid",),
    )

    assert record.raw_locator.location.pointer == "/decks/0"
    assert record.raw_locator.raw_object_path == "objects/object-1.json"
    assert record.original_source_values["quantity"] == "not-an-int"
    assert record.has_canonical_identity is False


def test_parse_failure_is_quarantined_without_canonical_invariants() -> None:
    record = StagingRecord.from_dto(
        SourceRecordDTO(
            source_id="fixture",
            record_type="deck",
            raw_locator=raw_locator(),
            original_source_values={"commander": None, "cards": [{"qty": "?"}]},
        ),
        staging_record_id="staging-parse-failure",
        status="PARSE_FAILED",
        finding_codes=(FindingCode.parse("parse.json.invalid"),),
    )

    quarantined = quarantine_record(record, reason_code="parse.json.invalid")

    assert quarantined.layer == "quarantine"
    assert quarantined.original_source_values["commander"] is None
    assert quarantined.raw_locator == record.raw_locator
    with pytest.raises(ValueError):
        type(quarantined).model_validate({**quarantined.model_dump(), "layer": "curated"})


def test_resolution_attempts_are_retained_including_ambiguous_and_unresolved() -> None:
    attempted_at = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)
    attempts = tuple(
        ResolutionAttempt(
            attempt_id=f"attempt-{status.lower()}",
            staging_record_id="staging-1",
            raw_locator=raw_locator(),
            source_field="card_name",
            original_source_value="Example Card",
            resolver_version="resolver-v1",
            normalization_policy_version="unicode-v1",
            alias_catalog_version="aliases-v1",
            card_catalog_snapshot_id="cards-v1",
            status=status,
            candidate_canonical_ids=("card-a", "card-b") if status == "AMBIGUOUS" else (),
            canonical_id="card-a" if status == "RESOLVED" else None,
            finding_codes=() if status == "RESOLVED" else (f"resolution.{status.lower()}",),
            attempted_at=attempted_at,
        )
        for status in ("RESOLVED", "AMBIGUOUS", "UNRESOLVED")
    )
    rows = AuditRows(
        resolution_attempts=attempts,
        findings=(
            AuditRecord(
                audit_id="audit-1",
                entity_id="staging-1",
                stage="resolution",
                finding_code="resolution.ambiguous",
                raw_locator=raw_locator(),
                details={"candidate_count": 2},
            ),
        ),
    )

    assert [attempt.status for attempt in rows.resolution_attempts] == [
        "RESOLVED",
        "AMBIGUOUS",
        "UNRESOLVED",
    ]
    assert rows.findings[0].layer == "audit"


def test_finding_namespaces_cannot_be_collapsed() -> None:
    assert FindingCode.parse("parse.json.invalid").namespace == "parse"
    assert FindingCode.parse("integrity.object.hash_mismatch").namespace == "integrity"
    assert FindingCode.parse("resolution.ambiguous").namespace == "resolution"
    assert FindingCode.parse("legality.ruleset.unknown").namespace == "legality"
    assert FindingCode.parse("quality.missing_field").namespace == "quality"

    with pytest.raises(ValueError):
        FindingCode.parse("resolution")


def test_staging_findings_are_limited_to_parse_and_integrity_namespaces() -> None:
    with pytest.raises(ValueError, match="staging"):
        StagingRecord.from_dto(
            SourceRecordDTO(
                source_id="fixture",
                record_type="deck",
                raw_locator=raw_locator(),
                original_source_values={},
            ),
            staging_record_id="staging-resolution",
            status="STRUCTURAL_INVALID",
            finding_codes=("resolution.ambiguous",),
        )


@pytest.mark.parametrize(
    ("status", "finding_codes"),
    (
        ("OBSERVED", ("parse.json.invalid",)),
        ("INCOMPLETE", ()),
        ("PARSE_FAILED", ("integrity.object.missing",)),
        ("STRUCTURAL_INVALID", ("integrity.object.missing",)),
    ),
)
def test_staging_status_and_finding_namespaces_are_consistent(
    status: str, finding_codes: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match=r"status|finding"):
        StagingRecord.from_dto(
            SourceRecordDTO(
                source_id="fixture",
                record_type="deck",
                raw_locator=raw_locator(),
                original_source_values={},
            ),
            staging_record_id="staging-inconsistent",
            status=status,  # type: ignore[arg-type]
            finding_codes=finding_codes,
        )


def test_parse_audit_findings_require_an_exact_raw_locator() -> None:
    with pytest.raises(ValueError, match="raw_locator"):
        AuditRecord(
            audit_id="audit-parse",
            entity_id="staging-1",
            stage="parse",
            finding_code="parse.json.invalid",
        )

    with pytest.raises(ValueError, match="raw_locator"):
        AuditRecord(
            audit_id="audit-integrity",
            entity_id="staging-1",
            stage="integrity",
            finding_code="integrity.object.missing",
        )


def test_provenance_top_level_locator_fields_must_match_raw_locator() -> None:
    locator = raw_locator()
    with pytest.raises(ValueError, match="raw_locator"):
        ProvenanceRow(
            provenance_id="prov-1",
            entity_id="entity-1",
            source_id="fixture",
            source_snapshot_id="other-snapshot",
            raw_object_id=locator.raw_object_id,
            raw_object_path=locator.raw_object_path,
            raw_sha256="a" * 64,
            raw_locator=locator,
            adapter_version="adapter-v1",
        )


def test_records_reject_a_locator_from_a_different_source() -> None:
    with pytest.raises(ValueError, match="source_id"):
        SourceRecordDTO(
            source_id="other-source",
            record_type="deck",
            raw_locator=raw_locator(),
            original_source_values={},
        )


def test_archive_member_is_portable_and_part_of_exact_locator() -> None:
    first = RawLocator(
        source_id="fixture",
        source_snapshot_id="fixture-snapshot",
        raw_object_id="archive-1",
        raw_object_path="objects/archive-1.zip",
        location=JsonPointerLocator(pointer="/0"),
        archive_member="nested/cards.json",
    )
    second = first.model_copy(update={"archive_member": "other/cards.json"})
    other_source = first.model_copy(update={"source_id": "other-source"})

    assert first.exact_locator != second.exact_locator
    assert first.exact_locator != other_source.exact_locator
    with pytest.raises(ValueError):
        first.model_copy(update={"archive_member": "nested\\cards.json"})


def test_audit_details_and_run_metadata_are_secret_free() -> None:
    audit = AuditRecord(
        audit_id="audit-secret",
        entity_id="staging-1",
        stage="quality",
        finding_code="quality.missing_field",
        details={
            "url": "https://example.invalid/check?credential=detail-secret&safe=1",
            "nested": {"authorization": "Bearer detail-token"},
        },
    )

    serialized = str(audit.model_dump(mode="json"))
    assert "detail-secret" not in serialized
    assert "detail-token" not in serialized
