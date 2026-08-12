"""Bind Spicerack records to verified evidence and generic staging/audit rows."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.staging.raw_locators import validate_raw_locator_against_snapshot
from commander_ai.data_pipeline.staging.records import SourceRecordDTO, StagingRecord, StagingStatus

from .dto import SpicerackParsedRecord
from .errors import SpicerackStagingError
from .parser import SpicerackParser
from .settings import SPICERACK_SOURCE_ID, SpicerackSettings


class SpicerackStagingMapper:
    """Keep source records source-shaped; canonical observation mapping is later."""

    def __init__(self, settings: SpicerackSettings, *, policy: SourcePolicy | None = None) -> None:
        self.settings = settings
        if policy is None:
            raise SpicerackStagingError("POLICY_CURRENT_USE_REQUIRED")
        self.policy = policy
        self.parser = SpicerackParser(settings)

    def map_records(
        self,
        records: Iterable[SpicerackParsedRecord],
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[StagingRecord, ...]:
        self._require_operation(PolicyOperation.NORMALIZE)
        return tuple(
            self._map_record(record)
            for record in self._validate_records(records, verified_snapshot)
        )

    def map_audit_records(
        self,
        records: Iterable[SpicerackParsedRecord],
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[AuditRecord, ...]:
        self._require_operation(PolicyOperation.AUDIT_INSPECT)
        audits: list[AuditRecord] = []
        for record in self._validate_records(records, verified_snapshot):
            entity_id = self._staging_record_id(record)
            for finding in record.findings:
                digest = hashlib.sha256(
                    f"{record.record_type}|{record.raw_locator.exact_locator}|{finding.code}".encode()
                ).hexdigest()[:32]
                audits.append(
                    AuditRecord(
                        audit_id=f"spicerack-audit-{digest}",
                        entity_id=entity_id,
                        stage=FindingCode.parse(finding.code).namespace,
                        finding_code=finding.code,
                        raw_locator=finding.raw_locator,
                        details={"record_type": record.record_type, "message": finding.message},
                    )
                )
        return tuple(audits)

    def _require_operation(self, operation: PolicyOperation) -> None:
        try:
            if self.policy is None:
                raise SpicerackStagingError("POLICY_CURRENT_USE_REQUIRED")
            self.policy.require_operation(SPICERACK_SOURCE_ID, operation)
        except SourcePolicyError as error:
            raise SpicerackStagingError(error.code) from None

    def _validate_records(
        self,
        records: Iterable[SpicerackParsedRecord],
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[SpicerackParsedRecord, ...]:
        if not isinstance(verified_snapshot, VerifiedSourceSnapshot):
            raise SpicerackStagingError("INTEGRITY_VERIFIED_SNAPSHOT_REQUIRED")
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise SpicerackStagingError("INTEGRITY_VERIFIED_SNAPSHOT_INVALID") from None
        if verified_snapshot.manifest.source_id != SPICERACK_SOURCE_ID:
            raise ValueError("Spicerack staging requires the Spicerack source")

        materialized = tuple(records)
        expected_by_key: dict[tuple[str, str], SpicerackParsedRecord] = {}
        source_object_ids = tuple(
            sorted(
                raw_object_id
                for raw_object_id, reference in verified_snapshot.object_index.items()
                if reference.source_object_id == "spicerack-public-decklists"
            )
        )
        for raw_object_id in source_object_ids:
            for item in self.parser.parse_object(verified_snapshot, raw_object_id=raw_object_id):
                key = (item.record_type, item.raw_locator.exact_locator)
                if key in expected_by_key:
                    raise ValueError("Spicerack parser emitted duplicate record locators")
                expected_by_key[key] = item

        validated: list[SpicerackParsedRecord] = []
        seen: set[tuple[str, str]] = set()
        for record in materialized:
            if not isinstance(record, SpicerackParsedRecord):
                raise TypeError("Spicerack staging requires parsed source records")
            key = (record.record_type, record.raw_locator.exact_locator)
            if key in seen:
                raise ValueError("Spicerack staging records must use unique locators")
            expected = expected_by_key.get(key)
            if expected is None:
                raise ValueError("Spicerack record is not present in verified source evidence")
            if (
                record.source_values != expected.source_values
                or record.finding_codes != expected.finding_codes
                or record.findings != expected.findings
                or _dump(record.dto) != _dump(expected.dto)
            ):
                raise ValueError("Spicerack record does not match verified source evidence")
            validate_raw_locator_against_snapshot(
                record.raw_locator,
                verified_snapshot=verified_snapshot,
                source_id=SPICERACK_SOURCE_ID,
                max_decoded_bytes=self.settings.max_response_bytes,
            )
            for finding in record.findings:
                validate_raw_locator_against_snapshot(
                    finding.raw_locator,
                    verified_snapshot=verified_snapshot,
                    source_id=SPICERACK_SOURCE_ID,
                    max_decoded_bytes=self.settings.max_response_bytes,
                )
            seen.add(key)
            validated.append(record)
        if set(expected_by_key) != seen:
            raise ValueError("Spicerack staging records omit verified source records")
        return tuple(validated)

    def _map_record(self, record: SpicerackParsedRecord) -> StagingRecord:
        source_dto = SourceRecordDTO(
            source_id=SPICERACK_SOURCE_ID,
            record_type=record.record_type,
            raw_locator=record.raw_locator,
            original_source_values=record.source_values,
        )
        pipeline_codes = tuple(
            code
            for code in record.finding_codes
            if code.split(".", maxsplit=1)[0] in {"parse", "integrity"}
        )
        status = self._status(pipeline_codes)
        return StagingRecord.from_dto(
            source_dto,
            staging_record_id=self._staging_record_id(record),
            status=status,
            finding_codes=pipeline_codes,
        )

    @staticmethod
    def _staging_record_id(record: SpicerackParsedRecord) -> str:
        digest = hashlib.sha256(record.raw_locator.exact_locator.encode("utf-8")).hexdigest()
        record_digest = hashlib.sha256(record.record_type.encode("utf-8")).hexdigest()[:8]
        return f"spicerack-staging-{record_digest}-{digest[:24]}"

    @staticmethod
    def _status(codes: tuple[str, ...]) -> StagingStatus:
        if not codes:
            return "OBSERVED"
        if any(code.startswith("integrity.") for code in codes):
            return "INCOMPLETE"
        return "PARSE_FAILED"


def _dump(value: object | None) -> object | None:
    model_dump = getattr(value, "model_dump", None)
    return model_dump(mode="json") if callable(model_dump) else value


__all__ = ["SpicerackStagingError", "SpicerackStagingMapper"]
