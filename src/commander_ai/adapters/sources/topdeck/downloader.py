"""Policy-gated TopDeck raw acquisition into immutable snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from commander_ai.adapters.http.transport import HttpTransportError
from commander_ai.adapters.storage.raw_snapshot_errors import RawSnapshotError
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.raw_snapshots import RawSnapshotWriter, SnapshotCommit
from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.domain.provenance import SourceSnapshotManifest

from .client import TopDeckClient
from .errors import TopDeckClientError, TopDeckDownloadError
from .settings import TopDeckSettings


@dataclass(frozen=True, slots=True)
class TopDeckDownloadResult:
    snapshot_commit: SnapshotCommit
    manifest: SourceSnapshotManifest
    raw_object_ids: tuple[str, ...]


class TopDeckDownloader:
    """Acquire one documented Tournaments v2 response after the source gate."""

    def __init__(
        self,
        *,
        settings: TopDeckSettings,
        policy: SourcePolicy,
        store: RawSnapshotStore,
        client: TopDeckClient | None = None,
    ) -> None:
        self.settings = settings
        self.policy = policy
        self.store = store
        candidate = client or TopDeckClient(settings, policy=policy)
        if not isinstance(candidate, TopDeckClient) or not candidate.matches_settings(settings):
            if isinstance(candidate, TopDeckClient):
                candidate.close()
            raise TopDeckDownloadError("TOPDECK_CLIENT_CONFIGURATION_MISMATCH")
        self.client = candidate

    def download(self, *, snapshot_id: str | None = None) -> TopDeckDownloadResult:
        if not self.client.matches_settings(self.settings):
            raise TopDeckDownloadError("TOPDECK_CLIENT_CONFIGURATION_MISMATCH")

        # This is intentionally before credential lookup and before any request.
        configuration = self.policy.adapter_configuration(self.settings.source.source_id)
        if configuration.source != self.settings.source:
            raise TopDeckDownloadError("POLICY_CONFIGURATION_MISMATCH")
        decision = self.policy.require_operation(
            self.settings.source.source_id,
            PolicyOperation.SOURCE_SYNC,
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
        request_parameters = self.settings.request_parameter_sets()
        object_ids: list[str] = []
        try:
            for index, parameters in enumerate(request_parameters, start=1):
                request = self.client.build_request(parameters)
                request_id = f"topdeck-tournaments-v2-{index}"
                object_id = (
                    "tournaments-v2.json"
                    if len(request_parameters) == 1
                    else f"tournaments-v2-{index}.json"
                )
                writer.add_request(
                    {
                        "request_id": request_id,
                        **self.client.request_metadata(request),
                    }
                )
                response = self.client.fetch_tournaments(request)
                try:
                    writer.write_object(
                        raw_object_id=object_id,
                        request_id=request_id,
                        chunks=response.iter_raw(),
                        content_type=response.metadata.content_type,
                        content_encoding=response.metadata.content_encoding,
                        source_object_id="tournaments-v2",
                    )
                finally:
                    response.close()
                object_ids.append(object_id)
            commit = writer.finalize()
        except (
            TopDeckClientError,
            TopDeckDownloadError,
            HttpTransportError,
            RawSnapshotError,
        ):
            self._fail_if_open(writer)
            raise
        except (OSError, TypeError, ValueError):
            self._fail_if_open(writer)
            raise TopDeckDownloadError("TOPDECK_DOWNLOAD_FAILED") from None
        return TopDeckDownloadResult(
            snapshot_commit=commit,
            manifest=writer.manifest,
            raw_object_ids=tuple(object_ids),
        )

    @staticmethod
    def _fail_if_open(writer: RawSnapshotWriter) -> None:
        if writer.state == "INCOMPLETE":
            writer._fail("TOPDECK_DOWNLOAD_FAILED", "TopDeck acquisition failed")


__all__ = ["TopDeckDownloadResult", "TopDeckDownloader"]
