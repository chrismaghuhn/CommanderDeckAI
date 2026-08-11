"""Construction and canonical serialization for the frozen run-manifest.v1 contract."""

from __future__ import annotations

import platform
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, field_validator, model_validator

from commander_ai.domain.path_policy import validate_portable_relative_path
from commander_ai.domain.provenance import DomainModel
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex


class RunInputReference(DomainModel):
    kind: str = Field(min_length=1)
    id: str = Field(min_length=1)
    path: str | None = Field(default=None, min_length=1)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str | None) -> str | None:
        return None if value is None else validate_portable_relative_path(value)


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


class RunEnvironment(DomainModel):
    python_version: str = Field(min_length=1)
    platform: str = Field(min_length=1)
    dependency_lock_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    tools: tuple[dict[str, str], ...] = Field(min_length=1)
    hardware: dict[str, object] | None = None


class RunManifest(DomainModel):
    """Typed v1 run manifest; no secrets or source response bodies are accepted."""

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
        if self.determinism == "STRICT" and self.git_dirty:
            raise ValueError("strict runs require a clean git worktree")
        if self.git_dirty and self.git_worktree_sha256 is None:
            raise ValueError("dirty runs require git_worktree_sha256")
        if not self.git_dirty and self.git_worktree_sha256 is not None:
            raise ValueError("clean runs cannot bind a worktree hash")
        if self.git_dirty and not any(item.kind == "git_worktree_state" for item in self.artifacts):
            raise ValueError("dirty runs require a git_worktree_state artifact")
        return self


def redacted_configuration_snapshot(value: object, *, key: str | None = None) -> object:
    """Return a JSON-safe config projection with credential-shaped values removed."""

    if key is not None and _is_secret_key(key):
        return "[REDACTED]"
    if isinstance(value, Mapping):
        return {
            str(item_key): redacted_configuration_snapshot(item, key=str(item_key))
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redacted_configuration_snapshot(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    raise TypeError(f"unsupported configuration value: {type(value).__name__}")


def configuration_snapshot_bytes(value: object) -> bytes:
    return canonical_json_bytes(redacted_configuration_snapshot(value))


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
    feature_versions = tuple(
        sorted(
            {f"schema:{value}" for value in schema_versions}
            | {f"mapper:{value}" for value in mapper_versions}
            | {f"transform:{value}" for value in transform_versions}
            | {f"policy:{value}" for value in policy_versions}
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
            ruleset_versions=tuple(sorted(set(ruleset_snapshot_ids))),
            determinism=determinism,
            random_seeds=tuple(sorted(set(random_seeds))),
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
    payload = manifest.model_dump(mode="json", exclude_none=True)
    expected = sha256_hex(
        canonical_json_bytes({key: value for key, value in payload.items() if key != "sha256"})
    )
    if expected != manifest.sha256:
        raise ValueError("run manifest digest does not match its canonical content")
    return canonical_json_bytes(payload)


def validate_run_manifest_bytes(value: bytes) -> RunManifest:
    import json

    payload = json.loads(value.decode("utf-8"))
    if canonical_json_bytes(payload) != value:
        raise ValueError("run manifest serialization is not canonical")
    manifest = RunManifest.model_validate(payload)
    expected = sha256_hex(
        canonical_json_bytes({key: item for key, item in payload.items() if key != "sha256"})
    )
    if expected != manifest.sha256:
        raise ValueError("run manifest digest mismatch")
    return manifest


def _with_manifest_digest(manifest: RunManifest) -> RunManifest:
    payload = manifest.model_dump(mode="json", exclude_none=True)
    digest = sha256_hex(
        canonical_json_bytes({key: value for key, value in payload.items() if key != "sha256"})
    )
    return manifest.model_copy(update={"sha256": digest})


def _is_secret_key(key: str) -> bool:
    normalized = key.casefold().replace("-", "_")
    return any(
        marker in normalized
        for marker in (
            "api_key",
            "apikey",
            "authorization",
            "cookie",
            "password",
            "secret",
            "token",
            "credential",
            "auth",
            "private_key",
            "client_secret",
        )
    )


def _tool_payload(tool: tuple[str, str] | Mapping[str, str]) -> dict[str, str]:
    if isinstance(tool, Mapping):
        return {"name": tool["name"], "version": tool["version"]}
    name, version = tool
    return {"name": name, "version": version}


build_run_provenance = build_run_manifest
serialize_run_manifest = run_manifest_bytes
validate_run_manifest = validate_run_manifest_bytes


__all__ = [
    "RunArtifactReference",
    "RunConfiguration",
    "RunEnvironment",
    "RunInputReference",
    "RunManifest",
    "build_run_manifest",
    "build_run_provenance",
    "configuration_snapshot_bytes",
    "redacted_configuration_snapshot",
    "run_manifest_bytes",
    "serialize_run_manifest",
    "validate_run_manifest",
    "validate_run_manifest_bytes",
]
