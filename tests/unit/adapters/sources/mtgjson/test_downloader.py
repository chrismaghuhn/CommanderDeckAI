from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commander_ai.adapters.http.transport import HttpTransportError
from commander_ai.adapters.sources.mtgjson.client import MTGJSONClient, MTGJSONClientError
from commander_ai.adapters.sources.mtgjson.downloader import (
    MTGJSONDownloader,
    MTGJSONDownloadError,
)
from commander_ai.adapters.sources.mtgjson.settings import MTGJSONProduct, MTGJSONSettings
from commander_ai.adapters.storage.raw_snapshot_errors import RawSnapshotError
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


def _archive_bytes() -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("AllPrintings.json", b'{"meta":{},"data":{}}')
    return output.getvalue()


def _registry(status: SourceApprovalStatus, *, current_status: str = "ALLOWED") -> SourceRegistry:
    redistribution = (
        "approved" if status is SourceApprovalStatus.APPROVED_REDISTRIBUTION else "review_required"
    )
    settings = SourceSettings(
        source_id="mtgjson",
        approval_status=status,
        review_path="docs/03-data/source-reviews/mtgjson.md",
        endpoints=("https://fixture.invalid/api/v5/",),
        host_allowlist=("fixture.invalid",),
        files=("AllPrintings",),
        max_retries=1,
        rate_limit_per_minute=10_000,
        max_download_bytes=1_000_000,
        attribution_required=True,
        raw_storage="allowed_local",
        redistribution=redistribution,
        filters={},
    )
    historical = HistoricalApprovalMetadata(
        source_id="mtgjson",
        approval_status=status,
        review_path="docs/03-data/source-reviews/mtgjson.md",
        reviewed_at=EFFECTIVE_AT,
        effective_at=EFFECTIVE_AT,
        reason="fixture review record",
        terms_reference="https://terms.fixture.invalid/mtgjson",
        attribution_required=True,
        raw_local_storage="allowed_local",
        redistribution_raw=redistribution,
        redistribution_derived=redistribution,
    )
    current = CurrentUseDecision(
        source_id="mtgjson",
        status=current_status,
        approval_status=status,
        reason="fixture current-use decision",
        effective_at=EFFECTIVE_AT,
    )
    return SourceRegistry(
        entries=(
            SourceRegistryEntry(
                source_id="mtgjson",
                settings=settings,
                historical_approval=historical,
                current_use=current,
            ),
        )
    )


def _downloader(
    tmp_path: Path,
    handler,
    status: SourceApprovalStatus = SourceApprovalStatus.APPROVED_LOCAL,
    *,
    current_status: str = "ALLOWED",
    filters: dict[str, object] | None = None,
):
    registry = _registry(status, current_status=current_status)
    if filters is not None:
        entry = registry.lookup("mtgjson")
        registry = SourceRegistry(
            entries=(
                entry.model_copy(
                    update={"settings": entry.settings.model_copy(update={"filters": filters})}
                ),
            )
        )
    source = registry.lookup("mtgjson").settings
    settings = MTGJSONSettings.from_source_settings(source)
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    adapter = MTGJSONDownloader(
        settings=settings,
        policy=SourcePolicy(registry),
        store=RawSnapshotStore(tmp_path, max_object_bytes=source.max_download_bytes),
        client=MTGJSONClient(settings, http_client=client),
    )
    return adapter, client


@pytest.mark.parametrize(
    "status",
    [SourceApprovalStatus.APPROVED_LOCAL, SourceApprovalStatus.APPROVED_REDISTRIBUTION],
)
def test_downloader_uses_shared_snapshot_store_and_keeps_upstream_checksum_separate(
    tmp_path: Path, status: SourceApprovalStatus
) -> None:
    archive = _archive_bytes()
    local_sha256 = hashlib.sha256(archive).hexdigest()
    upstream_sha256 = local_sha256

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".sha256"):
            body = f"{upstream_sha256}  AllPrintings.json.zip\n".encode("ascii")
        else:
            body = archive
        return httpx.Response(
            200,
            headers={"Content-Length": str(len(body))},
            stream=httpx.ByteStream(body),
            request=request,
        )

    adapter, transport = _downloader(tmp_path, handler, status)
    try:
        result = adapter.download(snapshot_id="mtgjson-download")
    finally:
        transport.close()

    manifest = RawSnapshotStore(tmp_path).load_manifest("mtgjson", "mtgjson-download")
    archive_object = next(
        item for item in manifest.objects if item.raw_object_id == "AllPrintings.json.zip"
    )
    assert result.snapshot_commit.source_snapshot_id == "mtgjson-download"
    assert archive_object.sha256 == local_sha256
    assert archive_object.upstream_sha256 == upstream_sha256
    assert archive_object.checksum_verification_status == "verified"
    checksum_object = next(
        item for item in manifest.objects if item.raw_object_id == "AllPrintings.json.zip.sha256"
    )
    assert checksum_object.source_object_id == "AllPrintings.json.zip.sha256"
    assert manifest.terms_reference == "https://terms.fixture.invalid/mtgjson"
    assert manifest.attribution_required is True
    assert manifest.redistribution_status == (
        "approved" if status is SourceApprovalStatus.APPROVED_REDISTRIBUTION else "not_approved"
    )


