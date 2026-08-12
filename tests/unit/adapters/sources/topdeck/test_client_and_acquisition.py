from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commander_ai.adapters.sources.topdeck.client import TopDeckClient
from commander_ai.adapters.sources.topdeck.downloader import TopDeckDownloader
from commander_ai.adapters.sources.topdeck.errors import TopDeckClientError
from commander_ai.adapters.sources.topdeck.settings import TopDeckSettings
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config.current_use_policy import CurrentUseDecision
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings

EFFECTIVE_AT = datetime(2026, 8, 10, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "topdeck"


def _registry(
    status: SourceApprovalStatus = SourceApprovalStatus.APPROVED_LOCAL,
    *,
    current_status: str = "ALLOWED",
    filters: dict[str, object] | None = None,
) -> SourceRegistry:
    redistribution = (
        "approved" if status is SourceApprovalStatus.APPROVED_REDISTRIBUTION else "review_required"
    )
    settings = SourceSettings(
        source_id="topdeck",
        approval_status=status,
        access_method="tournaments_v2_api",
        review_path="docs/03-data/source-reviews/topdeck.md",
        endpoints=("https://topdeck.gg",),
        host_allowlist=("topdeck.gg",),
        api_key_env="TOPDECK_API_KEY",
        timeout_seconds=2,
        max_retries=1,
        rate_limit_per_minute=10_000,
        max_pages=100,
        max_download_bytes=1_000_000,
        attribution_required=True,
        raw_storage="allowed_local",
        redistribution=redistribution,
        filters=filters or {"game": "Magic: The Gathering", "formats": ["EDH"]},
    )
    historical = HistoricalApprovalMetadata(
        source_id="topdeck",
        approval_status=status,
        review_path="docs/03-data/source-reviews/topdeck.md",
        reviewed_at=EFFECTIVE_AT,
        effective_at=EFFECTIVE_AT,
        reason="fixture source review",
        official_docs=("https://topdeck.gg/docs/tournaments-v2",),
        terms_reference="https://terms.fixture.invalid/topdeck",
        attribution_required=True,
        raw_local_storage="allowed_local",
        redistribution_raw=redistribution,
        redistribution_derived=redistribution,
    )
    current = CurrentUseDecision(
        source_id="topdeck",
        status=current_status,
        approval_status=status,
        reason="fixture current-use decision",
        effective_at=EFFECTIVE_AT,
    )
    return SourceRegistry(
        entries=(
            SourceRegistryEntry(
                source_id="topdeck",
                settings=settings,
                historical_approval=historical,
                current_use=current,
            ),
        )
    )


def _settings(
    status: SourceApprovalStatus = SourceApprovalStatus.APPROVED_LOCAL,
) -> TopDeckSettings:
    return TopDeckSettings.from_source_settings(_registry(status).lookup("topdeck").settings)


def _fixture() -> bytes:
    return (FIXTURE_ROOT / "valid_tournaments.json").read_bytes()


def test_settings_use_documented_endpoint_and_reject_unknown_filters() -> None:
    settings = _settings()
    assert settings.endpoint == "https://topdeck.gg/api/v2/tournaments"
    assert settings.request_parameters() == {
        "format": "EDH",
        "game": "Magic: The Gathering",
    }
    with pytest.raises(ValueError, match="unknown TopDeck filter"):
        TopDeckSettings.from_source_settings(
            _registry(filters={"undocumented": True}).lookup("topdeck").settings
        )


def test_missing_credential_fails_before_network_and_never_echoes_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=httpx.ByteStream(b"[]"), request=request)

    settings = _settings()
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = TopDeckClient(settings, policy=SourcePolicy(_registry()), http_client=http_client)
    monkeypatch.delenv("TOPDECK_API_KEY", raising=False)
    try:
        request = client.build_request(settings.request_parameters())
        with pytest.raises(TopDeckClientError) as error:
            client.fetch_tournaments(request)
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "TOPDECK_CREDENTIAL_MISSING"
    assert "TOPDECK_API_KEY" not in str(error.value)
    assert calls == 0


def test_credential_is_only_sent_in_authorization_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "fixture-api-secret"
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        assert request.headers["authorization"] == secret
        assert request.headers["content-type"] == "application/json"
        assert "cookie" not in request.headers
        assert secret.encode() not in request.content
        assert json.loads(request.content) == {
            "format": "EDH",
            "game": "Magic: The Gathering",
        }
        return httpx.Response(200, stream=httpx.ByteStream(b"[]"), request=request)

    monkeypatch.setenv("TOPDECK_API_KEY", secret)
    settings = _settings()
    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        headers={"Authorization": "wrong-default", "Cookie": "session=wrong-default"},
    )
    client = TopDeckClient(settings, policy=SourcePolicy(_registry()), http_client=http_client)
    try:
        request = client.build_request(settings.request_parameters())
        metadata = client.request_metadata(request)
        response = client.fetch_tournaments(request)
        assert b"".join(response.iter_raw()) == b"[]"
    finally:
        client.close()
        http_client.close()
    assert secret not in json.dumps(metadata)
    assert metadata["request_body_sha256"] == request.body_sha256
    assert len(observed) == 1


