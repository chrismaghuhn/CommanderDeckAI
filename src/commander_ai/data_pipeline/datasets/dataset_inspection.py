"""Fail-closed inspection of immutable dataset manifests and Parquet outputs."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import JsonArtifact
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.adapters.storage.path_policy import resolve_under_root
from commander_ai.adapters.storage.raw_snapshot_io import sha256_file
from commander_ai.domain.dataset_contracts import DatasetManifest
from commander_ai.domain.provenance import detached_manifest_sha256
from commander_ai.domain.serialization import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class DatasetInspection:
    manifest: DatasetManifest
    manifest_artifact: JsonArtifact
    output_rows: tuple[tuple[str, int], ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.manifest.dataset_id,
            "dataset_kind": self.manifest.dataset_kind,
            "manifest_sha256": self.manifest.manifest_sha256,
            "counts": dict(self.manifest.counts),
            "outputs": [{"name": name, "rows": rows} for name, rows in self.output_rows],
        }


def inspect_dataset(root: Path | str, dataset_id: str) -> DatasetInspection:
    """Read and verify one dataset without mutating or rebuilding it."""

    if not dataset_id.strip():
        raise ValueError("dataset_id must be non-empty")
    artifact_root = Path(root).expanduser().resolve()
    manifest_path = f"datasets/{dataset_id}/manifest.json"
    manifest_file = resolve_under_root(artifact_root, manifest_path)
    if not manifest_file.is_file() or manifest_file.is_symlink():
        raise FileNotFoundError(manifest_path)
    payload_bytes = manifest_file.read_bytes()
    payload = json.loads(payload_bytes.decode("utf-8"))
    if canonical_json_bytes(payload) != payload_bytes:
        raise ValueError("dataset manifest is not canonical JSON")
    manifest = DatasetManifest.model_validate(payload)
    expected_manifest_hash = detached_manifest_sha256(
        manifest.model_dump(mode="json", exclude_none=True)
    )
    if expected_manifest_hash != manifest.manifest_sha256:
        raise ValueError("dataset manifest digest mismatch")
    output_rows: list[tuple[str, int]] = []
    table_reader = ParquetTableWriter(artifact_root)
    for output in manifest.outputs:
        output_path = resolve_under_root(artifact_root, output.path)
        if not output_path.is_file() or output_path.is_symlink():
            raise FileNotFoundError(output.path)
        if sha256_file(output_path) != output.sha256:
            raise ValueError(f"dataset output hash mismatch: {output.path}")
        rows = table_reader.read_table(output.path)
        if len(rows) != output.rows:
            raise ValueError(f"dataset output row count mismatch: {output.path}")
        output_rows.append((output.name, len(rows)))
    return DatasetInspection(
        manifest=manifest,
        manifest_artifact=JsonArtifact(
            path=manifest_path,
            sha256=sha256_file(manifest_file),
            bytes=manifest_file.stat().st_size,
        ),
        output_rows=tuple(sorted(output_rows)),
    )


__all__ = ["DatasetInspection", "inspect_dataset"]
