"""Bind TopDeck parse records to raw evidence and generic staging/audit rows."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.staging.raw_locators import validate_raw_locator_against_snapshot
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord, StagingStatus

from .dto import TopDeckParsedRecord
from .errors import TopDeckStagingError
from .parser import TopDeckParser
from .settings import TOPDECK_SOURCE_ID, TopDeckSettings


class TopDeckStagingMapper:
    """Keep source table/event observations lossless and non-canonical."""

    def __init__(self, settings: TopDeckSettings) -> None:
        self.settings = settings
        self.parser = TopDeckParser(settings)

    def map_records(
        self,
        records: Iterable[TopDeckParsedRecord],
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[StagingRecord, ...]:
        return tuple(
            self._map_record(record)
            for record in self._validate_records(records, verified_snapshot)
        )

    def map_audit_records(
        self,
        records: Iterable[TopDeckParsedRecord],
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[AuditRecord, ...]:
        audits: list[AuditRecord] = []
        for record in self._validate_records(records, verified_snapshot):
            entity_id = self._staging_record_id(record)
            for finding in record.findings:
                digest = hashlib.sha256(
                    f"{record.raw_locator.exact_locator}|{finding.code}".encode()
                ).hexdigest()[:32]
                audits.append(
                    AuditRecord(
                        audit_id=f"topdeck-audit-{digest}",
                        entity_id=entity_id,
                        stage=FindingCode.parse(finding.code).namespace,
                        finding_code=finding.code,
                        raw_locator=finding.raw_locator,
                        details={"record_type": record.record_type, "message": finding.message},
                    )
                )
        return tuple(audits)

    def staging_record_id(
        self,
        record: TopDeckParsedRecord,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> str:
        self._validate_records((record,), verified_snapshot)
        return self._staging_record_id(record)

    def _validate_records(
        self,
        records: Iterable[TopDeckParsedRecord],
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[TopDeckParsedRecord, ...]:
        if not isinstance(verified_snapshot, VerifiedSourceSnapshot):
            raise TopDeckStagingError("INTEGRITY_VERIFIED_SNAPSHOT_REQUIRED")
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise TopDeckStagingError("INTEGRITY_VERIFIED_SNAPSHOT_INVALID") from None
        if verified_snapshot.manifest.source_id != TOPDECK_SOURCE_ID:
            raise ValueError("TopDeck staging requires the TopDeck source")

        materialized = tuple(records)
        expected_by_key: dict[tuple[str, str], TopDeckParsedRecord] = {}
        for raw_object_id in {item.raw_locator.raw_object_id for item in materialized}:
            parsed_records = self.parser.parse_object(
                verified_snapshot,
                raw_object_id=raw_object_id,
            )
            for item in parsed_records:
                key = (item.record_type, item.raw_locator.exact_locator)
                if key in expected_by_key:
                    raise ValueError("TopDeck parser emitted duplicate record locators")
                expected_by_key[key] = item

        validated: list[TopDeckParsedRecord] = []
        seen: set[tuple[str, str]] = set()
        for record in materialized:
            if not isinstance(record, TopDeckParsedRecord):
                raise TypeError("TopDeck staging requires parsed source records")
            key = (record.record_type, record.raw_locator.exact_locator)
            if key in seen:
                raise ValueError("TopDeck staging records must use unique locators")
            expected_record = expected_by_key.get(key)
            if expected_record is None:
                raise ValueError("TopDeck record is not present in verified source evidence")
            if (
                record.source_values != expected_record.source_values
                or record.finding_codes != expected_record.finding_codes
                or record.findings != expected_record.findings
                or _dump(record.dto) != _dump(expected_record.dto)
            ):
                raise ValueError("TopDeck record does not match verified source evidence")
            validate_raw_locator_against_snapshot(
                record.raw_locator,
                verified_snapshot=verified_snapshot,
                source_id=TOPDECK_SOURCE_ID,
            )
            for finding in record.findings:
                validate_raw_locator_against_snapshot(
                    finding.raw_locator,
                    verified_snapshot=verified_snapshot,
                    source_id=TOPDECK_SOURCE_ID,
                )
            seen.add(key)
            validated.append(record)
        return tuple(validated)

    def _map_record(self, record: TopDeckParsedRecord) -> StagingRecord:
        source_dto = SourceRecordDTO(
            source_id=TOPDECK_SOURCE_ID,
            record_type=record.record_type,
            raw_locator=record.raw_locator,
            original_source_values=record.source_values,
        )
        return StagingRecord.from_dto(
            source_dto,
            staging_record_id=self._staging_record_id(record),
            status=self._status(record.finding_codes),
            finding_codes=record.finding_codes,
        )

    @staticmethod
    def _staging_record_id(record: TopDeckParsedRecord) -> str:
        digest = hashlib.sha256(record.raw_locator.exact_locator.encode("utf-8")).hexdigest()
        return f"topdeck-staging-{digest[:32]}"

    @staticmethod
    def _status(codes: tuple[str, ...]) -> StagingStatus:
        if not codes:
            return "OBSERVED"
        if any(code.startswith("integrity.") for code in codes):
            return "INCOMPLETE"
        if any(
            code
            in {
                "parse.topdeck_invalid_json",
                "parse.topdeck_duplicate_json_key",
                "parse.topdeck_invalid_response_envelope",
                "parse.topdeck_record_not_object",
            }
            for code in codes
        ):
            return "PARSE_FAILED"
        return "STRUCTURAL_INVALID"


def _dump(value: object | None) -> object | None:
    model_dump = getattr(value, "model_dump", None)
    return model_dump(mode="json") if callable(model_dump) else value


__all__ = ["TopDeckStagingMapper"]
