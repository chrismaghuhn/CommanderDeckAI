"""TopDeck-specific settings for the documented Tournaments v2 contract."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.config.source_settings import SourceSettings
from commander_ai.domain.contract_validation import validate_json_value

TOPDECK_SOURCE_ID = "topdeck"
TOPDECK_API_VERSION = "v2"
TOPDECK_API_PATH = "/api/v2/tournaments"
TOPDECK_FILTER_FIELDS = frozenset(
    {
        "TID",
        "game",
        "format",
        "formats",
        "start",
        "end",
        "last",
        "participantMin",
        "participantMax",
        "columns",
        "rounds",
        "tables",
        "players",
    }
)
_BOOLEAN_FIELDS = frozenset({"rounds", "tables", "players"})
_INTEGER_FIELDS = frozenset({"last", "participantMin", "participantMax"})


class TopDeckSettings(BaseModel):
    """Immutable adapter configuration without the credential value itself."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SourceSettings
    api_version: str = Field(default=TOPDECK_API_VERSION, min_length=1)
    api_path: str = Field(default=TOPDECK_API_PATH, min_length=1)
    filters: Mapping[str, Any] = Field(default_factory=dict)
    adapter_version: str = Field(default="topdeck-v1", min_length=1)

    @field_validator("filters")
    @classmethod
    def validate_filters(cls, value: Mapping[str, Any]) -> Mapping[str, Any]:
        unknown = set(value) - TOPDECK_FILTER_FIELDS
        if unknown:
            raise ValueError("unknown TopDeck filter fields")
        normalized = dict(value)
        for key, item in normalized.items():
            validate_json_value(item)
            if key in {"game", "format", "start", "end"}:
                _require_text(item, key)
            elif key == "TID":
                normalized[key] = _normalize_ids(item)
            elif key == "formats":
                normalized[key] = _normalize_formats(item)
            elif key in _INTEGER_FIELDS:
                _require_integer(item, key, maximum=100_000)
            elif key in _BOOLEAN_FIELDS:
                if type(item) is not bool:
                    raise ValueError(f"TopDeck {key} must be a boolean")
            elif key == "columns":
                normalized[key] = _normalize_columns(item)
        return normalized

    @model_validator(mode="after")
    def validate_source_contract(self) -> TopDeckSettings:
        source = self.source
        if source.source_id != TOPDECK_SOURCE_ID:
            raise ValueError("TopDeck settings require source_id topdeck")
        if source.api_key_env is None:
            raise ValueError("TopDeck settings require api_key_env")
        if source.credential_env_vars:
            raise ValueError("TopDeck uses api_key_env for its documented credential")
        if source.host_allowlist != ("topdeck.gg",):
            raise ValueError("TopDeck settings require the documented host allowlist")
        if not source.endpoints:
            raise ValueError("TopDeck settings require a configured API base endpoint")
        endpoint = urlsplit(source.endpoints[0])
        if endpoint.scheme != "https" or endpoint.hostname != "topdeck.gg":
            raise ValueError("TopDeck settings require the documented HTTPS endpoint")
        if self.api_version != TOPDECK_API_VERSION or self.api_path != TOPDECK_API_PATH:
            raise ValueError("TopDeck settings require the documented Tournaments v2 endpoint")
        fields = set(self.filters)
        if "TID" in fields:
            if fields != {"TID"}:
                raise ValueError("TopDeck TID requests cannot mix query filters")
            return self
        if "game" not in fields:
            raise ValueError("TopDeck query requests require a game filter")
        if "format" in fields and "formats" in fields:
            raise ValueError("TopDeck requests cannot define format and formats together")
        if "format" not in fields and "formats" not in fields:
            raise ValueError("TopDeck query requests require a format filter")
        start = self.filters.get("start")
        end = self.filters.get("end")
        if (
            start is not None
            and end is not None
            and date.fromisoformat(start) > date.fromisoformat(end)
        ):
            raise ValueError("TopDeck start must not follow end")
        return self

    @classmethod
    def from_source_settings(
        cls,
        source: SourceSettings,
        *,
        adapter_version: str = "topdeck-v1",
    ) -> TopDeckSettings:
        """Create the source-owned view and reject undocumented filter fields."""

        return cls(
            source=source,
            filters=dict(source.filters),
            adapter_version=adapter_version,
        )

    @property
    def endpoint(self) -> str:
        return f"{self.source.endpoints[0].rstrip('/')}{self.api_path}"

    @property
    def api_key_env(self) -> str:
        if self.source.api_key_env is None:
            raise ValueError("TopDeck settings require api_key_env")
        return self.source.api_key_env

    @property
    def max_response_bytes(self) -> int:
        return self.source.max_download_bytes

    def request_parameter_sets(self) -> tuple[dict[str, object], ...]:
        """Expand source format filters into deterministic singular-format bodies."""

        if "TID" in self.filters:
            return ({"TID": self.filters["TID"]},)
        base = {
            str(key): value
            for key, value in sorted(self.filters.items(), key=lambda item: item[0])
            if key not in {"format", "formats"}
        }
        formats = self.filters.get("formats")
        selected = (self.filters["format"],) if formats is None else tuple(formats)
        return tuple({**base, "format": format_value} for format_value in selected)

    def request_parameters(self, *, format_value: str | None = None) -> dict[str, object]:
        """Return one canonical JSON request body, never an array-format shortcut."""

        parameter_sets = self.request_parameter_sets()
        if format_value is not None:
            for parameters in parameter_sets:
                if parameters.get("format") == format_value:
                    return parameters
            raise ValueError("TopDeck format is not configured")
        if len(parameter_sets) != 1:
            raise ValueError("TopDeck settings contain multiple format request bodies")
        return parameter_sets[0]


