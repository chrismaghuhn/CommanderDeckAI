"""Persisted contract for canonicalization outputs derived from staging."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Literal

from pydantic import AwareDatetime, Field, field_validator, model_validator

from commander_ai.domain.path_policy import validate_portable_relative_path
from commander_ai.domain.provenance import DomainModel, ProvenanceReference, QuarantineReference

from ..quality.finding_codes import validate_finding_codes


class CanonicalTableArtifact(DomainModel):
    """Immutable metadata for one canonicalization output table."""

    artifact_name: str = Field(min_length=1)
    artifact_kind: Literal[
        "canonical",
        "audit",
        "resolution",
        "resolution_attempt",
        "provenance",
        "quarantine",
    ]
    layer: Literal["normalized", "audit", "quarantine"]
    schema_version: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rows: int = Field(ge=0, strict=True)
    bytes: int = Field(ge=0, strict=True)

    @field_validator("artifact_name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if "/" in value or "\\" in value:
            raise ValueError("artifact name must be a scalar")
        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)

    @model_validator(mode="after")
    def validate_layer(self) -> CanonicalTableArtifact:
        expected_layer = {
            "canonical": "normalized",
            "audit": "audit",
            "resolution": "audit",
            "resolution_attempt": "audit",
            "provenance": "audit",
            "quarantine": "quarantine",
        }[self.artifact_kind]
        if self.layer != expected_layer:
            raise ValueError("canonical artifact kind and layer disagree")
        return self


class CanonicalSnapshotManifestV1(DomainModel):
    """Identity and provenance for canonical records derived from one normalized snapshot."""

    schema_version: Literal["canonical-snapshot-manifest.v1"] = "canonical-snapshot-manifest.v1"
    canonical_snapshot_id: str = Field(min_length=1)
    producing_run_id: str = Field(min_length=1)
    input_normalized_snapshot_id: str = Field(min_length=1)
    input_normalized_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_id: str = Field(min_length=1)
    status: Literal["COMPLETE", "INCOMPLETE", "FAILED"]
    canonical_schema_version: str = Field(min_length=1)
    mapper_version: str = Field(min_length=1)
    transform_version: str = Field(min_length=1)
    artifacts: tuple[CanonicalTableArtifact, ...] = Field(min_length=6)
    counts: Mapping[str, int]
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    quarantine_references: tuple[QuarantineReference, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)
    created_at: AwareDatetime
    started_at: AwareDatetime
    completed_at: AwareDatetime | None
    canonical_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("counts")
    @classmethod
    def validate_counts(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        if not value or any(
            not isinstance(key, str) or not key or type(count) is not int or count < 0
            for key, count in value.items()
        ):
            raise ValueError("canonical manifest counts must be non-negative integers")
        return dict(sorted(value.items()))

    @field_validator("finding_codes")
    @classmethod
    def validate_findings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = validate_finding_codes(value)
        if len(normalized) != len(set(normalized)):
            raise ValueError("canonical finding codes must be unique")
        return tuple(sorted(normalized))

    @field_validator("quarantine_references", mode="before")
    @classmethod
    def validate_quarantine_order(cls, value: object) -> tuple[QuarantineReference, ...]:
        if not isinstance(value, (tuple, list)):
            raise ValueError("quarantine references must be a sequence")
        references = tuple(QuarantineReference.model_validate(item) for item in value)
        ordered = tuple(
            sorted(
                references,
                key=lambda item: (
                    item.quarantine_id,
                    item.reason_code,
                    item.path or "",
                    item.record_locator or "",
                ),
            )
        )
        if references != ordered or len({item.quarantine_id for item in references}) != len(
            references
        ):
            raise ValueError("quarantine references must be unique and sorted")
        return references

    @model_validator(mode="after")
    def validate_bindings(self) -> CanonicalSnapshotManifestV1:
        if self.status in {"COMPLETE", "FAILED"} and self.completed_at is None:
            raise ValueError(f"{self.status} canonical manifests require completed_at")
        if self.status == "INCOMPLETE" and self.completed_at is not None:
            raise ValueError("INCOMPLETE canonical manifests cannot have completed_at")
        if self.started_at > self.created_at:
            raise ValueError("started_at must not follow created_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")
        kinds = [item.artifact_kind for item in self.artifacts]
        expected_kinds = [
            "audit",
            "canonical",
            "provenance",
            "quarantine",
            "resolution",
            "resolution_attempt",
        ]
        if sorted(kinds) != expected_kinds:
            raise ValueError("canonical manifest requires exactly one artifact of each kind")
        if len({item.path for item in self.artifacts}) != len(self.artifacts):
            raise ValueError("canonical artifact paths must be unique")
        for artifact in self.artifacts:
            key = {
                "canonical": "canonical_records",
                "audit": "audit_records",
                "resolution": "resolution_records",
                "resolution_attempt": "resolution_attempt_records",
                "provenance": "provenance_records",
                "quarantine": "quarantine_records",
            }[artifact.artifact_kind]
            if self.counts.get(key) != artifact.rows:
                raise ValueError(f"count for {key} does not match artifact rows")
        quarantine_artifact = next(
            item for item in self.artifacts if item.artifact_kind == "quarantine"
        )
        if len(self.quarantine_references) != quarantine_artifact.rows:
            raise ValueError("quarantine references must match quarantine rows")
        if any(
            reference.path != quarantine_artifact.path for reference in self.quarantine_references
        ):
            raise ValueError("quarantine references must bind the quarantine artifact")
        for reference in self.provenance:
            if reference.source_id != self.source_id:
                raise ValueError("canonical provenance source mismatch")
        return self


__all__ = ["CanonicalSnapshotManifestV1", "CanonicalTableArtifact"]
