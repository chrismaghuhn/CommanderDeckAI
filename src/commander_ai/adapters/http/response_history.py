"""Validate redirect history exposed by real or injected HTTP responses."""

from __future__ import annotations

import httpx

from .redirect_policy import RedirectPolicy, RedirectPolicyError

_REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def validate_response_history(response: httpx.Response, policy: RedirectPolicy) -> str | None:
    """Validate every recorded redirect response before its body is consumed."""

    try:
        _validate_response_history(response, policy)
    except RedirectPolicyError as error:
        return error.code
    return None


def _validate_response_history(response: httpx.Response, policy: RedirectPolicy) -> None:
    """Apply redirect policy checks without changing the public error type."""

    history = response.history
    if not isinstance(history, (list, tuple)):
        raise RedirectPolicyError("SECURITY_REDIRECT_URL")
    redirects_followed = 0
    for hop in history:
        if not isinstance(hop, httpx.Response):
            raise RedirectPolicyError("SECURITY_REDIRECT_URL")
        _validate_redirect_response_url(hop, policy)
        if hop.status_code not in _REDIRECT_STATUSES:
            continue
        location = hop.headers.get("location")
        if location is None:
            raise RedirectPolicyError("HTTP_REDIRECT_LOCATION")
        policy.resolve(str(hop.url), location, redirects_followed=redirects_followed)
        redirects_followed += 1

    try:
        policy.validate(str(response.url))
    except RedirectPolicyError:
        raise RedirectPolicyError("SECURITY_RESPONSE_HOST") from None


def _validate_redirect_response_url(response: httpx.Response, policy: RedirectPolicy) -> None:
    try:
        policy.validate(str(response.url))
    except RedirectPolicyError as error:
        code = (
            "SECURITY_REDIRECT_HOST"
            if error.code == "SECURITY_HOST_NOT_ALLOWLISTED"
            else "SECURITY_REDIRECT_URL"
        )
        raise RedirectPolicyError(code) from None


__all__ = ["validate_response_history"]