def _require_text(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"TopDeck {field_name} must be a non-empty string")
    if field_name in {"start", "end"}:
        try:
            date.fromisoformat(value)
        except ValueError:
            raise ValueError(f"TopDeck {field_name} must be an ISO date") from None


def _require_integer(value: object, field_name: str, *, maximum: int) -> None:
    if type(value) is not int or value < 0 or value > maximum:
        raise ValueError(f"TopDeck {field_name} must be a bounded non-negative integer")


def _normalize_ids(value: object) -> object:
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (tuple, list, set, frozenset)):
        values = tuple(value)
    else:
        raise ValueError("TopDeck TID must be a string or sequence of strings")
    if not values or any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError("TopDeck TID values must be non-empty strings")
    if len(values) != len(set(values)) or len(values) > 1_000:
        raise ValueError("TopDeck TID values must be unique and bounded")
    return tuple(sorted(values))


def _normalize_formats(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (tuple, list, set, frozenset)):
        values = tuple(value)
    else:
        raise ValueError("TopDeck formats must be a sequence of strings")
    if not values or any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError("TopDeck formats must be non-empty strings")
    if len(values) != len(set(values)) or len(values) > 32:
        raise ValueError("TopDeck formats must be unique and bounded")
    return tuple(sorted(values))


def _normalize_columns(value: object) -> object:
    if isinstance(value, bool):
        return value
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise ValueError("TopDeck columns must be a boolean or sequence of strings")
    values = tuple(value)
    if not values or any(not isinstance(item, str) or not item.strip() for item in values):
        raise ValueError("TopDeck columns must contain non-empty strings")
    if len(values) != len(set(values)) or len(values) > 64:
        raise ValueError("TopDeck columns must be unique and bounded")
    return tuple(sorted(values))


__all__ = [
    "TOPDECK_API_PATH",
    "TOPDECK_API_VERSION",
    "TOPDECK_FILTER_FIELDS",
    "TOPDECK_SOURCE_ID",
    "TopDeckSettings",
]
