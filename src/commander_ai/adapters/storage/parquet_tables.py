"""Deterministic Parquet persistence for rebuildable normalized-layer tables."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]

from commander_ai.domain.serialization import canonical_json_bytes

from .path_policy import resolve_under_root, validate_portable_relative_path
from .raw_snapshot_io import fsync_directory, publish_new, sha256_file

_PARQUET_LAYERS = frozenset({"staging", "normalized", "audit", "quarantine", "curated"})


@dataclass(frozen=True, slots=True)
class ParquetArtifact:
    table_name: str
    layer: Literal["staging", "normalized", "audit", "quarantine", "curated"]
    path: str
    sha256: str
    rows: int
    bytes: int
    schema_version: str


class ParquetTableWriter:
    """Write immutable row-json Parquet tables below one configured artifact root."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def write_table(
        self,
        table_name: str,
        rows: Iterable[object],
        *,
        relative_path: str | None = None,
        schema_version: str = "staging.v1",
        layer: Literal["staging", "normalized", "audit", "quarantine", "curated"] | None = None,
    ) -> ParquetArtifact:
        if not table_name or table_name.startswith("."):
            raise ValueError("table name must be a portable non-hidden name")
        if layer is None:
            raise ValueError("Parquet table persistence requires an explicit layer")
        if not isinstance(layer, str) or layer not in _PARQUET_LAYERS:
            raise ValueError("Parquet table layer is not recognized")
        if table_name.casefold() == "audit" and layer != "audit":
            raise ValueError("audit tables require the audit layer")
        if table_name.casefold() == "quarantine" and layer != "quarantine":
            raise ValueError("quarantine tables require the quarantine layer")
        if table_name.casefold().startswith("curated") and layer != "curated":
            raise ValueError("curated tables require the curated layer")
        normalized_rows = [_row_payload(row) for row in rows]
        if layer == "curated" and any(row.get("layer") != "curated" for row in normalized_rows):
            raise ValueError(
                "staging, normalized, audit, or quarantine rows cannot be written to curated tables"
            )
        if layer in {"audit", "quarantine"} and any(
            row.get("layer") != layer for row in normalized_rows
        ):
            raise ValueError(f"{layer} rows must carry the {layer} layer metadata")
        if layer == "normalized" and any(
            row.get("layer") not in {None, "staging", "normalized"} for row in normalized_rows
        ):
            raise ValueError("normalized tables cannot contain audit or quarantine rows")
        portable_path = validate_portable_relative_path(
            relative_path or f"normalized/{table_name}.parquet"
        )
        final_path = resolve_under_root(self.root, portable_path)
        if final_path.exists() or final_path.is_symlink():
            raise FileExistsError(portable_path)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        row_json = [canonical_json_bytes(row).decode("utf-8") for row in normalized_rows]
        table = pa.Table.from_arrays(
            [pa.array(row_json, type=pa.string())], names=["row_json"]
        ).replace_schema_metadata(
            {
                b"commander_ai.table_name": table_name.encode("utf-8"),
                b"commander_ai.layer": layer.encode("utf-8"),
                b"commander_ai.schema_version": schema_version.encode("utf-8"),
            }
        )
        temporary_path: Path | None = None
        try:
            descriptor, name = _temporary_path(final_path.parent)
            os.close(descriptor)
            temporary_path = Path(name)
            pq.write_table(
                table,
                temporary_path,
                compression="zstd",
                compression_level=3,
                data_page_version="1.0",
                use_dictionary=False,
                write_statistics=False,
                version="2.6",
            )
            with temporary_path.open("r+b") as stream:
                os.fsync(stream.fileno())
            publish_new(temporary_path, final_path)
            temporary_path = None
            fsync_directory(final_path.parent)
        finally:
            if temporary_path is not None:
                with suppress(FileNotFoundError):
                    temporary_path.unlink()
        return ParquetArtifact(
            table_name=table_name,
            layer=layer,
            path=portable_path,
            sha256=sha256_file(final_path),
            rows=len(normalized_rows),
            bytes=final_path.stat().st_size,
            schema_version=schema_version,
        )

    def write_normalized_tables(
        self,
        *,
        staging: Iterable[object],
        audit: Iterable[object],
        quarantine: Iterable[object],
        schema_version: str = "staging.v1",
    ) -> tuple[ParquetArtifact, ParquetArtifact, ParquetArtifact]:
        """Write the three non-curated Task-5 layers as separate immutable tables."""

        return (
            self.write_table(
                "staging", staging, schema_version=schema_version, layer="normalized"
            ),
            self.write_table("audit", audit, schema_version="audit.v1", layer="audit"),
            self.write_table(
                "quarantine", quarantine, schema_version="quarantine.v1", layer="quarantine"
            ),
        )

    def read_table(self, relative_path: str) -> list[dict[str, Any]]:
        path = resolve_under_root(self.root, relative_path)
        table = pq.read_table(path)
        return [json.loads(value) for value in table.column("row_json").to_pylist()]


def _row_payload(row: object) -> dict[str, object]:
    model_dump = getattr(row, "model_dump", None)
    if callable(model_dump):
        value = model_dump(mode="json")
    elif isinstance(row, Mapping):
        value = dict(row)
    else:
        raise TypeError("Parquet rows must be mappings or Pydantic models")
    if not isinstance(value, dict):
        raise TypeError("Parquet row model_dump must return a mapping")
    return value


def _temporary_path(directory: Path) -> tuple[int, str]:
    import tempfile

    return tempfile.mkstemp(prefix=".parquet-", dir=directory)


__all__ = ["ParquetArtifact", "ParquetTableWriter"]
