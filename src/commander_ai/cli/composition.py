"""CLI composition root for data-foundation application use cases."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from commander_ai.adapters.data_pipeline import (
    LocalDatasetInspector,
    VerifiedNormalizedSnapshot,
    VerifiedSnapshotNormalizer,
)
from commander_ai.adapters.dataset_building import ConfiguredDatasetBuild
from commander_ai.adapters.registry_context import SourceRegistryProvider
from commander_ai.adapters.reporting import ConfiguredReport
from commander_ai.adapters.ruleset_snapshots import FileRulesetSnapshotProvider
from commander_ai.adapters.source_catalog import ConfiguredSourceCatalog
from commander_ai.adapters.source_sync import ConfiguredSourceSync
from commander_ai.application.ports.data_pipeline import NormalizeDataPort, ValidateDataPort
from commander_ai.application.ports.dataset_store import DatasetBuildPort, DatasetInspectPort
from commander_ai.application.ports.reporting import ReportDataPort
from commander_ai.application.ports.source_adapter import SourceCatalogPort, SourceSyncPort
from commander_ai.application.use_cases import (
    BuildDataset,
    InspectDataset,
    NormalizeData,
    ReportData,
    SourceCommands,
    ValidateData,
)
from commander_ai.config import RuntimeConfig


@dataclass(frozen=True, slots=True)
class CliServices:
    source: SourceCommands
    normalize: NormalizeData
    validate: ValidateData
    report: ReportData
    build_dataset: BuildDataset
    inspect_dataset: InspectDataset


def build_default_services(repository_root: Path | str | None = None) -> CliServices:
    root = Path(repository_root or _repository_root()).expanduser().absolute()
    runtime = RuntimeConfig.from_environment(repository_root=root)
    registry_provider = SourceRegistryProvider(root)
    catalog: SourceCatalogPort = ConfiguredSourceCatalog(root)
    sync: SourceSyncPort = ConfiguredSourceSync(runtime)
    ruleset_provider = FileRulesetSnapshotProvider(runtime.data_root)
    normalizer: NormalizeDataPort = VerifiedSnapshotNormalizer(
        runtime,
        registry_provider,
        ruleset_provider,
    )
    validator: ValidateDataPort = VerifiedNormalizedSnapshot(runtime, registry_provider)
    reporter: ReportDataPort = ConfiguredReport(runtime, registry_provider)
    dataset_builder: DatasetBuildPort = ConfiguredDatasetBuild(runtime, registry_provider)
    dataset_inspector: DatasetInspectPort = LocalDatasetInspector(runtime)
    return CliServices(
        source=SourceCommands(catalog, sync),
        normalize=NormalizeData(normalizer),
        validate=ValidateData(validator),
        report=ReportData(reporter),
        build_dataset=BuildDataset(dataset_builder),
        inspect_dataset=InspectDataset(dataset_inspector),
    )


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


__all__ = ["CliServices", "build_default_services"]
