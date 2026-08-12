"""Application use cases for source discovery, review, and synchronization."""

from __future__ import annotations

from collections.abc import Sequence

from commander_ai.application.errors import ApplicationError, from_port_error
from commander_ai.application.ports.source_adapter import (
    SourceCatalogPort,
    SourceReview,
    SourceSummary,
    SourceSyncPort,
    SourceSyncResult,
)
from commander_ai.config.source_settings import normalize_source_id


class SourceCommands:
    """Coordinate source operations while keeping source I/O behind ports."""

    def __init__(self, catalog: SourceCatalogPort, sync: SourceSyncPort) -> None:
        self._catalog = catalog
        self._sync = sync

    def list_sources(self) -> Sequence[SourceSummary]:
        try:
            return tuple(sorted(self._catalog.list_sources(), key=lambda item: item.source_id))
        except ApplicationError:
            raise
        except Exception as error:
            raise from_port_error(error, "CONFIG_SOURCE_CATALOG_FAILED") from None

    def review(self, source_id: str) -> SourceReview:
        normalized = _source_id(source_id)
        try:
            return self._catalog.review_source(normalized)
        except ApplicationError:
            raise
        except Exception as error:
            raise from_port_error(error, "CONFIG_SOURCE_REVIEW_FAILED") from None

    def sync(self, source_id: str, config_path: str) -> SourceSyncResult:
        normalized = _source_id(source_id)
        path = _required_text(config_path, "config_path", "CONFIG_CONFIG_PATH_REQUIRED")
        try:
            return self._sync.sync_source(normalized, path)
        except ApplicationError:
            raise
        except Exception as error:
            raise from_port_error(error, "ACQ_SOURCE_SYNC_FAILED") from None


def _source_id(value: str) -> str:
    try:
        return normalize_source_id(value)
    except (TypeError, ValueError):
        raise ApplicationError("CONFIG_SOURCE_ID_INVALID") from None


def _required_text(value: str, field_name: str, code: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ApplicationError(code)
    return value.strip()


__all__ = ["SourceCommands"]
