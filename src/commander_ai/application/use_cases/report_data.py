"""Application use case for source and dataset quality reports."""

from __future__ import annotations

from commander_ai.application.errors import ApplicationError, from_port_error
from commander_ai.application.ports.reporting import ReportDataPort, ReportResult


class ReportData:
    def __init__(self, reporting: ReportDataPort) -> None:
        self._reporting = reporting

    def execute(self, selector: str) -> ReportResult:
        if not isinstance(selector, str) or not selector.strip():
            raise ApplicationError("CONFIG_REPORT_SELECTOR_INVALID")
        normalized = selector.strip().casefold()
        allowed = "abcdefghijklmnopqrstuvwxyz0123456789_-"
        if normalized != "all" and any(character not in allowed for character in normalized):
            raise ApplicationError("CONFIG_REPORT_SELECTOR_INVALID")
        try:
            return self._reporting.build_report(normalized)
        except ApplicationError:
            raise
        except Exception as error:
            raise from_port_error(error, "QUALITY_REPORT_FAILED") from None


__all__ = ["ReportData"]
