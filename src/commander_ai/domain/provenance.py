"""Source-neutral provenance and manifest value objects."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DomainModel(BaseModel):
    """Strict immutable base for domain values."""

    model_config = ConfigDict(extra="forbid", frozen=True)


Sha256 = str
ApprovalStatus = Literal["APPROVED_LOCAL", "APPROVED_REDISTRIBUTION"]


class ProvenanceReference(DomainModel):
    """Link a normalized value to an immutable source object."""

    source_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    source_object_id: str = Field(min_length=1)
    raw_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    retrieved_at: datetime | None = None
    adapter_version: str | None = Field(default=None, min_length=1)
    mapper_version: str | None = Field(default=None, min_length=1)
    approval_status: ApprovalStatus | None = None


class QuarantineReference(DomainModel):
    """Stable pointer to a record withheld from normalized output."""

    quarantine_id: str = Field(min_length=1)
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
    path: str | None = Field(default=None, min_length=1)
    record_locator: str | None = Field(default=None, min_length=1)


class SourceSnapshotRequest(DomainModel):
    """Sanitized request lineage for a source snapshot."""

    request_id: str = Field(min_length=1)
    sanitized_method: str = Field(min_length=1)
    sanitized_endpoint: str = Field(min_length=1)
    api_version: str | None = Field(default=None, min_length=1)
    format: str = Field(min_length=1)
    sanitized_parameters: Mapping[str, object] = Field(default_factory=dict)


class RawObjectReference(DomainModel):
    """Immutable raw object metadata; ``sha256`` covers exact raw bytes."""

    raw_object_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    retrieved_at: datetime
    path: str = Field(min_length=1)
    bytes: int = Field(ge=0)
    content_type: str | None = None
    sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    source_object_id: str | None = Field(default=None, min_length=1)
    upstream_sha256: Sha256 | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    checksum_verification_status: Literal[
        "verified",
        "mismatch",
        "not_provided",
        "not_checked",
        "not_applicable",
    ]
    logical_record_count: int | None = Field(default=None, ge=0)


class SourceSnapshotManifest(DomainModel):
    """Authoritative v2 source snapshot provenance."""

    schema_version: Literal["source-snapshot-manifest.v2"] = "source-snapshot-manifest.v2"
    source_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    status: Literal["COMPLETE", "INCOMPLETE", "FAILED"]
    approval_status: ApprovalStatus
    adapter_version: str = Field(min_length=1)
    started_at: datetime
    completed_at: datetime | None
    terms_reference: str | None = None
    usage_status: str = Field(min_length=1)
    request_parameters_redacted: Mapping[str, object] = Field(default_factory=dict)
    requests: tuple[SourceSnapshotRequest, ...]
    objects: tuple[RawObjectReference, ...]
    pagination_state: Mapping[str, object] | None = None
    attribution_required: bool
    redistribution_status: Literal["not_approved", "derived_only", "approved"]
    snapshot_content_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")


class NormalizedSnapshotManifest(DomainModel):
    """Identity and provenance for one deterministic normalization output."""

    schema_version: Literal["normalized-snapshot-manifest.v1"] = "normalized-snapshot-manifest.v1"
    normalized_snapshot_id: str = Field(min_length=1)
    producing_run_id: str = Field(min_length=1)
    input_source_snapshot_manifest_id: str = Field(min_length=1)
    input_source_snapshot_manifest_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    source_id: str = Field(min_length=1)
    status: Literal["COMPLETE", "INCOMPLETE", "FAILED"]
    normalized_schema_version: str = Field(min_length=1)
    mapper_version: str = Field(min_length=1)
    transform_version: str = Field(min_length=1)
    normalized_artifact_path: str | None = Field(default=None, min_length=1)
    normalized_artifact_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    audit_artifact_path: str | None = Field(default=None, min_length=1)
    audit_artifact_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    counts: Mapping[str, int]
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    quarantine_references: tuple[QuarantineReference, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...]
    created_at: datetime
    started_at: datetime
    completed_at: datetime | None
    normalized_content_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")


class DatasetInputReference(DomainModel):
    """Hashed input manifest reference bound into a dataset manifest."""

    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    path: str | None = Field(default=None, min_length=1)
    sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")


class DatasetOutputReference(DomainModel):
    """Hashed dataset output artifact reference."""

    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    rows: int = Field(ge=0)
    bytes: int | None = Field(default=None, ge=0)


class DatasetExclusion(DomainModel):
    """Versioned exclusion reason and count for a dataset build."""

    code: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
    count: int = Field(ge=0)
    references: tuple[str, ...] = Field(default_factory=tuple)


class DatasetManifest(DomainModel):
    """Dataset provenance; it is not a normalization or operation manifest."""

    schema_version: Literal["dataset-manifest.v2"] = "dataset-manifest.v2"
    dataset_id: str = Field(min_length=1)
    created_at: datetime
    builder_version: str = Field(min_length=1)
    code_commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    dependency_lock_hash: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    input_manifests: tuple[DatasetInputReference, ...]
    schema_versions: tuple[str, ...]
    transform_versions: tuple[str, ...]
    policy_versions: tuple[str, ...]
    ruleset_versions: tuple[str, ...] = Field(default_factory=tuple)
    card_snapshot_ids: tuple[str, ...] = Field(default_factory=tuple)
    source_snapshots: tuple[str, ...] = Field(default_factory=tuple)
    filters: Mapping[str, object] = Field(default_factory=dict)
    split_policy: Mapping[str, object] = Field(default_factory=dict)
    exclusions: tuple[DatasetExclusion, ...] = Field(default_factory=tuple)
    counts: Mapping[str, int]
    outputs: tuple[DatasetOutputReference, ...]
    quality_report: DatasetOutputReference | None = None
    leakage_report: DatasetOutputReference | None = None
    random_seeds: tuple[int, ...] = Field(default_factory=tuple)
    redistribution_status: Literal["local_only", "derived_only", "redistributable"] = "local_only"
    dataset_content_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    manifest_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
