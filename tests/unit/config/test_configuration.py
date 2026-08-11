from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from commander_ai.application.configuration import OperationConfig
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.config.runtime import RuntimeConfig
from commander_ai.config.source_settings import SourceSettings
from commander_ai.config.yaml_loader import (
    ConfigurationError,
    load_dataset_settings,
    load_source_settings,
    serialize_config,
)


def minimal_source_payload() -> dict[str, object]:
    return {
        "source_id": "Example-Source",
        "approval_status": "PROPOSED",
        "review_path": "docs/03-data/source-reviews/example.md",
        "endpoints": ["https://example.com/api"],
        "host_allowlist": ["example.com"],
    }


@pytest.mark.parametrize(
    ("model", "payload"),
    [
        (RuntimeConfig, {"unexpected": True}),
        (SourceSettings, {**minimal_source_payload(), "unexpected": True}),
        (DatasetSettings, {"dataset_id": "fixture", "unexpected": True}),
        (
            OperationConfig,
            {"operation": "normalize", "source_id": "example", "unexpected": True},
        ),
    ],
)
def test_configuration_models_reject_unknown_fields(
    model: type[BaseModel], payload: dict[str, object]
) -> None:
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_nested_unknown_fields_are_rejected() -> None:
    source_payload = minimal_source_payload()
    source_payload["rate_limit"] = {"requests_per_minute": 10, "unexpected": True}

    with pytest.raises(ValidationError):
        SourceSettings.model_validate(source_payload)

    dataset_payload = {
        "dataset_id": "fixture",
        "split_policy": {"strategy": "temporal_grouped", "unexpected": True},
    }

    with pytest.raises(ValidationError):
        DatasetSettings.model_validate(dataset_payload)


def test_runtime_roots_are_normalized_and_artifact_paths_stay_portable(tmp_path: Path) -> None:
    runtime = RuntimeConfig(
        data_root=tmp_path / "data" / ".." / "data",
        artifact_root=tmp_path / "artifacts",
    )

    assert runtime.data_root == (tmp_path / "data").resolve()
    assert (
        runtime.resolve_artifact_path("reports/summary.json")
        == (tmp_path / "artifacts" / "reports" / "summary.json").resolve()
    )

    with pytest.raises(ValueError):
        runtime.resolve_artifact_path("../outside.json")

    with pytest.raises(ValueError):
        runtime.resolve_artifact_path("reports\\summary.json")

    with pytest.raises(ValueError):
        runtime.portable_artifact_path("reports\\summary.json")


def test_source_ids_and_statuses_are_normalized() -> None:
    settings = SourceSettings.model_validate(minimal_source_payload())

    assert settings.source_id == "example_source"
    assert settings.approval_status.value == "PROPOSED"


def test_checked_in_source_and_dataset_configs_are_explicit_and_offline_loadable() -> None:
    project_root = Path(__file__).resolve().parents[3]
    source_expectations = {
        "mtgjson": "APPROVED_LOCAL",
        "commander_spellbook": "APPROVED_LOCAL",
        "scryfall": "APPROVED_LOCAL",
        "topdeck": "PROPOSED",
        "spicerack": "PROPOSED",
    }

    for source_id, expected_status in source_expectations.items():
        settings = load_source_settings(project_root / "configs" / "sources" / f"{source_id}.yaml")
        assert settings.approval_status.value == expected_status
        assert settings.review_path is not None
        assert settings.endpoints
        assert settings.host_allowlist
        serialized = serialize_config(settings)
        assert "api_key_env" in serialized
        if settings.api_key_env is not None:
            assert serialized["api_key_env"] == settings.api_key_env

    for filename in ("completion-v1.yaml", "cedh-outcome-v1.yaml"):
        dataset = load_dataset_settings(project_root / "configs" / "datasets" / filename)
        assert dataset.split_policy.version
        assert dataset.near_duplicate_policy.algorithm
        assert dataset.near_duplicate_policy.version
        assert 0 <= dataset.near_duplicate_policy.threshold <= 1


def test_dataset_rejects_conflicting_source_filters_instead_of_merging() -> None:
    with pytest.raises(ValidationError):
        DatasetSettings.model_validate(
            {
                "dataset_id": "fixture",
                "inputs": {"sources": ["mtgjson"]},
                "filters": {"source_ids": ["topdeck"]},
            }
        )


def test_operation_configuration_has_no_experiment_or_optimizer_override_fields() -> None:
    for forbidden_field in ("experiment", "optimizer", "source", "dataset"):
        with pytest.raises(ValidationError):
            OperationConfig.model_validate(
                {
                    "operation": "dataset_build",
                    "dataset_id": "fixture",
                    forbidden_field: {"timeout_seconds": 1},
                }
            )


def test_loader_error_and_serialized_config_do_not_expose_secret_values(tmp_path: Path) -> None:
    config_path = tmp_path / "source.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source_id: topdeck",
                "approval_status: PROPOSED",
                "api_key: super-secret-value",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as error:
        load_source_settings(config_path)

    assert "super-secret-value" not in str(error.value)

    with pytest.raises(ValidationError) as direct_error:
        SourceSettings.model_validate(
            {
                "source_id": "topdeck",
                "approval_status": "PROPOSED",
                "api_key": "super-secret-value",
            }
        )

    assert "super-secret-value" not in str(direct_error.value)

    class ResolvedSecrets(BaseModel):
        api_key: str
        api_key_env: str

    serialized = serialize_config(
        ResolvedSecrets(api_key="super-secret-value", api_key_env="TOPDECK_API_KEY")
    )

    assert "super-secret-value" not in str(serialized)
    assert serialized["api_key"] == "[REDACTED]"
    assert serialized["api_key_env"] == "TOPDECK_API_KEY"

    text_config = serialize_config(
        {
            "endpoint": "https://example.com/data?token=query-secret&safe=1",
            "reason": "Authorization: Bearer header-secret",
        }
    )

    assert "query-secret" not in str(text_config)
    assert "header-secret" not in str(text_config)
