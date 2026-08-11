"""Source DTO and non-canonical staging record contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, field_validator, model_validator

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
        findings = validate_finding_codes(value)
        if any(code.split(".", maxsplit=1)[0] not in {"parse", "integrity"} for code in findings):
            raise ValueError("staging finding codes must use parse or integrity namespaces")
        if len(findings) != len(set(findings)):
            raise ValueError("staging finding codes must be unique")
        if findings != tuple(sorted(findings)):
            raise ValueError("staging finding codes must be sorted")
        return findings

    @model_validator(mode="after")
    def validate_status_findings(self) -> StagingRecord:
        namespaces = {code.split(".", maxsplit=1)[0] for code in self.finding_codes}
        if self.status == "OBSERVED" and self.finding_codes:
            raise ValueError("OBSERVED staging records cannot carry findings")
        if self.status == "INCOMPLETE" and "integrity" not in namespaces:
            raise ValueError("INCOMPLETE staging records require an integrity finding")
        if self.status in {"PARSE_FAILED", "STRUCTURAL_INVALID"} and "parse" not in namespaces:
            raise ValueError(f"{self.status} staging records require a parse finding")
        return self

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
