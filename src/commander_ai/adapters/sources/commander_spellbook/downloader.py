"""Bounded Commander Spellbook acquisition into immutable raw snapshots."""

from __future__ import annotations

from dataclasses import dataclass

from commander_ai.adapters.http.transport import HttpTransportError
from commander_ai.adapters.storage.raw_snapshot_errors import RawSnapshotError
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.raw_snapshots import RawSnapshotWriter, SnapshotCommit
from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config.current_use_policy import PolicyOperation
from commander_ai.domain.provenance import SourceSnapshotManifest

from .client import CommanderSpellbookClient
from .errors import (
    CommanderSpellbookClientError,
    CommanderSpellbookDownloadError,
)
from .settings import (
    DOCUMENTED_BULK_OBJECT_ID,
    CommanderSpellbookSettings,
)


@dataclass(frozen=True, slots=True)
class CommanderSpellbookDownloadResult:
    snapshot_commit: SnapshotCommit
    manifest: SourceSnapshotManifest
    raw_object_ids: tuple[str, ...]


class CommanderSpellbookDownloader:
    """Acquire the documented bulk JSON with shared policy and storage gates."""

    def __init__(
        self,
        *,
        settings: CommanderSpellbookSettings,
        policy: SourcePolicy,
        store: RawSnapshotStore,
        client: CommanderSpellbookClient | None = None,
    ) -> None:
        self.settings = settings
        self.policy = policy
        self.store = store
        candidate = client or CommanderSpellbookClient(settings, policy=policy)
        if (
            not isinstance(candidate, CommanderSpellbookClient)
            or candidate.settings != settings
            or not candidate.matches_settings(settings)
        ):
            if isinstance(candidate, CommanderSpellbookClient):
                candidate.close()
            raise CommanderSpellbookDownloadError("SPELLBOOK_CLIENT_CONFIGURATION_MISMATCH")
        self.client = candidate

    def download(self, *, snapshot_id: str | None = None) -> CommanderSpellbookDownloadResult:
        if not self.client.matches_settings(self.settings):
            raise CommanderSpellbookDownloadError("SPELLBOOK_CLIENT_CONFIGURATION_MISMATCH")
        configuration = self.policy.adapter_configuration(self.settings.source.source_id)
        if configuration.source != self.settings.source:
            raise CommanderSpellbookDownloadError("POLICY_CONFIGURATION_MISMATCH")
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
            pagination_state={"mode": "bulk_json", "product": self.settings.bulk_product},
            max_object_bytes=self.settings.max_response_bytes,
        )
        try:
            request_id = "commander-spellbook-bulk-variants"
            writer.add_request(
                {
                    "request_id": request_id,
                    **self.client.request_bulk_metadata(),
                }
            )
            response = self.client.fetch_bulk()
            try:
                writer.write_object(
                    raw_object_id=DOCUMENTED_BULK_OBJECT_ID,
                    request_id=request_id,
                    chunks=response.iter_raw(),
                    content_type=response.metadata.content_type,
                    content_encoding=response.metadata.content_encoding,
                    source_object_id="variants",
                )
            finally:
                response.close()
            commit = writer.finalize()
        except (
            CommanderSpellbookClientError,
            CommanderSpellbookDownloadError,
            HttpTransportError,
            RawSnapshotError,
        ):
            self._fail_if_open(writer)
            raise
        except (OSError, TypeError, ValueError):
            self._fail_if_open(writer)
            raise CommanderSpellbookDownloadError("SPELLBOOK_DOWNLOAD_FAILED") from None
        return CommanderSpellbookDownloadResult(
            snapshot_commit=commit,
            manifest=writer.manifest,
            raw_object_ids=(DOCUMENTED_BULK_OBJECT_ID,),
        )

    def acquire(self, *, snapshot_id: str | None = None) -> CommanderSpellbookDownloadResult:
        """Alias using the source-review term for a raw acquisition operation."""

        return self.download(snapshot_id=snapshot_id)

    @staticmethod
    def _fail_if_open(writer: RawSnapshotWriter) -> None:
        if writer.state == "INCOMPLETE":
            writer._fail("SPELLBOOK_DOWNLOAD_FAILED", "Commander Spellbook acquisition failed")


__all__ = [
    "CommanderSpellbookDownloadError",
    "CommanderSpellbookDownloadResult",
    "CommanderSpellbookDownloader",
]
