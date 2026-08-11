"""Explicit source-specific synchronization composition for the CLI."""

from __future__ import annotations

from typing import Protocol, cast

from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.raw_snapshots import SnapshotCommit
from commander_ai.application.ports.source_adapter import SourceSyncResult
from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config import (
    ConfigurationError,
    RuntimeConfig,
    SourceRegistry,
    load_config,
    load_source_settings,
)
from commander_ai.config.source_settings import SourceSettings
from commander_ai.domain.provenance import SourceSnapshotManifest


class _Closable(Protocol):
    def close(self) -> None:
        """Close source transport resources."""


class _DownloadResult(Protocol):
    snapshot_commit: SnapshotCommit
    manifest: SourceSnapshotManifest


class _Downloader(Protocol):
    client: _Closable

    def download(self, *, snapshot_id: str | None = None) -> _DownloadResult:
        """Download one complete snapshot."""


class SourceSyncConfigurationError(ValueError):
    """A safe source-sync configuration failure."""

    code = "POLICY_SOURCE_REGISTRY_REQUIRED"


class ConfiguredSourceSync:
    """Load a full source registry and dispatch only to a known adapter."""

    def __init__(self, runtime: RuntimeConfig) -> None:
        self._runtime = runtime

    def sync_source(self, source_id: str, config_path: str) -> SourceSyncResult:
        try:
            registry = load_config(config_path, SourceRegistry)
        except ConfigurationError as error:
            try:
                load_source_settings(config_path)
            except ConfigurationError:
                raise error from None
            raise SourceSyncConfigurationError from None
        entry = registry.lookup(source_id)
        policy = SourcePolicy(registry)
        store = RawSnapshotStore(
            self._runtime.data_root,
            max_object_bytes=entry.settings.max_download_bytes,
        )
        result = self._download(entry.source_id, entry.settings, policy, store)
        manifest_path = self._runtime.portable_data_path(result.snapshot_commit.manifest_path)
        return SourceSyncResult(
            source_id=result.manifest.source_id,
            snapshot_id=result.manifest.source_snapshot_id,
            status=result.manifest.status,
            manifest_path=manifest_path,
            manifest_sha256=result.snapshot_commit.manifest_sha256,
        )

    @staticmethod
    def _download(
        source_id: str,
        settings: SourceSettings,
        policy: SourcePolicy,
        store: RawSnapshotStore,
    ) -> _DownloadResult:
        downloader: _Downloader
        if source_id == "mtgjson":
            from commander_ai.adapters.sources.mtgjson import MTGJSONDownloader, MTGJSONSettings

            downloader = cast(
                _Downloader,
                MTGJSONDownloader(
                    settings=MTGJSONSettings.from_source_settings(settings),
                    policy=policy,
                    store=store,
                ),
            )
        elif source_id == "commander_spellbook":
            from commander_ai.adapters.sources.commander_spellbook import (
                CommanderSpellbookDownloader,
                CommanderSpellbookSettings,
            )

            downloader = cast(
                _Downloader,
                CommanderSpellbookDownloader(
                    settings=CommanderSpellbookSettings.from_source_settings(settings),
                    policy=policy,
                    store=store,
                ),
            )
        elif source_id == "topdeck":
            from commander_ai.adapters.sources.topdeck import TopDeckDownloader, TopDeckSettings

            downloader = cast(
                _Downloader,
                TopDeckDownloader(
                    settings=TopDeckSettings.from_source_settings(settings),
                    policy=policy,
                    store=store,
                ),
            )
        elif source_id == "spicerack":
            from commander_ai.adapters.sources.spicerack import (
                SpicerackDownloader,
                SpicerackSettings,
            )

            downloader = cast(
                _Downloader,
                SpicerackDownloader(
                    settings=SpicerackSettings.from_source_settings(settings),
                    policy=policy,
                    store=store,
                ),
            )
        else:
            raise ValueError("source adapter is not implemented")
        try:
            return downloader.download()
        finally:
            downloader.client.close()


__all__ = ["ConfiguredSourceSync"]
