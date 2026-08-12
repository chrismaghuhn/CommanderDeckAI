"""Immutable JSON/Markdown publication for derived quality reports."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import JsonArtifact, ManifestFileWriter
from commander_ai.domain.serialization import canonical_json_bytes

ReportArtifact = JsonArtifact


@dataclass(frozen=True, slots=True)
class ReportArtifacts:
    json: JsonArtifact
    markdown: JsonArtifact | None = None


class ReportWriter:
    """Publish report artifacts below one configured, portable root."""

    def __init__(self, root: Path | str) -> None:
        self._writer = ManifestFileWriter(root)

    def write_report(
        self,
        report: Mapping[str, object] | object,
        *,
        json_path: str,
        markdown_path: str | None = None,
    ) -> ReportArtifacts:
        payload = _report_payload(report)
        json_artifact = self._writer.write_json(json_path, canonical_json_bytes(payload))
        markdown = None
        if markdown_path is not None:
            markdown = self._writer.write_json(markdown_path, render_markdown(payload))
        return ReportArtifacts(json=json_artifact, markdown=markdown)


def render_markdown(report: Mapping[str, object]) -> bytes:
    """Render a concise Markdown view from the exact machine-readable payload."""

    title = str(report.get("schema_version", "quality-report"))
    lines = [f"# {title}", ""]
    for key in sorted(report):
        value = report[key]
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        lines.append(f"- **{key}**: `{serialized}`")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _report_payload(report: Mapping[str, object] | object) -> dict[str, object]:
    if isinstance(report, Mapping):
        return {str(key): value for key, value in report.items()}
    as_dict = getattr(report, "as_dict", None)
    if not callable(as_dict):
        raise TypeError("report must be a mapping or expose as_dict()")
    payload = as_dict()
    if not isinstance(payload, Mapping):
        raise TypeError("report as_dict() must return a mapping")
    return {str(key): value for key, value in payload.items()}


__all__ = ["ReportArtifact", "ReportArtifacts", "ReportWriter", "render_markdown"]
