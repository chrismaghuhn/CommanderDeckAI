"""Explicit source-specific synchronization composition for the CLI."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, Protocol, cast

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
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
from commander_ai.config.source_registry import SourceRegistryEntry
from commander_ai.config.source_settings import SourceSettings
from commander_ai.config.yaml_loader import serialize_config
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    build_run_manifest,
)
from commander_ai.domain.provenance import SourceSnapshotManifest, detached_manifest_sha256
from commander_ai.domain.serialization import canonical_json_bytes

from .operation_provenance import operation_context


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
        self._write_run_manifest(entry, result)
        return SourceSyncResult(
            source_id=result.manifest.source_id,
            snapshot_id=result.manifest.source_snapshot_id,
            status=result.manifest.status,
            manifest_path=manifest_path,
            manifest_sha256=result.snapshot_commit.manifest_sha256,
        )

    def _write_run_manifest(self, entry: SourceRegistryEntry, result: _DownloadResult) -> None:
        source_id = result.manifest.source_id
        snapshot_id = result.manifest.source_snapshot_id
        run_id = f"source-sync-{source_id}-{snapshot_id}"
        operation = operation_context(self._runtime.artifact_root, run_id)
        raw_manifest_bytes = Path(result.snapshot_commit.manifest_path).read_bytes()
        try:
            raw_manifest_payload = json.loads(raw_manifest_bytes.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as error:
            raise ValueError("source snapshot manifest is not valid JSON") from error
        if not isinstance(raw_manifest_payload, Mapping):
            raise ValueError("source snapshot manifest must be a JSON object")
        if canonical_json_bytes(raw_manifest_payload) != raw_manifest_bytes:
            raise ValueError("source snapshot manifest is not canonical JSON")
        if detached_manifest_sha256(raw_manifest_payload) != result.snapshot_commit.manifest_sha256:
            raise ValueError("source snapshot detached digest mismatch")
        raw_manifest_artifact = ManifestFileWriter(self._runtime.artifact_root).write_json(
            f"runs/{run_id}/source-snapshot-manifest.json",
            raw_manifest_bytes,
        )
        config_snapshot = {
            "source": serialize_config(entry.settings),
            "historical_approval": serialize_config(entry.historical_approval),
            "current_use": (
                None if entry.current_use is None else serialize_config(entry.current_use)
            ),
        }
        status: Literal["succeeded", "failed"] = (
            "succeeded" if result.manifest.status == "COMPLETE" else "failed"
        )
        finished_at = result.manifest.completed_at or datetime.now(UTC)
        run = build_run_manifest(
            run_id=run_id,
            run_kind="source_sync",
            stage="data",
            status=status,
            git_commit=operation.git_commit,
            git_dirty=operation.git_dirty,
            git_worktree_sha256=operation.git_worktree_sha256,
            dependency_lock_hash=operation.dependency_lock_hash,
            configuration_path=f"configs/source-sync/{source_id}/{snapshot_id}.json",
            configuration_snapshot=config_snapshot,
            schema_versions=("source-snapshot-manifest.v2",),
            policy_versions=("source-approval-gate-v1",),
            artifacts=(
                *operation.artifacts,
                RunArtifactReference(
                    path=raw_manifest_artifact.path,
                    sha256=raw_manifest_artifact.sha256,
                    kind="source_snapshot_manifest",
                ),
            ),
            determinism="EXTERNAL",
            created_at=result.manifest.started_at,
            started_at=result.manifest.started_at,
            finished_at=finished_at,
        )
        ManifestFileWriter(self._runtime.artifact_root).write_run_manifest(
            run,
            manifest_path=f"runs/{run_id}/manifest.json",
            configuration_snapshot=config_snapshot,
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
