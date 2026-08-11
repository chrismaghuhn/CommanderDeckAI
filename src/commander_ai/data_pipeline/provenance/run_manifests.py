"""Construction and canonical serialization for the frozen run-manifest.v1 contract."""

from __future__ import annotations

import json
import math
import platform
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from commander_ai.domain.path_policy import validate_portable_relative_path
from commander_ai.domain.provenance import DomainModel
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .run_manifest_redaction import (
    _safe_text,
    configuration_snapshot_bytes,
    redacted_configuration_snapshot,
)


class RunInputReference(DomainModel):
    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    path: str | None = Field(default=None, min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("kind", "id")
    @classmethod
    def redact_identifiers(cls, value: str) -> str:
        return _safe_text(value)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else validate_portable_relative_path(value)

    @model_validator(mode="after")
    def validate_path_binding(self) -> RunInputReference:
        if self.path is None and self.kind not in {"current_use_decision", "policy_decision"}:
            raise ValueError("file and object run inputs require a portable path")
        return self


class RunArtifactReference(DomainModel):
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: str = Field(min_length=1)

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)


class RunConfiguration(DomainModel):
    path: str = Field(min_length=1)
    format: str = Field(default="json", min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)


class RunTool(DomainModel):
    name: str = Field(min_length=1)
    version: str = Field(min_length=1)

    @field_validator("name", "version")
    @classmethod
    def sanitize_metadata(cls, value: str) -> str:
        return _safe_text(value)


class RunHardware(DomainModel):
    cpu: str | None = Field(default=None, min_length=1)
    accelerator: str | None = Field(default=None, min_length=1)
    thread_count: int | None = Field(default=None, ge=1, strict=True)

    @field_validator("cpu", "accelerator")
    @classmethod
    def sanitize_metadata(cls, value: str | None) -> str | None:
        return None if value is None else _safe_text(value)


class RunEnvironment(DomainModel):
    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    dependency_lock_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    tools: tuple[RunTool, ...] = Field(min_length=1)
    hardware: RunHardware | None = None


