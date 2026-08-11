"""MTGJSON request construction over the shared bounded HTTP transport."""

from __future__ import annotations

from typing import Literal

from commander_ai.adapters.http.transport import HttpTransport, SafeHttpResponse

from .settings import MTGJSONProduct, MTGJSONSettings


class MTGJSONClientError(RuntimeError):
    """Stable client failure without endpoint or credential echo."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class MTGJSONClient:
    """Build only configured MTGJSON bulk and checksum requests."""

    def __init__(self, settings: MTGJSONSettings, transport: HttpTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport or HttpTransport(
            allowed_hosts=set(settings.source.host_allowlist),
            timeout_seconds=settings.source.timeout_seconds,
            max_retries=settings.source.max_retries,
            max_response_bytes=settings.source.max_download_bytes,
            respect_retry_after=settings.source.respect_retry_after,
            rate_limit_per_minute=settings.source.rate_limit_per_minute,
        )
        self._owns_transport = transport is None

    def request_metadata(
        self,
        product: MTGJSONProduct,
        *,
        kind: Literal["archive", "checksum"],
    ) -> dict[str, object]:
        url = self._url(product, kind)
        return self._transport.request_metadata(
            "GET",
            url,
            format="binary" if kind == "archive" else "text",
        )

    def fetch_archive(self, product: MTGJSONProduct) -> SafeHttpResponse:
        return self._transport.request(
            "GET",
            self.settings.archive_url(product),
            format="binary",
        )

    def fetch_checksum(self, product: MTGJSONProduct) -> SafeHttpResponse:
        if self.settings.checksum_url(product) is None:
            raise MTGJSONClientError("MTGJSON_CHECKSUM_NOT_CONFIGURED")
        return self._transport.request(
            "GET",
            self.settings.checksum_url(product) or "",
            format="text",
        )

    def close(self) -> None:
        if self._owns_transport:
            self._transport.close()

    def _url(self, product: MTGJSONProduct, kind: Literal["archive", "checksum"]) -> str:
        if kind == "archive":
            return self.settings.archive_url(product)
        checksum_url = self.settings.checksum_url(product)
        if checksum_url is None:
            raise MTGJSONClientError("MTGJSON_CHECKSUM_NOT_CONFIGURED")
        return checksum_url


__all__ = ["MTGJSONClient", "MTGJSONClientError"]