def test_downloader_rejects_checksum_mismatch_without_replacing_authoritative_bytes(
    tmp_path: Path,
) -> None:
    archive = _archive_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            ("0" * 64 + "  AllPrintings.json.zip\n").encode("ascii")
            if request.url.path.endswith(".sha256")
            else archive
        )
        return httpx.Response(200, stream=httpx.ByteStream(body), request=request)

    adapter, transport = _downloader(tmp_path, handler)
    try:
        with pytest.raises(RawSnapshotError) as error:
            adapter.download(snapshot_id="mtgjson-mismatch")
    finally:
        transport.close()

    assert error.value.code == "ACQ_UPSTREAM_CHECKSUM_MISMATCH"
    manifest = RawSnapshotStore(tmp_path).load_manifest("mtgjson", "mtgjson-mismatch")
    assert manifest.status == "FAILED"
    archive_object = next(
        item for item in manifest.objects if item.raw_object_id == "AllPrintings.json.zip"
    )
    assert archive_object.sha256 == hashlib.sha256(archive).hexdigest()
    assert archive_object.sha256 != archive_object.upstream_sha256


def test_downloader_rejects_a_missing_checksum_sidecar_before_archive_persistence(
    tmp_path: Path,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".sha256"):
            return httpx.Response(404, request=request)
        return httpx.Response(200, content=_archive_bytes(), request=request)

    adapter, transport = _downloader(tmp_path, handler)
    try:
        with pytest.raises(HttpTransportError) as error:
            adapter.download(snapshot_id="mtgjson-missing-checksum")
    finally:
        transport.close()

    manifest = RawSnapshotStore(tmp_path).load_manifest("mtgjson", "mtgjson-missing-checksum")
    assert error.value.code == "HTTP_STATUS_ERROR"
    assert manifest.status == "FAILED"
    assert not any(item.raw_object_id == "AllPrintings.json.zip" for item in manifest.objects)


def test_partial_archive_download_is_bounded_and_leaves_no_partial_archive_object(
    tmp_path: Path,
) -> None:
    upstream_sha256 = "b" * 64

    class PartialBody(httpx.SyncByteStream):
        def __iter__(self):
            yield b"partial archive bytes"
            raise httpx.ReadError("fixture body failure")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(".sha256"):
            return httpx.Response(
                200,
                stream=httpx.ByteStream(f"{upstream_sha256}\n".encode("ascii")),
                request=request,
            )
        return httpx.Response(200, stream=PartialBody(), request=request)

    adapter, transport = _downloader(tmp_path, handler)
    try:
        with pytest.raises(HttpTransportError) as error:
            adapter.download(snapshot_id="mtgjson-partial")
    finally:
        transport.close()

    assert error.value.code == "HTTP_ENTITY_STREAM_FAILED"
    manifest = RawSnapshotStore(tmp_path).load_manifest("mtgjson", "mtgjson-partial")
    assert manifest.status == "FAILED"
    assert not any(item.raw_object_id == "AllPrintings.json.zip" for item in manifest.objects)


@pytest.mark.parametrize(
    "status",
    [
        SourceApprovalStatus.PROPOSED,
        SourceApprovalStatus.REVIEWED,
        SourceApprovalStatus.REJECTED,
        SourceApprovalStatus.PAUSED,
    ],
)
def test_downloader_blocks_every_non_allowlisted_historical_status(
    tmp_path: Path, status: SourceApprovalStatus
) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"should not be requested", request=request)

    adapter, transport = _downloader(tmp_path, handler, status)
    try:
        with pytest.raises(SourcePolicyError) as error:
            adapter.download(snapshot_id="mtgjson-blocked")
    finally:
        transport.close()

    assert error.value.code == "POLICY_SOURCE_NOT_APPROVED"
    assert calls == 0


