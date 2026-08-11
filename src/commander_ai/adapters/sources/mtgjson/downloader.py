"""Policy-gated MTGJSON acquisition through shared immutable raw snapshots."""

from __future__ import annotations

import re
from dataclasses import dataclass

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
        client: MTGJSONClient,
    ) -> None:
        self.settings = settings
        self.policy = policy
        self.store = store
        self.client = client

    def download(self, *, snapshot_id: str | None = None) -> MTGJSONDownloadResult:
        configuration = self.policy.adapter_configuration(self.settings.source.source_id)
        if configuration.source != self.settings.source:
            raise MTGJSONDownloadError("POLICY_CONFIGURATION_MISMATCH")
        decision = self.policy.require_operation(
            self.settings.source.source_id,
            PolicyOperation.SOURCE_SYNC,
        )
        writer = self.store.start_snapshot(
            source_id=self.settings.source.source_id,
            snapshot_id=snapshot_id,
            approval_status=self.settings.source.approval_status.value,
            adapter_version=self.settings.adapter_version,
            usage_status=decision.code,
            attribution_required=self.settings.source.attribution_required,
            redistribution_status=(
                "approved"
                if self.settings.source.approval_status.value == "APPROVED_REDISTRIBUTION"
                else "derived_only"
            ),
            terms_reference=(
                self.settings.terms_reference or configuration.historical_approval.terms_reference
            ),
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
    ) -> str | None:
        checksum_url = self.settings.checksum_url(product)
        if checksum_url is None:
            return None
        request_id = f"mtgjson-{product.value}-checksum"
        raw_object_id = f"{self.settings.archive_filename(product)}.sha256"
        writer.add_request(
            {
                "request_id": request_id,
                **self.client.request_metadata(product, kind="checksum"),
            }
        )
        response = self.client.fetch_checksum(product)
        try:
            body = b"".join(response.iter_raw())
            content_type = response.metadata.content_type
        finally:
            response.close()
        writer.write_object(
            raw_object_id=raw_object_id,
            request_id=request_id,
            chunks=[body],
            content_type=content_type,
            source_object_id=f"{product.value}.sha256",
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


def _parse_checksum(body: bytes) -> str:
    try:
        tokens = body.decode("ascii").strip().split()
    except UnicodeDecodeError:
        raise ValueError("checksum sidecar is not ASCII") from None
    if len(tokens) not in {1, 2} or re.fullmatch(r"[0-9a-fA-F]{64}", tokens[0]) is None:
        raise ValueError("checksum sidecar does not contain one SHA-256 digest")
    return tokens[0].lower()


__all__ = ["MTGJSONDownloadError", "MTGJSONDownloadResult", "MTGJSONDownloader"]
