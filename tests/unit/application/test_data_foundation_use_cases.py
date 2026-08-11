from __future__ import annotations

from dataclasses import dataclass

import pytest

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


@dataclass
class FakeSourceCatalog:
    def list_sources(self):
        return (
            SourceSummary("zeta", "PROPOSED", None, False, False, True),
            SourceSummary("alpha", "APPROVED_LOCAL", None, True, False, False),
        )

    def review_source(self, source_id: str) -> SourceReview:
        return SourceReview(source_id, "APPROVED_LOCAL", "review.md", True, False)


@dataclass
class FakeSourceSync:
    calls: list[tuple[str, str]]

    def sync_source(self, source_id: str, config_path: str) -> SourceSyncResult:
        self.calls.append((source_id, config_path))
        return SourceSyncResult(source_id, "snapshot-1", "COMPLETE", "raw/manifest.json", "a" * 64)


class FakePipeline:
    def normalize_snapshot(self, snapshot_id: str) -> NormalizeResult:
        return NormalizeResult(
            "mtgjson", snapshot_id, "normalized-1", "COMPLETE", "m.json", "b" * 64
        )

    def validate_snapshot(self, normalized_snapshot_id: str) -> ValidateResult:
        return ValidateResult(normalized_snapshot_id, "VALID", {"quality": 0}, ("a.parquet",))


class FakeDatasets:
    def build_dataset(self, config_path: str) -> DatasetBuildResult:
        return DatasetBuildResult(
            "dataset-1", "deck_completion", "COMPLETE", "m.json", "c" * 64, ()
        )

    def inspect_dataset(self, dataset_id: str) -> DatasetInspectionResult:
        return DatasetInspectionResult(dataset_id, "deck_completion", "d" * 64, {"train": 1}, ())


class FakeReporting:
    def build_report(self, selector: str) -> ReportResult:
        return ReportResult(selector, "COMPLETE", "report.json", "e" * 64, {"rows": 1})


def test_source_commands_sort_and_forward_without_source_io() -> None:
    sync = FakeSourceSync([])
    commands = SourceCommands(FakeSourceCatalog(), sync)

    assert [item.source_id for item in commands.list_sources()] == ["alpha", "zeta"]
    assert commands.review(" ALPHA ").source_id == "alpha"
    assert commands.sync("ALPHA", " config.yaml ").manifest_sha256 == "a" * 64
    assert sync.calls == [("alpha", "config.yaml")]


@pytest.mark.parametrize(
    ("factory", "value", "code"),
    (
        (
            lambda: SourceCommands(FakeSourceCatalog(), FakeSourceSync([])).review(""),
            "",
            "CONFIG_SOURCE_ID_INVALID",
        ),
        (lambda: NormalizeData(FakePipeline()).execute(""), "", "CONFIG_SNAPSHOT_ID_INVALID"),
        (
            lambda: ValidateData(FakePipeline()).execute(""),
            "",
            "CONFIG_NORMALIZED_SNAPSHOT_ID_INVALID",
        ),
        (
            lambda: ReportData(FakeReporting()).execute("bad selector"),
            "bad selector",
            "CONFIG_REPORT_SELECTOR_INVALID",
        ),
        (lambda: BuildDataset(FakeDatasets()).execute(""), "", "CONFIG_DATASET_CONFIG_REQUIRED"),
        (lambda: InspectDataset(FakeDatasets()).execute(""), "", "CONFIG_DATASET_ID_INVALID"),
    ),
)
def test_use_cases_reject_invalid_input(factory, value: str, code: str) -> None:
    del value
    with pytest.raises(ApplicationError, match=code):
        factory()


def test_port_failures_are_redacted_to_stable_codes() -> None:
    class Broken:
        def normalize_snapshot(self, snapshot_id: str) -> NormalizeResult:
            raise RuntimeError("Bearer super-secret")

    with pytest.raises(ApplicationError) as error:
        NormalizeData(Broken()).execute("snapshot-1")

    assert error.value.code == "INTEGRITY_NORMALIZATION_REJECTED"
    assert "super-secret" not in str(error.value)