def test_downloader_blocks_a_non_allowlisted_current_use_decision(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, content=b"should not be requested", request=request)

    adapter, transport = _downloader(tmp_path, handler, current_status="REJECTED")
    try:
        with pytest.raises(SourcePolicyError) as error:
            adapter.download(snapshot_id="mtgjson-current-blocked")
    finally:
        transport.close()

    assert error.value.code == "POLICY_CURRENT_USE_BLOCKED"
    assert calls == 0


@pytest.mark.parametrize(
    "status",
    [SourceApprovalStatus.APPROVED_LOCAL, SourceApprovalStatus.APPROVED_REDISTRIBUTION],
)
def test_settings_allow_only_configured_documented_products(status: SourceApprovalStatus) -> None:
    registry = _registry(status)
    settings = MTGJSONSettings.from_source_settings(registry.lookup("mtgjson").settings)

    assert settings.products == (MTGJSONProduct.ALL_PRINTINGS,)
    assert settings.archive_url(MTGJSONProduct.ALL_PRINTINGS).endswith("/AllPrintings.json.zip")
    assert settings.checksum_url(MTGJSONProduct.ALL_PRINTINGS).endswith(
        "/AllPrintings.json.zip.sha256"
    )


def test_mtgjson_settings_reject_unknown_products_filters_and_conflicting_locations() -> None:
    source = _registry(SourceApprovalStatus.APPROVED_LOCAL).lookup("mtgjson").settings

    with pytest.raises(ValueError, match="unknown MTGJSON filter"):
        MTGJSONSettings.from_source_settings(
            source.model_copy(update={"filters": {"unexpected": True}})
        )

    with pytest.raises(ValueError):
        MTGJSONSettings.from_source_settings(source.model_copy(update={"files": ("AtomicCards",)}))

    with pytest.raises(ValueError, match="conflicting"):
        MTGJSONSettings.from_source_settings(
            source.model_copy(
                update={
                    "files": ("AllPrintings",),
                    "filters": {"files": ["AllDeckFiles"]},
                }
            )
        )


@pytest.mark.parametrize("field_name", ["archive_extension", "checksum_suffix"])
@pytest.mark.parametrize("value", [".zip", ".json", ".tar.gz", None])
def test_mtgjson_settings_reject_non_official_file_suffixes(field_name: str, value: object) -> None:
    source = _registry(SourceApprovalStatus.APPROVED_LOCAL).lookup("mtgjson").settings

    with pytest.raises(ValueError):
        MTGJSONSettings.from_source_settings(
            source.model_copy(update={"filters": {field_name: value}})
        )


def test_mtgjson_settings_rejects_disabled_checksum_sidecars() -> None:
    source = _registry(SourceApprovalStatus.APPROVED_LOCAL).lookup("mtgjson").settings

    with pytest.raises(ValueError, match="checksum sidecar"):
        MTGJSONSettings.from_source_settings(
            source.model_copy(update={"filters": {"checksum_required": False}})
        )


def test_mtgjson_downloader_rejects_client_bound_to_another_endpoint() -> None:
    registry = _registry(SourceApprovalStatus.APPROVED_LOCAL)
    settings = MTGJSONSettings.from_source_settings(registry.lookup("mtgjson").settings)
    foreign_source = settings.source.model_copy(
        update={
            "endpoints": ("https://other.invalid/api/v5/",),
            "host_allowlist": ("other.invalid",),
        }
    )
    foreign_settings = MTGJSONSettings.from_source_settings(foreign_source)
    foreign_client = MTGJSONClient(
        foreign_settings,
        http_client=httpx.Client(
            transport=httpx.MockTransport(lambda request: httpx.Response(500))
        ),
    )
    try:
        with pytest.raises(MTGJSONDownloadError, match="MTGJSON_CLIENT_CONFIGURATION_MISMATCH"):
            MTGJSONDownloader(
                settings=settings,
                policy=SourcePolicy(registry),
                store=RawSnapshotStore(".", max_object_bytes=settings.source.max_download_bytes),
                client=foreign_client,
            )
    finally:
        foreign_client.close()


