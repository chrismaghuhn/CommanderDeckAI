from __future__ import annotations

import pytest
from pydantic import ValidationError

from commander_ai.application.configuration import OperationConfig, ResolvedConfiguration
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.config.runtime import RuntimeConfig
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings


def test_resolved_configuration_keeps_ownership_boundaries_explicit(tmp_path) -> None:
    resolved = ResolvedConfiguration(
        runtime=RuntimeConfig(data_root=tmp_path / "data", artifact_root=tmp_path / "artifacts"),
        operation=OperationConfig(
            operation="dataset_build",
            dataset_id="completion",
            dataset_config_path="configs/datasets/completion.yaml",
        ),
        dataset=DatasetSettings(dataset_id="completion"),
    )

    assert resolved.dataset is not None
    assert resolved.dataset.dataset_id == resolved.operation.dataset_id


def test_resolved_configuration_rejects_source_reference_override() -> None:
    with pytest.raises(ValidationError):
        ResolvedConfiguration(
            runtime=RuntimeConfig(),
            operation=OperationConfig(operation="normalize", source_id="mtgjson"),
            source=SourceSettings(
                source_id="topdeck",
                approval_status=SourceApprovalStatus.PROPOSED,
            ),
        )


def test_resolved_configuration_rejects_dataset_reference_override() -> None:
    with pytest.raises(ValidationError):
        ResolvedConfiguration(
            runtime=RuntimeConfig(),
            operation=OperationConfig(operation="dataset_build", dataset_id="completion"),
            dataset=DatasetSettings(dataset_id="other-dataset"),
        )
