import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commander_ai.data_pipeline.reports.report_writer import (
    ReportWriter,
    render_markdown,
)


def test_report_writer_derives_markdown_from_the_same_stable_payload(tmp_path: Path) -> None:
    payload = {
        "schema_version": "fixture-report.v1",
        "report_id": "report-1",
        "reported_at": datetime(2026, 8, 11, tzinfo=UTC).isoformat().replace("+00:00", "Z"),
        "summary": {"z": 2, "a": 1},
        "sources": [{"source_id": "b"}, {"source_id": "a"}],
    }

    artifacts = ReportWriter(tmp_path).write_report(
        payload,
        json_path="reports/report.json",
        markdown_path="reports/report.md",
    )

    json_bytes = (tmp_path / "reports/report.json").read_bytes()
    markdown_bytes = (tmp_path / "reports/report.md").read_bytes()
    assert json.loads(json_bytes) == payload
    assert markdown_bytes == render_markdown(payload)
    assert artifacts.json.path == "reports/report.json"
    assert artifacts.markdown is not None
    with pytest.raises(FileExistsError):
        ReportWriter(tmp_path).write_report(payload, json_path="reports/report.json")