@pytest.mark.parametrize(
    "status",
    [SourceApprovalStatus.PROPOSED, SourceApprovalStatus.REVIEWED],
)
def test_unapproved_status_blocks_before_any_request(
    tmp_path: Path,
    status: SourceApprovalStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_fixture(), request=request)

    monkeypatch.setenv("TOPDECK_API_KEY", "should-not-be-read")
    registry = _registry(status)
    settings = TopDeckSettings.from_source_settings(registry.lookup("topdeck").settings)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = TopDeckClient(settings, policy=SourcePolicy(registry), http_client=http_client)
    downloader = TopDeckDownloader(
        settings=settings,
        policy=SourcePolicy(registry),
        store=RawSnapshotStore(tmp_path),
        client=client,
    )
    try:
        with pytest.raises(SourcePolicyError) as error:
            downloader.download(snapshot_id=f"blocked-{status.value.lower()}")
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "POLICY_SOURCE_NOT_APPROVED"
    assert calls == 0


@pytest.mark.parametrize(
    "status",
    [
        SourceApprovalStatus.PROPOSED,
        SourceApprovalStatus.REVIEWED,
        SourceApprovalStatus.REJECTED,
        SourceApprovalStatus.PAUSED,
    ],
)
def test_direct_client_is_gate_protected_before_credentials(
    status: SourceApprovalStatus,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=httpx.ByteStream(b"[]"), request=request)

    registry = _registry(status)
    settings = TopDeckSettings.from_source_settings(registry.lookup("topdeck").settings)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = TopDeckClient(settings, policy=SourcePolicy(registry), http_client=http_client)
    monkeypatch.delenv("TOPDECK_API_KEY", raising=False)
    try:
        request = client.build_request(settings.request_parameters())
        with pytest.raises(TopDeckClientError) as error:
            client.fetch_tournaments(request)
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "POLICY_SOURCE_NOT_APPROVED"
    assert calls == 0


def test_multiple_source_formats_fan_out_to_singular_documented_bodies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = b"[]"
    bodies: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return httpx.Response(200, stream=httpx.ByteStream(raw), request=request)

    monkeypatch.setenv("TOPDECK_API_KEY", "fixture-api-secret")
    registry = _registry(filters={"game": "Magic: The Gathering", "formats": ["EDH", "Casual EDH"]})
    settings = TopDeckSettings.from_source_settings(registry.lookup("topdeck").settings)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = TopDeckClient(settings, policy=SourcePolicy(registry), http_client=http_client)
    try:
        result = TopDeckDownloader(
            settings=settings,
            policy=SourcePolicy(registry),
            store=RawSnapshotStore(tmp_path),
            client=client,
        ).download(snapshot_id="topdeck-multi-format")
    finally:
        client.close()
        http_client.close()
    assert bodies == [
        {"format": "Casual EDH", "game": "Magic: The Gathering"},
        {"format": "EDH", "game": "Magic: The Gathering"},
    ]
    assert result.raw_object_ids == ("tournaments-v2-1.json", "tournaments-v2-2.json")


def test_redirect_is_rejected_before_following_even_on_allowlisted_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            307,
            headers={"location": "https://topdeck.gg/api/v2/tournaments?next=1"},
            stream=httpx.ByteStream(b""),
            request=request,
        )

    monkeypatch.setenv("TOPDECK_API_KEY", "fixture-api-secret")
    settings = _settings()
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = TopDeckClient(settings, policy=SourcePolicy(_registry()), http_client=http_client)
    try:
        request = client.build_request(settings.request_parameters())
        with pytest.raises(TopDeckClientError) as error:
            client.fetch_tournaments(request)
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "HTTP_REDIRECT_LIMIT"
    assert calls == 1


def test_approved_download_preserves_exact_response_and_safe_request_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "fixture-api-secret"
    raw = _fixture()
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-length": str(len(raw))},
            stream=httpx.ByteStream(raw),
            request=request,
        )

    monkeypatch.setenv("TOPDECK_API_KEY", secret)
    registry = _registry()
    settings = TopDeckSettings.from_source_settings(registry.lookup("topdeck").settings)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = TopDeckClient(settings, policy=SourcePolicy(registry), http_client=http_client)
    downloader = TopDeckDownloader(
        settings=settings,
        policy=SourcePolicy(registry),
        store=RawSnapshotStore(tmp_path),
        client=client,
    )
    try:
        result = downloader.download(snapshot_id="topdeck-fixture")
    finally:
        client.close()
        http_client.close()
    manifest = RawSnapshotStore(tmp_path).load_manifest("topdeck", "topdeck-fixture")
    raw_path = tmp_path / "raw" / "topdeck" / "topdeck-fixture" / "objects" / "tournaments-v2.json"
    assert result.raw_object_ids == ("tournaments-v2.json",)
    assert manifest.status == "COMPLETE"
    assert raw_path.read_bytes() == raw
    assert manifest.requests[0].sanitized_method == "POST"
    assert manifest.requests[0].sanitized_parameters["format"] == "EDH"
    assert manifest.requests[0].request_body_sha256
    assert secret not in json.dumps(manifest.model_dump(mode="json"))
    assert observed[0].headers["authorization"] == secret
