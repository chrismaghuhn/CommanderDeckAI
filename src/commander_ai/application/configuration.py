"""Application-owned operation references and configuration ports."""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.config.runtime import RuntimeConfig
from commander_ai.config.source_settings import SourceSettings, normalize_source_id
from commander_ai.domain.provenance import validate_portable_relative_path


class OperationConfig(BaseModel):
    """Strict operation references; source and dataset policies are not merged."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["operation.v1"] = "operation.v1"
    operation: PolicyOperation
    source_id: str | None = None
    dataset_id: str | None = Field(default=None, min_length=1)
    runtime_config_path: str | None = None
    source_config_path: str | None = None
    dataset_config_path: str | None = None

    @field_validator("operation", mode="before")
    @classmethod
    def normalize_operation(cls, value: object) -> object:
        return PolicyOperation.normalize(value)

    @field_validator("source_id")
    @classmethod
    def normalize_source(cls, value: str | None) -> str | None:
        return None if value is None else normalize_source_id(value)

    @field_validator("runtime_config_path", "source_config_path", "dataset_config_path")
    @classmethod
    def validate_config_path(cls, value: str | None) -> str | None:
        return None if value is None else validate_portable_relative_path(value)

    @model_validator(mode="after")
    def require_operation_references(self) -> OperationConfig:
        source_operations = {
            PolicyOperation.SOURCE_SYNC,
            PolicyOperation.NORMALIZE,
            PolicyOperation.VALIDATE,
            PolicyOperation.REPORT,
            PolicyOperation.PUBLIC_EXPORT,
        }
        if self.operation in source_operations and self.source_id is None:
            raise ValueError("source_id is required for this operation")
        if self.operation is PolicyOperation.DATASET_BUILD and self.dataset_id is None:
            raise ValueError("dataset_id is required for dataset_build")
        return self


class ResolvedConfiguration(BaseModel):
    """Explicitly nested resolved config; no cross-domain field override is possible."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    runtime: RuntimeConfig
    operation: OperationConfig
    source: SourceSettings | None = None
    dataset: DatasetSettings | None = None

    @model_validator(mode="after")
    def validate_references(self) -> ResolvedConfiguration:
        if self.operation.source_id is not None:
            if self.source is None:
                raise ValueError("operation source_id requires an explicit source config")
            if self.source.source_id != self.operation.source_id:
                raise ValueError("operation source_id does not match source config")
        if self.operation.dataset_id is not None:
            if self.dataset is None:
                raise ValueError("operation dataset_id requires an explicit dataset config")
            if self.dataset.dataset_id != self.operation.dataset_id:
                raise ValueError("operation dataset_id does not match dataset config")
        return self


@runtime_checkable
class ConfigurationPort(Protocol):
    """Application port for already-typed, already-resolved configuration."""

    def resolve(self, operation: OperationConfig) -> ResolvedConfiguration:
        """Resolve an operation without defining how YAML or files are loaded."""


ConfigurationProvider = ConfigurationPort
