"""Source DTO and non-canonical staging record contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator

from commander_ai.domain.provenance import DomainModel

from ..quality.finding_codes import validate_finding_codes
from .raw_locators import RawLocator

StagingStatus = Literal["OBSERVED", "INCOMPLETE", "PARSE_FAILED", "STRUCTURAL_INVALID"]


class SourceRecordDTO(DomainModel):
    """Source-shaped values before staging adds pipeline status and identity."""

    source_id: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    raw_locator: RawLocator
    original_source_values: object


class StagingRecord(DomainModel):
    """Lossless source observation; canonical identity is intentionally absent."""

    staging_record_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    record_type: str = Field(min_length=1)
    raw_locator: RawLocator
    original_source_values: object
    status: StagingStatus
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    layer: Literal["staging"] = "staging"

    @field_validator("finding_codes")
    @classmethod
    def validate_findings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return validate_finding_codes(value)

    @classmethod
    def from_dto(
        cls,
        dto: SourceRecordDTO,
        *,
        staging_record_id: str,
        status: StagingStatus,
        finding_codes: tuple[str, ...] = (),
    ) -> StagingRecord:
        return cls(
            staging_record_id=staging_record_id,
            source_id=dto.source_id,
            record_type=dto.record_type,
            raw_locator=dto.raw_locator,
            original_source_values=dto.original_source_values,
            status=status,
            finding_codes=tuple(str(code) for code in finding_codes),
        )

    @property
    def has_canonical_identity(self) -> bool:
        return False

    @property
    def original_values(self) -> object:
        return self.original_source_values

    @property
    def source_values(self) -> object:
        return self.original_source_values


__all__ = ["SourceRecordDTO", "StagingRecord", "StagingStatus"]
