"""Mapping from MTGJSON observations into the common Task-5 staging contract."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from commander_ai.data_pipeline.staging.records import (
    SourceRecordDTO,
    StagingRecord,
    StagingStatus,
)

from .parser import MTGJSONParsedRecord


class MTGJSONStagingMapper:
    """Preserve source values and findings without resolving canonical identity."""

    def map_records(self, records: Iterable[MTGJSONParsedRecord]) -> tuple[StagingRecord, ...]:
        return tuple(self.map_record(record) for record in records)

    def map_record(self, record: MTGJSONParsedRecord) -> StagingRecord:
        dto = SourceRecordDTO(
            source_id=record.raw_locator.source_id,
            record_type=record.record_type,
            raw_locator=record.raw_locator,
            original_source_values=record.source_values,
        )
        return StagingRecord.from_dto(
            dto,
            staging_record_id=self._staging_record_id(record),
            status=self._status(record),
            finding_codes=record.finding_codes,
        )

    @staticmethod
    def _staging_record_id(record: MTGJSONParsedRecord) -> str:
        digest = hashlib.sha256(record.raw_locator.exact_locator.encode("utf-8")).hexdigest()
        return f"mtgjson-staging-{digest[:32]}"

    @staticmethod
    def _status(record: MTGJSONParsedRecord) -> StagingStatus:
        if not record.finding_codes:
            return "OBSERVED"
        if any(code.startswith("integrity.") for code in record.finding_codes):
            return "INCOMPLETE"
        if any(
            code in {"parse.invalid_json", "parse.duplicate_json_key", "parse.record_not_object"}
            for code in record.finding_codes
        ):
            return "PARSE_FAILED"
        return "STRUCTURAL_INVALID"


def map_to_staging(records: Iterable[MTGJSONParsedRecord]) -> tuple[StagingRecord, ...]:
    """Functional adapter entry point for Task-5 staging consumers."""

    return MTGJSONStagingMapper().map_records(records)


__all__ = ["MTGJSONStagingMapper", "map_to_staging"]
