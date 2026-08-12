from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from commander_ai.adapters.data_pipeline import VerifiedSnapshotNormalizer
from commander_ai.adapters.ruleset_snapshots import FileRulesetSnapshotProvider
from commander_ai.adapters.source_sync import ConfiguredSourceSync, SourceSyncConfigurationError
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.application.errors import ApplicationError
from commander_ai.application.ports.data_pipeline import NormalizeResult, ValidateResult
from commander_ai.application.ports.dataset_store import DatasetBuildResult, DatasetInspectionResult
from commander_ai.application.ports.reporting import ReportResult
from commander_ai.application.ports.source_adapter import (
    SourceReview,
    SourceSummary,
    SourceSyncResult,
)
from commander_ai.application.use_cases import (
    BuildDataset,
    InspectDataset,
    NormalizeData,
    ReportData,
    SourceCommands,
    ValidateData,
)
from commander_ai.cli.composition import CliServices, build_default_services
from commander_ai.cli.main import app
from commander_ai.config import RuntimeConfig


class SourceCatalog:
    def list_sources(self):
        return (SourceSummary("example", "PROPOSED", None, False, False, True),)

    def review_source(self, source_id: str) -> SourceReview:
        return SourceReview(source_id, "PROPOSED", "review.md", True, True)


class SourceSync:
    def sync_source(self, source_id: str, config_path: str) -> SourceSyncResult:
        return SourceSyncResult(source_id, "snapshot-1", "COMPLETE", "raw/m.json", "a" * 64)


class Pipeline:
    def normalize_snapshot(self, snapshot_id: str) -> NormalizeResult:
        return NormalizeResult(
            "example", snapshot_id, "normalized-1", "COMPLETE", "m.json", "b" * 64
        )

    def validate_snapshot(self, normalized_snapshot_id: str) -> ValidateResult:
        return ValidateResult(normalized_snapshot_id, "VALID", {}, ())


class Reports:
    def build_report(self, selector: str) -> ReportResult:
        return ReportResult(selector, "COMPLETE", "report.json", "c" * 64, {"rows": 2})


class Datasets:
    def build_dataset(self, config_path: str) -> DatasetBuildResult:
        return DatasetBuildResult("dataset-1", "combo", "COMPLETE", "m.json", "d" * 64, ())

    def inspect_dataset(self, dataset_id: str) -> DatasetInspectionResult:
        return DatasetInspectionResult(dataset_id, "combo", "e" * 64, {"test": 1}, ())


def _services() -> CliServices:
    return CliServices(
        source=SourceCommands(SourceCatalog(), SourceSync()),
        normalize=NormalizeData(Pipeline()),
        validate=ValidateData(Pipeline()),
        report=ReportData(Reports()),
        build_dataset=BuildDataset(Datasets()),
        inspect_dataset=InspectDataset(Datasets()),
    )


def test_cli_uses_exact_source_and_data_vocabulary(monkeypatch) -> None:
    monkeypatch.setattr("commander_ai.cli.main.build_default_services", _services)
    runner = CliRunner()

    listed = runner.invoke(app, ["source", "list", "--json"])
    assert listed.exit_code == 0
    assert json.loads(listed.stdout)["sources"][0]["source_id"] == "example"

    report = runner.invoke(app, ["data", "report", "all", "--json"])
    assert report.exit_code == 0
    assert json.loads(report.stdout)["selector"] == "all"

    alias = runner.invoke(app, ["data", "fetch", "snapshot-1"])
    assert alias.exit_code != 0


def test_cli_renders_stable_errors_and_exit_codes(monkeypatch) -> None:
    monkeypatch.setattr("commander_ai.cli.main.build_default_services", _services)
    result = CliRunner().invoke(app, ["data", "normalize", "", "--json"])

    assert result.exit_code == 2
    assert json.loads(result.stdout) == {"error_code": "CONFIG_SNAPSHOT_ID_INVALID"}
    assert "secret" not in result.stdout.casefold()


def test_default_normalization_rejects_incomplete_snapshot_before_mapper(tmp_path) -> None:
    runtime = RuntimeConfig(data_root=tmp_path / "data", artifact_root=tmp_path / "artifacts")
    RawSnapshotStore(runtime.data_root).start_snapshot(
        source_id="fixture",
        snapshot_id="fixture-1",
        approval_status="APPROVED_LOCAL",
        adapter_version="fixture-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
    )

    with pytest.raises(ApplicationError) as error:
        VerifiedSnapshotNormalizer(runtime).normalize_snapshot("fixture-1")

    assert error.value.code == "INTEGRITY_SNAPSHOT_NOT_COMPLETE"


def test_plain_source_settings_cannot_bypass_registry_gate() -> None:
    runtime = RuntimeConfig()
    with pytest.raises(SourceSyncConfigurationError) as error:
        ConfiguredSourceSync(runtime).sync_source("topdeck", "configs/sources/topdeck.yaml")

    assert error.value.code == "POLICY_SOURCE_REGISTRY_REQUIRED"


def test_default_cli_services_inject_authoritative_ruleset_provider(tmp_path) -> None:
    services = build_default_services(tmp_path)

    assert isinstance(services.normalize._pipeline, VerifiedSnapshotNormalizer)
    assert isinstance(services.normalize._pipeline._ruleset_provider, FileRulesetSnapshotProvider)
