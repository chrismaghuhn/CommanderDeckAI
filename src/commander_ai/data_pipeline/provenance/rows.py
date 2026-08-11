"""Immutable audit, resolution-attempt, and source-provenance rows."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from commander_ai.domain.path_policy import validate_portable_relative_path
from commander_ai.domain.provenance import DomainModel

from ..quality.finding_codes import (
    FindingNamespace,
    validate_finding_code,
    validate_finding_codes,
)
from ..quality.quarantine import QuarantineRecord
from ..staging.raw_locators import RawLocator


class AuditRecord(DomainModel):
    """A finding row that is always retained in the audit layer."""

    audit_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    stage: FindingNamespace
    finding_code: str = Field(min_length=1)
    raw_locator: RawLocator | None = None
    details: dict[str, object] = Field(default_factory=dict)
    layer: Literal["audit"] = "audit"

    @field_validator("finding_code")
    @classmethod
    def validate_finding(cls, value: str) -> str:
        return validate_finding_code(value)

    @model_validator(mode="after")
    def validate_stage_code(self) -> AuditRecord:
        if self.finding_code.split(".", maxsplit=1)[0] != self.stage:
            raise ValueError("audit stage and finding namespace must match")
        return self


class ResolutionAttempt(DomainModel):
    """One deterministic identity-resolution attempt, including non-successes."""

    attempt_id: str = Field(min_length=1)
    staging_record_id: str = Field(min_length=1)
    raw_locator: RawLocator
    source_field: str = Field(min_length=1)
    original_source_value: object
    resolver_version: str = Field(min_length=1)
    normalization_policy_version: str = Field(min_length=1)
    alias_catalog_version: str = Field(min_length=1)
    card_catalog_snapshot_id: str = Field(min_length=1)
    status: Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED"]
    candidate_canonical_ids: tuple[str, ...] = Field(default_factory=tuple)
    canonical_id: str | None = None
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    attempted_at: datetime
    layer: Literal["audit"] = "audit"

    @field_validator("finding_codes")
    @classmethod
    def validate_findings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return validate_finding_codes(value, namespace="resolution")

    @model_validator(mode="after")
    def validate_resolution_state(self) -> ResolutionAttempt:
        if self.status == "RESOLVED" and self.canonical_id is None:
            raise ValueError("resolved attempts require canonical_id")
        if self.status != "RESOLVED" and self.canonical_id is not None:
            raise ValueError("ambiguous or unresolved attempts cannot have canonical_id")
        return self


class ProvenanceRow(DomainModel):
    """Locatable provenance for a normalized/audit observation."""

    provenance_id: str = Field(min_length=1)
    entity_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    raw_object_id: str = Field(min_length=1)
    raw_object_path: str = Field(min_length=1)
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    raw_locator: RawLocator
    adapter_version: str = Field(min_length=1)
    mapper_version: str | None = Field(default=None, min_length=1)
    layer: Literal["normalized", "audit"] = "audit"

    @field_validator("raw_object_path")
    @classmethod
    def validate_raw_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)


class AuditRows(DomainModel):
    """A lossless in-memory handoff to audit/provenance/quarantine persistence."""

    resolution_attempts: tuple[ResolutionAttempt, ...] = Field(default_factory=tuple)
    findings: tuple[AuditRecord, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceRow, ...] = Field(default_factory=tuple)
    quarantines: tuple[QuarantineRecord, ...] = Field(default_factory=tuple)


__all__ = ["AuditRecord", "AuditRows", "ProvenanceRow", "ResolutionAttempt"]
