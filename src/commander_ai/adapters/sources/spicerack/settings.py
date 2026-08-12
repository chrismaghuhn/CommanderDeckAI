"""Source-owned settings for the documented Spicerack read contract."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Literal, cast
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.config.source_settings import SourceSettings

SPICERACK_SOURCE_ID = "spicerack"
SPICERACK_API_PATH = "/api/export-decklists/"
SPICERACK_RESPONSE_FORMATS = ("json", "ndjson")
SPICERACK_FORMATS = frozenset({"COMMANDER2", "PAUPER_COMMANDER", "DUEL"})
_HEADER = re.compile(r"^[A-Za-z][A-Za-z0-9-]{0,63}$")


class SpicerackSettings(BaseModel):
    """Strict adapter view; credential values are never part of this model."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SourceSettings
    api_path: str = Field(min_length=1)
    credential_header: str = Field(default="X-API-Key", min_length=1)
    response_format: Literal["json", "ndjson"] = "json"
    adapter_version: str = Field(default="spicerack-v1", min_length=1)
    formats: tuple[str, ...] = Field(min_length=1)
    num_days: int = Field(default=14, ge=1, le=3650)
    organization_id: int | None = Field(default=None, ge=1)
    decklist_as_text: bool = True

    @field_validator("api_path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        normalized = value if value.endswith("/") else f"{value}/"
        if normalized != SPICERACK_API_PATH:
            raise ValueError("Spicerack api_path must match the reviewed export endpoint")
        return SPICERACK_API_PATH

    @field_validator("credential_header")
    @classmethod
    def validate_header(cls, value: str) -> str:
        if _HEADER.fullmatch(value) is None or value.casefold() in {"authorization", "cookie"}:
            raise ValueError("Spicerack credential_header is not an approved header")
        return value

    @field_validator("formats", mode="before")
    @classmethod
    def normalize_formats(cls, value: object) -> object:
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list, set, frozenset)):
            raise ValueError("Spicerack formats must be a sequence")
        values = tuple(
            str(item).strip().upper() if isinstance(item, str) else item for item in value
        )
        if not values or any(not isinstance(item, str) or not item for item in values):
            raise ValueError("Spicerack formats must contain non-empty strings")
        if len(values) != len(set(values)) or any(item not in SPICERACK_FORMATS for item in values):
            raise ValueError("Spicerack format is not documented")
        return tuple(sorted(values))

    @model_validator(mode="after")
    def validate_source(self) -> SpicerackSettings:
        source = self.source
        if source.source_id != SPICERACK_SOURCE_ID:
            raise ValueError("Spicerack settings require source_id spicerack")
        if source.api_key_env is None:
            raise ValueError("Spicerack settings require api_key_env")
        if source.credential_env_vars:
            raise ValueError("Spicerack uses one configured api_key_env")
        if source.host_allowlist != ("api.spicerack.gg",):
            raise ValueError("Spicerack settings require the reviewed host allowlist")
        if not source.endpoints:
            raise ValueError("Spicerack settings require a configured endpoint")
        endpoint = urlsplit(source.endpoints[0])
        if (
            endpoint.scheme != "https"
            or endpoint.hostname != "api.spicerack.gg"
            or endpoint.path not in {"", "/"}
            or endpoint.port is not None
            or endpoint.username is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
        ):
            raise ValueError("Spicerack settings require the reviewed HTTPS endpoint")
        return self

    @classmethod
    def from_source_settings(
        cls,
        source: SourceSettings,
        *,
        api_path: str = SPICERACK_API_PATH,
        credential_header: str = "X-API-Key",
        response_format: Literal["json", "ndjson"] = "json",
        adapter_version: str = "spicerack-v1",
    ) -> SpicerackSettings:
        filters: Mapping[str, object] = source.filters
        unknown = set(filters) - {"formats", "num_days", "organization_id", "decklist_as_text"}
        if unknown:
            raise ValueError("unknown Spicerack filter fields")
        formats = cast(tuple[str, ...], filters.get("formats", ("COMMANDER2",)))
        num_days = cast(int, filters.get("num_days", 14))
        organization_id = cast(int | None, filters.get("organization_id"))
        decklist_as_text = cast(bool, filters.get("decklist_as_text", True))
        return cls(
            source=source,
            api_path=api_path,
            credential_header=credential_header,
            response_format=response_format,
            adapter_version=adapter_version,
            formats=formats,
            num_days=num_days,
            organization_id=organization_id,
            decklist_as_text=decklist_as_text,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.source.endpoints[0].rstrip('/')}{self.api_path}"

    @property
    def api_key_env(self) -> str:
        if self.source.api_key_env is None:
            raise ValueError("Spicerack settings require api_key_env")
        return self.source.api_key_env

    @property
    def max_pages(self) -> int:
        return self.source.max_pages

    @property
    def max_response_bytes(self) -> int:
        return self.source.max_download_bytes

    def request_parameter_sets(self) -> tuple[dict[str, object], ...]:
        return tuple(self.request_parameters(selected_format=selected) for selected in self.formats)

    def request_parameters(self, *, selected_format: str | None = None) -> dict[str, object]:
        if selected_format is None:
            if len(self.formats) != 1:
                raise ValueError("Spicerack settings contain multiple format request bodies")
            selected_format = self.formats[0]
        if selected_format not in self.formats:
            raise ValueError("Spicerack format is not configured")
        parameters: dict[str, object] = {
            "num_days": self.num_days,
            "event_format": selected_format,
            "decklist_as_text": self.decklist_as_text,
        }
        if self.organization_id is not None:
            parameters["organization_id"] = self.organization_id
        return parameters


__all__ = [
    "SPICERACK_API_PATH",
    "SPICERACK_FORMATS",
    "SPICERACK_SOURCE_ID",
    "SpicerackSettings",
]
