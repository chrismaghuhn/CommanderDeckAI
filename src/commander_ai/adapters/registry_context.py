"""Lazy loading of the reviewed source registry for downstream operations."""

from __future__ import annotations

import os
from pathlib import Path

from commander_ai.application.errors import ApplicationError
from commander_ai.config import ConfigurationError, SourceRegistry, load_config

SOURCE_REGISTRY_ENV = "COMMANDER_AI_SOURCE_REGISTRY"


class SourceRegistryProvider:
    """Resolve a full registry without making source operations implicit."""

    def __init__(self, repository_root: Path | str) -> None:
        self._root = Path(repository_root).expanduser().absolute()

    def load(self) -> tuple[SourceRegistry, Path]:
        configured = os.environ.get(SOURCE_REGISTRY_ENV)
        candidate = (
            Path(configured).expanduser()
            if configured
            else self._root / "configs" / "sources" / "registry.yaml"
        )
        if not candidate.is_file() or candidate.is_symlink():
            raise ApplicationError("POLICY_SOURCE_REGISTRY_REQUIRED")
        try:
            registry = load_config(candidate, SourceRegistry)
        except ConfigurationError:
            raise ApplicationError("CONFIG_SOURCE_REGISTRY_INVALID") from None
        return registry, candidate


__all__ = ["SOURCE_REGISTRY_ENV", "SourceRegistryProvider"]
