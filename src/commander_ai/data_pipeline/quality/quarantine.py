"""Typed quarantine records that retain failed source observations."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from commander_ai.domain.provenance import DomainModel
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from ..staging.raw_locators import RawLocator
from ..staging.records import StagingRecord
from .finding_codes import validate_finding_code


class QuarantineRecord(DomainModel):
    """A retained observation withheld from canonical or curated output."""

    quarantine_id: str = Field(min_length=1)
    staging_record_id: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    raw_locator: RawLocator
    original_source_values: object
    layer: Literal["quarantine"] = "quarantine"

    @field_validator("reason_code")
    @classmethod
    def validate_reason(cls, value: str) -> str:
        return validate_finding_code(value)


def quarantine_record(
    record: StagingRecord,
    *,
    reason_code: str,
    quarantine_id: str | None = None,
) -> QuarantineRecord:
    """Create a deterministic retained quarantine row without altering the staging record."""

    normalized_code = validate_finding_code(reason_code)
    if quarantine_id is None:
        fingerprint = sha256_hex(
            canonical_json_bytes(
                {
                    "reason_code": normalized_code,
                    "staging_record_id": record.staging_record_id,
                    "raw_locator": record.raw_locator.model_dump(mode="json"),
                }
            )
        )
        quarantine_id = f"quarantine-{fingerprint[:32]}"
    return QuarantineRecord(
        quarantine_id=quarantine_id,
        staging_record_id=record.staging_record_id,
        reason_code=normalized_code,
        raw_locator=record.raw_locator,
        original_source_values=record.original_source_values,
    )


__all__ = ["QuarantineRecord", "quarantine_record"]
