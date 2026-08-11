from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from commander_ai.application.configuration import OperationConfig, ResolvedConfiguration
from commander_ai.config import load_permission_gated_catalog
from commander_ai.config.current_use_policy import CurrentUseDecision, CurrentUsePolicy
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.config.runtime import RuntimeConfig
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings
from commander_ai.config.yaml_loader import (
    ConfigurationError,
    load_dataset_settings,
    load_runtime_config,
    load_source_settings,
    redact_text,
    serialize_config,
    serialize_config_json,
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


def test_default_runtime_roots_are_repository_anchored_not_cwd(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)

    default_runtime = RuntimeConfig()
    runtime = RuntimeConfig(
        data_root=Path("portable-data"), artifact_root=Path("portable-artifacts")
    )
    repository_root = Path(__file__).resolve().parents[3]

    assert default_runtime.data_root == (repository_root / "data").resolve()
    assert default_runtime.artifact_root == (repository_root / "artifacts").resolve()
    assert runtime.data_root == (repository_root / "portable-data").resolve()
    assert runtime.artifact_root == (repository_root / "portable-artifacts").resolve()


def test_serialized_runtime_roots_are_repository_relative_or_opaque_external_markers(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[3]
    runtime = RuntimeConfig(
        data_root=repository_root / "data" / "raw",
        artifact_root=tmp_path / "artifacts",
    )

    serialized = serialize_config(runtime)
    serialized_json = serialize_config_json(runtime)

    assert serialized["data_root"] == "data/raw"
    assert serialized["artifact_root"] == "<external-root>"
    assert str(repository_root) not in serialized_json
    assert str(tmp_path) not in serialized_json
    assert '"data_root":"data/raw"' in serialized_json
    assert '"artifact_root":"<external-root>"' in serialized_json


def test_serialized_repository_root_uses_a_non_path_marker() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    serialized = serialize_config(
        RuntimeConfig(data_root=repository_root, artifact_root=repository_root)
    )

    assert serialized["data_root"] == "<repository-root>"
    assert serialized["artifact_root"] == "<repository-root>"


@pytest.mark.parametrize(
    ("field_name", "marker"),
    [
        ("data_root", "<external-root>"),
        ("artifact_root", "<repository-root>"),
    ],
)
def test_runtime_rejects_non_reloadable_snapshot_root_markers(field_name: str, marker: str) -> None:
    with pytest.raises(ValidationError, match="snapshot-only"):
        RuntimeConfig(**{field_name: Path(marker)})


@pytest.mark.parametrize(
    ("field_name", "marker"),
    [
        ("data_root", "<external-root>"),
        ("artifact_root", "<repository-root>"),
    ],
)
def test_yaml_runtime_loader_rejects_non_reloadable_snapshot_root_markers(
    tmp_path: Path, field_name: str, marker: str
) -> None:
    config_path = tmp_path / "runtime.yaml"
    config_path.write_text(f"{field_name}: {marker}\n", encoding="utf-8")

    with pytest.raises(ConfigurationError, match="snapshot-only"):
        load_runtime_config(config_path)


def test_source_ids_and_statuses_are_normalized() -> None:
    settings = SourceSettings.model_validate(minimal_source_payload())

    assert settings.source_id == "example_source"
    assert settings.approval_status.value == "PROPOSED"


@pytest.mark.parametrize(
    "nested_filters",
    [
        {"request": {"api_key": "nested-secret"}},
        {"items": [{"authorization": "Bearer nested-secret"}]},
        {"items": [{"details": [{"token": "nested-secret"}]}]},
    ],
)
def test_source_filters_reject_credential_keys_at_any_nesting_depth(
    nested_filters: dict[str, object],
) -> None:
    payload = minimal_source_payload()
    payload["filters"] = nested_filters

    with pytest.raises(ValidationError) as error:
        SourceSettings.model_validate(payload)

    assert "nested-secret" not in str(error.value)


def test_source_features_reject_credential_keys() -> None:
    payload = minimal_source_payload()
    payload["features"] = {"token": True}

    with pytest.raises(ValidationError):
        SourceSettings.model_validate(payload)


@pytest.mark.parametrize(
    "nested_filters",
    [
        {"request": {"api_key_env": "actual-secret"}},
        {"items": [{"details": [{"token_env": "actual-secret"}]}]},
    ],
)
def test_source_filters_reject_credential_like_environment_keys(
    nested_filters: dict[str, object],
) -> None:
    payload = minimal_source_payload()
    payload["filters"] = nested_filters

    with pytest.raises(ValidationError) as error:
        SourceSettings.model_validate(payload)

    assert "actual-secret" not in str(error.value)


def test_top_level_source_credential_environment_names_are_preserved() -> None:
    payload = minimal_source_payload()
    payload["api_key_env"] = "TOPDECK_API_KEY"
    payload["credential_env_vars"] = ["TOPDECK_TOKEN"]

    settings = SourceSettings.model_validate(payload)
    serialized = serialize_config(settings)

    assert serialized["api_key_env"] == "TOPDECK_API_KEY"
    assert serialized["credential_env_vars"] == ["TOPDECK_TOKEN"]


def test_nested_source_settings_environment_names_are_preserved_in_registry_and_application(
    tmp_path: Path,
) -> None:
    settings = SourceSettings(
        source_id="example_source",
        approval_status=SourceApprovalStatus.PROPOSED,
        api_key_env="EXAMPLE_API_KEY",
        credential_env_vars=("EXAMPLE_TOKEN",),
        user_agent_env="EXAMPLE_USER_AGENT",
    )
    historical = HistoricalApprovalMetadata(
        source_id="example_source",
        approval_status=SourceApprovalStatus.PROPOSED,
        review_path="docs/03-data/source-reviews/example.md",
        reviewed_at=datetime(2026, 8, 10, tzinfo=UTC),
        effective_at=datetime(2026, 8, 10, tzinfo=UTC),
        reason="fixture review",
    )
    registry = SourceRegistry(
        entries=(
            SourceRegistryEntry(
                source_id="example_source",
                settings=settings,
                historical_approval=historical,
            ),
        )
    )
    resolved = ResolvedConfiguration(
        runtime=RuntimeConfig(data_root=tmp_path / "data", artifact_root=tmp_path / "artifacts"),
        operation=OperationConfig(operation="normalize", source_id="example_source"),
        source=settings,
    )

    registry_settings = serialize_config(registry)["entries"][0]["settings"]
    application_settings = serialize_config(resolved)["source"]

    for serialized_settings in (registry_settings, application_settings):
        assert serialized_settings["api_key_env"] == "EXAMPLE_API_KEY"
        assert serialized_settings["credential_env_vars"] == ["EXAMPLE_TOKEN"]
        assert serialized_settings["user_agent_env"] == "EXAMPLE_USER_AGENT"


def test_untrusted_nested_environment_keys_are_redacted() -> None:
    serialized = serialize_config(
        {
            "settings": SourceSettings(
                source_id="example_source",
                approval_status=SourceApprovalStatus.PROPOSED,
                api_key_env="EXAMPLE_API_KEY",
            ),
            "metadata": {
                "nested": {
                    "user_agent_env": "not-a-valid-environment-name",
                    "service_env": "actual-secret",
                }
            },
        }
    )

    assert serialized["settings"]["api_key_env"] == "EXAMPLE_API_KEY"
    assert serialized["metadata"]["nested"]["user_agent_env"] == "[REDACTED]"
    assert serialized["metadata"]["nested"]["service_env"] == "[REDACTED]"


def test_nested_serialization_redacts_bare_authorization_values() -> None:
    nested = serialize_config(
        {
            "items": [
                "Bearer bearer-secret",
                {"headers": ["Basic basic-secret"]},
                {"api_key_env": "actual-secret"},
            ]
        }
    )
    nested_text = str(nested)
    assert "bearer-secret" not in nested_text
    assert "basic-secret" not in nested_text
    assert "actual-secret" not in nested_text


def test_redact_text_removes_url_userinfo_and_credential_bearing_forms() -> None:
    value = (
        "https://user:pass@example.com/data?api_key=query-secret&safe=1; "
        "Bearer bearer-secret; Basic basic-secret; token=assignment-secret"
    )

    redacted = redact_text(value)

    assert "user" not in redacted
    assert "pass" not in redacted
    assert "query-secret" not in redacted
    assert "bearer-secret" not in redacted
    assert "basic-secret" not in redacted
    assert "assignment-secret" not in redacted
    assert "https://[REDACTED]@example.com" in redacted


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "http://alice:password@example.com/path",
            "http://[REDACTED]@example.com/path",
        ),
        (
            "https://alice:password@example.com/path",
            "https://[REDACTED]@example.com/path",
        ),
        (
            "ftp://alice:password@example.com/path",
            "ftp://[REDACTED]@example.com/path",
        ),
        (
            "ssh://alice:password@example.com:22/path",
            "ssh://[REDACTED]@example.com:22/path",
        ),
        (
            "//alice:password@example.com/path",
            "//[REDACTED]@example.com/path",
        ),
        (
            "ssh://alice:password@[2001:db8::1]:22/path",
            "ssh://[REDACTED]@[2001:db8::1]:22/path",
        ),
    ],
)
def test_redact_text_redacts_userinfo_for_network_uri_forms(value: str, expected: str) -> None:
    redacted = redact_text(value)

    assert redacted == expected
    assert redact_text(redacted) == redacted
    assert "alice" not in redacted
    assert "password" not in redacted


