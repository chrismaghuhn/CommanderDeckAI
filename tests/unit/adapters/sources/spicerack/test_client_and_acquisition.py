from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commander_ai.adapters.http.transport import HttpTransportError
from commander_ai.adapters.sources.spicerack.client import (
    SpicerackClient,
    SpicerackClientError,
)
from commander_ai.adapters.sources.spicerack.downloader import (
    SpicerackDownloader,
)
from commander_ai.adapters.sources.spicerack.settings import SpicerackSettings
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config.current_use_policy import CurrentUseDecision
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings

FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "spicerack"
EFFECTIVE_AT = datetime(2026, 8, 10, tzinfo=UTC)


def _source_settings(
    status: SourceApprovalStatus = SourceApprovalStatus.APPROVED_LOCAL,
    *,
    max_pages: int = 100,
    max_download_bytes: int = 1_000_000,
) -> SourceSettings:
    return SourceSettings(
        source_id="spicerack",
        approval_status=status,
        review_path="docs/03-data/source-reviews/spicerack.md",
        endpoints=("https://api.spicerack.gg",),
        host_allowlist=("api.spicerack.gg",),
        api_key_env="SPICERACK_API_KEY",
        timeout_seconds=30,
        max_retries=2,
        rate_limit_per_minute=30,
        respect_retry_after=True,
        max_pages=max_pages,
        max_download_bytes=max_download_bytes,
        attribution_required=True,
        raw_storage="allowed_local",
        redistribution=(
            "approved" if status is SourceApprovalStatus.APPROVED_REDISTRIBUTION else "not_approved"
        ),
        filters={"formats": ["COMMANDER2"]},
    )


def _registry(
    status: SourceApprovalStatus = SourceApprovalStatus.APPROVED_LOCAL,
    *,
    current_status: str = "ALLOWED",
    max_pages: int = 100,
    max_download_bytes: int = 1_000_000,
) -> SourceRegistry:
    settings = _source_settings(status, max_pages=max_pages, max_download_bytes=max_download_bytes)
    redistribution = (
        "approved" if status is SourceApprovalStatus.APPROVED_REDISTRIBUTION else "not_approved"
    )
    historical = HistoricalApprovalMetadata(
        source_id="spicerack",
        approval_status=status,
        review_path="docs/03-data/source-reviews/spicerack.md",
        reviewed_at=EFFECTIVE_AT,
        effective_at=EFFECTIVE_AT,
        reason="fixture source review",
        official_docs=("https://docs.spicerack.gg/api-reference/public-decklist-database",),
        terms_reference="https://terms.fixture.invalid/spicerack",
        attribution_required=True,
        raw_local_storage="allowed_local",
        redistribution_raw=redistribution,
        redistribution_derived=redistribution,
    )
    current = CurrentUseDecision(
        source_id="spicerack",
        status=current_status,
        approval_status=status,
        reason="fixture current-use decision",
        effective_at=EFFECTIVE_AT,
    )
    return SourceRegistry(
        entries=(
            SourceRegistryEntry(
                source_id="spicerack",
                settings=settings,
                historical_approval=historical,
                current_use=current,
            ),
        )
    )


def _settings(registry: SourceRegistry | None = None) -> SpicerackSettings:
    source = (registry or _registry()).lookup("spicerack").settings
    return SpicerackSettings.from_source_settings(
        source,
        credential_header="X-API-Key",
        response_format="json",
    )


