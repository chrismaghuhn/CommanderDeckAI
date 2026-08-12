"""Application use case for source-snapshot normalization."""

from __future__ import annotations

from commander_ai.application.errors import ApplicationError, from_port_error
from commander_ai.application.ports.data_pipeline import NormalizeDataPort, NormalizeResult


class NormalizeData:
    def __init__(self, pipeline: NormalizeDataPort) -> None:
        self._pipeline = pipeline

    def execute(self, snapshot_id: str) -> NormalizeResult:
        if not isinstance(snapshot_id, str) or not snapshot_id.strip():
            raise ApplicationError("CONFIG_SNAPSHOT_ID_INVALID")
        try:
            return self._pipeline.normalize_snapshot(snapshot_id.strip())
        except ApplicationError:
            raise
        except Exception as error:
            raise from_port_error(error, "INTEGRITY_NORMALIZATION_REJECTED") from None


__all__ = ["NormalizeData"]
