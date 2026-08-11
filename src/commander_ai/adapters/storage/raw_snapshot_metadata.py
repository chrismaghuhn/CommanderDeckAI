"""Persistence-boundary sanitization for raw snapshot metadata."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

from commander_ai.adapters.http.redaction import (
    redact_request_parameters,
    sanitize_endpoint,
    sanitize_metadata_token,
    sanitize_method,
)
from commander_ai.domain.provenance import SourceSnapshotRequest


def sanitize_snapshot_request(
    request: SourceSnapshotRequest | Mapping[str, object],
) -> SourceSnapshotRequest:
    """Return the only request projection allowed into a raw manifest."""

    value = SourceSnapshotRequest.model_validate(request)
    if not _safe_identifier(value.request_id):
        raise ValueError("request ID is not a safe metadata identifier")
    endpoint = sanitize_endpoint(value.sanitized_endpoint)
    if endpoint == "[redacted-endpoint]":
        raise ValueError("request endpoint is not a safe HTTP URI")
    return value.model_copy(
        update={
            "sanitized_method": sanitize_method(value.sanitized_method),
            "sanitized_endpoint": endpoint,
            "api_version": sanitize_metadata_token(value.api_version, optional=True),
            "format": sanitize_metadata_token(value.format, optional=False),
            "sanitized_parameters": redact_request_parameters(value.sanitized_parameters),
        }
    )


def sanitize_terms_reference(value: str | None) -> str | None:
    """Keep a terms URI without credentials, queries, fragments, or unsafe syntax."""

    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = value.strip()
    try:
        parsed = urlsplit(candidate)
        if parsed.scheme.casefold() in {"http", "https"}:
            safe = sanitize_endpoint(candidate)
            return None if safe == "[redacted-endpoint]" else safe
        if (
            not parsed.scheme
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or "\\" in candidate
            or any(char.isspace() or ord(char) < 0x20 for char in candidate)
        ):
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except (TypeError, ValueError):
        return None


def _safe_identifier(value: str) -> bool:
    return (
        isinstance(value, str)
        and bool(value)
        and len(value) <= 128
        and value[0].isalnum()
        and all(char.isalnum() or char in "._-" for char in value)
    )


__all__ = ["sanitize_snapshot_request", "sanitize_terms_reference"]
