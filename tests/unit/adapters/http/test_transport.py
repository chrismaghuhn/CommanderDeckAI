from __future__ import annotations

import gzip
from collections.abc import Callable

import httpx
import pytest

from commander_ai.adapters.http.transport import HttpTransport, HttpTransportError


def _transport(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    allowed_hosts: set[str] | None = None,
    **kwargs: object,
) -> HttpTransport:
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    transport_kwargs = {"rate_limit_per_minute": None}
    transport_kwargs.update(kwargs)
    return HttpTransport(
        allowed_hosts=allowed_hosts or {"fixture.invalid"},
        client=client,
        user_agent="CommanderDeckAI/Test-1.0",
        **transport_kwargs,
    )


def test_transport_exposes_exact_iter_raw_entity_bytes_and_safe_response_metadata() -> None:
    raw_entity = gzip.compress(b'{"cards":[]}')

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "CommanderDeckAI/Test-1.0"
        return httpx.Response(
            200,
            headers={
                "Content-Type": "application/gzip",
                "Content-Encoding": "gzip",
                "ETag": "etag-1",
                "Authorization": "Bearer secret",
                "Set-Cookie": "session=secret",
            },
            stream=httpx.ByteStream(raw_entity),
            request=request,
        )

    response = _transport(handler).request(
        "GET",
        "https://fixture.invalid/download?api_key=secret&page=1",
        format="archive",
    )

    assert b"".join(response.iter_raw()) == raw_entity
    assert response.metadata.as_dict() == {
        "content_type": "application/gzip",
        "content_encoding": "gzip",
        "etag": "etag-1",
    }
    assert response.sanitized_endpoint == "https://fixture.invalid/download"
    assert "secret" not in repr(response.metadata.as_dict())


def test_redirect_to_non_allowlisted_host_is_rejected_before_following() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            302,
            headers={"Location": "https://evil.invalid/secret?token=secret"},
            request=request,
        )

    transport = _transport(handler)
    with pytest.raises(HttpTransportError) as error:
        transport.request("GET", "https://fixture.invalid/start")

    assert error.value.code == "SECURITY_REDIRECT_HOST"
    assert calls == ["https://fixture.invalid/start"]
    assert "secret" not in str(error.value)


def test_injected_follow_redirects_client_cannot_bypass_manual_host_policy() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) > 1:
            return httpx.Response(200, stream=httpx.ByteStream(b"evil"), request=request)
        return httpx.Response(
            302,
            headers={"Location": "https://evil.invalid/secret"},
            request=request,
        )

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )
    transport = HttpTransport(
        allowed_hosts={"fixture.invalid"},
        client=client,
        rate_limit_per_minute=None,
        user_agent="CommanderDeckAI/Test-1.0",
    )

    with pytest.raises(HttpTransportError) as error:
        transport.request("GET", "https://fixture.invalid/start")

    assert error.value.code == "SECURITY_REDIRECT_HOST"
    assert calls == ["https://fixture.invalid/start"]


def test_sensitive_request_headers_are_stripped_when_redirect_changes_origin() -> None:
    observed: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request.headers)
        if len(observed) == 1:
            return httpx.Response(
                302,
                headers={"Location": "https://cdn.fixture.invalid/final"},
                request=request,
            )
        return httpx.Response(200, stream=httpx.ByteStream(b"ok"), request=request)

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        headers={
            "Authorization": "Bearer client-secret",
            "Cookie": "session=client-secret",
        },
        follow_redirects=True,
    )
    transport = HttpTransport(
        allowed_hosts={"fixture.invalid", "cdn.fixture.invalid"},
        client=client,
        rate_limit_per_minute=None,
        user_agent="CommanderDeckAI/Test-1.0",
    )

    response = transport.request(
        "GET",
        "https://fixture.invalid/start",
        headers={
            "Authorization": "Bearer request-secret",
            "Cookie": "session=request-secret",
            "X-API-Key": "api-secret",
            "X-Signature": "signature-secret",
        },
    )

    assert b"".join(response.iter_raw()) == b"ok"
    assert observed[0].get("authorization") == "Bearer request-secret"
    assert observed[0].get("cookie") == "session=request-secret"
    for header in ("authorization", "cookie", "x-api-key", "x-signature"):
        assert header not in observed[1]


def test_blank_request_user_agent_cannot_override_validated_default() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["user-agent"] == "CommanderDeckAI/Test-1.0"
        return httpx.Response(200, stream=httpx.ByteStream(b"ok"), request=request)

    response = _transport(handler).request(
        "GET",
        "https://fixture.invalid/ua",
        headers={"User-Agent": "   "},
    )

    assert b"".join(response.iter_raw()) == b"ok"


def test_request_metadata_is_an_explicit_safe_projection() -> None:
    transport = _transport(lambda request: httpx.Response(200, request=request))

    metadata = transport.request_metadata(
        "get",
        "https://fixture.invalid/cards?page=2&api_key=url-secret",
        parameters={"page": 2, "api_key": "parameter-secret", "format": "json"},
        api_version="v1",
        format="json",
    )

    assert metadata == {
        "sanitized_method": "GET",
        "sanitized_endpoint": "https://fixture.invalid/cards",
        "api_version": "v1",
        "format": "json",
        "sanitized_parameters": {"format": "json", "page": 2},
    }