def test_redact_text_preserves_noncredential_double_slash_path_text() -> None:
    value = "https://example.com/path//public@example.com"

    assert redact_text(value) == value


def test_redact_text_handles_credential_suffixes_and_is_idempotent() -> None:
    value = (
        "https://user:pass@example.com/path?token=query-secret]]}&safe=1; "
        "Authorization: Bearer bearer-secret]]}#bearer-suffix; "
        "Basic basic-secret)]}; api_key=assignment-secret]]}#assignment-suffix"
    )

    redacted = redact_text(value)

    assert "user" not in redacted
    assert "pass" not in redacted
    assert "query-secret" not in redacted
    assert "bearer-secret" not in redacted
    assert "bearer-suffix" not in redacted
    assert "basic-secret" not in redacted
    assert "assignment-secret" not in redacted
    assert "assignment-suffix" not in redacted
    assert "safe=1" in redacted
    assert "[REDACTED]]" not in redacted
    assert redact_text(redacted) == redacted


@pytest.mark.parametrize(
    ("key", "key_quote", "value_quote", "secret"),
    [
        ("api_key", '"', '"', "json-api-secret"),
        ("access_token", "'", "'", "yaml-access-secret"),
        ("authorization", '"', "'", "quoted-authorization-secret"),
        ("cookie", "'", '"', "quoted-cookie-secret"),
        ("password", '"', "'", "quoted-password-secret"),
        ("secret", "'", '"', "quoted-secret-value"),
        ("token", '"', '"', "json-secret"),
    ],
)
def test_redact_text_redacts_quoted_credential_keys_preserving_shape(
    key: str, key_quote: str, value_quote: str, secret: str
) -> None:
    value = f"{key_quote}{key}{key_quote}\t :\n {value_quote}{secret}{value_quote}, safe=1"
    expected = f"{key_quote}{key}{key_quote}\t :\n {value_quote}[REDACTED]{value_quote}, safe=1"

    redacted = redact_text(value)

    assert redacted == expected
    assert secret not in redacted
    assert redact_text(redacted) == redacted


