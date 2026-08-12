"""Application use case for verified dataset inspection."""

from __future__ import annotations

from commander_ai.application.errors import ApplicationError, from_port_error
from commander_ai.application.ports.dataset_store import (
    DatasetInspectionResult,
    DatasetInspectPort,
)


class InspectDataset:
    def __init__(self, datasets: DatasetInspectPort) -> None:
        self._datasets = datasets

    def execute(self, dataset_id: str) -> DatasetInspectionResult:
        if not isinstance(dataset_id, str) or not dataset_id.strip():
            raise ApplicationError("CONFIG_DATASET_ID_INVALID")
        try:
            return self._datasets.inspect_dataset(dataset_id.strip())
        except ApplicationError:
            raise
        except Exception as error:
            raise from_port_error(error, "INTEGRITY_DATASET_INSPECTION") from None


__all__ = ["InspectDataset"]
