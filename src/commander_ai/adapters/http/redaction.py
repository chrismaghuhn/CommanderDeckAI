"""Deterministic allowlist redaction for HTTP metadata and error text."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, MutableMapping, Set
from urllib.parse import urlsplit, urlunsplit

_SECRET_KEY = re.compile(
    r"(?:api[_-]?key|access[_-]?(?:key|token)|authorization|cookie|credential|"
    r"password|secret|token|signature|sig)",
    re.IGNORECASE,
)
_SECRET_TEXT = re.compile(
    r"(?i)(authorization|cookie|api[_-]?key|access[_-]?(?:key|token)|password|secret|"
    r"token|signature|sig)"
    r"\s*[:=]\s*(?:Bearer\s+)?([^\s,;]+)"
)
_URL = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
_SAFE_METHOD = re.compile(r"[A-Z][A-Z0-9-]*")
_SAFE_METADATA_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+:-]{0,63}")
_SAFE_HEADERS = frozenset(
    {"content-type", "content-encoding", "content-length", "etag", "last-modified", "retry-after"}
)
SAFE_REQUEST_PARAMETER_KEYS = frozenset(
    {
        "cursor",
        "date",
        "end_date",
        "event_format",
        "fields",
        "filter",
        "format",
        "from",
        "has_more",
        "include",
        "tid",
        "game",
        "formats",
        "start",
        "end",
        "last",
        "participantmin",
        "participantmax",
        "columns",
        "rounds",
        "tables",
        "players",
        "language",
        "limit",
        "num_days",
        "locale",
        "name",
        "next",
        "next_page",
        "offset",
        "order",
        "organization_id",
        "page",
        "page_size",
        "pagesize",
        "query",
        "set",
        "sets",
        "sort",
        "start_date",
        "type",
        "version",
        "decklist_as_text",
    }
)


def redact_parameters(
    parameters: Mapping[str, object], *, allowed_keys: Set[str] | None = None
) -> dict[str, object]:
    """Retain JSON-safe parameters while recursively dropping credential keys."""

    if not isinstance(parameters, Mapping):
        raise TypeError("HTTP parameters must be a mapping")
    allowed = {str(key).casefold() for key in allowed_keys} if allowed_keys is not None else None
    result: dict[str, object] = {}
    for key in sorted(parameters, key=str):
        key_text = str(key)
        if _SECRET_KEY.search(key_text) or (
            allowed is not None and key_text.casefold() not in allowed
        ):
            continue
        result[key_text] = _redact_value(parameters[key], allowed)
    return result


def redact_request_parameters(parameters: Mapping[str, object]) -> dict[str, object]:
    """Apply the explicit allowlist used at the snapshot persistence boundary."""

    return redact_parameters(parameters, allowed_keys=SAFE_REQUEST_PARAMETER_KEYS)


def sanitize_method(value: object) -> str:
    """Normalize an HTTP method to the manifest's safe uppercase grammar."""

    if not isinstance(value, str):
        raise ValueError("HTTP method must be a string")
    normalized = value.strip().upper()
    if not _SAFE_METHOD.fullmatch(normalized):
        raise ValueError("HTTP method is not a safe token")
    return normalized


def sanitize_metadata_token(
    value: object,
    *,
    optional: bool,
    redacted_value: str = "[redacted]",
) -> str | None:
    """Keep only bounded scalar metadata after credential/error redaction."""

    if value is None:
        if optional:
            return None
        raise ValueError("required metadata is missing")
    if not isinstance(value, str) or not value.strip():
        raise ValueError("metadata token must be a non-empty string")
    safe = redact_error_text(value).strip()
    if not _SAFE_METADATA_TOKEN.fullmatch(safe):
        return None if optional else redacted_value
    return safe


def sanitize_request_metadata(
    method: object,
    endpoint: str,
    parameters: Mapping[str, object] | None,
    api_version: object,
    format_value: object,
) -> dict[str, object]:
    """Build the allowlisted request projection used by snapshot persistence."""

    sanitized_endpoint = sanitize_endpoint(endpoint)
    if sanitized_endpoint == "[redacted-endpoint]":
        raise ValueError("request endpoint is not safe")
    return {
        "sanitized_method": sanitize_method(method),
        "sanitized_endpoint": sanitized_endpoint,
        "api_version": sanitize_metadata_token(api_version, optional=True),
        "format": sanitize_metadata_token(format_value, optional=False),
        "sanitized_parameters": redact_request_parameters(parameters or {}),
    }


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


def is_sensitive_request_header(name: str) -> bool:
    """Identify request headers that must not cross an origin boundary."""

    normalized = str(name).casefold()
    return normalized in {"authorization", "proxy-authorization", "cookie", "set-cookie"} or bool(
        _SECRET_KEY.search(normalized)
    )


def strip_default_sensitive_headers(
    headers: MutableMapping[str, str], explicit_headers: Mapping[str, str]
) -> None:
    """Remove sensitive client defaults unless the caller explicitly supplied them."""

    explicit = {
        str(key).casefold() for key in explicit_headers if is_sensitive_request_header(str(key))
    }
    for key in list(headers):
        if is_sensitive_request_header(str(key)) and str(key).casefold() not in explicit:
            del headers[key]


def redact_error_text(message: str) -> str:
    """Remove credentials and query material without echoing transport exceptions."""

    safe = _URL.sub(lambda match: sanitize_endpoint(match.group(0)), str(message))
    return _SECRET_TEXT.sub(lambda match: f"{match.group(1)}=[REDACTED]", safe)


def redact_persisted_text(message: str) -> str:
    """Redact credentials and remove all URL query/fragment material for storage."""

    return _URL.sub(lambda match: sanitize_endpoint(match.group(0)), redact_error_text(message))


def _redact_value(value: object, allowed_keys: Set[str] | None) -> object:
    if value is None or isinstance(value, (bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("HTTP parameters cannot contain non-finite numbers")
        return value
    if isinstance(value, str):
        return redact_error_text(value)
    if isinstance(value, Mapping):
        return redact_parameters(value, allowed_keys=allowed_keys)
    if isinstance(value, (list, tuple)):
        return [_redact_value(item, allowed_keys) for item in value]
    raise TypeError("HTTP parameters must contain JSON-safe values")


__all__ = [
    "SAFE_REQUEST_PARAMETER_KEYS",
    "is_sensitive_request_header",
    "redact_error_text",
    "redact_parameters",
    "redact_persisted_text",
    "redact_request_parameters",
    "sanitize_endpoint",
    "sanitize_headers",
    "sanitize_metadata_token",
    "sanitize_method",
    "sanitize_request_metadata",
    "strip_default_sensitive_headers",
]
