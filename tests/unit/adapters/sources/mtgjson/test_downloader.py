from __future__ import annotations

import hashlib
import io
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from commander_ai.adapters.http.transport import HttpTransport, HttpTransportError
from commander_ai.adapters.sources.mtgjson.client import MTGJSONClient
from commander_ai.adapters.sources.mtgjson.downloader import MTGJSONDownloader
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
    settings = SourceSettings(
        source_id="mtgjson",
        approval_status=status,
        review_path="docs/03-data/source-reviews/mtgjson.md",
        endpoints=("https://fixture.invalid/api/v5/",),
        host_allowlist=("fixture.invalid",),
        files=("AllPrintings",),
        max_retries=1,
        rate_limit_per_minute=1,
        max_download_bytes=1_000_000,
        attribution_required=True,
        filters={"archive_extension": ".zip", "checksum_suffix": ".sha256"},
    )
    historical = HistoricalApprovalMetadata(
        source_id="mtgjson",
        approval_status=status,
        review_path="docs/03-data/source-reviews/mtgjson.md",
        reviewed_at=EFFECTIVE_AT,
        effective_at=EFFECTIVE_AT,
        reason="fixture review record",
        attribution_required=True,
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
):
    registry = _registry(status, current_status=current_status)
    source = registry.lookup("mtgjson").settings
    settings = MTGJSONSettings.from_source_settings(source)
    client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    transport = HttpTransport(
        allowed_hosts=set(source.host_allowlist),
        timeout_seconds=source.timeout_seconds,
        max_retries=source.max_retries,
        max_response_bytes=source.max_download_bytes,
        rate_limit_per_minute=None,
        client=client,
        user_agent="CommanderDeckAI/Test-1.0",
    )
    adapter = MTGJSONDownloader(
        settings=settings,
        policy=SourcePolicy(registry),
        store=RawSnapshotStore(tmp_path, max_object_bytes=source.max_download_bytes),
        client=MTGJSONClient(settings, transport),
    )
    return adapter, transport


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
            body = f"{upstream_sha256}  AllPrintings.zip\n".encode("ascii")
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
        item for item in manifest.objects if item.raw_object_id == "AllPrintings.zip"
    )
    assert result.snapshot_commit.source_snapshot_id == "mtgjson-download"
    assert archive_object.sha256 == local_sha256
    assert archive_object.upstream_sha256 == upstream_sha256
    assert archive_object.checksum_verification_status == "verified"


def test_downloader_rejects_checksum_mismatch_without_replacing_authoritative_bytes(
    tmp_path: Path,
) -> None:
    archive = _archive_bytes()

    def handler(request: httpx.Request) -> httpx.Response:
        body = (
            ("0" * 64 + "  AllPrintings.zip\n").encode("ascii")
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
        item for item in manifest.objects if item.raw_object_id == "AllPrintings.zip"
    )
    assert archive_object.sha256 == hashlib.sha256(archive).hexdigest()
    assert archive_object.sha256 != archive_object.upstream_sha256


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
    assert not any(item.raw_object_id == "AllPrintings.zip" for item in manifest.objects)


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
    assert settings.archive_url(MTGJSONProduct.ALL_PRINTINGS).endswith("/AllPrintings.zip")
    assert settings.checksum_url(MTGJSONProduct.ALL_PRINTINGS).endswith("/AllPrintings.zip.sha256")