class RunManifest(DomainModel):
    schema_version: Literal["run-manifest.v1"] = "run-manifest.v1"
    run_id: str = Field(min_length=1)
    run_kind: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    status: Literal["created", "running", "succeeded", "failed", "cancelled"]
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    git_commit: str = Field(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")
    git_dirty: bool
    git_worktree_sha256: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    inputs: tuple[RunInputReference, ...] = Field(default_factory=tuple)
    configuration: RunConfiguration
    feature_spec_versions: tuple[str, ...] = Field(default_factory=tuple)
    ruleset_versions: tuple[str, ...] = Field(default_factory=tuple)
    determinism: Literal["STRICT", "BEST_EFFORT", "EXTERNAL"]
    random_seeds: tuple[int, ...] = Field(default_factory=tuple)
    environment: RunEnvironment
    checkpoint_selection_rule: str | None = None
    artifacts: tuple[RunArtifactReference, ...] = Field(default_factory=tuple)
    metrics: dict[str, float] = Field(default_factory=dict)
    warnings: tuple[str, ...] = Field(default_factory=tuple)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("created_at", "started_at", "finished_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("run timestamps must include a timezone")
        return value

    @field_validator("random_seeds")
    @classmethod
    def validate_seeds(cls, value: tuple[int, ...]) -> tuple[int, ...]:
        if any(type(seed) is not int or seed < 0 for seed in value):
            raise ValueError("random seeds must be non-negative integers")
        if len(value) != len(set(value)):
            raise ValueError("random seeds must be unique")
        return value

    @field_validator("feature_spec_versions", "ruleset_versions")
    @classmethod
    def validate_unique_versions(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not isinstance(item, str) or not item for item in value):
            raise ValueError("run version references must be non-empty strings")
        if len(value) != len(set(value)):
            raise ValueError("run version references must be unique")
        return value

    @field_validator("ruleset_versions")
    @classmethod
    def validate_unique_rulesets(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(value) != len(set(value)):
            raise ValueError("run ruleset references must be unique")
        return value

    @field_validator("metrics")
    @classmethod
    def validate_metrics(cls, value: Mapping[str, float]) -> Mapping[str, float]:
        if any(
            not isinstance(key, str) or not key or not math.isfinite(metric)
            for key, metric in value.items()
        ):
            raise ValueError("run metrics must have non-empty keys and finite numbers")
        return dict(value)

    @field_validator("checkpoint_selection_rule")
    @classmethod
    def redact_checkpoint_rule(cls, value: str | None) -> str | None:
        return None if value is None else _safe_text(value)

    @field_validator("warnings", mode="before")
    @classmethod
    def redact_warnings(cls, value: object) -> object:
        if not isinstance(value, (tuple, list)):
            raise ValueError("warnings must be a sequence")
        return tuple(_safe_text(item) for item in value)

    @model_validator(mode="after")
    def validate_lifecycle_and_determinism(self) -> RunManifest:
        if self.status == "created" and (
            self.started_at is not None or self.finished_at is not None
        ):
            raise ValueError("created runs cannot have lifecycle timestamps")
        if self.status == "running" and (self.started_at is None or self.finished_at is not None):
            raise ValueError("running runs require started_at and forbid finished_at")
        if self.status in {"succeeded", "failed"} and (
            self.started_at is None or self.finished_at is None
        ):
            raise ValueError("finished runs require started_at and finished_at")
        if self.status == "cancelled" and self.finished_at is None:
            raise ValueError("cancelled runs require finished_at")
        if self.started_at is not None and self.started_at < self.created_at:
            raise ValueError("started_at must not precede created_at")
        if (
            self.finished_at is not None
            and self.started_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at must not precede started_at")
        if self.determinism == "STRICT" and self.git_dirty:
            raise ValueError("strict runs require a clean git worktree")
        if self.git_dirty and self.git_worktree_sha256 is None:
            raise ValueError("dirty runs require git_worktree_sha256")
        if not self.git_dirty and self.git_worktree_sha256 is not None:
            raise ValueError("clean runs cannot bind a worktree hash")
        if self.git_dirty and not any(item.kind == "git_worktree_state" for item in self.artifacts):
            raise ValueError("dirty runs require a git_worktree_state artifact")
        input_keys = [(item.kind, item.id) for item in self.inputs]
        if len(input_keys) != len(set(input_keys)):
            raise ValueError("run inputs must have unique kind/id pairs")
        artifact_paths = [item.path for item in self.artifacts]
        if len(artifact_paths) != len(set(artifact_paths)):
            raise ValueError("run artifacts must have unique paths")
        tool_keys = [(item.name, item.version) for item in self.environment.tools]
        if len(tool_keys) != len(set(tool_keys)):
            raise ValueError("run tools must be unique")
        return self


def build_run_manifest(
    *,
    run_id: str,
    run_kind: str,
    stage: str,
    status: Literal["created", "running", "succeeded", "failed", "cancelled"],
    git_commit: str,
    git_dirty: bool,
    dependency_lock_hash: str,
    configuration_path: str,
    configuration_snapshot: object,
    inputs: Sequence[RunInputReference] = (),
    schema_versions: Sequence[str] = (),
    mapper_versions: Sequence[str] = (),
    transform_versions: Sequence[str] = (),
    policy_versions: Sequence[str] = (),
    ruleset_snapshot_ids: Sequence[str] = (),
    random_seeds: Sequence[int] = (),
    artifacts: Sequence[RunArtifactReference] = (),
    determinism: Literal["STRICT", "BEST_EFFORT", "EXTERNAL"] = "STRICT",
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    git_worktree_sha256: str | None = None,
    tools: Sequence[tuple[str, str] | Mapping[str, str]] = (("commander-deck-ai", "0.1.0"),),
    warnings: Sequence[str] = (),
) -> RunManifest:
    snapshot_bytes = configuration_snapshot_bytes(configuration_snapshot)
    schema_values = _unique_strings(schema_versions, "schema versions")
    mapper_values = _unique_strings(mapper_versions, "mapper versions")
    transform_values = _unique_strings(transform_versions, "transform versions")
    policy_values = _unique_strings(policy_versions, "policy versions")
    ruleset_values = _unique_strings(ruleset_snapshot_ids, "ruleset versions")
    seed_values = _unique_seeds(random_seeds)
    feature_versions = tuple(
        sorted(
            {f"schema:{value}" for value in schema_values}
            | {f"mapper:{value}" for value in mapper_values}
            | {f"transform:{value}" for value in transform_values}
            | {f"policy:{value}" for value in policy_values}
        )
    )
    created_value = created_at or datetime.now(UTC)
    return _with_manifest_digest(
        RunManifest(
            run_id=run_id,
            run_kind=run_kind,
            stage=stage,
            status=status,
            created_at=created_value,
            started_at=started_at,
            finished_at=finished_at,
            git_commit=git_commit,
            git_dirty=git_dirty,
            git_worktree_sha256=git_worktree_sha256,
            inputs=tuple(inputs),
            configuration=RunConfiguration(
                path=configuration_path,
                sha256=sha256_hex(snapshot_bytes),
            ),
            feature_spec_versions=feature_versions,
            ruleset_versions=tuple(sorted(ruleset_values)),
            determinism=determinism,
            random_seeds=tuple(sorted(seed_values)),
            environment=RunEnvironment(
                python_version=platform.python_version(),
                platform=platform.platform(aliased=True),
                dependency_lock_hash=dependency_lock_hash,
                tools=tuple(_tool_payload(tool) for tool in tools),
            ),
            artifacts=tuple(artifacts),
            warnings=tuple(warnings),
            sha256="0" * 64,
        )
    )


def run_manifest_bytes(manifest: RunManifest) -> bytes:
    validated = RunManifest.model_validate(manifest.model_dump(mode="json", exclude_none=True))
    payload = validated.model_dump(mode="json", exclude_none=True)
    expected = sha256_hex(
        canonical_json_bytes({key: value for key, value in payload.items() if key != "sha256"})
    )
    if expected != validated.sha256:
        raise ValueError("run manifest digest does not match its canonical content")
    return canonical_json_bytes(payload)


def validate_run_manifest_bytes(value: bytes) -> RunManifest:
    try:
        payload = json.loads(value.decode("utf-8"), object_pairs_hook=_reject_duplicate_members)
    except (UnicodeError, json.JSONDecodeError, ValueError) as error:
        raise ValueError("run manifest is not valid JSON or contains duplicate members") from error
    if not isinstance(payload, dict):
        raise ValueError("run manifest must be a JSON object")
    if canonical_json_bytes(payload) != value:
        raise ValueError("run manifest serialization is not canonical")
    manifest = RunManifest.model_validate(payload)
    expected = sha256_hex(
        canonical_json_bytes({key: item for key, item in payload.items() if key != "sha256"})
    )
    if expected != manifest.sha256:
        raise ValueError("run manifest digest mismatch")
    return manifest


def verify_run_manifest(root: Path | str, manifest_path: str) -> RunManifest:
    from .run_manifest_verifier import verify_run_manifest as verify

    return verify(root, manifest_path)


def _with_manifest_digest(manifest: RunManifest) -> RunManifest:
    payload = manifest.model_dump(mode="json", exclude_none=True)
    digest = sha256_hex(
        canonical_json_bytes({key: value for key, value in payload.items() if key != "sha256"})
    )
    return manifest.model_copy(update={"sha256": digest})


def _reject_duplicate_members(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate run manifest member: {key}")
        result[key] = value
    return result


def _unique_strings(values: Sequence[str], label: str) -> tuple[str, ...]:
    selected = tuple(values)
    if any(not isinstance(value, str) or not value for value in selected):
        raise ValueError(f"{label} must be non-empty strings")
    if len(selected) != len(set(selected)):
        raise ValueError(f"{label} must be unique")
    return selected


def _unique_seeds(values: Sequence[int]) -> tuple[int, ...]:
    selected = tuple(values)
    if any(type(value) is not int or value < 0 for value in selected):
        raise ValueError("random seeds must be non-negative integers")
    if len(selected) != len(set(selected)):
        raise ValueError("random seeds must be unique")
    return selected


def _tool_payload(tool: tuple[str, str] | Mapping[str, str]) -> RunTool:
    if isinstance(tool, Mapping):
        if set(tool) != {"name", "version"}:
            raise ValueError("tool metadata must contain only name and version")
        return RunTool(name=tool["name"], version=tool["version"])
    name, version = tool
    return RunTool(name=name, version=version)


build_run_provenance = build_run_manifest
serialize_run_manifest = run_manifest_bytes
validate_run_manifest = validate_run_manifest_bytes


__all__ = [
    "RunArtifactReference",
    "RunConfiguration",
    "RunEnvironment",
    "RunHardware",
    "RunInputReference",
    "RunManifest",
    "RunTool",
    "build_run_manifest",
    "build_run_provenance",
    "configuration_snapshot_bytes",
    "redacted_configuration_snapshot",
    "run_manifest_bytes",
    "serialize_run_manifest",
    "validate_run_manifest",
    "validate_run_manifest_bytes",
    "verify_run_manifest",
]
