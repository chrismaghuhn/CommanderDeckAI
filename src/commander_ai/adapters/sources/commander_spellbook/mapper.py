"""Map Spellbook parse observations into Task 5 staging and audit rows."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.staging.records import (
    SourceRecordDTO,
    StagingRecord,
    StagingStatus,
)

from .api_models import CommanderSpellbookParsedRecord


class CommanderSpellbookStagingMapper:
    """Keep source observations permissive and never assign semantic identity."""

    def map_records(
        self, records: Iterable[CommanderSpellbookParsedRecord]
    ) -> tuple[StagingRecord, ...]:
        return tuple(self._map_record(record) for record in records)

    def map_audit_records(
        self, records: Iterable[CommanderSpellbookParsedRecord]
    ) -> tuple[AuditRecord, ...]:
        audits: list[AuditRecord] = []
        for record in records:
            staging_id = self.staging_record_id(record)
            for finding in record.findings:
                digest = hashlib.sha256(
                    f"{record.raw_locator.exact_locator}|{finding.code}".encode()
                ).hexdigest()[:32]
                audits.append(
                    AuditRecord(
                        audit_id=f"commander-spellbook-audit-{digest}",
                        entity_id=staging_id,
                        stage=FindingCode.parse(finding.code).namespace,
                        finding_code=finding.code,
                        raw_locator=finding.raw_locator,
                        details={
                            "record_type": record.record_type,
                            "message": finding.message,
                        },
                    )
                )
        return tuple(audits)

    @staticmethod
    def staging_record_id(record: CommanderSpellbookParsedRecord) -> str:
        digest = hashlib.sha256(record.raw_locator.exact_locator.encode("utf-8")).hexdigest()
        return f"commander-spellbook-staging-{digest[:32]}"

    def _map_record(self, record: CommanderSpellbookParsedRecord) -> StagingRecord:
        source_dto = SourceRecordDTO(
            source_id=record.raw_locator.source_id,
            record_type=record.record_type,
            raw_locator=record.raw_locator,
            original_source_values=record.source_values,
        )
        return StagingRecord.from_dto(
            source_dto,
            staging_record_id=self.staging_record_id(record),
            status=self._status(record.finding_codes),
            finding_codes=record.finding_codes,
        )

    @staticmethod
    def _status(codes: tuple[str, ...]) -> StagingStatus:
        if not codes:
            return "OBSERVED"
        if any(code.startswith("integrity.") for code in codes):
            return "INCOMPLETE"
        if any(
            code
            in {
                "parse.invalid_json",
                "parse.duplicate_json_key",
                "parse.record_not_object",
            }
            for code in codes
        ):
            return "PARSE_FAILED"
        return "STRUCTURAL_INVALID"


CommanderSpellbookMapper = CommanderSpellbookStagingMapper


__all__ = ["CommanderSpellbookMapper", "CommanderSpellbookStagingMapper"]
