from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commander_ai.adapters.http.transport import HttpTransportError
from commander_ai.adapters.sources.commander_spellbook.client import (
    CommanderSpellbookClient,
)
from commander_ai.adapters.sources.commander_spellbook.downloader import (
    CommanderSpellbookDownloader,
    CommanderSpellbookDownloadError,
)
from commander_ai.adapters.sources.commander_spellbook.settings import (
    CommanderSpellbookSettings,
)
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


def _registry(
    status: SourceApprovalStatus = SourceApprovalStatus.APPROVED_LOCAL,
    *,
    current_status: str = "ALLOWED",
    max_pages: int = 100,
    max_retries: int = 1,
    max_download_bytes: int = 1_000_000,
    filters: dict[str, object] | None = None,
    endpoints: tuple[str, ...] = ("https://backend.commanderspellbook.com",),
    host_allowlist: tuple[str, ...] = ("backend.commanderspellbook.com",),
) -> SourceRegistry:
    redistribution = (
        "approved" if status is SourceApprovalStatus.APPROVED_REDISTRIBUTION else "review_required"
    )
    settings = SourceSettings(
        source_id="commander_spellbook",
        approval_status=status,
        access_method="rest_api_or_approved_export",
        review_path="docs/03-data/source-reviews/commander-spellbook.md",
        endpoints=endpoints,
        host_allowlist=host_allowlist,
        timeout_seconds=2,
        max_retries=max_retries,
        rate_limit_per_minute=10_000,
        max_pages=max_pages,
        max_download_bytes=max_download_bytes,
        attribution_required=True,
        raw_storage="allowed_local",
        redistribution=redistribution,
        filters=filters or {"documented_read_contracts": ["cards", "variants"]},
        features={"combos": True, "variants": True},
    )
    historical = HistoricalApprovalMetadata(
        source_id="commander_spellbook",
        approval_status=status,
        review_path="docs/03-data/source-reviews/commander-spellbook.md",
        reviewed_at=EFFECTIVE_AT,
        effective_at=EFFECTIVE_AT,
        reason="fixture source review",
        official_docs=("https://spacecowmedia.github.io/commander-spellbook-backend/api.html",),
        terms_reference="https://terms.fixture.invalid/commander-spellbook",
        attribution_required=True,
        raw_local_storage="allowed_local",
        redistribution_raw=redistribution,
        redistribution_derived=redistribution,
    )
    current = CurrentUseDecision(
        source_id="commander_spellbook",
        status=current_status,
        approval_status=status,
        reason="fixture current-use decision",
        effective_at=EFFECTIVE_AT,
    )
    return SourceRegistry(
        entries=(
            SourceRegistryEntry(
                source_id="commander_spellbook",
                settings=settings,
                historical_approval=historical,
                current_use=current,
            ),
        )
    )


def _adapter(
    tmp_path: Path,
    handler,
    *,
    status: SourceApprovalStatus = SourceApprovalStatus.APPROVED_LOCAL,
    current_status: str = "ALLOWED",
    max_pages: int = 100,
    max_retries: int = 1,
    max_download_bytes: int = 1_000_000,
    filters: dict[str, object] | None = None,
):
    registry = _registry(
        status,
        current_status=current_status,
        max_pages=max_pages,
        max_retries=max_retries,
        max_download_bytes=max_download_bytes,
        filters=filters,
    )
    source = registry.lookup("commander_spellbook").settings
    settings = CommanderSpellbookSettings.from_source_settings(source)
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport, follow_redirects=False)
    client = CommanderSpellbookClient(settings, http_client=http_client)
    adapter = CommanderSpellbookDownloader(
        settings=settings,
        policy=SourcePolicy(registry),
        store=RawSnapshotStore(tmp_path, max_object_bytes=source.max_download_bytes),
        client=client,
    )
    return adapter, http_client, settings


def _page(contract: str, page: int, *, next_page: str | None = None) -> bytes:
    if contract == "cards":
        records = [{"id": page, "name": f"Card {page}"}]
    else:
        records = [
            {
                "id": page,
                "uses": [],
                "requires": [],
                "produces": [],
                "status": "LEGAL",
                "of": [{"id": 9000 + page}],
            }
        ]
    return json.dumps(
        {"count": 1, "next": next_page, "previous": None, "results": records},
        separators=(",", ":"),
    ).encode("utf-8")


def test_settings_admit_only_documented_contracts_and_build_allowlisted_api_urls() -> None:
    source = _registry().lookup("commander_spellbook").settings
    settings = CommanderSpellbookSettings.from_source_settings(source)

    assert settings.contracts == ("cards", "variants")
    assert settings.endpoint("cards") == "https://backend.commanderspellbook.com/api/cards/"
    assert settings.endpoint("variants") == "https://backend.commanderspellbook.com/api/variants/"
    assert settings.source.max_pages == 100
    assert settings.source.max_download_bytes == 1_000_000

    with pytest.raises(ValueError, match="unknown Commander Spellbook filter"):
        CommanderSpellbookSettings.from_source_settings(
            source.model_copy(update={"filters": {"undocumented": True}})
        )
    with pytest.raises(ValueError):
        CommanderSpellbookSettings.from_source_settings(
            source.model_copy(update={"filters": {"documented_read_contracts": ["features"]}})
        )
    with pytest.raises(ValueError, match="credentials"):
        CommanderSpellbookSettings.from_source_settings(
            source.model_copy(update={"api_key_env": "SPELLBOOK_API_KEY"})
        )


