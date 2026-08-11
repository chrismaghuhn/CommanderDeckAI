"""Strict runtime configuration and portable artifact-root handling."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from commander_ai.domain.path_policy import (
    resolve_under_root,
    to_portable_relative_path,
    validate_portable_relative_path,
)

_REPOSITORY_ROOT_MARKER = "<repository-root>"
_EXTERNAL_ROOT_MARKER = "<external-root>"
_NON_RELOADABLE_ROOT_MARKERS = frozenset({_REPOSITORY_ROOT_MARKER, _EXTERNAL_ROOT_MARKER})


class RuntimeConfig(BaseModel):
    """Global paths anchored to the repository, not the process working directory.

    Filesystem operations use resolved absolute roots. Persisted snapshots should use
    :meth:`portable_snapshot`, which emits repository-relative POSIX roots and opaque
    markers for roots outside the repository.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    schema_version: Literal["runtime.v1"] = "runtime.v1"
    data_root: Path = Path("data")
    artifact_root: Path = Path("artifacts")
    default_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    default_max_retries: int = Field(default=2, ge=0, le=8)
    default_rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)
    default_max_pages: int = Field(default=100, ge=1, le=100_000)
    default_max_download_bytes: int = Field(default=2_000_000_000, ge=1, le=20_000_000_000)

    @model_validator(mode="after")
    def normalize_roots(self) -> RuntimeConfig:
        repository_root = self._repository_root()
        data_root = self._resolve_root(self.data_root, repository_root)
        artifact_root = self._resolve_root(self.artifact_root, repository_root)
        object.__setattr__(self, "data_root", data_root)
        object.__setattr__(self, "artifact_root", artifact_root)
        return self

    @staticmethod
    def _repository_root() -> Path:
        return Path(__file__).resolve().parents[3]

    @staticmethod
    def _resolve_root(path: Path, repository_root: Path) -> Path:
        if path.as_posix() in _NON_RELOADABLE_ROOT_MARKERS:
            raise ValueError(
                "portable snapshot root markers are snapshot-only and cannot be loaded "
                "as filesystem roots"
            )
        expanded = path.expanduser()
        if not expanded.is_absolute():
            expanded = repository_root / expanded
        return expanded.resolve()

    def resolve_artifact_path(self, relative_path: str) -> Path:
        """Resolve a portable artifact path while keeping it below ``artifact_root``."""

        return resolve_under_root(self.artifact_root, relative_path)

    def resolve_data_path(self, relative_path: str) -> Path:
        """Resolve a portable data path while keeping it below ``data_root``."""

        return resolve_under_root(self.data_root, relative_path)

    def portable_artifact_path(self, path: Path | str) -> str:
        """Return a validated POSIX path relative to the configured artifact root."""

        return to_portable_relative_path(path, self.artifact_root)

    def portable_data_path(self, path: Path | str) -> str:
        """Return a validated POSIX path relative to the configured data root."""

        return to_portable_relative_path(path, self.data_root)

    def portable_snapshot(self) -> dict[str, object]:
        """Return the runtime config with portable, non-machine-specific root values."""

        return {
            "schema_version": self.schema_version,
            "data_root": self.portable_root_reference(self.data_root),
            "artifact_root": self.portable_root_reference(self.artifact_root),
            "default_timeout_seconds": self.default_timeout_seconds,
            "default_max_retries": self.default_max_retries,
            "default_rate_limit_per_minute": self.default_rate_limit_per_minute,
            "default_max_pages": self.default_max_pages,
            "default_max_download_bytes": self.default_max_download_bytes,
        }

    @classmethod
    def portable_root_reference(cls, path: Path | str) -> str:
        """Represent a root relative to the repository or as an opaque external marker."""

        candidate = cls._resolve_root(Path(path), cls._repository_root())
        repository_root = cls._repository_root()
        try:
            relative = candidate.relative_to(repository_root)
        except ValueError:
            return _EXTERNAL_ROOT_MARKER
        if relative == Path("."):
            return _REPOSITORY_ROOT_MARKER
        return validate_portable_relative_path(relative.as_posix())
