"""Application port for source and dataset quality reports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ReportResult:
    selector: str
    status: str
    report_path: str
    report_sha256: str
    summary: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return {
            "selector": self.selector,
            "status": self.status,
            "report_path": self.report_path,
            "report_sha256": self.report_sha256,
            "summary": dict(self.summary),
        }


class ReportDataPort(Protocol):
    def build_report(self, selector: str) -> ReportResult:
        """Build one report from already acquired, policy-eligible artifacts."""


__all__ = ["ReportDataPort", "ReportResult"]