def _fixture(name: str = "valid_export.json") -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def test_missing_credential_is_stable_and_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=httpx.ByteStream(_fixture()), request=request)

    settings = _settings()
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = SpicerackClient(settings, policy=SourcePolicy(_registry()), http_client=http_client)
    monkeypatch.delenv("SPICERACK_API_KEY", raising=False)
    try:
        request = client.build_request(settings.request_parameters())
        with pytest.raises(SpicerackClientError) as error:
            client.fetch_page(request)
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "SPICERACK_CREDENTIAL_MISSING"
    assert "SPICERACK_API_KEY" not in str(error.value)
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
def test_source_status_blocks_before_any_request(
    status: SourceApprovalStatus, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=httpx.ByteStream(_fixture()), request=request)

    registry = _registry(status)
    settings = _settings(registry)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = SpicerackClient(settings, policy=SourcePolicy(registry), http_client=http_client)
    monkeypatch.setenv("SPICERACK_API_KEY", "must-not-be-read")
    try:
        request = client.build_request(settings.request_parameters())
        with pytest.raises(SourcePolicyError) as error:
            client.fetch_page(request)
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "POLICY_SOURCE_NOT_APPROVED"
    assert calls == 0


def test_credential_only_uses_configured_header_and_strips_sensitive_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "fixture-api-secret"
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        assert request.headers["x-api-key"] == secret
        assert "authorization" not in request.headers
        assert "cookie" not in request.headers
        assert secret.encode() not in request.url.raw_path
        assert request.url.params["event_format"] == "COMMANDER2"
        assert request.url.params["num_days"] == "14"
        assert request.url.params["decklist_as_text"] == "true"
        assert json.loads(_fixture())
        return httpx.Response(200, stream=httpx.ByteStream(_fixture()), request=request)

    monkeypatch.setenv("SPICERACK_API_KEY", secret)
    settings = _settings()
    http_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=False,
        headers={"Authorization": "wrong-default", "Cookie": "session=wrong-default"},
    )
    client = SpicerackClient(settings, policy=SourcePolicy(_registry()), http_client=http_client)
    try:
        response = client.fetch_page(client.build_request(settings.request_parameters()))
        assert b"".join(response.iter_raw()) == _fixture()
    finally:
        client.close()
        http_client.close()
    assert len(observed) == 1


def test_unknown_path_is_rejected_by_the_configured_contract() -> None:
    settings = _settings()
    client = SpicerackClient(settings, policy=SourcePolicy(_registry()))
    try:
        with pytest.raises(SpicerackClientError) as error:
            client.build_request(settings.request_parameters(), path="/undocumented")
    finally:
        client.close()
    assert error.value.code == "SPICERACK_PATH_NOT_CONFIGURED"


def test_settings_reject_unreviewed_same_host_path() -> None:
    with pytest.raises(ValueError, match="reviewed export endpoint"):
        SpicerackSettings.from_source_settings(
            _registry().lookup("spicerack").settings,
            api_path="/api/undocumented-export/",
        )


def test_settings_reject_non_root_base_endpoint() -> None:
    source = (
        _registry()
        .lookup("spicerack")
        .settings.model_copy(update={"endpoints": ("https://api.spicerack.gg/unreviewed-base",)})
    )

    with pytest.raises(ValueError, match="reviewed HTTPS endpoint"):
        SpicerackSettings.from_source_settings(source)


def test_direct_client_rejects_settings_not_bound_to_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _registry()
    source = registry.lookup("spicerack").settings.model_copy(
        update={"filters": {"formats": ["DUEL"]}}
    )
    settings = SpicerackSettings.from_source_settings(source)
    client = SpicerackClient(settings, policy=SourcePolicy(registry))
    monkeypatch.setenv("SPICERACK_API_KEY", "must-not-be-read")
    try:
        request = client.build_request(settings.request_parameters())
        with pytest.raises(SpicerackClientError) as error:
            client.fetch_page(request)
    finally:
        client.close()

    assert error.value.code == "SPICERACK_POLICY_CONFIGURATION_MISMATCH"


def test_fetch_rejects_forged_request_endpoint_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, stream=httpx.ByteStream(_fixture()), request=request)

    settings = _settings()
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = SpicerackClient(settings, policy=SourcePolicy(_registry()), http_client=http_client)
    monkeypatch.setenv("SPICERACK_API_KEY", "must-not-be-read")
    try:
        valid = client.build_request(settings.request_parameters())
        forged = replace(
            valid,
            endpoint="https://api.spicerack.gg/api/other",
        )
        with pytest.raises(SpicerackClientError) as error:
            client.fetch_page(forged)
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "SPICERACK_REQUEST_CONFIGURATION_MISMATCH"
    assert calls == 0


