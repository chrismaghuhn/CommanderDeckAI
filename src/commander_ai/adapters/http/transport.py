"""Bounded, serial HTTP transport that exposes raw entity-byte streaming."""

from __future__ import annotations

import email.utils
import math
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

import httpx

from .entity_framing import parse_content_length
from .error_boundary import detached_error_boundary, detached_generator_boundary
from .origin import same_origin
from .redaction import (
    is_sensitive_request_header,
    redact_error_text,
    sanitize_endpoint,
    sanitize_headers,
    sanitize_request_metadata,
)
from .redirect_policy import RedirectPolicy, RedirectPolicyError

HttpQueryValue = str | int | float | bool | None | list[str | int | float | bool | None]
MAX_RATE_LIMIT_PER_MINUTE = 1_000_000


class HttpTransportError(RuntimeError):
    """Safe HTTP failure with no exception or credential echo."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        safe_detail = redact_error_text(detail)
        super().__init__(code if not safe_detail else f"{code}: {safe_detail}")


@dataclass(frozen=True, slots=True)
class HttpResponseMetadata:
    """Explicitly allowlisted response metadata; never raw response headers."""

    content_type: str | None = None
    content_encoding: str | None = None
    etag: str | None = None
    last_modified: str | None = None
    retry_after: str | None = None

    def as_dict(self) -> dict[str, str]:
        values = {
            "content_type": self.content_type,
            "content_encoding": self.content_encoding,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "retry_after": self.retry_after,
        }
        return {key: value for key, value in values.items() if value is not None}


class SafeHttpResponse:
    """Response port whose only body interface is bounded ``iter_raw``."""

    @detached_error_boundary(HttpTransportError)
    def __init__(
        self,
        response: httpx.Response,
        *,
        method: str,
        max_response_bytes: int,
    ) -> None:
        self._response = response
        self._max_response_bytes = max_response_bytes
        self._read_bytes = 0
        try:
            self._expected_bytes = parse_content_length(response.headers.get("content-length"))
        except ValueError:
            response.close()
            raise HttpTransportError("HTTP_ENTITY_INVALID") from None
        if self._expected_bytes is not None and self._expected_bytes > max_response_bytes:
            response.close()
            raise HttpTransportError("HTTP_RESPONSE_TOO_LARGE")
        self.status_code = response.status_code
        self.method = method
        self.sanitized_endpoint = sanitize_endpoint(str(response.url))
        safe_headers = sanitize_headers(response.headers)
        self.metadata = HttpResponseMetadata(
            content_type=safe_headers.get("content-type"),
            content_encoding=safe_headers.get("content-encoding"),
            etag=safe_headers.get("etag"),
            last_modified=safe_headers.get("last-modified"),
            retry_after=safe_headers.get("retry-after"),
        )

    @detached_generator_boundary(HttpTransportError)
    def iter_raw(self) -> Iterator[bytes]:
        """Yield HTTPX ``iter_raw`` chunks without content decoding."""
        try:
            for chunk in self._response.iter_raw():
                if not isinstance(chunk, bytes):
                    raise HttpTransportError("HTTP_ENTITY_INVALID")
                self._read_bytes += len(chunk)
                if self._read_bytes > self._max_response_bytes:
                    raise HttpTransportError("HTTP_RESPONSE_TOO_LARGE")
                yield chunk
            if self._expected_bytes is not None and self._read_bytes != self._expected_bytes:
                raise HttpTransportError("HTTP_ENTITY_TRUNCATED")
        except HttpTransportError:
            self.close()
            raise
        except Exception:
            self.close()
            raise HttpTransportError("HTTP_ENTITY_STREAM_FAILED") from None
        finally:
            self.close()

    @detached_error_boundary(HttpTransportError)
    def close(self) -> None:
        try:
            self._response.close()
        except Exception:
            raise HttpTransportError("HTTP_RESPONSE_CLOSE_FAILED") from None

    def __enter__(self) -> SafeHttpResponse:
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> Literal[False]:
        self.close()
        return False


class HttpTransport:
    """Serial HTTPX transport with bounded retries and manual redirect checks."""

    def __init__(
        self,
        *,
        allowed_hosts: set[str] | tuple[str, ...] | list[str],
        timeout_seconds: float = 30.0,
        max_retries: int = 2,
        max_response_bytes: int = 2_000_000_000,
        max_redirects: int = 5,
        respect_retry_after: bool = True,
        backoff_seconds: float = 0.5,
        max_retry_delay_seconds: float = 30.0,
        rate_limit_per_minute: int | None = 60,
        user_agent: str = "CommanderDeckAI/0.1",
        client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if (
            not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
            or not isinstance(max_retries, int)
            or isinstance(max_retries, bool)
            or max_retries < 0
            or not isinstance(max_response_bytes, int)
            or isinstance(max_response_bytes, bool)
            or max_response_bytes < 1
        ):
            raise ValueError("HTTP timeout, retry, and response limits are invalid")
        if (
            not math.isfinite(backoff_seconds)
            or not math.isfinite(max_retry_delay_seconds)
            or backoff_seconds < 0
            or max_retry_delay_seconds < 0
        ):
            raise ValueError("HTTP retry delays cannot be negative")
        if rate_limit_per_minute is not None and (
            isinstance(rate_limit_per_minute, bool)
            or not isinstance(rate_limit_per_minute, (int, float))
            or not math.isfinite(float(rate_limit_per_minute))
            or rate_limit_per_minute < 1
            or rate_limit_per_minute > MAX_RATE_LIMIT_PER_MINUTE
        ):
            raise ValueError("rate_limit_per_minute must be finite, bounded, and positive or None")
        if not user_agent.strip():
            raise ValueError("user_agent must be identifiable")
        self._policy = RedirectPolicy(allowed_hosts, max_redirects=max_redirects)
        self._timeout_seconds = timeout_seconds
        self._max_retries = max_retries
        self._max_response_bytes = max_response_bytes
        self._respect_retry_after = respect_retry_after
        self._backoff_seconds = backoff_seconds
        self._max_retry_delay = max_retry_delay_seconds
        self._interval = None if rate_limit_per_minute is None else 60.0 / rate_limit_per_minute
        self._next_request_at = 0.0
        self._user_agent = user_agent.strip()
        self._sleeper = sleeper
        self._clock = clock
        self._client = client or httpx.Client(follow_redirects=False, timeout=timeout_seconds)
        self._owns_client = client is None

    @detached_error_boundary(HttpTransportError)
    def request(
        self,
        method: str,
        url: str,
        *,
        parameters: Mapping[str, object] | None = None,
        headers: Mapping[str, str] | None = None,
        api_version: str | None = None,
        format: str = "binary",
    ) -> SafeHttpResponse:
        """Perform one bounded request and return raw entity bytes only."""

        try:
            self._policy.validate(url)
        except RedirectPolicyError as error:
            raise HttpTransportError(error.code) from None
        normalized_method = method.strip().upper()
        if not normalized_method:
            raise HttpTransportError("HTTP_METHOD_INVALID")
        current_url = url
        current_parameters = parameters
        current_method = normalized_method
        redirects_followed = 0
        strip_sensitive_headers = False
        while True:
            response = self._request_with_retries(
                current_method,
                current_url,
                parameters=current_parameters,
                headers=headers,
                strip_sensitive_headers=strip_sensitive_headers,
            )
            if response.status_code not in {301, 302, 303, 307, 308}:
                if response.status_code >= 400:
                    response.close()
                    raise HttpTransportError("HTTP_STATUS_ERROR", str(response.status_code))
                return SafeHttpResponse(
                    response,
                    method=current_method,
                    max_response_bytes=self._max_response_bytes,
                )
            location = response.headers.get("location")
            response.close()
            if location is None:
                raise HttpTransportError("HTTP_REDIRECT_LOCATION")
            try:
                next_url = self._policy.resolve(
                    str(response.url), location, redirects_followed=redirects_followed
                )
            except RedirectPolicyError as error:
                raise HttpTransportError(error.code) from None
            if not same_origin(str(response.url), next_url):
                strip_sensitive_headers = True
            current_method = _redirect_method(current_method, response.status_code)
            current_url = next_url
            current_parameters = None
            redirects_followed += 1

    @detached_error_boundary(HttpTransportError)
    def request_metadata(
        self,
        method: str,
        url: str,
        *,
        parameters: Mapping[str, object] | None = None,
        api_version: str | None = None,
        format: str = "binary",
    ) -> dict[str, object]:
        """Return the only request fields safe for a snapshot manifest."""

        try:
            return sanitize_request_metadata(method, url, parameters, api_version, format)
        except (TypeError, ValueError):
            raise HttpTransportError("HTTP_METADATA_INVALID") from None

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _request_with_retries(
        self,
        method: str,
        url: str,
        *,
        parameters: Mapping[str, object] | None,
        headers: Mapping[str, str] | None,
        strip_sensitive_headers: bool,
    ) -> httpx.Response:
        request_headers = {str(key): str(value) for key, value in (headers or {}).items()}
        if not any(
            value.strip()
            for key, value in request_headers.items()
            if key.casefold() == "user-agent"
        ):
            request_headers = {
                key: value
                for key, value in request_headers.items()
                if key.casefold() != "user-agent"
            }
            request_headers["User-Agent"] = self._user_agent
        for attempt in range(self._max_retries + 1):
            self._wait_for_rate_limit()
            try:
                request = self._client.build_request(
                    method,
                    url,
                    params=_query_parameters(parameters),
                    headers=request_headers,
                    timeout=self._timeout_seconds,
                )
                if strip_sensitive_headers:
                    for key in list(request.headers):
                        if is_sensitive_request_header(key):
                            del request.headers[key]
                response = self._client.send(
                    request,
                    stream=True,
                    auth=None if strip_sensitive_headers else httpx.USE_CLIENT_DEFAULT,
                    follow_redirects=False,
                )
            except httpx.TimeoutException:
                if attempt >= self._max_retries:
                    raise HttpTransportError("HTTP_TIMEOUT") from None
                self._sleeper(self._retry_delay(attempt, None))
                continue
            except httpx.RequestError:
                if attempt >= self._max_retries:
                    raise HttpTransportError("HTTP_CONNECTION_FAILED") from None
                self._sleeper(self._retry_delay(attempt, None))
                continue
            if (
                response.status_code not in {408, 425, 429}
                and not 500 <= response.status_code <= 599
            ):
                return response
            retry_after = response.headers.get("retry-after")
            response.close()
            if attempt >= self._max_retries:
                raise HttpTransportError("HTTP_RETRIES_EXHAUSTED")
            self._sleeper(self._retry_delay(attempt, retry_after))
        raise HttpTransportError("HTTP_RETRIES_EXHAUSTED")

    def _wait_for_rate_limit(self) -> None:
        if self._interval is None:
            return
        delay = self._next_request_at - self._clock()
        if delay > 0:
            self._sleeper(delay)
        self._next_request_at = self._clock() + self._interval

    def _retry_delay(self, attempt: int, retry_after: str | None) -> float:
        if self._respect_retry_after and retry_after:
            parsed = _retry_after_seconds(retry_after)
            if parsed is not None:
                return min(parsed, self._max_retry_delay)
        delay = self._backoff_seconds * float(2**attempt)
        return min(delay, self._max_retry_delay)


def _redirect_method(method: str, status_code: int) -> str:
    if status_code == 303 or (status_code in {301, 302} and method not in {"GET", "HEAD"}):
        return "GET"
    return method


def _query_parameters(
    parameters: Mapping[str, object] | None,
) -> dict[str, HttpQueryValue] | None:
    if parameters is None:
        return None
    result: dict[str, HttpQueryValue] = {}
    for key, value in parameters.items():
        if value is None or isinstance(value, (str, int, float, bool)):
            result[str(key)] = value
            continue
        if isinstance(value, (list, tuple)):
            values: list[str | int | float | bool | None] = []
            for item in value:
                if not (item is None or isinstance(item, (str, int, float, bool))):
                    raise HttpTransportError("HTTP_PARAMETERS_INVALID")
                values.append(item)
            result[str(key)] = values
            continue
        raise HttpTransportError("HTTP_PARAMETERS_INVALID")
    return result


def _retry_after_seconds(value: str) -> float | None:
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            delay = (parsed - datetime.now(UTC)).total_seconds()
            return max(0.0, float(delay))
        except (TypeError, ValueError, OverflowError):
            return None


__all__ = ["HttpResponseMetadata", "HttpTransport", "HttpTransportError", "SafeHttpResponse"]
