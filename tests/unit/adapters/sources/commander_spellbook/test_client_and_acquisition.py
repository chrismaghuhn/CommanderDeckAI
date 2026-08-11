from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commander_ai.adapters.http.transport import HttpTransportError
from commander_ai.adapters.sources.commander_spellbook.client import (
    CommanderSpellbookClient,
    CommanderSpellbookClientError,
)
from commander_ai.adapters.sources.commander_spellbook.downloader import (
    CommanderSpellbookDownloader,
    CommanderSpellbookDownloadError,
)
from commander_ai.adapters.sources.commander_spellbook.settings import (
    CommanderSpellbookSettings,
)
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotIntegrityError, SnapshotVerifier
from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config.current_use_policy import CurrentUseDecision
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings

EFFECTIVE_AT = datetime(2026, 8, 10, tzinfo=UTC)
FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "commander_spellbook"


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


def _fixture(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


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
    with pytest.raises(ValueError):
        CommanderSpellbookSettings(source=source, contracts=("cards",), api_path="/private")
    with pytest.raises(ValueError):
        CommanderSpellbookSettings(
            source=source.model_copy(
                update={"endpoints": ("https://backend.commanderspellbook.com/private",)}
            ),
            contracts=("cards",),
        )


def test_client_revalidates_constructed_settings_before_network_setup() -> None:
    source = _registry().lookup("commander_spellbook").settings
    forged = CommanderSpellbookSettings.model_construct(
        source=source,
        contracts=("cards",),
        api_path="/private",
        adapter_version="commander-spellbook-v1",
    )
    with pytest.raises(CommanderSpellbookClientError) as error:
        CommanderSpellbookClient(forged)
    assert error.value.code == "SPELLBOOK_SETTINGS_INVALID"
    with pytest.raises(ValueError, match="unknown Commander Spellbook filter"):
        CommanderSpellbookSettings(
            source=source.model_copy(update={"filters": {"undocumented": True}}),
            contracts=("cards", "variants"),
        )
    with pytest.raises(ValueError, match="conflicting"):
        CommanderSpellbookSettings(
            source=source.model_copy(update={"filters": {"documented_read_contracts": ["cards"]}}),
            contracts=("variants",),
        )
    with pytest.raises(ValueError, match="credentials"):
        CommanderSpellbookSettings(
            source=source.model_copy(update={"api_key_env": "SPELLBOOK_API_KEY"}),
            contracts=("cards", "variants"),
        )
    with pytest.raises(ValueError, match="bulk files"):
        CommanderSpellbookSettings(
            source=source.model_copy(update={"files": ("cards.json",)}),
            contracts=("cards", "variants"),
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
            stream=httpx.ByteStream(
                _page(
                    contract,
                    1,
                    next_page=(f"https://backend.commanderspellbook.com/api/{contract}/?page=2"),
                )
            ),
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
    ("body", "code"),
    [
        (b'{"results":[', "SPELLBOOK_PAGINATION_INVALID_JSON"),
        (_fixture("malformed_pagination.json"), "SPELLBOOK_PAGINATION_INVALID_LINK"),
        (
            b'{"count":1,"next":null,"previous":null,"results":{}}',
            "SPELLBOOK_PAGINATION_INVALID_SHAPE",
        ),
        (
            b'{"count":1,"next":"https://evil.invalid/api/variants/?page=2","previous":null,"results":[]}',
            "SPELLBOOK_PAGINATION_INVALID_LINK",
        ),
    ],
)
def test_downloader_fails_closed_on_malformed_pagination(
    tmp_path: Path, body: bytes, code: str
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=httpx.ByteStream(body), request=request)

    adapter, http_client, _ = _adapter(tmp_path, handler)
    try:
        with pytest.raises(CommanderSpellbookDownloadError) as error:
            adapter.download(snapshot_id=f"spellbook-malformed-{code.lower()}")
    finally:
        http_client.close()

    assert error.value.code == code
    manifest = RawSnapshotStore(tmp_path).load_manifest(
        "commander_spellbook", f"spellbook-malformed-{code.lower()}"
    )
    assert manifest.status == "FAILED"
    assert len(manifest.objects) == 1
    raw_object = manifest.objects[0]
    assert raw_object.raw_object_id == "cards-page-1.json"
    assert (
        tmp_path / "raw" / "commander_spellbook" / manifest.source_snapshot_id / raw_object.path
    ).read_bytes() == body
    with pytest.raises(SnapshotIntegrityError) as verification_error:
        SnapshotVerifier(tmp_path).verify_complete_snapshot(
            "commander_spellbook", manifest.source_snapshot_id
        )
    assert verification_error.value.code == "INTEGRITY_SNAPSHOT_NOT_COMPLETE"


def test_downloader_preserves_partial_response_evidence_on_stream_failure(
    tmp_path: Path,
) -> None:
    class PartialBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b'{"count":1,"next":'
            raise httpx.ReadError("fixture body failure")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "application/json"},
            stream=PartialBody(),
            request=request,
        )

    adapter, http_client, _ = _adapter(tmp_path, handler)
    try:
        with pytest.raises(HttpTransportError) as error:
            adapter.download(snapshot_id="spellbook-partial-response")
    finally:
        http_client.close()

    assert error.value.code == "HTTP_ENTITY_STREAM_FAILED"
    manifest = RawSnapshotStore(tmp_path).load_manifest(
        "commander_spellbook", "spellbook-partial-response"
    )
    assert manifest.status == "FAILED"
    assert [item.raw_object_id for item in manifest.objects] == ["cards-page-1.partial.json"]
    partial = manifest.objects[0]
    assert (
        tmp_path / "raw" / "commander_spellbook" / manifest.source_snapshot_id / partial.path
    ).read_bytes() == b'{"count":1,"next":'
    with pytest.raises(SnapshotIntegrityError) as verification_error:
        SnapshotVerifier(tmp_path).verify_complete_snapshot(
            "commander_spellbook", manifest.source_snapshot_id
        )
    assert verification_error.value.code == "INTEGRITY_SNAPSHOT_NOT_COMPLETE"


