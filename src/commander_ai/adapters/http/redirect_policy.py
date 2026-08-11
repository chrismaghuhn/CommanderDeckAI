"""Explicit host policy for initial HTTP URLs and every redirect hop."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import PurePosixPath
from urllib.parse import SplitResult, urljoin, urlsplit


class RedirectPolicyError(ValueError):
    """Redirect or endpoint rejection with a safe stable code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class RedirectPolicy:
    """Validate HTTP(S) URLs against a fixed host allowlist."""

    def __init__(self, allowed_hosts: Iterable[str], *, max_redirects: int = 5) -> None:
        normalized = {str(host).strip().casefold().rstrip(".") for host in allowed_hosts}
        if not normalized or any(
            not host or "/" in host or ":" in host or "*" in host for host in normalized
        ):
            raise ValueError("an explicit non-empty host allowlist is required")
        if max_redirects < 0:
            raise ValueError("max_redirects must be non-negative")
        self.allowed_hosts = frozenset(normalized)
        self.max_redirects = max_redirects

    def validate(self, url: str) -> str:
        """Validate an initial or already-resolved destination before sending."""

        parsed = self._parse(url)
        if (
            parsed.hostname is None
            or parsed.hostname.casefold().rstrip(".") not in self.allowed_hosts
        ):
            raise RedirectPolicyError("SECURITY_HOST_NOT_ALLOWLISTED")
        return url

    def resolve(self, current_url: str, location: str, *, redirects_followed: int) -> str:
        """Resolve one Location value and validate it before the next request."""

        if not isinstance(location, str) or not location or "\\" in location:
            raise RedirectPolicyError("SECURITY_REDIRECT_URL")
        raw_path = urlsplit(location).path
        if any(part == ".." for part in PurePosixPath(raw_path).parts):
            raise RedirectPolicyError("SECURITY_REDIRECT_URL")
        try:
            destination = urljoin(current_url, location)
        except (TypeError, ValueError) as error:
            raise RedirectPolicyError("SECURITY_REDIRECT_URL") from error
        validated = self._validate_redirect(destination)
        if redirects_followed >= self.max_redirects:
            raise RedirectPolicyError("HTTP_REDIRECT_LIMIT")
        return validated

    def _validate_redirect(self, url: str) -> str:
        parsed = self._parse(url, redirect=True)
        if (
            parsed.hostname is None
            or parsed.hostname.casefold().rstrip(".") not in self.allowed_hosts
        ):
            raise RedirectPolicyError("SECURITY_REDIRECT_HOST")
        return url

    @staticmethod
    def _parse(url: str, *, redirect: bool = False) -> SplitResult:
        try:
            if "\\" in url or any(char.isspace() or ord(char) < 0x20 for char in url):
                raise RedirectPolicyError(
                    "SECURITY_REDIRECT_URL" if redirect else "SECURITY_ENDPOINT_URL"
                )
            parsed = urlsplit(url)
            if parsed.scheme.casefold() not in {"http", "https"} or parsed.hostname is None:
                raise RedirectPolicyError(
                    "SECURITY_REDIRECT_URL" if redirect else "SECURITY_ENDPOINT_URL"
                )
            if parsed.username is not None or parsed.password is not None:
                raise RedirectPolicyError(
                    "SECURITY_REDIRECT_URL" if redirect else "SECURITY_ENDPOINT_URL"
                )
            if parsed.fragment:
                raise RedirectPolicyError(
                    "SECURITY_REDIRECT_URL" if redirect else "SECURITY_ENDPOINT_URL"
                )
            _ = parsed.port
            return parsed
        except RedirectPolicyError:
            raise
        except (TypeError, ValueError) as error:
            raise RedirectPolicyError(
                "SECURITY_REDIRECT_URL" if redirect else "SECURITY_ENDPOINT_URL"
            ) from error


__all__ = ["RedirectPolicy", "RedirectPolicyError"]
