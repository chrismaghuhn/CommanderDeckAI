"""Offline-safe YAML loading and secret-free configuration serialization."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError

from .dataset_settings import DatasetSettings
from .runtime import RuntimeConfig
from .source_settings import SourceSettings, is_credential_key

if TYPE_CHECKING:
    from commander_ai.application.configuration import OperationConfig

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|cookie|password|secret|token)"
    r"(\s*[:=]\s*)([^,\s;}]+)"
)
_AUTHORIZATION_VALUE = re.compile(
    r"(?i)((?:authorization|proxy-authorization)(?:\s*[:=])\s*)"
    r"(?:bearer|basic)\s+[^,\s;}]+"
)
_SECRET_QUERY_PARAMETER = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|authorization|cookie|password|secret|token)=)"
    r"[^&#\s]+"
)


class ConfigurationError(ValueError):
    """Stable, redacted error for invalid or unreadable configuration."""

    code = "CONFIG_INVALID"


def _redact_value(value: object) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if is_credential_key(key) else _redact_value(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_redact_value(item) for item in sorted(value, key=str)]
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(text: str, secret_values: Sequence[str] = ()) -> str:
    """Remove known secret values and common credential assignments from text."""

    redacted = text
    for secret in secret_values:
        if secret:
            redacted = redacted.replace(secret, "[REDACTED]")
    redacted = _AUTHORIZATION_VALUE.sub(r"\1[REDACTED]", redacted)
    redacted = _SECRET_QUERY_PARAMETER.sub(r"\1[REDACTED]", redacted)
    redacted = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", redacted)
    return redacted


def serialize_config(config: BaseModel | Mapping[str, object]) -> dict[str, object]:
    """Return a JSON-compatible config snapshot with credential values redacted."""

    if isinstance(config, BaseModel):
        data = config.model_dump(mode="json")
    elif isinstance(config, Mapping):
        data = dict(config)
    else:
        raise TypeError("config must be a Pydantic model or mapping")
    redacted = _redact_value(data)
    if not isinstance(redacted, dict):
        raise TypeError("serialized config must be a mapping")
    return redacted


def serialize_config_json(config: BaseModel | Mapping[str, object]) -> str:
    """Serialize a resolved config snapshot deterministically and without secrets."""

    return json.dumps(
        serialize_config(config),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _safe_validation_message(error: ValidationError) -> str:
    details = []
    for item in error.errors(include_input=False, include_context=False):
        location = ".".join(str(part) for part in item.get("loc", ())) or "<root>"
        details.append(f"{location}: {item.get('msg', 'invalid value')}")
    return redact_text("; ".join(details))


def load_config[ModelT: BaseModel](path: Path | str, model: type[ModelT]) -> ModelT:
    """Load one strict YAML document using ``yaml.safe_load`` and no network I/O."""

    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ConfigurationError(
            redact_text(f"{config_path}: unable to read configuration")
        ) from error
    if not isinstance(raw, Mapping):
        raise ConfigurationError("CONFIG_INVALID: top-level YAML value must be a mapping")
    try:
        return model.model_validate(raw)
    except ValidationError as error:
        raise ConfigurationError(_safe_validation_message(error)) from error


def load_runtime_config(path: Path | str) -> RuntimeConfig:
    return load_config(path, RuntimeConfig)


def load_source_settings(path: Path | str) -> SourceSettings:
    return load_config(path, SourceSettings)


def load_dataset_settings(path: Path | str) -> DatasetSettings:
    return load_config(path, DatasetSettings)


def load_operation_config(path: Path | str) -> OperationConfig:
    from commander_ai.application.configuration import OperationConfig

    return load_config(path, OperationConfig)


serialize_resolved_config = serialize_config
