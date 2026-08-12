"""Source-neutral provenance and manifest value objects."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Any, Literal, NoReturn, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .contract_validation import (
    ContentEncoding,
    JSONMapping,
    NonEmptyCounts,
    UniqueTuple,
    URIString,
)
from .normalized_snapshot_validation import (
    validate_finding_codes as validate_normalized_finding_codes,
)
from .normalized_snapshot_validation import (
    validate_provenance_order,
    validate_quarantine_references,
)
from .path_policy import validate_portable_relative_path as validate_portable_relative_path

DETACHED_MANIFEST_DIGEST_FIELD = "manifest_sha256"


class FrozenDict(dict[str, object]):
    """JSON-serializable mapping whose mutation operations always fail."""

    def __setitem__(self, key: str, value: object) -> NoReturn:
        raise TypeError("frozen domain mappings cannot be mutated")

    def __delitem__(self, key: str) -> NoReturn:
        raise TypeError("frozen domain mappings cannot be mutated")

    def clear(self) -> NoReturn:
        raise TypeError("frozen domain mappings cannot be mutated")

    def pop(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise TypeError("frozen domain mappings cannot be mutated")

    def popitem(self) -> NoReturn:
        raise TypeError("frozen domain mappings cannot be mutated")

    def setdefault(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise TypeError("frozen domain mappings cannot be mutated")

    def update(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise TypeError("frozen domain mappings cannot be mutated")

    def __ior__(self, value: Any) -> dict[str, object]:  # type: ignore[override, misc]
        raise TypeError("frozen domain mappings cannot be mutated")


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return FrozenDict({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


def detached_manifest_sha256(manifest: Mapping[str, object]) -> str:
    """Return the SHA-256 stored in a detached ``manifest.sha256`` sidecar.

    The optional legacy key is omitted from the hashed payload so this hook can
    verify that a digest is never self-referential when inspecting old fixtures.
    Persisted source and normalized manifests do not contain that key.
    """

    payload = {
        key: value for key, value in manifest.items() if key != DETACHED_MANIFEST_DIGEST_FIELD
    }
    return sha256_hex(canonical_json_bytes(payload))


class DomainModel(BaseModel):
    """Strict immutable base for domain values."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Return a revalidated copy whose nested values are frozen again.

        Pydantic's default ``model_copy`` intentionally trusts ``update`` and
        writes it directly into the new instance. Domain models must preserve
        their deep immutability invariant even when callers use that API.
        """

        del deep
        values = self.model_dump(mode="python")
        if update is not None:
            values.update(update)
        return type(self).model_validate(values)

    def model_post_init(self, __context: object) -> None:
        for field_name in type(self).model_fields:
            value = getattr(self, field_name)
            frozen_value = _freeze(value)
            if frozen_value is not value:
                object.__setattr__(self, field_name, frozen_value)


Sha256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ApprovalStatus = Literal["APPROVED_LOCAL", "APPROVED_REDISTRIBUTION"]


class ProvenanceReference(DomainModel):
    """Link a normalized value to an immutable source object."""

    source_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    source_object_id: str = Field(min_length=1)
    raw_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    retrieved_at: AwareDatetime | None = None
    adapter_version: str | None = Field(default=None, min_length=1)
    mapper_version: str | None = Field(default=None, min_length=1)
    approval_status: ApprovalStatus | None = None


class QuarantineReference(DomainModel):
    """Stable pointer to a record withheld from normalized output."""

    quarantine_id: str = Field(min_length=1)
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
    path: str | None = Field(default=None, min_length=1)
    record_locator: str | None = Field(default=None, min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else validate_portable_relative_path(value)


class SourceSnapshotRequest(DomainModel):
    """Sanitized request lineage for a source snapshot."""

    request_id: str = Field(min_length=1)
    sanitized_method: str = Field(min_length=1)
    sanitized_endpoint: URIString
    api_version: str | None = Field(default=None, min_length=1)
    format: str = Field(min_length=1)
    request_body_sha256: Sha256 | None = Field(default=None, exclude_if=lambda value: value is None)
    sanitized_parameters: JSONMapping = Field(default_factory=dict)


class RequestParametersSummary(DomainModel):
    """Deterministic v1-compatible summary derived from request records."""

    request_ids: UniqueTuple[str]
    methods: UniqueTuple[str]
    endpoints: UniqueTuple[URIString]
    formats: UniqueTuple[str]
    api_versions: UniqueTuple[str]
    parameter_keys: UniqueTuple[str]


def derive_request_parameters_summary(
    requests: Sequence[SourceSnapshotRequest],
) -> RequestParametersSummary:
    """Build the only permitted compatibility summary from authoritative requests."""

    return RequestParametersSummary(
        request_ids=tuple(sorted({request.request_id for request in requests})),
        methods=tuple(sorted({request.sanitized_method for request in requests})),
        endpoints=tuple(sorted({request.sanitized_endpoint for request in requests})),
        formats=tuple(sorted({request.format for request in requests})),
        api_versions=tuple(
            sorted({request.api_version for request in requests if request.api_version is not None})
        ),
        parameter_keys=tuple(
            sorted({key for request in requests for key in request.sanitized_parameters})
        ),
    )


class RawObjectReference(DomainModel):
    """Immutable raw object metadata; ``sha256`` covers exact raw bytes."""

    raw_object_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    retrieved_at: AwareDatetime
    path: str = Field(min_length=1)
    bytes: int = Field(ge=0)
    content_type: str | None = None
    content_encoding: ContentEncoding = Field(
        default=None,
        min_length=1,
        exclude_if=lambda value: value is None,
    )
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

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)


class SourceSnapshotManifest(DomainModel):
    """Authoritative v2 source snapshot provenance."""

    schema_version: Literal["source-snapshot-manifest.v2"] = "source-snapshot-manifest.v2"
    source_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    status: Literal["COMPLETE", "INCOMPLETE", "FAILED"]
    approval_status: ApprovalStatus
    adapter_version: str = Field(min_length=1)
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    terms_reference: URIString | None = None
    usage_status: str = Field(min_length=1)
    request_parameters_redacted: RequestParametersSummary
    requests: tuple[SourceSnapshotRequest, ...]
    objects: tuple[RawObjectReference, ...]
    pagination_state: JSONMapping | None = None
    attribution_required: bool
    redistribution_status: Literal["not_approved", "derived_only", "approved"]
    snapshot_content_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_request_lineage(self) -> SourceSnapshotManifest:
        request_ids = [request.request_id for request in self.requests]
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("requests must have unique request_id values")

        known_request_ids = set(request_ids)
        missing_request_ids = {
            raw_object.request_id
            for raw_object in self.objects
            if raw_object.request_id not in known_request_ids
        }
        if missing_request_ids:
            missing = ", ".join(sorted(missing_request_ids))
            raise ValueError(f"objects reference unknown request_id values: {missing}")

        raw_object_ids = [raw_object.raw_object_id for raw_object in self.objects]
        if len(raw_object_ids) != len(set(raw_object_ids)):
            raise ValueError("objects must have unique raw_object_id values")

        expected_summary = derive_request_parameters_summary(self.requests)
        if self.request_parameters_redacted != expected_summary:
            raise ValueError("request_parameters_redacted must equal the derived request summary")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        if self.status == "COMPLETE" and self.completed_at is None:
            raise ValueError("COMPLETE snapshots require completed_at")
        if self.status == "INCOMPLETE" and self.completed_at is not None:
            raise ValueError("INCOMPLETE snapshots cannot have completed_at")
        return self


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
    normalized_artifact_path: str = Field(min_length=1)
    normalized_artifact_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    audit_artifact_path: str = Field(min_length=1)
    audit_artifact_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")
    counts: NonEmptyCounts
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    quarantine_references: tuple[QuarantineReference, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)
    created_at: AwareDatetime
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    normalized_content_sha256: Sha256 = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("normalized_artifact_path", "audit_artifact_path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)

    @field_validator("finding_codes")
    @classmethod
    def validate_finding_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return validate_normalized_finding_codes(value)

    @field_validator("quarantine_references", mode="before")
    @classmethod
    def validate_quarantine_references(cls, value: object) -> tuple[QuarantineReference, ...]:
        return validate_quarantine_references(value)  # type: ignore[return-value]

    @field_validator("provenance")
    @classmethod
    def validate_provenance_order(
        cls, value: tuple[ProvenanceReference, ...]
    ) -> tuple[ProvenanceReference, ...]:
        return validate_provenance_order(value)  # type: ignore[return-value]

    @model_validator(mode="after")
    def validate_provenance_scope(self) -> NormalizedSnapshotManifest:
        for reference in self.provenance:
            if reference.source_id != self.source_id:
                raise ValueError("provenance source_id must match source_id")
            if reference.source_snapshot_id != self.input_source_snapshot_manifest_id:
                raise ValueError(
                    "provenance source_snapshot_id must match input_source_snapshot_manifest_id"
                )
        if self.status in {"COMPLETE", "FAILED"} and self.completed_at is None:
            raise ValueError(f"{self.status} normalized manifests require completed_at")
        if self.status == "INCOMPLETE" and self.completed_at is not None:
            raise ValueError("INCOMPLETE normalized manifests cannot have completed_at")
        if self.started_at > self.created_at:
            raise ValueError("started_at must not follow created_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("normalized completed_at must not precede started_at")
        return self


from .dataset_contracts import (  # noqa: E402, F401
    DatasetExclusion,
    DatasetInputReference,
    DatasetManifest,
    DatasetOutputReference,
)