def test_downloader_persists_exact_raw_pages_with_policy_lineage_and_no_live_network(
    tmp_path: Path,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        contract = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        body = _page(contract, int(request.url.params.get("page", "1")))
        return httpx.Response(
            200,
            headers={"content-type": "application/json", "content-length": str(len(body))},
            stream=httpx.ByteStream(body),
            request=request,
        )

    adapter, http_client, settings = _adapter(tmp_path, handler)
    try:
        result = adapter.download(snapshot_id="spellbook-download")
    finally:
        http_client.close()

    manifest = RawSnapshotStore(tmp_path).load_manifest("commander_spellbook", "spellbook-download")
    assert manifest.status == "COMPLETE"
    assert result.raw_object_ids == ("cards-page-1.json", "variants-page-1.json")
    assert len(calls) == 2
    assert all("backend.commanderspellbook.com" in call for call in calls)
    assert manifest.approval_status == "APPROVED_LOCAL"
    assert manifest.attribution_required is True
    assert manifest.terms_reference == "https://terms.fixture.invalid/commander-spellbook"
    assert manifest.redistribution_status == "not_approved"
    assert all(item.format == "json" for item in manifest.requests)
    assert all(
        (tmp_path / "raw" / "commander_spellbook" / "spellbook-download" / item.path).read_bytes()
        == _page(item.source_object_id or "", 1)
        for item in manifest.objects
    )
    assert settings.adapter_version == "commander-spellbook-v1"


def test_downloader_fails_closed_at_configured_page_bound(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        contract = request.url.path.rstrip("/").rsplit("/", 1)[-1]
        return httpx.Response(
            200,
            stream=httpx.ByteStream(_page(contract, 1, next_page="next")),
            request=request,
        )

    adapter, http_client, _ = _adapter(tmp_path, handler, max_pages=1)
    try:
        with pytest.raises(CommanderSpellbookDownloadError) as error:
            adapter.download(snapshot_id="spellbook-page-bound")
    finally:
        http_client.close()

    assert error.value.code == "SPELLBOOK_PAGE_LIMIT_EXCEEDED"
    assert calls == 1
    manifest = RawSnapshotStore(tmp_path).load_manifest(
        "commander_spellbook", "spellbook-page-bound"
    )
    assert manifest.status == "FAILED"


@pytest.mark.parametrize(
    "status",
    [
        SourceApprovalStatus.PROPOSED,
        SourceApprovalStatus.REVIEWED,
        SourceApprovalStatus.REJECTED,
        SourceApprovalStatus.PAUSED,
    ],
)
def test_downloader_blocks_unapproved_historical_sources_without_request(
    tmp_path: Path, status: SourceApprovalStatus
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"must not be requested", request=request)

    adapter, http_client, _ = _adapter(tmp_path, handler, status=status)
    try:
        with pytest.raises(SourcePolicyError) as error:
            adapter.download(snapshot_id=f"spellbook-blocked-{status.value.lower()}")
    finally:
        http_client.close()
    assert error.value.code == "POLICY_SOURCE_NOT_APPROVED"
    assert calls == 0


def test_downloader_blocks_current_use_without_request(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"must not be requested", request=request)

    adapter, http_client, _ = _adapter(tmp_path, handler, current_status="REJECTED")
    try:
        with pytest.raises(SourcePolicyError) as error:
            adapter.download(snapshot_id="spellbook-current-blocked")
    finally:
        http_client.close()
    assert error.value.code == "POLICY_CURRENT_USE_BLOCKED"
    assert calls == 0


def test_client_retries_are_bounded_and_never_fall_back_to_live_network(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, content=b"retry", request=request)

    adapter, http_client, _ = _adapter(tmp_path, handler, max_retries=2)
    try:
        with pytest.raises(HttpTransportError) as error:
            adapter.client.fetch("cards", page=1)
    finally:
        http_client.close()
    assert error.value.code == "HTTP_RETRIES_EXHAUSTED"
    assert calls == 3


def test_client_enforces_the_configured_response_byte_bound(tmp_path: Path) -> None:
    body = b"x" * 128

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-length": str(len(body))},
            stream=httpx.ByteStream(body),
            request=request,
        )

    adapter, http_client, _ = _adapter(
        tmp_path,
        handler,
        max_download_bytes=32,
    )
    try:
        with pytest.raises(HttpTransportError) as error:
            adapter.client.fetch("cards", page=1)
    finally:
        http_client.close()
    assert error.value.code == "HTTP_RESPONSE_TOO_LARGE"


def test_client_rejects_disallowed_redirect_history() -> None:
    source = _registry().lookup("commander_spellbook").settings
    settings = CommanderSpellbookSettings.from_source_settings(source)

    class HistoryInjectingClient(httpx.Client):
        def send(self, request: httpx.Request, *args: object, **kwargs: object) -> httpx.Response:
            response = httpx.Response(200, content=b"{}", request=request)
            response.history = [
                httpx.Response(
                    302,
                    headers={"location": "https://evil.invalid/redirected"},
                    request=request,
                )
            ]
            return response

    http_client = HistoryInjectingClient(follow_redirects=False)
    client = CommanderSpellbookClient(settings, http_client=http_client)
    try:
        with pytest.raises(HttpTransportError) as error:
            client.fetch("variants", page=1)
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "SECURITY_REDIRECT_HOST"


def test_client_rejects_endpoint_host_outside_source_allowlist() -> None:
    with pytest.raises(ValueError):
        _registry(
            endpoints=("https://evil.invalid",),
            host_allowlist=("backend.commanderspellbook.com",),
        )