def test_mtgjson_client_rejects_disallowed_redirect_in_injected_response_history() -> None:
    source = _registry(SourceApprovalStatus.APPROVED_LOCAL).lookup("mtgjson").settings
    settings = MTGJSONSettings.from_source_settings(source)

    class HistoryInjectingClient(httpx.Client):
        def send(self, request: httpx.Request, *args: object, **kwargs: object) -> httpx.Response:
            response = httpx.Response(200, content=b"allowed-final", request=request)
            response.history = [
                httpx.Response(
                    302,
                    headers={"location": "https://evil.invalid/redirected"},
                    request=request,
                )
            ]
            return response

    http_client = HistoryInjectingClient(follow_redirects=False)
    client = MTGJSONClient(settings, http_client=http_client)
    try:
        with pytest.raises(HttpTransportError) as error:
            client.fetch_archive(MTGJSONProduct.ALL_PRINTINGS)
    finally:
        client.close()
        http_client.close()

    assert error.value.code == "SECURITY_REDIRECT_HOST"


def test_mtgjson_checksum_limit_is_dedicated_to_small_sidecars() -> None:
    source = _registry(SourceApprovalStatus.APPROVED_LOCAL).lookup("mtgjson").settings
    settings = MTGJSONSettings.from_source_settings(
        source.model_copy(update={"filters": {"checksum_max_bytes": 32}})
    )

    assert settings.checksum_max_bytes == 32
    assert settings.source.max_download_bytes > settings.checksum_max_bytes


def test_mtgjson_client_rejects_injected_response_from_unallowlisted_host() -> None:
    source = _registry(SourceApprovalStatus.APPROVED_LOCAL).lookup("mtgjson").settings
    settings = MTGJSONSettings.from_source_settings(source)
    calls: list[str] = []

    class ReplacingClient(httpx.Client):
        def send(self, request: httpx.Request, *args: object, **kwargs: object) -> httpx.Response:
            calls.append(str(request.url))
            return httpx.Response(
                200,
                stream=httpx.ByteStream(b"replaced"),
                request=httpx.Request("GET", "https://evil.invalid/replaced"),
            )

    http_client = ReplacingClient(follow_redirects=True)
    client = MTGJSONClient(settings, http_client=http_client)
    try:
        with pytest.raises(MTGJSONClientError) as error:
            client.fetch_archive(MTGJSONProduct.ALL_PRINTINGS)
    finally:
        client.close()
        http_client.close()

    assert error.value.code == "MTGJSON_RESPONSE_HOST_NOT_ALLOWLISTED"
    assert calls == ["https://fixture.invalid/api/v5/AllPrintings.json.zip"]


def test_shared_transport_rejects_an_injected_request_url_before_send() -> None:
    source = _registry(SourceApprovalStatus.APPROVED_LOCAL).lookup("mtgjson").settings
    settings = MTGJSONSettings.from_source_settings(source)

    class ReplacingClient(httpx.Client):
        def build_request(self, method: str, url: str, **kwargs: object) -> httpx.Request:
            return httpx.Request(method, "https://evil.invalid/replaced")

        def send(self, request: httpx.Request, *args: object, **kwargs: object) -> httpx.Response:
            raise AssertionError("the policy must reject before send")

    http_client = ReplacingClient()
    client = MTGJSONClient(settings, http_client=http_client)
    try:
        with pytest.raises(HttpTransportError) as error:
            client.fetch_archive(MTGJSONProduct.ALL_PRINTINGS)
    finally:
        client.close()
        http_client.close()

    assert error.value.code == "SECURITY_HOST_NOT_ALLOWLISTED"


def test_oversized_checksum_sidecar_fails_before_archive_object_is_written(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = b"x" * 33 if request.url.path.endswith(".sha256") else _archive_bytes()
        return httpx.Response(200, stream=httpx.ByteStream(body), request=request)

    adapter, client = _downloader(
        tmp_path,
        handler,
        filters={"checksum_max_bytes": 32},
    )
    try:
        with pytest.raises(MTGJSONDownloadError) as error:
            adapter.download(snapshot_id="mtgjson-checksum-limit")
    finally:
        client.close()

    manifest = RawSnapshotStore(tmp_path).load_manifest("mtgjson", "mtgjson-checksum-limit")
    assert error.value.code == "MTGJSON_CHECKSUM_TOO_LARGE"
    assert manifest.status == "FAILED"
    assert not any(item.raw_object_id == "AllPrintings.json.zip" for item in manifest.objects)
