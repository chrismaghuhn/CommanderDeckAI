"""MTGJSON request construction over the shared bounded HTTP transport."""

from __future__ import annotations

from typing import Literal

import httpx

from commander_ai.adapters.http.redaction import sanitize_endpoint
from commander_ai.adapters.http.redirect_policy import RedirectPolicy, RedirectPolicyError
from commander_ai.adapters.http.transport import HttpTransport, SafeHttpResponse

from .settings import MTGJSONProduct, MTGJSONSettings


class MTGJSONClientError(RuntimeError):
    """Stable client failure without endpoint or credential echo."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class MTGJSONClient:
    """Build only configured MTGJSON bulk and checksum requests."""

    def __init__(
        self, settings: MTGJSONSettings, *, http_client: httpx.Client | None = None
    ) -> None:
        self.settings = settings
        self._policy = RedirectPolicy(settings.source.host_allowlist)
        self._transport = HttpTransport(
            allowed_hosts=set(settings.source.host_allowlist),
            timeout_seconds=settings.source.timeout_seconds,
            max_retries=settings.source.max_retries,
            max_response_bytes=settings.source.max_download_bytes,
            respect_retry_after=settings.source.respect_retry_after,
            rate_limit_per_minute=settings.source.rate_limit_per_minute,
            client=http_client,
        )

    def request_metadata(
        self,
        product: MTGJSONProduct,
        *,
        kind: Literal["archive", "checksum"],
    ) -> dict[str, object]:
        url = self._url(product, kind)
        metadata = self._transport.request_metadata(
            "GET",
            url,
            format="binary" if kind == "archive" else "text",
        )
        if metadata.get("sanitized_endpoint") != sanitize_endpoint(url):
            raise MTGJSONClientError("MTGJSON_METADATA_ENDPOINT_MISMATCH")
        return metadata

    def fetch_archive(self, product: MTGJSONProduct) -> SafeHttpResponse:
        return self._fetch(product, kind="archive")

    def fetch_checksum(self, product: MTGJSONProduct) -> SafeHttpResponse:
        if self.settings.checksum_url(product) is None:
            raise MTGJSONClientError("MTGJSON_CHECKSUM_NOT_CONFIGURED")
        return self._fetch(product, kind="checksum")

    def close(self) -> None:
        self._transport.close()

    def _url(self, product: MTGJSONProduct, kind: Literal["archive", "checksum"]) -> str:
        if kind == "archive":
            url = self.settings.archive_url(product)
        else:
            checksum_url = self.settings.checksum_url(product)
            if checksum_url is None:
                raise MTGJSONClientError("MTGJSON_CHECKSUM_NOT_CONFIGURED")
            url = checksum_url
        try:
            self._policy.validate(url)
        except (RedirectPolicyError, TypeError):
            raise MTGJSONClientError("MTGJSON_ENDPOINT_NOT_ALLOWLISTED") from None
        return url

    def _fetch(
        self, product: MTGJSONProduct, *, kind: Literal["archive", "checksum"]
    ) -> SafeHttpResponse:
        response = self._transport.request(
            "GET",
            self._url(product, kind),
            format="binary" if kind == "archive" else "text",
        )
        try:
            self._policy.validate(response.sanitized_endpoint)
        except (RedirectPolicyError, TypeError):
            response.close()
            raise MTGJSONClientError("MTGJSON_RESPONSE_HOST_NOT_ALLOWLISTED") from None
        return response


__all__ = ["MTGJSONClient", "MTGJSONClientError"]