def test_redirect_chain_rechecks_every_destination() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if len(calls) == 1:
            return httpx.Response(
                302, headers={"Location": "https://cdn.fixture.invalid/one"}, request=request
            )
        return httpx.Response(
            302,
            headers={"Location": "https://evil.invalid/two"},
            request=request,
        )

    transport = _transport(handler, allowed_hosts={"fixture.invalid", "cdn.fixture.invalid"})
    with pytest.raises(HttpTransportError) as error:
        transport.request("GET", "https://fixture.invalid/start")

    assert error.value.code == "SECURITY_REDIRECT_HOST"
    assert calls == [
        "https://fixture.invalid/start",
        "https://cdn.fixture.invalid/one",
    ]


def test_retry_after_and_bounded_retries_are_respected_without_endless_retry() -> None:
    statuses = iter([429, 503, 200])
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        headers = {"Retry-After": "2"} if status == 429 else {}
        return httpx.Response(
            status, headers=headers, stream=httpx.ByteStream(b"ok"), request=request
        )

    transport = _transport(handler, max_retries=2, sleeper=sleeps.append, backoff_seconds=0.1)
    response = transport.request("GET", "https://fixture.invalid/retry")

    assert b"".join(response.iter_raw()) == b"ok"
    assert sleeps == [2.0, 0.2]

    exhausted_calls = 0

    def always_fail(request: httpx.Request) -> httpx.Response:
        nonlocal exhausted_calls
        exhausted_calls += 1
        return httpx.Response(503, request=request)

    exhausted = _transport(always_fail, max_retries=2, sleeper=lambda _delay: None)
    with pytest.raises(HttpTransportError) as error:
        exhausted.request("GET", "https://fixture.invalid/retry")
    assert error.value.code == "HTTP_RETRIES_EXHAUSTED"
    assert exhausted_calls == 3


@pytest.mark.parametrize("exception_type", [httpx.ConnectError, httpx.ReadTimeout])
def test_connection_and_timeout_failures_are_bounded_and_redacted(
    exception_type: type[Exception],
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise exception_type("transport secret should not escape")

    transport = _transport(handler, max_retries=1, sleeper=lambda _delay: None)
    with pytest.raises(HttpTransportError) as error:
        transport.request(
            "GET",
            "https://fixture.invalid/fail?api_key=transport-secret",
        )

    assert error.value.code in {"HTTP_CONNECTION_FAILED", "HTTP_TIMEOUT"}
    assert calls == 2
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "transport-secret" not in str(error.value)
    assert "transport secret" not in str(error.value)


def test_response_size_limit_is_enforced_while_iterating_raw_bytes() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(b"12345"), request=request)

    response = _transport(handler, max_response_bytes=3).request(
        "GET", "https://fixture.invalid/large"
    )
    with pytest.raises(HttpTransportError) as error:
        list(response.iter_raw())
    assert error.value.code == "HTTP_RESPONSE_TOO_LARGE"


def test_truncated_content_length_is_rejected_after_raw_stream_completion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Length": "5"},
            stream=httpx.ByteStream(b"123"),
            request=request,
        )

    response = _transport(handler).request("GET", "https://fixture.invalid/truncated")
    with pytest.raises(HttpTransportError) as error:
        list(response.iter_raw())
    assert error.value.code == "HTTP_ENTITY_TRUNCATED"


def test_unexpected_body_failure_is_a_sanitized_transport_error() -> None:
    class FailingBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial"
            raise RuntimeError("body-secret")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=FailingBody(), request=request)

    response = _transport(handler).request("GET", "https://fixture.invalid/body")
    with pytest.raises(HttpTransportError) as error:
        list(response.iter_raw())

    assert error.value.code == "HTTP_ENTITY_STREAM_FAILED"
    assert error.value.__cause__ is None
    assert error.value.__context__ is None
    assert "body-secret" not in str(error.value)


def test_transport_error_text_is_sanitized_before_exposure() -> None:
    error = HttpTransportError(
        "HTTP_FAILURE",
        "https://fixture.invalid/path?sig=url-secret Authorization: Bearer header-secret",
    )

    assert "url-secret" not in str(error)
    assert "header-secret" not in str(error)


def test_malformed_redirect_location_is_a_stable_sanitized_transport_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            302,
            headers={"Location": "https://[malformed"},
            request=request,
        )

    transport = _transport(handler)
    with pytest.raises(HttpTransportError) as error:
        transport.request("GET", "https://fixture.invalid/start")

    assert error.value.code == "SECURITY_REDIRECT_URL"
    assert error.value.__cause__ is None


@pytest.mark.parametrize("rate_limit", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_rate_limits_are_rejected(rate_limit: float) -> None:
    with pytest.raises(ValueError):
        _transport(
            lambda request: httpx.Response(200, request=request),
            rate_limit_per_minute=rate_limit,
        )


def test_rate_limit_sleeps_between_requests_without_parallelism() -> None:
    now = 0.0
    sleeps: list[float] = []

    def clock() -> float:
        return now

    def sleep(delay: float) -> None:
        nonlocal now
        sleeps.append(delay)
        now += delay

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(b"ok"), request=request)

    transport = _transport(
        handler,
        rate_limit_per_minute=60,
        clock=clock,
        sleeper=sleep,
    )
    first = transport.request("GET", "https://fixture.invalid/one")
    list(first.iter_raw())
    second = transport.request("GET", "https://fixture.invalid/two")
    list(second.iter_raw())

    assert sleeps == [1.0]
