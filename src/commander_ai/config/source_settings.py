"""Typed, source-owned access and filtering configuration."""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.domain.provenance import validate_portable_relative_path

_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]{1,127}$")
_SOURCE_ID = re.compile(r"^[a-z0-9]+(?:[_-][a-z0-9]+)*$")
_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|authorization|cookie|credential|password|secret|token)",
    re.IGNORECASE,
)


def is_credential_key(value: object) -> bool:
    """Return whether a configuration key names a credential-like value."""

    return _SECRET_KEY.search(str(value)) is not None


def is_environment_name(value: object) -> bool:
    """Return whether a value is a valid environment-variable name."""

    return isinstance(value, str) and _ENVIRONMENT_NAME.fullmatch(value.strip().upper()) is not None


def _reject_nested_credential_keys(
    value: object, *, field_name: str, seen: set[int] | None = None
) -> None:
    if not isinstance(value, (Mapping, list, tuple, set, frozenset)):
        return
    visited = seen if seen is not None else set()
    marker = id(value)
    if marker in visited:
        return
    visited.add(marker)

    if isinstance(value, Mapping):
        for key, item in value.items():
            if is_credential_key(key):
                raise ValueError(f"{field_name} cannot contain credential fields")
            _reject_nested_credential_keys(item, field_name=field_name, seen=visited)
        return

    for item in value:
        _reject_nested_credential_keys(item, field_name=field_name, seen=visited)


class SourceApprovalStatus(StrEnum):
    """Historical acquisition/redistribution status from a source review."""

    PROPOSED = "PROPOSED"
    REVIEWED = "REVIEWED"
    APPROVED_LOCAL = "APPROVED_LOCAL"
    APPROVED_REDISTRIBUTION = "APPROVED_REDISTRIBUTION"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"


def normalize_source_id(value: str) -> str:
    """Normalize a source identifier without accepting path or host syntax."""

    if not isinstance(value, str):
        raise ValueError("source_id must be a string")
    normalized = value.strip().casefold().replace("-", "_")
    if not _SOURCE_ID.fullmatch(normalized.replace("_", "-")):
        raise ValueError("source_id must contain only letters, digits, '_' or '-'")
    return normalized


def _normalize_status(value: object) -> object:
    if not isinstance(value, str):
        return value
    return value.strip().upper().replace("-", "_")


def _merge_legacy_field(
    data: dict[str, object], canonical: str, legacy_value: object, *, source: str
) -> None:
    if canonical in data and data[canonical] != legacy_value:
        raise ValueError(f"{source} conflicts with {canonical}")
    data.setdefault(canonical, legacy_value)


def _legacy_mapping(
    data: dict[str, object], name: str, allowed: set[str]
) -> dict[str, object] | None:
    value = data.pop(name, None)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    unknown = set(value) - allowed
    if unknown:
        raise ValueError(f"{name} contains unknown fields")
    return {str(key): item for key, item in value.items()}


