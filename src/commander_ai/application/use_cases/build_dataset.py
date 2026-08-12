"""Application use case for task-specific dataset builds."""

from __future__ import annotations

from commander_ai.application.errors import ApplicationError, from_port_error
from commander_ai.application.ports.dataset_store import DatasetBuildPort, DatasetBuildResult


class BuildDataset:
    def __init__(self, datasets: DatasetBuildPort) -> None:
        self._datasets = datasets

    def execute(self, config_path: str) -> DatasetBuildResult:
        if not isinstance(config_path, str) or not config_path.strip():
            raise ApplicationError("CONFIG_DATASET_CONFIG_REQUIRED")
        try:
            return self._datasets.build_dataset(config_path.strip())
        except ApplicationError:
            raise
        except Exception as error:
            raise from_port_error(error, "QUALITY_DATASET_BUILD_FAILED") from None


__all__ = ["BuildDataset"]