def test_pagination_read_failure_is_not_treated_as_end_of_pagination(tmp_path: Path) -> None:
    adapter, http_client, _ = _adapter(
        tmp_path,
        lambda request: httpx.Response(200, content=_page("cards", 1), request=request),
    )
    try:
        with pytest.raises(CommanderSpellbookDownloadError) as error:
            adapter._has_next_page(tmp_path / "missing-page.json", "cards")
    finally:
        http_client.close()
    assert error.value.code == "SPELLBOOK_PAGINATION_READ_FAILED"


def test_direct_client_calls_enforce_max_pages_before_transport(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=_page("cards", 1), request=request)

    adapter, http_client, _ = _adapter(tmp_path, handler, max_pages=1)
    try:
        for operation in (
            lambda: adapter.client.fetch("cards", page=2),
            lambda: adapter.client.request_metadata("cards", page=2),
        ):
            with pytest.raises(CommanderSpellbookClientError) as error:
                operation()
            assert error.value.code == "SPELLBOOK_PAGE_INVALID"
    finally:
        http_client.close()
    assert calls == 0


def test_downloader_rejects_mismatched_injected_client_settings(tmp_path: Path) -> None:
    registry = _registry(max_pages=1)
    settings = CommanderSpellbookSettings.from_source_settings(
        registry.lookup("commander_spellbook").settings
    )
    mismatched_source = _registry(max_pages=2).lookup("commander_spellbook").settings
    mismatched_settings = CommanderSpellbookSettings.from_source_settings(mismatched_source)
    http_client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=_page("cards", 1), request=request)
        ),
        follow_redirects=False,
    )
    client = CommanderSpellbookClient(mismatched_settings, http_client=http_client)
    try:
        with pytest.raises(CommanderSpellbookDownloadError) as error:
            CommanderSpellbookDownloader(
                settings=settings,
                policy=SourcePolicy(registry),
                store=RawSnapshotStore(tmp_path),
                client=client,
            )
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "SPELLBOOK_CLIENT_CONFIGURATION_MISMATCH"


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


def test_client_rejects_response_path_different_from_source_owned_contract() -> None:
    source = _registry().lookup("commander_spellbook").settings
    settings = CommanderSpellbookSettings.from_source_settings(source)

    class ForeignEndpointClient(httpx.Client):
        def send(self, request: httpx.Request, *args: object, **kwargs: object) -> httpx.Response:
            del request, args, kwargs
            foreign_request = httpx.Request(
                "GET",
                "https://backend.commanderspellbook.com/api/variants/?page=1",
            )
            return httpx.Response(200, content=b"{}", request=foreign_request)

    http_client = ForeignEndpointClient(follow_redirects=False)
    client = CommanderSpellbookClient(settings, http_client=http_client)
    try:
        with pytest.raises(CommanderSpellbookClientError) as error:
            client.fetch("cards", page=1)
    finally:
        client.close()
        http_client.close()
    assert error.value.code == "SPELLBOOK_RESPONSE_ENDPOINT_MISMATCH"


def test_client_rejects_endpoint_host_outside_source_allowlist() -> None:
    with pytest.raises(ValueError):
        _registry(
            endpoints=("https://evil.invalid",),
            host_allowlist=("backend.commanderspellbook.com",),
        )
