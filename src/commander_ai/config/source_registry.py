"""In-memory source registry with separate historical and current-use records."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.domain.provenance import validate_portable_relative_path

from .current_use_policy import CurrentUseDecision
from .source_settings import SourceApprovalStatus, SourceSettings, normalize_source_id


class HistoricalApprovalMetadata(BaseModel):
    """Evidence about what was approved when an acquisition was made."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    source_id: str
    approval_status: SourceApprovalStatus
    review_path: str = Field(min_length=1)
    reviewed_at: datetime
    effective_at: datetime
    reason: str = Field(min_length=1)
    official_docs: tuple[str, ...] = Field(default_factory=tuple)
    terms_reference: str | None = Field(default=None, min_length=1)
    attribution_required: bool | None = None
    raw_local_storage: str | None = Field(default=None, min_length=1)
    normalized_local_storage: str | None = Field(default=None, min_length=1)
    redistribution_raw: str | None = Field(default=None, min_length=1)
    redistribution_derived: str | None = Field(default=None, min_length=1)

    @field_validator("source_id")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return normalize_source_id(value)

    @field_validator("approval_status", mode="before")
    @classmethod
    def normalize_status(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper().replace("-", "_")
        return value

    @field_validator("review_path")
    @classmethod
    def validate_review_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)


class SourceRegistryEntry(BaseModel):
    """One source config plus independent historical and current-use metadata."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    source_id: str
    settings: SourceSettings
    historical_approval: HistoricalApprovalMetadata
    current_use: CurrentUseDecision | None = None

    @field_validator("source_id")
    @classmethod
    def validate_source(cls, value: str) -> str:
        return normalize_source_id(value)

    @model_validator(mode="after")
    def validate_ownership(self) -> SourceRegistryEntry:
        if self.settings.source_id != self.source_id:
            raise ValueError("source registry source_id does not match source settings")
        if self.historical_approval.source_id != self.source_id:
            raise ValueError("source registry source_id does not match historical approval")
        if self.current_use is not None and self.current_use.source_id != self.source_id:
            raise ValueError("source registry source_id does not match current-use decision")
        if self.settings.approval_status is not self.historical_approval.approval_status:
            raise ValueError("source settings and historical approval status must match")
        return self


class SourceRegistry(BaseModel):
    """Strict source lookup with normalized identifiers and no implicit fallback."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    entries: tuple[SourceRegistryEntry, ...] = Field(default_factory=tuple)

    @model_validator(mode="before")
    @classmethod
    def accept_entry_mapping(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        entries = data.get("entries")
        if isinstance(entries, Mapping):
            converted = []
            for source_id, entry in entries.items():
                if not isinstance(entry, Mapping):
                    raise ValueError("source registry entries must be mappings")
                entry_data = dict(entry)
                entry_data.setdefault("source_id", source_id)
                converted.append(entry_data)
            data["entries"] = converted
        return data

    @model_validator(mode="after")
    def reject_duplicate_ids(self) -> SourceRegistry:
        source_ids = [entry.source_id for entry in self.entries]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("source registry source IDs must be unique")
        return self

    def lookup(self, source_id: str) -> SourceRegistryEntry:
        normalized = normalize_source_id(source_id)
        for entry in self.entries:
            if entry.source_id == normalized:
                return entry
        raise KeyError(f"unknown source: {normalized}")

    def get(self, source_id: str) -> SourceRegistryEntry | None:
        try:
            return self.lookup(source_id)
        except KeyError:
            return None
