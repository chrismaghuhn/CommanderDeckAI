from __future__ import annotations

from datetime import UTC, datetime

import pytest

from commander_ai.data_pipeline.provenance.rows import AuditRecord, AuditRows, ResolutionAttempt
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.quality.quarantine import quarantine_record
from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    RawLocator,
)
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord


def raw_locator() -> RawLocator:
    return RawLocator(
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