def test_redact_text_handles_quoted_query_and_bearer_values() -> None:
    value = (
        'https://user:pass@example.com/data?token="query-secret"&safe=1; '
        "Authorization: Bearer 'bearer-secret'; Basic \"basic-secret\""
    )

    redacted = redact_text(value)

    assert redacted == (
        'https://[REDACTED]@example.com/data?token="[REDACTED]"&safe=1; '
        "Authorization: Bearer '[REDACTED]'; Basic \"[REDACTED]\""
    )
    assert redact_text(redacted) == redacted


def test_redact_text_handles_quoted_and_unquoted_assignment_suffixes() -> None:
    value = (
        '{"token": "json-secret"}, "safe": "keep"; '
        "api_key=assignment-secret]]}#assignment-suffix; safe=1"
    )

    redacted = redact_text(value)

    assert redacted == ('{"token": "[REDACTED]"}, "safe": "keep"; api_key=[REDACTED]; safe=1')
    assert redact_text(redacted) == redacted


def test_redact_text_does_not_redact_environment_variable_names() -> None:
    value = "TOPDECK_API_KEY CDA_USER_AGENT TOKEN_ENV"

    assert redact_text(value) == value


def test_redact_text_does_not_reprocess_marker_with_known_secret_values() -> None:
    secrets = ("actual-secret", "REDACTED")

    redacted = redact_text("message actual-secret", secret_values=secrets)

    assert redacted == "message [REDACTED]"
    assert redact_text(redacted, secret_values=secrets) == redacted


