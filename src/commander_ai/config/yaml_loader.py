"""Offline-safe YAML loading and secret-free configuration serialization."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING

import yaml  # type: ignore[import-untyped]
from pydantic import BaseModel, ValidationError
from yaml.nodes import MappingNode  # type: ignore[import-untyped]
from yaml.resolver import BaseResolver  # type: ignore[import-untyped]

from .dataset_settings import DatasetSettings
from .runtime import RuntimeConfig
from .source_catalog import PermissionGatedSourceCatalog
from .source_settings import SourceSettings, is_credential_key, is_environment_name

if TYPE_CHECKING:
    from commander_ai.application.configuration import OperationConfig

_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|cookie|credential|password|secret|token)"
    r"(\s*[:=]\s*)([^,\s;}]+)"
)
_BEARER_BASIC_VALUE = re.compile(
    r"(?i)(?<![\w-])"
    r"(?P<label>(?:(?:proxy-)?authorization\s*[:=]\s*)?)"
    r"(?P<scheme>bearer|basic)\s+(?P<value>[^,\s;}]+)"
)
_SECRET_QUERY_PARAMETER = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|authorization|cookie|credential|password|secret|token)=)"
    r"[^&#\s]+"
)
_SOURCE_SETTINGS_ENV_FIELDS = frozenset(
    {"api_key_env", "credential_env_vars", "user_agent_env"}
)


class _DuplicateYamlKeyError(yaml.constructor.ConstructorError):  # type: ignore[misc]
    """Raised when a YAML mapping repeats a key."""


class _StrictSafeLoader(yaml.SafeLoader):  # type: ignore[misc]
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_strict_mapping(
    loader: _StrictSafeLoader, node: MappingNode, deep: bool = False
) -> dict[object, object]:
    if not isinstance(node, MappingNode):
        raise yaml.constructor.ConstructorError(
            None, None, "expected a mapping node", node.start_mark
        )

    mapping: dict[object, object] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as error:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable key",
                key_node.start_mark,
            ) from error
        if duplicate:
            raise _DuplicateYamlKeyError(
                "while constructing a mapping",
                node.start_mark,
                "duplicate YAML key",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictSafeLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_strict_mapping,
)


class ConfigurationError(ValueError):
    """Stable, redacted error for invalid or unreadable configuration."""

    code = "CONFIG_INVALID"


def _is_safe_source_environment_field(key: object, value: object) -> bool:
    key_text = str(key)
    if key_text not in _SOURCE_SETTINGS_ENV_FIELDS:
        return False
    if value is None:
        return True
    if key_text == "credential_env_vars":
        return isinstance(value, (list, tuple)) and all(is_environment_name(item) for item in value)
    return is_environment_name(value)


def _redact_value(value: object, *, allow_source_environment_fields: bool = False) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): (
                item
                if allow_source_environment_fields and _is_safe_source_environment_field(key, item)
                else "[REDACTED]"
                if is_credential_key(key)
                else _redact_value(item)
            )
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
    redacted = _BEARER_BASIC_VALUE.sub(r"\g<label>\g<scheme> [REDACTED]", redacted)
    redacted = _SECRET_QUERY_PARAMETER.sub(r"\1[REDACTED]", redacted)
    redacted = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", redacted)
    return redacted


def serialize_config(config: BaseModel | Mapping[str, object]) -> dict[str, object]:
    """Return a JSON-compatible config snapshot with credential values redacted."""

    if isinstance(config, BaseModel):
        data = config.model_dump(mode="json")
        allow_source_environment_fields = isinstance(config, SourceSettings)
    elif isinstance(config, Mapping):
        data = dict(config)
        allow_source_environment_fields = False
    else:
        raise TypeError("config must be a Pydantic model or mapping")
    redacted = _redact_value(
        data,
        allow_source_environment_fields=allow_source_environment_fields,
    )
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
    """Load one strict, duplicate-key-rejecting YAML document without network I/O."""

    config_path = Path(path)
    try:
        raw = yaml.load(config_path.read_text(encoding="utf-8"), Loader=_StrictSafeLoader)
    except _DuplicateYamlKeyError as error:
        raise ConfigurationError(
            redact_text(f"{config_path}: duplicate YAML key")
        ) from error
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


def load_permission_gated_catalog(path: Path | str) -> PermissionGatedSourceCatalog:
    return load_config(path, PermissionGatedSourceCatalog)


def load_operation_config(path: Path | str) -> OperationConfig:
    from commander_ai.application.configuration import OperationConfig

    return load_config(path, OperationConfig)


serialize_resolved_config = serialize_config
