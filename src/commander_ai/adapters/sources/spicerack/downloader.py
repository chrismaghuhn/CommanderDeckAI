"""Bounded Spicerack acquisition into shared immutable raw snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from commander_ai.adapters.http.transport import HttpTransportError
from commander_ai.adapters.storage.raw_snapshot_errors import RawSnapshotError
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.raw_snapshots import RawSnapshotWriter, SnapshotCommit
from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.domain.provenance import SourceSnapshotManifest

from .client import SpicerackClient
from .errors import SpicerackClientError, SpicerackDownloadError
from .settings import SpicerackSettings


@dataclass(frozen=True, slots=True)
class SpicerackDownloadResult:
    snapshot_commit: SnapshotCommit
    manifest: SourceSnapshotManifest
    raw_object_ids: tuple[str, ...]


class SpicerackDownloader:
    """Acquire configured pages serially, retaining evidence on failure."""

    def __init__(
        self,
        *,
        settings: SpicerackSettings,
        policy: SourcePolicy,
        store: RawSnapshotStore,
        client: SpicerackClient | None = None,
    ) -> None:
        self.settings = settings
        self.policy = policy
        self.store = store
        candidate = client or SpicerackClient(settings, policy=policy)
        if not isinstance(candidate, SpicerackClient) or not candidate.matches_settings(settings):
            if isinstance(candidate, SpicerackClient):
                candidate.close()
            raise SpicerackDownloadError("SPICERACK_CLIENT_CONFIGURATION_MISMATCH")
        self.client = candidate

    def download(self, *, snapshot_id: str | None = None) -> SpicerackDownloadResult:
        if not self.client.matches_settings(self.settings):
            raise SpicerackDownloadError("SPICERACK_CLIENT_CONFIGURATION_MISMATCH")
        configuration = self.policy.adapter_configuration(self.settings.source.source_id)
        if configuration.source != self.settings.source:
            raise SpicerackDownloadError("POLICY_CONFIGURATION_MISMATCH")
        decision = self.policy.require_operation(
            self.settings.source.source_id, PolicyOperation.SOURCE_SYNC
        )
        writer = self.store.start_snapshot(
            source_id=self.settings.source.source_id,
            snapshot_id=snapshot_id,
            approval_status=configuration.historical_approval.approval_status.value,
            adapter_version=self.settings.adapter_version,
            usage_status=decision.code,
            attribution_required=configuration.attribution_required,
            redistribution_status=configuration.redistribution_status,
            terms_reference=configuration.terms_reference,
            pagination_state={},
            max_object_bytes=self.settings.max_response_bytes,
        )
        object_ids: list[str] = []
        try:
            for selected_format in self.settings.formats:
                self._download_format(writer, selected_format, object_ids)
            commit = writer.finalize()
        except (
            SpicerackClientError,
            SpicerackDownloadError,
            HttpTransportError,
            RawSnapshotError,
        ):
            self._fail_if_open(writer)
            raise
        except (OSError, TypeError, ValueError):
            self._fail_if_open(writer)
            raise SpicerackDownloadError("SPICERACK_DOWNLOAD_FAILED") from None
        return SpicerackDownloadResult(
            snapshot_commit=commit,
            manifest=writer.manifest,
            raw_object_ids=tuple(object_ids),
        )

    def _download_format(
        self,
        writer: RawSnapshotWriter,
        selected_format: str,
        object_ids: list[str],
    ) -> None:
        parameters = self.settings.request_parameters(selected_format=selected_format)
        request = self.client.build_request(parameters)
        request_id = f"spicerack-{selected_format.lower()}"
        raw_object_id = f"{request_id}.{self.settings.response_format}"
        writer.add_request(
            {
                "request_id": request_id,
                **self.client.request_metadata(request),
            }
        )
        response = self.client.fetch_page(request)
        try:
            reference = writer.write_object(
                raw_object_id=raw_object_id,
                request_id=request_id,
                chunks=response.iter_raw(),
                content_type=response.metadata.content_type,
                content_encoding=response.metadata.content_encoding,
                source_object_id="spicerack-public-decklists",
            )
        finally:
            response.close()
        object_ids.append(reference.raw_object_id)

    @staticmethod
    def _fail_if_open(writer: RawSnapshotWriter) -> None:
        if writer.state == "INCOMPLETE":
            writer._fail("SPICERACK_DOWNLOAD_FAILED", "Spicerack acquisition failed")


__all__ = ["SpicerackDownloadError", "SpicerackDownloadResult", "SpicerackDownloader"]
