from __future__ import annotations

from commander_ai.adapters.http.redaction import (
    redact_error_text,
    redact_parameters,
    sanitize_endpoint,
    sanitize_headers,
)


def test_redaction_is_deterministic_idempotent_and_excludes_secret_fields() -> None:
    parameters = {
        "page": 2,
        "api_key": "super-secret",
        "nested": {"token": "nested-secret", "format": "json"},
        "safe": ["a", "b"],
    }

    redacted = redact_parameters(parameters)

    assert redacted == {"page": 2, "nested": {"format": "json"}, "safe": ["a", "b"]}
    assert redact_parameters(redacted) == redacted
    assert "super-secret" not in repr(redacted)
    assert "nested-secret" not in repr(redacted)


def test_endpoint_and_headers_keep_only_safe_metadata() -> None:
    endpoint = sanitize_endpoint(
        "https://example.invalid/cards?page=2&api_key=super-secret#fragment"
    )
    headers = sanitize_headers(
        {
            "Content-Type": "application/json",
            "ETag": "etag-1",
            "Authorization": "Bearer super-secret",
            "Cookie": "session=super-secret",
            "X-Internal": "secret",
        }
    )

    assert endpoint == "https://example.invalid/cards"
    assert headers == {"content-type": "application/json", "etag": "etag-1"}
    assert "super-secret" not in repr(headers)


def test_error_redaction_removes_credentials_from_text_and_urls() -> None:
    message = (
        "GET https://user:password@example.invalid/cards?api_key=super-secret failed; "
        "Authorization: Bearer header-secret Cookie: session-cookie"
    )

    safe = redact_error_text(message)

    assert "password" not in safe
    assert "super-secret" not in safe
    assert "header-secret" not in safe
    assert "session-cookie" not in safe
    assert "example.invalid/cards" in safe
