"""Fail-closed inspection of immutable dataset manifests and Parquet outputs."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import JsonArtifact
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.adapters.storage.path_policy import resolve_under_root
from commander_ai.adapters.storage.raw_snapshot_io import sha256_file
from commander_ai.data_pipeline.datasets.dataset_content import compute_dataset_content_sha256
from commander_ai.domain.dataset_contracts import DatasetManifest, DatasetOutputReference
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
    artifact_root = Path(root).expanduser().absolute()
    manifest_path = f"datasets/{dataset_id}/manifest.json"
    manifest_file = resolve_under_root(artifact_root, manifest_path)
    if not manifest_file.is_file() or manifest_file.is_symlink():
        raise FileNotFoundError(manifest_path)
    payload_bytes = manifest_file.read_bytes()
    payload = json.loads(payload_bytes.decode("utf-8"))
    if canonical_json_bytes(payload) != payload_bytes:
        raise ValueError("dataset manifest is not canonical JSON")
    manifest = DatasetManifest.model_validate(payload)
    if manifest.dataset_id != dataset_id:
        raise ValueError("dataset manifest id does not match requested dataset")
    expected_manifest_hash = detached_manifest_sha256(
        manifest.model_dump(mode="json", exclude_none=True)
    )
    if expected_manifest_hash != manifest.manifest_sha256:
        raise ValueError("dataset manifest digest mismatch")
    output_rows: list[tuple[str, int]] = []
    table_reader = ParquetTableWriter(artifact_root)
    content_inputs: list[tuple[str, list[dict[str, object]]]] = []
    for output in manifest.outputs:
        _verify_output_artifact(artifact_root, dataset_id, output)
        rows = table_reader.read_table(output.path)
        if len(rows) != output.rows:
            raise ValueError(f"dataset output row count mismatch: {output.path}")
        output_rows.append((output.name, len(rows)))
        content_inputs.append((output.name, rows))
    declared_output_rows = manifest.counts.get("output_rows")
    actual_output_rows = sum(rows for _, rows in output_rows)
    if declared_output_rows is not None and declared_output_rows != actual_output_rows:
        raise ValueError("dataset manifest output row count mismatch")
    _verify_dataset_counts(manifest, content_inputs)
    for report in (manifest.quality_report, manifest.leakage_report):
        if report is not None:
            _verify_report_artifact(artifact_root, dataset_id, manifest, report)
    if len(content_inputs) != 1:
        raise ValueError("dataset content digest verification requires one output table")
    table_name, rows = content_inputs[0]
    expected_content_digest = compute_dataset_content_sha256(
        dataset_id=manifest.dataset_id,
        dataset_kind=manifest.dataset_kind,
        table_name=table_name,
        rows=rows,
    )
    if expected_content_digest != manifest.dataset_content_sha256:
        raise ValueError("dataset content digest mismatch")
    return DatasetInspection(
        manifest=manifest,
        manifest_artifact=JsonArtifact(
            path=manifest_path,
            sha256=sha256_file(manifest_file),
            bytes=manifest_file.stat().st_size,
        ),
        output_rows=tuple(sorted(output_rows)),
    )


def _validate_dataset_output_path(path: str, dataset_id: str) -> None:
    expected_prefix = f"datasets/{dataset_id}/"
    if not path.startswith(expected_prefix):
        raise ValueError("dataset output path escapes its dataset directory")


def _verify_output_artifact(root: Path, dataset_id: str, output: DatasetOutputReference) -> Path:
    path_value = output.path
    _validate_dataset_output_path(path_value, dataset_id)
    output_path = resolve_under_root(root, path_value)
    if not output_path.is_file() or output_path.is_symlink():
        raise FileNotFoundError(path_value)
    if sha256_file(output_path) != output.sha256:
        raise ValueError(f"dataset output hash mismatch: {path_value}")
    if output.bytes is None:
        raise ValueError(f"dataset output byte count required: {path_value}")
    if output_path.stat().st_size != output.bytes:
        raise ValueError(f"dataset output byte count mismatch: {path_value}")
    return output_path


def _verify_dataset_counts(
    manifest: DatasetManifest,
    content_inputs: list[tuple[str, list[dict[str, object]]]],
) -> None:
    required = {
        "train",
        "validation",
        "test",
        "eligible_records",
        "excluded_records",
        "input_records",
        "output_rows",
    }
    missing = sorted(required - manifest.counts.keys())
    if missing:
        raise ValueError("dataset manifest counts are incomplete: " + ", ".join(missing))
    record_splits: dict[str, str] = {}
    strata: dict[str, str] = {}
    for _, rows in content_inputs:
        for row in rows:
            values = row.get("values")
            if not isinstance(values, Mapping):
                raise ValueError("curated row values must be a mapping")
            record_id = values.get("record_id")
            split = values.get("split")
            if not isinstance(record_id, str) or not record_id:
                raise ValueError("curated row record_id is required")
            if split not in {"train", "validation", "test"}:
                raise ValueError("curated row split is invalid")
            previous = record_splits.setdefault(record_id, split)
            if previous != split:
                raise ValueError("one dataset record appears in multiple splits")
            stratum = values.get("familiar_stratum")
            if stratum is not None:
                if stratum not in {"familiar", "unseen"}:
                    raise ValueError("curated row familiar_stratum is invalid")
                previous_stratum = strata.setdefault(record_id, stratum)
                if previous_stratum != stratum:
                    raise ValueError("one dataset record has multiple familiarity strata")
    split_counts = Counter(record_splits.values())
    for split in ("train", "validation", "test"):
        if manifest.counts[split] != split_counts.get(split, 0):
            raise ValueError(f"dataset manifest {split} count mismatch")
    eligible = len(record_splits)
    if manifest.counts["eligible_records"] != eligible:
        raise ValueError("dataset manifest eligible record count mismatch")
    exclusion_count = sum(exclusion.count for exclusion in manifest.exclusions)
    if manifest.counts["excluded_records"] != exclusion_count:
        raise ValueError("dataset manifest excluded record count mismatch")
    for exclusion in manifest.exclusions:
        if exclusion.count != len(exclusion.references):
            raise ValueError(f"dataset exclusion reference count mismatch: {exclusion.code}")
    if manifest.counts["input_records"] != eligible + exclusion_count:
        raise ValueError("dataset manifest input record count mismatch")
    if "familiar_records" in manifest.counts or "unseen_records" in manifest.counts:
        if manifest.counts.get("familiar_records", 0) != sum(
            value == "familiar" for value in strata.values()
        ):
            raise ValueError("dataset manifest familiar record count mismatch")
        if manifest.counts.get("unseen_records", 0) != sum(
            value == "unseen" for value in strata.values()
        ):
            raise ValueError("dataset manifest unseen record count mismatch")


def _verify_report_artifact(
    root: Path,
    dataset_id: str,
    manifest: DatasetManifest,
    output: DatasetOutputReference,
) -> None:
    path = _verify_output_artifact(root, dataset_id, output)
    if output.rows != 1 or path.suffix.casefold() != ".json":
        raise ValueError("dataset report must be one canonical JSON document")
    payload_bytes = path.read_bytes()
    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeError, json.JSONDecodeError) as error:
        raise ValueError("dataset report is not valid JSON") from error
    if not isinstance(payload, Mapping) or canonical_json_bytes(payload) != payload_bytes:
        raise ValueError("dataset report is not canonical JSON")
    if payload.get("dataset_id") != manifest.dataset_id:
        raise ValueError("dataset report dataset_id mismatch")
    if payload.get("dataset_kind") != manifest.dataset_kind:
        raise ValueError("dataset report dataset_kind mismatch")
    if payload.get("dataset_content_sha256") != manifest.dataset_content_sha256:
        raise ValueError("dataset report content binding mismatch")
    expected_inputs = [item.model_dump(mode="json") for item in manifest.input_manifests]
    if payload.get("input_manifests") != expected_inputs:
        raise ValueError("dataset report input binding mismatch")


__all__ = ["DatasetInspection", "inspect_dataset"]
