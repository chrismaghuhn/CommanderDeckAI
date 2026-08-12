"""Versioned normalized-snapshot artifact bindings and semantic value objects."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from commander_ai.domain.path_policy import validate_portable_relative_path
from commander_ai.domain.provenance import (
    DomainModel,
    ProvenanceReference,
    QuarantineReference,
)

from ..quality.finding_codes import validate_finding_codes


class NormalizedTableArtifact(DomainModel):
    """Immutable byte, path, layer, and row metadata for one Parquet table."""

    table_name: str = Field(min_length=1)
    layer: Literal["normalized", "audit", "quarantine"]
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    rows: int = Field(ge=0, strict=True)
    bytes: int = Field(ge=0, strict=True)

    @field_validator("table_name")
    @classmethod
    def validate_table_name(cls, value: str) -> str:
        if not value.strip() or "/" in value or "\\" in value:
            raise ValueError("table name must be a portable scalar name")
        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)


class NormalizedSnapshotManifestV2(DomainModel):
    """Closed v2 extension that binds every normalized-layer artifact explicitly."""

    schema_version: Literal["normalized-snapshot-manifest.v2"] = "normalized-snapshot-manifest.v2"
    normalized_snapshot_id: str = Field(min_length=1)
    producing_run_id: str = Field(min_length=1)
    input_source_snapshot_manifest_id: str = Field(min_length=1)
    input_source_snapshot_manifest_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_id: str = Field(min_length=1)
    status: Literal["COMPLETE", "INCOMPLETE", "FAILED"]
    normalized_schema_version: str = Field(min_length=1)
    mapper_version: str = Field(min_length=1)
    transform_version: str = Field(min_length=1)
    policy_version: str = Field(min_length=1)
    normalized_artifact_path: str = Field(min_length=1)
    normalized_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    audit_artifact_path: str = Field(min_length=1)
    audit_artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    artifacts: tuple[NormalizedTableArtifact, ...] = Field(min_length=3)
    counts: Mapping[str, int]
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    quarantine_references: tuple[QuarantineReference, ...] = Field(default_factory=tuple)
    provenance: tuple[ProvenanceReference, ...] = Field(min_length=1)
    created_at: datetime
    started_at: datetime
    completed_at: datetime | None
    normalized_content_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("normalized_artifact_path", "audit_artifact_path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)

    @field_validator("created_at", "started_at", "completed_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("normalized manifest timestamps must include a timezone")
        return value

    @field_validator("counts")
    @classmethod
    def validate_counts(cls, value: Mapping[str, int]) -> Mapping[str, int]:
        if not value or any(
            not isinstance(key, str) or not key or type(count) is not int or count < 0
            for key, count in value.items()
        ):
            raise ValueError("normalized manifest counts must be non-negative integers")
        return dict(sorted(value.items()))

    @field_validator("finding_codes")
    @classmethod
    def validate_findings(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        findings = validate_finding_codes(value)
        if len(findings) != len(set(findings)):
            raise ValueError("normalized finding codes must be unique")
        return tuple(sorted(findings))

    @field_validator("quarantine_references", mode="before")
    @classmethod
    def validate_quarantine_order(cls, value: object) -> tuple[QuarantineReference, ...]:
        if not isinstance(value, (tuple, list)):
            raise ValueError("quarantine references must be a sequence")
        references = tuple(QuarantineReference.model_validate(item) for item in value)
        if len({item.quarantine_id for item in references}) != len(references):
            raise ValueError("quarantine references must be unique")
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
        if references != ordered:
            raise ValueError("quarantine references must be sorted")
        return references

    @model_validator(mode="after")
    def validate_bindings(self) -> NormalizedSnapshotManifestV2:
        if self.status in {"COMPLETE", "FAILED"} and self.completed_at is None:
            raise ValueError(f"{self.status} normalized manifests require completed_at")
        if self.status == "INCOMPLETE" and self.completed_at is not None:
            raise ValueError("INCOMPLETE normalized manifests cannot have completed_at")
        if self.started_at > self.created_at:
            raise ValueError("started_at must not follow created_at")
        if self.completed_at is not None and self.completed_at < self.started_at:
            raise ValueError("completed_at must not precede started_at")

        layers = [artifact.layer for artifact in self.artifacts]
        if sorted(layers) != ["audit", "normalized", "quarantine"]:
            raise ValueError("normalized manifest requires exactly one artifact per layer")
        identities = [(item.layer, item.table_name, item.path) for item in self.artifacts]
        if len(identities) != len(set(identities)):
            raise ValueError("normalized artifact bindings must be unique")
        normalized = _artifact_for_layer(self.artifacts, "normalized")
        audit = _artifact_for_layer(self.artifacts, "audit")
        if (self.normalized_artifact_path, self.normalized_artifact_sha256) != (
            normalized.path,
            normalized.sha256,
        ):
            raise ValueError("normalized artifact binding mismatch")
        if (self.audit_artifact_path, self.audit_artifact_sha256) != (
            audit.path,
            audit.sha256,
        ):
            raise ValueError("audit artifact binding mismatch")
        for artifact in self.artifacts:
            count_key = f"{artifact.layer}_records"
            if self.counts.get(count_key) != artifact.rows:
                raise ValueError(f"count for {count_key} does not match artifact rows")
        quarantine_path = _artifact_for_layer(self.artifacts, "quarantine").path
        quarantine_ids = [reference.quarantine_id for reference in self.quarantine_references]
        if len(quarantine_ids) != len(set(quarantine_ids)):
            raise ValueError("quarantine references must be unique")
        for quarantine_reference in self.quarantine_references:
            if quarantine_reference.path is None or quarantine_reference.path != quarantine_path:
                raise ValueError("quarantine references must bind the quarantine artifact")
        for provenance_reference in self.provenance:
            if provenance_reference.source_id != self.source_id:
                raise ValueError("provenance source_id must match source_id")
            if provenance_reference.source_snapshot_id != self.input_source_snapshot_manifest_id:
                raise ValueError(
                    "provenance source_snapshot_id must match input_source_snapshot_manifest_id"
                )
        return self


def _artifact_for_layer(
    artifacts: tuple[NormalizedTableArtifact, ...],
    layer: Literal["normalized", "audit", "quarantine"],
) -> NormalizedTableArtifact:
    matches = [artifact for artifact in artifacts if artifact.layer == layer]
    if len(matches) != 1:
        raise ValueError(f"missing or duplicate {layer} artifact")
    return matches[0]


__all__ = ["NormalizedSnapshotManifestV2", "NormalizedTableArtifact"]
