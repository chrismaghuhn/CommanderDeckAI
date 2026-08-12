"""Policy-gated MTGJSON acquisition through shared immutable raw snapshots."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from commander_ai.adapters.http.transport import HttpTransportError
from commander_ai.adapters.storage.raw_snapshot_errors import RawSnapshotError
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.raw_snapshots import RawSnapshotWriter, SnapshotCommit
from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.domain.provenance import SourceSnapshotManifest

from .client import MTGJSONClient, MTGJSONClientError
from .settings import MTGJSONProduct, MTGJSONSettings


class MTGJSONDownloadError(RuntimeError):
    """Stable source-specific failure after shared transport/storage cleanup."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class MTGJSONDownloadResult:
    snapshot_commit: SnapshotCommit
    manifest: SourceSnapshotManifest
    archive_object_ids: tuple[str, ...]
    checksum_object_ids: tuple[str, ...]


class MTGJSONDownloader:
    """Acquire only products selected by the approved MTGJSON source settings."""

    def __init__(
        self,
        *,
        settings: MTGJSONSettings,
        policy: SourcePolicy,
        store: RawSnapshotStore,
        client: MTGJSONClient | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        if client is not None and http_client is not None:
            raise MTGJSONDownloadError("MTGJSON_CLIENT_CONFIGURATION_MISMATCH")
        self.settings = settings
        self.policy = policy
        self.store = store
        self.client = client or MTGJSONClient(settings, policy=policy, http_client=http_client)
        if not self.client.matches_settings(settings):
            self.client.close()
            raise MTGJSONDownloadError("MTGJSON_CLIENT_CONFIGURATION_MISMATCH")

    def download(self, *, snapshot_id: str | None = None) -> MTGJSONDownloadResult:
        if not self.client.matches_settings(self.settings):
            raise MTGJSONDownloadError("MTGJSON_CLIENT_CONFIGURATION_MISMATCH")
        configuration = self.policy.adapter_configuration(self.settings.source.source_id)
        if configuration.source != self.settings.source:
            raise MTGJSONDownloadError("POLICY_CONFIGURATION_MISMATCH")
        decision = self.policy.require_operation(
            self.settings.source.source_id,
            PolicyOperation.SOURCE_SYNC,
        )
        historical = configuration.historical_approval
        writer = self.store.start_snapshot(
            source_id=self.settings.source.source_id,
            snapshot_id=snapshot_id,
            approval_status=historical.approval_status.value,
            adapter_version=self.settings.adapter_version,
            usage_status=decision.code,
            attribution_required=configuration.attribution_required,
            redistribution_status=configuration.redistribution_status,
            terms_reference=configuration.terms_reference,
            pagination_state={"products": [product.value for product in self.settings.products]},
            max_object_bytes=self.settings.source.max_download_bytes,
        )
        archive_ids: list[str] = []
        checksum_ids: list[str] = []
        try:
            for product in self.settings.products:
                upstream_sha256 = self._download_checksum(writer, product, checksum_ids)
                archive_id = self.settings.archive_filename(product)
                request_id = f"mtgjson-{product.value}-archive"
                writer.add_request(
                    {
                        "request_id": request_id,
                        **self.client.request_metadata(product, kind="archive"),
                    }
                )
                response = self.client.fetch_archive(product)
                try:
                    writer.write_object(
                        raw_object_id=archive_id,
                        request_id=request_id,
                        chunks=response.iter_raw(),
                        content_type=response.metadata.content_type,
                        source_object_id=product.value,
                        upstream_sha256=upstream_sha256,
                        checksum_verification_status=(
                            "not_provided" if upstream_sha256 is None else "not_checked"
                        ),
                    )
                finally:
                    response.close()
                archive_ids.append(archive_id)
            commit = writer.finalize()
        except (HttpTransportError, RawSnapshotError, MTGJSONClientError):
            self._fail_if_open(writer, "MTGJSON_DOWNLOAD_FAILED")
            raise
        except MTGJSONDownloadError:
            self._fail_if_open(writer, "MTGJSON_DOWNLOAD_FAILED")
            raise
        except (OSError, TypeError, ValueError):
            self._fail_if_open(writer, "MTGJSON_DOWNLOAD_FAILED")
            raise MTGJSONDownloadError("MTGJSON_DOWNLOAD_FAILED") from None
        return MTGJSONDownloadResult(
            snapshot_commit=commit,
            manifest=writer.manifest,
            archive_object_ids=tuple(archive_ids),
            checksum_object_ids=tuple(checksum_ids),
        )

    def _download_checksum(
        self,
        writer: RawSnapshotWriter,
        product: MTGJSONProduct,
        checksum_ids: list[str],
    ) -> str:
        request_id = f"mtgjson-{product.value}-checksum"
        raw_object_id = self.settings.checksum_url(product).rsplit("/", maxsplit=1)[-1]
        writer.add_request(
            {
                "request_id": request_id,
                **self.client.request_metadata(product, kind="checksum"),
            }
        )
        response = self.client.fetch_checksum(product)
        try:
            body = _read_bounded_checksum(response.iter_raw(), self.settings.checksum_max_bytes)
            content_type = response.metadata.content_type
        finally:
            response.close()
        writer.write_object(
            raw_object_id=raw_object_id,
            request_id=request_id,
            chunks=[body],
            content_type=content_type,
            source_object_id=raw_object_id,
            checksum_verification_status="not_applicable",
        )
        checksum_ids.append(raw_object_id)
        try:
            return _parse_checksum(body)
        except ValueError:
            raise MTGJSONDownloadError("MTGJSON_CHECKSUM_INVALID") from None

    @staticmethod
    def _fail_if_open(writer: RawSnapshotWriter, code: str) -> None:
        if writer.state == "INCOMPLETE":
            writer._fail(code, "MTGJSON acquisition failed")


def _read_bounded_checksum(chunks: Iterable[object], max_bytes: int) -> bytes:
    if not isinstance(max_bytes, int) or isinstance(max_bytes, bool) or max_bytes < 1:
        raise MTGJSONDownloadError("MTGJSON_CHECKSUM_LIMIT_INVALID")
    body = bytearray()
    for chunk in chunks:
        if not isinstance(chunk, bytes):
            raise MTGJSONDownloadError("MTGJSON_CHECKSUM_INVALID")
        if len(body) + len(chunk) > max_bytes:
            raise MTGJSONDownloadError("MTGJSON_CHECKSUM_TOO_LARGE")
        body.extend(chunk)
    return bytes(body)


def _parse_checksum(body: bytes) -> str:
    try:
        tokens = body.decode("ascii").strip().split()
    except UnicodeDecodeError:
        raise ValueError("checksum sidecar is not ASCII") from None
    if len(tokens) not in {1, 2} or re.fullmatch(r"[0-9a-fA-F]{64}", tokens[0]) is None:
        raise ValueError("checksum sidecar does not contain one SHA-256 digest")
    return tokens[0].lower()


__all__ = ["MTGJSONDownloadError", "MTGJSONDownloadResult", "MTGJSONDownloader"]
