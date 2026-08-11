"""Typed, assessment-only catalog for sources that are not enabled."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .source_settings import SourceApprovalStatus, normalize_source_id

_PERMISSION_GATED_STATUSES = frozenset({SourceApprovalStatus.PAUSED, SourceApprovalStatus.PROPOSED})


class PermissionGatedSource(BaseModel):
    """One source assessment that cannot authorize acquisition."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    source_id: str
    approval_status: SourceApprovalStatus
    reason: str = Field(min_length=1)

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        return normalize_source_id(value)

    @field_validator("approval_status", mode="before")
    @classmethod
    def normalize_status(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper().replace("-", "_")
        return value

    @model_validator(mode="after")
    def remain_permission_gated(self) -> PermissionGatedSource:
        if self.approval_status not in _PERMISSION_GATED_STATUSES:
            raise ValueError("permission-gated sources must remain PROPOSED or PAUSED")
        return self


class PermissionGatedSourceCatalog(BaseModel):
    """Strict mapping of assessment-only sources with fail-closed acquisition."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    sources: tuple[PermissionGatedSource, ...] = Field(default_factory=tuple)

    @model_validator(mode="before")
    @classmethod
    def accept_source_mapping(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = dict(value)
        sources = data.get("sources")
        if isinstance(sources, Mapping):
            entries = []
            for source_id, entry in sources.items():
                if not isinstance(entry, Mapping):
                    raise ValueError("permission-gated source entries must be mappings")
                entry_data = dict(entry)
                entry_data.setdefault("source_id", source_id)
                entries.append(entry_data)
            data["sources"] = entries
        return data

    @model_validator(mode="after")
    def reject_duplicate_ids(self) -> PermissionGatedSourceCatalog:
        source_ids = [source.source_id for source in self.sources]
        if len(source_ids) != len(set(source_ids)):
            raise ValueError("permission-gated source IDs must be unique")
        return self

    def get(self, source_id: str) -> PermissionGatedSource | None:
        normalized = normalize_source_id(source_id)
        return next((source for source in self.sources if source.source_id == normalized), None)

    def status_for(self, source_id: str) -> SourceApprovalStatus:
        source = self.get(source_id)
        if source is None:
            raise KeyError(f"unknown permission-gated source: {normalize_source_id(source_id)}")
        return source.approval_status

    def acquisition_allowed(self, source_id: str) -> bool:
        """Return false for every catalog entry; this catalog never enables acquisition."""

        normalize_source_id(source_id)
        return False