def test_current_use_takedown_reference_is_redacted_in_direct_dumps_and_snapshots() -> None:
    decision = CurrentUseDecision(
        source_id="example_source",
        status="TAKEDOWN",
        reason="fixture takedown",
        effective_at=datetime(2026, 8, 10, tzinfo=UTC),
        takedown_reference=("https://user:pass@example.com/takedown?token=query-secret"),
    )

    direct_dump = decision.model_dump()
    serialized = serialize_config(decision)

    assert "user" not in str(direct_dump)
    assert "pass" not in str(direct_dump)
    assert "query-secret" not in str(direct_dump)
    assert "user" not in str(serialized)
    assert "pass" not in str(serialized)
    assert "query-secret" not in str(serialized)


def test_current_use_takedown_reference_dump_is_safe_after_unvalidated_model_copy() -> None:
    decision = CurrentUseDecision(
        source_id="example_source",
        status="TAKEDOWN",
        reason="fixture takedown",
        effective_at=datetime(2026, 8, 10, tzinfo=UTC),
    ).model_copy(update={"takedown_reference": "https://user:pass@example.com/takedown"})

    assert "user" not in str(decision.model_dump())
    assert "pass" not in str(decision.model_dump())


def test_current_use_sensitive_fields_are_safe_in_all_direct_dumps_after_model_copy_update() -> (
    None
):
    reason = (
        "keep this explanation; https://user:pass@example.com/path?token=query-secret "
        "Authorization: Bearer bearer-secret; api_key=assignment-secret"
    )
    takedown_reference = (
        "ssh://reference-user:reference-pass@example.com/takedown"
        "?access_token=reference-query-secret"
    )
    decision = CurrentUseDecision(
        source_id="example_source",
        status="TAKEDOWN",
        reason="safe initial reason",
        effective_at=datetime(2026, 8, 10, tzinfo=UTC),
    ).model_copy(update={"reason": reason, "takedown_reference": takedown_reference})

    direct_dump = decision.model_dump()
    direct_json = decision.model_dump_json()

    for secret in (
        "user",
        "pass",
        "query-secret",
        "bearer-secret",
        "assignment-secret",
        "reference-user",
        "reference-pass",
        "reference-query-secret",
    ):
        assert secret not in str(direct_dump)
        assert secret not in direct_json
    assert "keep this explanation" in direct_dump["reason"]
    assert "[REDACTED]" in direct_dump["reason"]
    assert "[REDACTED]" in direct_dump["takedown_reference"]


