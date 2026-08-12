"""Fail-closed validation of reviewed source rights metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from commander_ai.config.source_registry import SourceRegistryEntry
from commander_ai.config.source_settings import SourceApprovalStatus

RedistributionStatus = Literal["not_approved", "derived_only", "approved"]


@dataclass(frozen=True, slots=True)
class ReviewedSourceMetadata:
    attribution_required: bool
    raw_local_storage: str
    terms_reference: str
    redistribution_status: RedistributionStatus


class SourceMetadataError(ValueError):
    """Safe policy failure for missing or contradictory reviewed metadata."""

    def __init__(self, code: str, reason: str) -> None:
        self.code = code
        self.reason = reason
        super().__init__(reason)


def validate_reviewed_source_metadata(entry: SourceRegistryEntry) -> ReviewedSourceMetadata:
    """Validate registry evidence and return only authoritative adapter inputs."""

    historical = entry.historical_approval
    terms_reference = historical.terms_reference
    if terms_reference is None:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_MISSING",
            "reviewed terms reference is required",
        )
    parsed_terms = urlsplit(terms_reference)
    if parsed_terms.scheme not in {"http", "https"} or not parsed_terms.hostname:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_CONTRADICTORY",
            "reviewed terms reference must be an absolute HTTP(S) URI",
        )
    if historical.attribution_required is None:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_MISSING",
            "reviewed attribution metadata is required",
        )
    raw_storage = historical.raw_local_storage
    if raw_storage is None:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_MISSING",
            "reviewed raw-storage metadata is required",
        )
    if raw_storage.casefold() != "allowed_local":
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_CONTRADICTORY",
            "reviewed raw-storage metadata does not permit local acquisition",
        )
    raw_status = _normalize_redistribution(historical.redistribution_raw)
    derived_status = _normalize_redistribution(historical.redistribution_derived)
    if raw_status is None or derived_status is None:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_MISSING",
            "reviewed raw and derived redistribution metadata are both required",
        )
    if raw_status != derived_status:
        code = (
            "POLICY_SOURCE_METADATA_CONTRADICTORY"
            if historical.approval_status is SourceApprovalStatus.APPROVED_REDISTRIBUTION
            or raw_status == "approved"
            else "POLICY_SOURCE_METADATA_MISMATCH"
        )
        raise SourceMetadataError(
            code,
            "reviewed raw and derived redistribution metadata must agree",
        )
    redistribution_status: RedistributionStatus = (
        "approved" if raw_status == "approved" else "not_approved"
    )
    if historical.approval_status is SourceApprovalStatus.APPROVED_REDISTRIBUTION:
        if redistribution_status != "approved":
            raise SourceMetadataError(
                "POLICY_SOURCE_METADATA_CONTRADICTORY",
                "redistribution approval status conflicts with reviewed redistribution metadata",
            )
    elif redistribution_status == "approved":
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_CONTRADICTORY",
            "reviewed redistribution approval exceeds historical approval status",
        )
    configured_redistribution = _normalize_redistribution(entry.settings.redistribution)
    if configured_redistribution is None:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_MISSING",
            "configured redistribution metadata is required",
        )
    if entry.settings.attribution_required != historical.attribution_required:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_MISMATCH",
            "source attribution metadata is not equal to reviewed policy",
        )
    if entry.settings.raw_storage != raw_storage:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_MISMATCH",
            "source raw-storage metadata is not equal to reviewed policy",
        )
    if configured_redistribution != raw_status:
        raise SourceMetadataError(
            "POLICY_SOURCE_METADATA_MISMATCH",
            "source redistribution metadata is not equal to reviewed policy",
        )
    return ReviewedSourceMetadata(
        attribution_required=historical.attribution_required,
        raw_local_storage=raw_storage,
        terms_reference=terms_reference,
        redistribution_status=redistribution_status,
    )


def _normalize_redistribution(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().casefold().replace("-", "_").replace(" ", "_")
    return {
        "approved": "approved",
        "true": "approved",
        "yes": "approved",
        "review_required": "review_required",
        "license_and_content_review": "review_required",
        "false": "not_approved",
        "no": "not_approved",
        "not_approved": "not_approved",
        "denied": "not_approved",
        "prohibited": "not_approved",
    }.get(normalized)


__all__ = [
    "RedistributionStatus",
    "ReviewedSourceMetadata",
    "SourceMetadataError",
    "validate_reviewed_source_metadata",
]
