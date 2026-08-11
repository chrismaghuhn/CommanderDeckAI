"""Map Spellbook parse observations into Task 5 staging and audit rows."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.staging.raw_locators import validate_raw_locator_against_snapshot
from commander_ai.data_pipeline.staging.records import (
    SourceRecordDTO,
    StagingRecord,
    StagingStatus,
)

from .api_models import CommanderSpellbookParsedRecord
from .errors import CommanderSpellbookStagingError
from .settings import documented_endpoint, raw_object_identity


class CommanderSpellbookStagingMapper:
    """Keep source observations permissive and never assign semantic identity."""

    def map_records(
        self,
        records: Iterable[CommanderSpellbookParsedRecord],
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[StagingRecord, ...]:
        validated = self._validate_records(records, verified_snapshot)
        return tuple(self._map_record(record) for record in validated)

    def map_audit_records(
        self,
        records: Iterable[CommanderSpellbookParsedRecord],
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[AuditRecord, ...]:
        audits: list[AuditRecord] = []
        for record in self._validate_records(records, verified_snapshot):
            staging_id = self._staging_record_id(record)
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
                            "source_values": record.source_values,
                        },
                    )
                )
        return tuple(audits)

    @staticmethod
    def _validate_records(
        records: Iterable[CommanderSpellbookParsedRecord],
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[CommanderSpellbookParsedRecord, ...]:
        if not isinstance(verified_snapshot, VerifiedSourceSnapshot):
            raise CommanderSpellbookStagingError("INTEGRITY_VERIFIED_SNAPSHOT_REQUIRED")
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise ValueError(
                "Commander Spellbook staging requires consistent snapshot evidence"
            ) from None
        if verified_snapshot.manifest.source_id != "commander_spellbook":
            raise ValueError("Commander Spellbook staging requires the Commander Spellbook source")

        validated: list[CommanderSpellbookParsedRecord] = []
        for record in records:
            if not isinstance(record, CommanderSpellbookParsedRecord):
                raise TypeError("Commander Spellbook staging requires parsed source records")
            try:
                contract, page = raw_object_identity(record.raw_locator.raw_object_id)
            except ValueError:
                raise ValueError("Commander Spellbook record product identity is invalid") from None
            expected_record_types = {contract, contract[:-1]}
            if record.record_type not in expected_record_types:
                raise ValueError(
                    "Commander Spellbook record type does not match its source product"
                )
            reference = verified_snapshot.object_index.get(record.raw_locator.raw_object_id)
            request = (
                None
                if reference is None
                else next(
                    (
                        item
                        for item in verified_snapshot.manifest.requests
                        if item.request_id == reference.request_id
                    ),
                    None,
                )
            )
            parameters = {} if request is None else request.sanitized_parameters
            if (
                reference is None
                or reference.source_object_id != contract
                or request is None
                or request.sanitized_method != "GET"
                or request.format != "json"
                or request.sanitized_endpoint != documented_endpoint(contract)
                or set(parameters) != {"page"}
                or not isinstance(parameters.get("page"), int)
                or isinstance(parameters.get("page"), bool)
                or parameters.get("page") != page
            ):
                raise ValueError("Commander Spellbook record request/product evidence disagrees")
            validate_raw_locator_against_snapshot(
                record.raw_locator,
                verified_snapshot=verified_snapshot,
                source_id="commander_spellbook",
            )
            validated.append(record)
        return tuple(validated)

    def staging_record_id(
        self,
        record: CommanderSpellbookParsedRecord,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> str:
        self._validate_records((record,), verified_snapshot)
        return self._staging_record_id(record)

    @staticmethod
    def _staging_record_id(record: CommanderSpellbookParsedRecord) -> str:
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
            staging_record_id=self._staging_record_id(record),
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
