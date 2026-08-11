"""Offline-safe YAML loading and secret-free configuration serialization."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any

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

_REDACTION_MARKER = "[REDACTED]"
_URI_USERINFO = re.compile(
    r"(?<![A-Za-z0-9+._-])"
    r"(?P<prefix>(?:[A-Za-z][A-Za-z0-9+.-]*:)?//)"
    r"(?P<userinfo>[^/\s?#]+)@"
)
_BEARER_BASIC_VALUE = re.compile(
    r"(?i)(?<![\w-])"
    r"(?P<label>(?:(?:proxy-)?authorization\s*[:=]\s*)?)"
    r"(?P<scheme>bearer|basic)\s+(?P<value>[^,\s;&]+)"
)
_SECRET_QUERY_PARAMETER = re.compile(
    r"(?i)(?P<prefix>[?&](?:api[_-]?key|access[_-]?token|authorization|cookie|credential|password|secret|token)=)"
    r"(?!(?:bearer|basic)\s+)"
    r"(?P<value>[^&#\s,;]+)"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?P<label>api[_-]?key|access[_-]?token|authorization|cookie|credential|password|secret|token)"
    r"(?P<separator>\s*[:=]\s*)"
    r"(?!(?:bearer|basic)\s+)"
    r"(?P<value>[^,\s;&]+)"
)
_SOURCE_SETTINGS_ENV_FIELDS = frozenset({"api_key_env", "credential_env_vars", "user_agent_env"})
_MISSING = object()


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


def _is_environment_key(key: object) -> bool:
    return str(key).casefold().endswith(("_env", "_env_vars"))


def _serialized_item(serialized: object, key: object) -> object:
    if not isinstance(serialized, Mapping):
        return _MISSING
    if key in serialized:
        return serialized[key]
    return serialized.get(str(key), _MISSING)


def _redact_mapping(
    value: Mapping[Any, Any],
    *,
    serialized: object = _MISSING,
    allow_source_environment_fields: bool = False,
) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, item in value.items():
        key_text = str(key)
        serialized_value = _serialized_item(serialized, key)
        if allow_source_environment_fields and _is_safe_source_environment_field(key, item):
            redacted[key_text] = _redact_value(
                item if serialized_value is _MISSING else serialized_value
            )
        elif is_credential_key(key) or _is_environment_key(key):
            redacted[key_text] = "[REDACTED]"
        else:
            redacted[key_text] = _redact_model_field(item, serialized_value)
    return redacted


def _redact_model_field(original: object, serialized: object) -> object:
    if original is _MISSING:
        return _redact_value(serialized)
    if isinstance(original, BaseModel):
        return _redact_value(original)
    if isinstance(original, Mapping):
        return _redact_mapping(original, serialized=serialized)
    if isinstance(original, (list, tuple)):
        serialized_items = list(serialized) if isinstance(serialized, Sequence) else []
        return [
            _redact_model_field(
                item,
                serialized_items[index] if index < len(serialized_items) else _MISSING,
            )
            for index, item in enumerate(original)
        ]
    if isinstance(original, (set, frozenset)):
        return [_redact_value(item) for item in sorted(original, key=str)]
    return _redact_value(serialized if serialized is not _MISSING else original)


def _redact_model(value: BaseModel) -> dict[str, object]:
    if isinstance(value, RuntimeConfig):
        return _redact_mapping(value.portable_snapshot())
    if isinstance(value, SourceSettings):
        return _redact_mapping(
            value.model_dump(mode="json"),
            allow_source_environment_fields=True,
        )

    serialized = value.model_dump(mode="json")
    return {
        str(key): (
            "[REDACTED]"
            if is_credential_key(key) or _is_environment_key(key)
            else _redact_model_field(getattr(value, key, _MISSING), item)
        )
        for key, item in serialized.items()
    }


def _redact_value(value: object, *, allow_source_environment_fields: bool = False) -> object:
    if isinstance(value, BaseModel):
        return _redact_model(value)
    if isinstance(value, Mapping):
        return _redact_mapping(
            value,
            allow_source_environment_fields=allow_source_environment_fields,
        )
    if isinstance(value, (list, tuple)):
        return [_redact_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_redact_value(item) for item in sorted(value, key=str)]
    if isinstance(value, Path):
        return redact_text(value.as_posix())
    if isinstance(value, str):
        return redact_text(value)
    return value


def redact_text(text: str, secret_values: Sequence[str] = ()) -> str:
    """Remove known secret values and common credential assignments from text."""

    redacted = text
    for secret in sorted(
        (value for value in secret_values if value),
        key=len,
        reverse=True,
    ):
        redacted = _REDACTION_MARKER.join(
            fragment.replace(secret, _REDACTION_MARKER)
            for fragment in redacted.split(_REDACTION_MARKER)
        )
    redacted = _URI_USERINFO.sub(rf"\g<prefix>{_REDACTION_MARKER}@", redacted)
    redacted = _BEARER_BASIC_VALUE.sub(rf"\g<label>\g<scheme> {_REDACTION_MARKER}", redacted)
    redacted = _SECRET_QUERY_PARAMETER.sub(rf"\g<prefix>{_REDACTION_MARKER}", redacted)
    redacted = _SECRET_ASSIGNMENT.sub(rf"\g<label>\g<separator>{_REDACTION_MARKER}", redacted)
    return redacted


def serialize_config(config: BaseModel | Mapping[str, object]) -> dict[str, object]:
    """Return a JSON-compatible config snapshot with credential values redacted."""

    if not isinstance(config, (BaseModel, Mapping)):
        raise TypeError("config must be a Pydantic model or mapping")
    redacted = _redact_value(config)
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
        raise ConfigurationError(redact_text(f"{config_path}: duplicate YAML key")) from error
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
