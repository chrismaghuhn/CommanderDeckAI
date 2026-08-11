"""Application use case for normalized-snapshot validation."""

from __future__ import annotations

from commander_ai.application.errors import ApplicationError, from_port_error
from commander_ai.application.ports.data_pipeline import ValidateDataPort, ValidateResult


class ValidateData:
    def __init__(self, pipeline: ValidateDataPort) -> None:
        self._pipeline = pipeline

    def execute(self, normalized_snapshot_id: str) -> ValidateResult:
        if not isinstance(normalized_snapshot_id, str) or not normalized_snapshot_id.strip():
            raise ApplicationError("CONFIG_NORMALIZED_SNAPSHOT_ID_INVALID")
        try:
            return self._pipeline.validate_snapshot(normalized_snapshot_id.strip())
        except ApplicationError:
            raise
        except Exception as error:
            raise from_port_error(error, "INTEGRITY_NORMALIZED_SNAPSHOT_INVALID") from None


__all__ = ["ValidateData"]
