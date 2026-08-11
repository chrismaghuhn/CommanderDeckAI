"""Shared semantic checks for source snapshot manifests."""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from commander_ai.adapters.http.redaction import redact_request_parameters
from commander_ai.domain.provenance import SourceSnapshotManifest

from .raw_snapshot_metadata import sanitize_snapshot_request, sanitize_terms_reference
from .raw_snapshot_object_policy import checksum_metadata_code


def manifest_semantic_code(manifest: SourceSnapshotManifest) -> str | None:
    """Return the verifier code for semantic values beyond model validation."""

    if manifest.terms_reference is not None and (
        not _safe_uri(manifest.terms_reference)
        or sanitize_terms_reference(manifest.terms_reference) != manifest.terms_reference
    ):
        return "INTEGRITY_MANIFEST_FORMAT"
    if manifest.pagination_state is not None:
        try:
            if redact_request_parameters(manifest.pagination_state) != dict(
                manifest.pagination_state
            ):
                return "INTEGRITY_MANIFEST_FORMAT"
        except (TypeError, ValueError):
            return "INTEGRITY_MANIFEST_FORMAT"
    for raw_object in manifest.objects:
        checksum_code = checksum_metadata_code(
            raw_object.checksum_verification_status,
            raw_object.upstream_sha256,
        )
        if checksum_code is not None:
            return checksum_code
    for request in manifest.requests:
        if not re.fullmatch(r"[A-Z][A-Z0-9-]*", request.sanitized_method):
            return "INTEGRITY_MANIFEST_FORMAT"
        if not _safe_http_endpoint(request.sanitized_endpoint):
            return "INTEGRITY_MANIFEST_FORMAT"
        try:
            if sanitize_snapshot_request(request) != request:
                return "INTEGRITY_MANIFEST_FORMAT"
        except (TypeError, ValueError):
            return "INTEGRITY_MANIFEST_FORMAT"
    for endpoint in manifest.request_parameters_redacted.endpoints:
        if not _safe_http_endpoint(endpoint):
            return "INTEGRITY_MANIFEST_FORMAT"
    return None


def _safe_http_endpoint(value: str) -> bool:
    if not _safe_uri(value):
        return False
    try:
        parsed = urlsplit(value)
        return parsed.scheme.casefold() in {"http", "https"} and not parsed.query
    except (TypeError, ValueError):
        return False


def _safe_uri(value: str) -> bool:
    if not isinstance(value, str) or not value or any(char.isspace() for char in value):
        return False
    if "\\" in value or any(ord(char) < 0x20 for char in value):
        return False
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or parsed.username is not None or parsed.password is not None:
            return False
        if parsed.scheme.casefold() in {"http", "https"} and parsed.hostname is None:
            return False
        _ = parsed.port
        return True
    except (TypeError, ValueError):
        return False


__all__ = ["manifest_semantic_code"]