class SourceSettings(BaseModel):
    """Configuration for one source; secrets are represented only by env names."""

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    source_id: str
    approval_status: SourceApprovalStatus
    access_method: str = Field(default="configured", min_length=1)
    review_path: str | None = Field(default=None, min_length=1)
    endpoints: tuple[str, ...] = Field(default_factory=tuple)
    host_allowlist: tuple[str, ...] = Field(default_factory=tuple)
    api_key_env: str | None = None
    credential_env_vars: tuple[str, ...] = Field(default_factory=tuple)
    user_agent_env: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    max_retries: int = Field(default=2, ge=0, le=8)
    rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)
    respect_retry_after: bool = True
    max_pages: int = Field(default=100, ge=1, le=100_000)
    max_download_bytes: int = Field(default=2_000_000_000, ge=1, le=20_000_000_000)
    attribution_required: bool = False
    raw_storage: str = Field(default="unknown", min_length=1)
    redistribution: str = Field(default="not_approved", min_length=1)
    filters: Mapping[str, Any] = Field(default_factory=dict)
    files: tuple[str, ...] = Field(default_factory=tuple)
    bulk_type: str | None = Field(default=None, min_length=1)
    features: Mapping[str, bool] = Field(default_factory=dict)
    api_status: str | None = Field(default=None, min_length=1)
    sync_policy: str = Field(default="explicit", min_length=1)

    @model_validator(mode="before")
    @classmethod
    def normalize_legacy_shapes(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = {str(key): item for key, item in value.items()}
        if "source_id" in data:
            source_id = data["source_id"]
            if not isinstance(source_id, str):
                raise ValueError("source_id must be a string")
            data["source_id"] = normalize_source_id(source_id)
        if "approval_status" in data:
            data["approval_status"] = _normalize_status(data["approval_status"])

        http = _legacy_mapping(
            data,
            "http",
            {"timeout_seconds", "max_download_bytes", "max_pages", "user_agent_env"},
        )
        if http is not None:
            for field_name in (
                "timeout_seconds",
                "max_download_bytes",
                "max_pages",
                "user_agent_env",
            ):
                if field_name in http:
                    _merge_legacy_field(
                        data, field_name, http[field_name], source=f"http.{field_name}"
                    )

        rate_limit = _legacy_mapping(
            data,
            "rate_limit",
            {"requests_per_minute", "respect_retry_after", "max_retries"},
        )
        if rate_limit is not None:
            aliases = {
                "requests_per_minute": "rate_limit_per_minute",
                "respect_retry_after": "respect_retry_after",
                "max_retries": "max_retries",
            }
            for old_name, new_name in aliases.items():
                if old_name in rate_limit:
                    _merge_legacy_field(
                        data, new_name, rate_limit[old_name], source=f"rate_limit.{old_name}"
                    )

        for old_name, new_name in (("allowed_hosts", "host_allowlist"), ("base_urls", "endpoints")):
            if old_name in data:
                _merge_legacy_field(data, new_name, data.pop(old_name), source=old_name)
        return data

    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, value: str) -> str:
        return normalize_source_id(value)

    @field_validator("approval_status", mode="before")
    @classmethod
    def validate_approval_status(cls, value: object) -> object:
        return _normalize_status(value)

    @field_validator("review_path")
    @classmethod
    def validate_review_path(cls, value: str | None) -> str | None:
        return None if value is None else validate_portable_relative_path(value)

    @field_validator("host_allowlist", mode="before")
    @classmethod
    def normalize_hosts(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list, set, frozenset)):
            raise ValueError("host_allowlist must be a sequence")
        hosts: list[str] = []
        for host in value:
            if not isinstance(host, str):
                raise ValueError("host_allowlist entries must be strings")
            normalized = host.strip().casefold().rstrip(".")
            if not normalized or "/" in normalized or ":" in normalized or "*" in normalized:
                raise ValueError("host_allowlist entries must be host names")
            hosts.append(normalized)
        return tuple(dict.fromkeys(hosts))

    @field_validator("endpoints")
    @classmethod
    def validate_endpoints(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized: list[str] = []
        for endpoint in value:
            parsed = urlsplit(endpoint)
            if parsed.scheme not in {"http", "https"} or parsed.hostname is None:
                raise ValueError("endpoints must be absolute http(s) URLs")
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                raise ValueError("endpoints must not contain credentials, query, or fragment data")
            normalized.append(endpoint.rstrip("/"))
        return tuple(dict.fromkeys(normalized))

    @field_validator("api_key_env", "user_agent_env")
    @classmethod
    def validate_environment_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not is_environment_name(normalized):
            raise ValueError("credential fields must contain environment-variable names")
        return normalized

    @field_validator("credential_env_vars", mode="before")
    @classmethod
    def validate_environment_names(cls, value: object) -> object:
        if value is None:
            return ()
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list, set, frozenset)):
            raise ValueError("credential_env_vars must be a sequence")
        normalized = []
        for item in value:
            if not is_environment_name(item):
                raise ValueError("credential fields must contain environment-variable names")
            normalized.append(item.strip().upper())
        return tuple(dict.fromkeys(normalized))

    @field_validator("filters", "features")
    @classmethod
    def validate_credential_free_mappings(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        _reject_nested_credential_keys(value, field_name="source configuration mappings")
        return value

    @model_validator(mode="after")
    def validate_endpoint_policy(self) -> SourceSettings:
        if self.endpoints and not self.host_allowlist:
            raise ValueError("endpoints require an explicit host_allowlist")
        allowlisted = set(self.host_allowlist)
        for endpoint in self.endpoints:
            hostname = urlsplit(endpoint).hostname
            if hostname is None or hostname.casefold().rstrip(".") not in allowlisted:
                raise ValueError("every endpoint host must be explicitly allowlisted")
        return self


SourceConfig = SourceSettings
