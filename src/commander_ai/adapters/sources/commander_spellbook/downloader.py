"""Bounded Commander Spellbook acquisition into immutable raw snapshots."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

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
from .json_support import DuplicateJSONKey, decode_pagination_json
from .settings import CommanderSpellbookSettings, SpellbookContract


@dataclass(frozen=True, slots=True)
class CommanderSpellbookDownloadResult:
    snapshot_commit: SnapshotCommit
    manifest: SourceSnapshotManifest
    raw_object_ids: tuple[str, ...]


class CommanderSpellbookDownloader:
    """Acquire configured API pages serially with shared policy and storage gates."""

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
        candidate = client or CommanderSpellbookClient(settings)
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
            pagination_state={"contracts": list(self.settings.contracts)},
            max_object_bytes=self.settings.max_response_bytes,
        )
        object_ids: list[str] = []
        try:
            for contract in self.settings.contracts:
                self._download_contract(writer, contract, object_ids)
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
            raw_object_ids=tuple(object_ids),
        )

    def acquire(self, *, snapshot_id: str | None = None) -> CommanderSpellbookDownloadResult:
        """Alias using the source-review term for a raw acquisition operation."""

        return self.download(snapshot_id=snapshot_id)

    def _download_contract(
        self,
        writer: RawSnapshotWriter,
        contract: SpellbookContract,
        object_ids: list[str],
    ) -> None:
        for page in range(1, self.settings.max_pages + 1):
            request_id = f"commander-spellbook-{contract}-page-{page}"
            raw_object_id = f"{contract}-page-{page}.json"
            writer.add_request(
                {
                    "request_id": request_id,
                    **self.client.request_metadata(contract, page=page),
                }
            )
            response = self.client.fetch(contract, page=page)
            try:
                object_writer = writer.open_object(
                    raw_object_id=raw_object_id,
                    request_id=request_id,
                    content_type=response.metadata.content_type,
                    source_object_id=contract,
                )
            except BaseException:
                response.close()
                raise
            try:
                for chunk in response.iter_raw():
                    object_writer.write(chunk)
                reference = object_writer.finalize()
                object_ids.append(reference.raw_object_id)
                if not self._has_next_page(
                    writer.snapshot_dir.joinpath(*reference.path.split("/")),
                    contract,
                    page=page,
                ):
                    return
            except (
                CommanderSpellbookDownloadError,
                HttpTransportError,
                RawSnapshotError,
                OSError,
                ValueError,
            ):
                object_writer.abort()
                raise
            except Exception:
                object_writer.abort()
                raise CommanderSpellbookDownloadError("SPELLBOOK_DOWNLOAD_FAILED") from None
            finally:
                response.close()
        raise CommanderSpellbookDownloadError("SPELLBOOK_PAGE_LIMIT_EXCEEDED")

    def _has_next_page(self, path: Path, contract: SpellbookContract, *, page: int) -> bool:
        """Inspect only persisted bytes to control pagination; never follow a source URL."""

        try:
            raw_bytes = path.read_bytes()
        except OSError:
            raise CommanderSpellbookDownloadError("SPELLBOOK_PAGINATION_READ_FAILED") from None
        try:
            payload = decode_pagination_json(raw_bytes)
        except (DuplicateJSONKey, UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise CommanderSpellbookDownloadError("SPELLBOOK_PAGINATION_INVALID_JSON") from None
        if not isinstance(payload, Mapping) or not {
            "count",
            "next",
            "previous",
            "results",
        }.issubset(payload):
            raise CommanderSpellbookDownloadError("SPELLBOOK_PAGINATION_INVALID_SHAPE")
        count = payload["count"]
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise CommanderSpellbookDownloadError("SPELLBOOK_PAGINATION_INVALID_SHAPE")
        if not isinstance(payload["results"], list):
            raise CommanderSpellbookDownloadError("SPELLBOOK_PAGINATION_INVALID_SHAPE")
        next_link = payload["next"]
        previous_link = payload["previous"]
        try:
            next_page = (
                None
                if next_link is None
                else self.settings.validate_pagination_link(contract, next_link)
            )
            if previous_link is not None:
                self.settings.validate_pagination_link(contract, previous_link)
        except ValueError:
            raise CommanderSpellbookDownloadError("SPELLBOOK_PAGINATION_INVALID_LINK") from None
        if next_page is not None and next_page != page + 1:
            raise CommanderSpellbookDownloadError("SPELLBOOK_PAGINATION_SEQUENCE_MISMATCH")
        return next_page is not None

    @staticmethod
    def _fail_if_open(writer: RawSnapshotWriter) -> None:
        if writer.state == "INCOMPLETE":
            writer._fail("SPELLBOOK_DOWNLOAD_FAILED", "Commander Spellbook acquisition failed")


__all__ = [
    "CommanderSpellbookDownloadError",
    "CommanderSpellbookDownloadResult",
    "CommanderSpellbookDownloader",
]