def test_current_use_model_copy_dumps_redact_quoted_assignments_everywhere() -> None:
    reason = (
        '{"token": "json-secret", "api_key": \'single-api-secret\'}; '
        'Authorization: Bearer "bearer-secret"'
    )
    takedown_reference = "https://user:pass@example.com/takedown?access_token='query-secret'"
    decision = CurrentUseDecision(
        source_id="example_source",
        status="TAKEDOWN",
        reason="safe initial reason",
        effective_at=datetime(2026, 8, 10, tzinfo=UTC),
    ).model_copy(update={"reason": reason, "takedown_reference": takedown_reference})

    snapshots = (
        decision.model_dump(),
        decision.model_dump_json(),
        serialize_config(decision),
    )

    for snapshot in snapshots:
        snapshot_text = str(snapshot)
        for secret in (
            "json-secret",
            "single-api-secret",
            "bearer-secret",
            "user",
            "pass",
            "query-secret",
        ):
            assert secret not in snapshot_text
    assert "[REDACTED]" in str(snapshots[0]["reason"])
    assert "[REDACTED]" in str(snapshots[0]["takedown_reference"])


def test_current_use_reason_redacts_bearer_and_other_credential_forms() -> None:
    decision = CurrentUseDecision(
        source_id="example_source",
        status="ALLOWED",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        reason=(
            "Bearer bearer-secret; Basic basic-secret; Authorization: Bearer labeled-secret; "
            "api_key=api-secret; "
            "access_token: access-secret; cookie=cookie-secret; "
            "password=password-secret; secret: secret-value; token=token-secret"
        ),
        effective_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    assert "bearer-secret" not in decision.reason
    assert "basic-secret" not in decision.reason
    assert "labeled-secret" not in decision.reason

    result = CurrentUsePolicy.check(
        source_id="example_source",
        historical_status=SourceApprovalStatus.APPROVED_LOCAL,
        current_use=decision,
        operation="normalize",
    )

    assert result.allowed
    assert "bearer-secret" not in result.reason
    assert "api-secret" not in result.reason
    assert "access-secret" not in result.reason
    assert "cookie-secret" not in result.reason
    assert "password-secret" not in result.reason
    assert "secret-value" not in result.reason
    assert "token-secret" not in result.reason
    assert "Authorization" in result.reason
    assert "[REDACTED]" in result.reason


def test_strict_yaml_loader_rejects_duplicate_keys_without_exposing_values(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "duplicate.yaml"
    config_path.write_text(
        "\n".join(
            [
                "source_id: example_source",
                "approval_status: PROPOSED",
                "review_path: docs/03-data/source-reviews/example.md",
                "endpoints: [https://example.com/api]",
                "host_allowlist: [example.com]",
                "filters:",
                "  api_key: actual-secret",
                "  api_key: duplicate-secret",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ConfigurationError) as error:
        load_source_settings(config_path)

    assert "duplicate YAML key" in str(error.value)
    assert "actual-secret" not in str(error.value)
    assert "duplicate-secret" not in str(error.value)


def test_permission_gated_catalog_loads_typed_statuses_and_denies_acquisition() -> None:
    project_root = Path(__file__).resolve().parents[3]

    catalog = load_permission_gated_catalog(
        project_root / "configs" / "sources" / "permission-gated.yaml"
    )

    assert catalog.status_for("edhrec").value == "PAUSED"
    assert catalog.status_for("spellbinder").value == "PROPOSED"
    assert not catalog.acquisition_allowed("edhrec")


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


def test_audit_inspect_requires_a_source_reference() -> None:
    with pytest.raises(ValidationError):
        OperationConfig(operation="audit_inspect")


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
    assert serialized["api_key_env"] == "[REDACTED]"

    text_config = serialize_config(
        {
            "endpoint": "https://example.com/data?token=query-secret&safe=1",
            "reason": "Authorization: Bearer header-secret",
        }
    )

    assert "query-secret" not in str(text_config)
    assert "header-secret" not in str(text_config)