def test_redirect_is_rejected_before_following(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(
            307,
            headers={"location": "https://api.spicerack.gg/other"},
            content=b"",
            request=request,
        )

    monkeypatch.setenv("SPICERACK_API_KEY", "fixture-api-secret")
    settings = _settings()
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = SpicerackClient(settings, policy=SourcePolicy(_registry()), http_client=http_client)
    try:
        with pytest.raises(SpicerackClientError) as error:
            client.fetch_page(client.build_request(settings.request_parameters()))
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "HTTP_REDIRECT_LIMIT"
    assert calls == 1


def test_download_preserves_exact_bytes_and_safe_request_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _fixture()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-length": str(len(raw))},
            stream=httpx.ByteStream(raw),
            request=request,
        )

    monkeypatch.setenv("SPICERACK_API_KEY", "fixture-api-secret")
    registry = _registry()
    settings = _settings(registry)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = SpicerackClient(settings, policy=SourcePolicy(registry), http_client=http_client)
    try:
        result = SpicerackDownloader(
            settings=settings,
            policy=SourcePolicy(registry),
            store=RawSnapshotStore(tmp_path),
            client=client,
        ).download(snapshot_id="spicerack-fixture")
    finally:
        client.close()
        http_client.close()
    manifest = RawSnapshotStore(tmp_path).load_manifest("spicerack", "spicerack-fixture")
    object_path = (
        tmp_path / "raw" / "spicerack" / "spicerack-fixture" / "objects" / result.raw_object_ids[0]
    )
    assert manifest.status == "COMPLETE"
    assert object_path.read_bytes() == raw
    assert manifest.requests[0].sanitized_method == "GET"
    assert manifest.requests[0].sanitized_parameters["event_format"] == "COMMANDER2"
    assert "fixture-api-secret" not in json.dumps(manifest.model_dump(mode="json"))


def test_response_size_limit_fails_closed_and_keeps_failed_snapshot_auditable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _fixture() + b" " * 2048

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(raw), request=request)

    monkeypatch.setenv("SPICERACK_API_KEY", "fixture-api-secret")
    registry = _registry(max_download_bytes=1024)
    settings = _settings(registry)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = SpicerackClient(settings, policy=SourcePolicy(registry), http_client=http_client)
    store = RawSnapshotStore(tmp_path)
    downloader = SpicerackDownloader(
        settings=settings, policy=SourcePolicy(registry), store=store, client=client
    )
    try:
        with pytest.raises(HttpTransportError) as error:
            downloader.download(snapshot_id="spicerack-response-size")
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "HTTP_RESPONSE_TOO_LARGE"
    manifest = store.load_manifest("spicerack", "spicerack-response-size")
    assert manifest.status == "FAILED"
    assert (tmp_path / "raw/spicerack/spicerack-response-size/objects").iterdir()


def test_malformed_export_is_retained_for_parser_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = _fixture("malformed_export.json")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(raw), request=request)

    monkeypatch.setenv("SPICERACK_API_KEY", "fixture-api-secret")
    registry = _registry()
    settings = _settings(registry)
    http_client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    client = SpicerackClient(settings, policy=SourcePolicy(registry), http_client=http_client)
    store = RawSnapshotStore(tmp_path)
    try:
        result = SpicerackDownloader(
            settings=settings,
            policy=SourcePolicy(registry),
            store=store,
            client=client,
        ).download(snapshot_id="spicerack-malformed-export")
    finally:
        client.close()
        http_client.close()
    assert result.manifest.status == "COMPLETE"
    assert store.load_manifest("spicerack", "spicerack-malformed-export").status == "COMPLETE"
