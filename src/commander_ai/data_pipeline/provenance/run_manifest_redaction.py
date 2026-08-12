"""Secret-free recursive serialization for run configuration metadata."""

from __future__ import annotations

import math
from collections.abc import Mapping

from commander_ai.adapters.http.redaction import redact_persisted_text
from commander_ai.domain.serialization import canonical_json_bytes


def redacted_configuration_snapshot(value: object, *, key: str | None = None) -> object:
    """Return a JSON-safe config projection with credential-shaped values removed."""

    if key is not None and _is_secret_key(key):
        return "[REDACTED]"
    if hasattr(value, "model_dump") and callable(value.model_dump):
        value = value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {
            str(item_key): redacted_configuration_snapshot(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redacted_configuration_snapshot(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("configuration values must contain finite numbers")
        return value
    raise TypeError(f"unsupported configuration value: {type(value).__name__}")


def configuration_snapshot_bytes(value: object) -> bytes:
    return canonical_json_bytes(redacted_configuration_snapshot(value))


def _is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "apikey",
            "authorization",
            "cookie",
            "password",
            "secret",
            "token",
            "credential",
            "auth",
            "private_key",
            "client_secret",
        )
    )


def _safe_text(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("metadata text must be a non-empty string")
    return redact_persisted_text(value)


__all__ = ["configuration_snapshot_bytes", "redacted_configuration_snapshot"]
