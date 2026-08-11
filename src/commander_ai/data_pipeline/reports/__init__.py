"""Deterministic source-quality and dataset-audit report builders."""

from .dataset_audit import DatasetAuditReport, build_dataset_audit_report
from .report_writer import ReportArtifact, ReportArtifacts, ReportWriter, render_markdown
from .source_metrics import (
    DeckMetricRecord,
    ReportInputBinding,
    SourceMetricsInput,
    SourceMetricsReport,
    build_source_metrics_report,
)

__all__ = [
    "DatasetAuditReport",
    "DeckMetricRecord",
    "ReportArtifact",
    "ReportArtifacts",
    "ReportInputBinding",
    "ReportWriter",
    "SourceMetricsInput",
    "SourceMetricsReport",
    "build_dataset_audit_report",
    "build_source_metrics_report",
    "render_markdown",
]
