"""Deterministic allowlist redaction for HTTP metadata and error text."""

from __future__ import annotations

import re
from collections.abc import Mapping, Set
from urllib.parse import urlsplit, urlunsplit

_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?token|authorization|cookie|credential|password|secret|token)",
    re.IGNORECASE,
)
_SECRET_TEXT = re.compile(
    r"(?i)(authorization|cookie|api[_-]?key|access[_-]?token|password|secret|token)"
    r"\s*[:=]\s*(?:Bearer\s+)?([^\s,;]+)"
)
_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SAFE_HEADERS = frozenset(
    {"content-type", "content-encoding", "content-length", "etag", "last-modified", "retry-after"}
)


def redact_parameters(
    parameters: Mapping[str, object], *, allowed_keys: Set[str] | None = None
) -> dict[str, object]:
    """Retain JSON-safe parameters while recursively dropping credential keys."""

    if not isinstance(parameters, Mapping):
        raise TypeError("HTTP parameters must be a mapping")
    allowed = {str(key) for key in allowed_keys} if allowed_keys is not None else None
    result: dict[str, object] = {}
    for key in sorted(parameters, key=str):
        key_text = str(key)
        if _SECRET_KEY.search(key_text) or (allowed is not None and key_text not in allowed):
            continue
        result[key_text] = _redact_value(parameters[key], allowed)
    return result


def sanitize_endpoint(url: str) -> str:
    """Return an endpoint without credentials, query parameters, or fragments."""

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
        if parsed.scheme.casefold() not in {"http", "https"} or hostname is None:
            return "[redacted-endpoint]"
        host = hostname.casefold().rstrip(".")
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        port = parsed.port
        netloc = host if port is None else f"{host}:{port}"
        return urlunsplit((parsed.scheme.casefold(), netloc, parsed.path or "/", "", ""))
    except (TypeError, ValueError):
        return "[redacted-endpoint]"


def sanitize_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Persist only the small explicit response-header allowlist."""

    result: dict[str, str] = {}
    for key in sorted(headers, key=lambda item: str(item).casefold()):
        normalized = str(key).casefold()
        if normalized in _SAFE_HEADERS:
            result[normalized] = str(headers[key])
    return result


def redact_error_text(message: str) -> str:
    """Remove credentials and query material without echoing transport exceptions."""

    safe = _URL.sub(lambda match: sanitize_endpoint(match.group(0)), str(message))
    return _SECRET_TEXT.sub(lambda match: f"{match.group(1)}=[REDACTED]", safe)


def _redact_value(value: object, allowed_keys: Set[str] | None) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Mapping):
        return redact_parameters(value, allowed_keys=allowed_keys)
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, allowed_keys) for item in value]
    raise TypeError("HTTP parameters must contain JSON-safe values")


__all__ = [
    "redact_error_text",
    "redact_parameters",
    "sanitize_endpoint",
    "sanitize_headers",
]
