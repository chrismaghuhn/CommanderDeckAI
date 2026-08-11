"""Versioned dataset input, output, exclusion, and manifest contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, field_validator

from .contract_validation import (
    JSONMapping,
    NonEmptyString,
    NonNegativeCounts,
    NonNegativeInt,
    UniqueTuple,
)
from .path_policy import validate_portable_relative_path
from .provenance import DomainModel

Sha256String = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


class DatasetInputReference(DomainModel):
    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    path: str | None = Field(default=None, min_length=1)
    sha256: Sha256String

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else validate_portable_relative_path(value)


class DatasetOutputReference(DomainModel):
    name: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: Sha256String
    rows: int = Field(ge=0)
    bytes: int | None = Field(default=None, ge=0)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)


class DatasetExclusion(DomainModel):
    code: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")
    count: int = Field(ge=0)
    references: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)


class DatasetManifest(DomainModel):
    schema_version: Literal["dataset-manifest.v2"] = "dataset-manifest.v2"
    dataset_id: str = Field(min_length=1)
    dataset_kind: Literal[
        "deck_completion",
        "tournament_outcomes",
        "card_cooccurrence",
        "combo",
        "unknown",
    ] = "unknown"
    config_version: str = Field(default="dataset-config.v1", min_length=1)
    producing_run_id: str | None = Field(default=None, min_length=1)
    created_at: AwareDatetime
    builder_version: str = Field(min_length=1)
    code_commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    dependency_lock_hash: Sha256String
    input_manifests: UniqueTuple[DatasetInputReference] = Field(min_length=1)
    schema_versions: UniqueTuple[NonEmptyString] = Field(min_length=1)
    transform_versions: UniqueTuple[NonEmptyString] = Field(min_length=1)
    policy_versions: UniqueTuple[NonEmptyString] = Field(min_length=1)
    ruleset_versions: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    card_snapshot_ids: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    source_snapshots: UniqueTuple[NonEmptyString] = Field(default_factory=tuple)
    filters: JSONMapping = Field(default_factory=dict)
    split_policy: JSONMapping = Field(default_factory=dict)
    split_policy_version: str = Field(default="unspecified", min_length=1)
    near_duplicate_algorithm: str | None = Field(default=None, min_length=1)
    near_duplicate_version: str | None = Field(default=None, min_length=1)
    near_duplicate_threshold: float | None = Field(default=None, ge=0, le=1)
    exclusion_policy_version: str = Field(default="unspecified", min_length=1)
    exclusions: tuple[DatasetExclusion, ...] = Field(default_factory=tuple)
    counts: NonNegativeCounts
    outputs: UniqueTuple[DatasetOutputReference] = Field(min_length=1)
    quality_report: DatasetOutputReference | None = None
    leakage_report: DatasetOutputReference | None = None
    random_seeds: UniqueTuple[NonNegativeInt] = Field(default_factory=tuple)
    redistribution_status: Literal["local_only", "derived_only", "redistributable"] = "local_only"
    dataset_content_sha256: Sha256String
    manifest_sha256: Sha256String


__all__ = [
    "DatasetExclusion",
    "DatasetInputReference",
    "DatasetManifest",
    "DatasetOutputReference",
]
