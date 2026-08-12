"""Current-use, takedown, and export decisions independent of history."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .source_settings import SourceApprovalStatus, normalize_source_id
from .yaml_loader import redact_text


class CurrentUseStatus(StrEnum):
    ALLOWED = "ALLOWED"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"
    TAKEDOWN = "TAKEDOWN"
    PROHIBITED = "PROHIBITED"


class PolicyOperation(StrEnum):
    SOURCE_SYNC = "source_sync"
    NORMALIZE = "normalize"
    VALIDATE = "validate"
    REPORT = "report"
    DATASET_BUILD = "dataset_build"
    PUBLIC_EXPORT = "public_export"
    AUDIT_INSPECT = "audit_inspect"

    @property
    def is_audit_only(self) -> bool:
        return self is PolicyOperation.AUDIT_INSPECT

    @classmethod
    def normalize(cls, value: object) -> PolicyOperation:
        if isinstance(value, cls):
            return value
        if not isinstance(value, str):
            raise ValueError("operation must be a string")
        normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
        aliases = {
            "source_sync": cls.SOURCE_SYNC,
            "normalize": cls.NORMALIZE,
            "validate": cls.VALIDATE,
            "report": cls.REPORT,
            "dataset_build": cls.DATASET_BUILD,
            "public_export": cls.PUBLIC_EXPORT,
            "audit_inspect": cls.AUDIT_INSPECT,
        }
        try:
            return aliases[normalized]
        except KeyError as error:
            raise ValueError("unknown operation") from error


def _normalize_current_status(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = value.strip().upper().replace("-", "_").replace(" ", "_")
    return {
        "ALLOW": "ALLOWED",
        "APPROVE": "ALLOWED",
        "APPROVED": "ALLOWED",
        "ACTIVE": "ALLOWED",
        "BLOCKED": "PROHIBITED",
    }.get(normalized, normalized)


class CurrentUseDecision(BaseModel):
    """One explicit current-use decision; no secret or raw response is retained."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    source_id: str
    status: CurrentUseStatus
    approval_status: SourceApprovalStatus | None = None
    reason: str = Field(min_length=1)
    effective_at: datetime
    decision_id: str = Field(default="current-use.v1", min_length=1)
    takedown_reference: str | None = Field(default=None, min_length=1)

    @field_validator("reason", "takedown_reference")
    @classmethod
    def redact_sensitive_text(cls, value: str) -> str:
        return redact_text(value)

    @field_serializer("reason")
    def serialize_reason(self, value: str) -> str:
        return redact_text(value)

    @field_serializer("takedown_reference")
    def serialize_takedown_reference(self, value: str | None) -> str | None:
        return None if value is None else redact_text(value)

    @field_validator("source_id")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return normalize_source_id(value)

    @field_validator("status", mode="before")
    @classmethod
    def validate_status(cls, value: object) -> object:
        return _normalize_current_status(value)

    @field_validator("approval_status", mode="before")
    @classmethod
    def normalize_approval_status(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper().replace("-", "_")
        return value

    @field_validator("effective_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("effective_at must include a timezone")
        return value


def current_use_decision_binding(
    *,
    source_id: str,
    historical_status: SourceApprovalStatus,
    current_use: CurrentUseDecision,
    operation: PolicyOperation | str,
) -> tuple[str, str]:
    """Return a deterministic reference and digest for one current-use decision."""

    normalized_source_id = normalize_source_id(source_id)
    normalized_operation = PolicyOperation.normalize(operation)
    payload = {
        "schema_version": "current-use-decision.v1",
        "source_id": normalized_source_id,
        "operation": normalized_operation.value,
        "historical_status": getattr(historical_status, "value", str(historical_status)),
        "current_use": current_use.model_dump(mode="json"),
    }
    digest = sha256_hex(canonical_json_bytes(payload))
    return f"current-use.v1:{normalized_source_id}:{digest[:32]}", digest


class CurrentUseResult(BaseModel):
    """Safe policy result suitable for application errors and run metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    source_id: str
    operation: PolicyOperation
    allowed: bool
    code: str
    reason: str
    historical_status: SourceApprovalStatus
    current_status: CurrentUseStatus | None = None
    decision_reference: str | None = Field(default=None, min_length=1)
    decision_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")


class CurrentUsePolicy:
    """Evaluate current-use decisions without reading files or making requests."""

    REQUIRED_OPERATIONS = frozenset(
        {
            PolicyOperation.NORMALIZE,
            PolicyOperation.VALIDATE,
            PolicyOperation.REPORT,
            PolicyOperation.DATASET_BUILD,
            PolicyOperation.PUBLIC_EXPORT,
        }
    )

    @classmethod
    def requires_decision(cls, operation: PolicyOperation | str) -> bool:
        return PolicyOperation.normalize(operation) in cls.REQUIRED_OPERATIONS

    @classmethod
    def check(
        cls,
        *,
        source_id: str,
        historical_status: SourceApprovalStatus,
        current_use: CurrentUseDecision | None,
        operation: PolicyOperation | str,
    ) -> CurrentUseResult:
        normalized_source_id = normalize_source_id(source_id)
        normalized_operation = PolicyOperation.normalize(operation)
        if current_use is None:
            decision_reference = None
            decision_sha256 = None
        else:
            decision_reference, decision_sha256 = current_use_decision_binding(
                source_id=normalized_source_id,
                historical_status=historical_status,
                current_use=current_use,
                operation=normalized_operation,
            )
        if current_use is None:
            if normalized_operation.is_audit_only:
                return CurrentUseResult(
                    source_id=normalized_source_id,
                    operation=normalized_operation,
                    allowed=True,
                    code="POLICY_AUDIT_ONLY_ALLOWED",
                    reason=(
                        "audit-only inspection does not emit processed or redistributable records"
                    ),
                    historical_status=historical_status,
                    decision_reference=decision_reference,
                    decision_sha256=decision_sha256,
                )
            if cls.requires_decision(normalized_operation):
                return CurrentUseResult(
                    source_id=normalized_source_id,
                    operation=normalized_operation,
                    allowed=False,
                    code="POLICY_CURRENT_USE_REQUIRED",
                    reason="current-use decision is required for this operation",
                    historical_status=historical_status,
                    decision_reference=decision_reference,
                    decision_sha256=decision_sha256,
                )
            return CurrentUseResult(
                source_id=normalized_source_id,
                operation=normalized_operation,
                allowed=True,
                code="POLICY_CURRENT_USE_NOT_REQUIRED",
                reason="operation does not require a current-use decision",
                historical_status=historical_status,
                decision_reference=decision_reference,
                decision_sha256=decision_sha256,
            )

        if current_use.source_id != normalized_source_id:
            return CurrentUseResult(
                source_id=normalized_source_id,
                operation=normalized_operation,
                allowed=False,
                code="POLICY_SOURCE_MISMATCH",
                reason="current-use decision source does not match requested source",
                historical_status=historical_status,
                current_status=current_use.status,
                decision_reference=decision_reference,
                decision_sha256=decision_sha256,
            )
        if normalized_operation.is_audit_only:
            return CurrentUseResult(
                source_id=normalized_source_id,
                operation=normalized_operation,
                allowed=True,
                code="POLICY_AUDIT_ONLY_ALLOWED",
                reason=("audit-only inspection does not emit processed or redistributable records"),
                historical_status=historical_status,
                current_status=current_use.status,
                decision_reference=decision_reference,
                decision_sha256=decision_sha256,
            )
        if current_use.status is not CurrentUseStatus.ALLOWED:
            return CurrentUseResult(
                source_id=normalized_source_id,
                operation=normalized_operation,
                allowed=False,
                code="POLICY_CURRENT_USE_BLOCKED",
                reason=f"current-use status is {current_use.status.value}",
                historical_status=historical_status,
                current_status=current_use.status,
                decision_reference=decision_reference,
                decision_sha256=decision_sha256,
            )
        if normalized_operation is PolicyOperation.PUBLIC_EXPORT and (
            current_use.approval_status is not SourceApprovalStatus.APPROVED_REDISTRIBUTION
        ):
            return CurrentUseResult(
                source_id=normalized_source_id,
                operation=normalized_operation,
                allowed=False,
                code="POLICY_REDISTRIBUTION_NOT_APPROVED",
                reason="current redistribution approval is required for public export",
                historical_status=historical_status,
                current_status=current_use.status,
                decision_reference=decision_reference,
                decision_sha256=decision_sha256,
            )
        return CurrentUseResult(
            source_id=normalized_source_id,
            operation=normalized_operation,
            allowed=True,
            code="POLICY_CURRENT_USE_ALLOWED",
            reason=redact_text(current_use.reason),
            historical_status=historical_status,
            current_status=current_use.status,
            decision_reference=decision_reference,
            decision_sha256=decision_sha256,
        )
