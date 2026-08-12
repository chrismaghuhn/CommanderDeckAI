"""Deterministic Parquet persistence for rebuildable normalized-layer tables."""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa  # type: ignore[import-untyped]
import pyarrow.parquet as pq  # type: ignore[import-untyped]
from pydantic import BaseModel

from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.data_pipeline.provenance.rows import (
    AuditRecord,
    ProvenanceRow,
    ResolutionAttempt,
)
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.data_pipeline.staging.raw_locators import (
    RawLocator,
    validate_raw_locator_against_snapshot,
    validate_raw_object_against_snapshot,
)
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CanonicalCard, CardFace, CardResolution, Printing
from commander_ai.domain.provenance import DomainModel
from commander_ai.domain.serialization import canonical_json_bytes

from .archive_safety import ArchiveLimits
from .path_policy import resolve_under_root, validate_portable_relative_path
from .raw_snapshot_io import fsync_directory, publish_new, sha256_file

_PARQUET_LAYERS = frozenset({"staging", "normalized", "audit", "quarantine", "curated"})


class CuratedRow(DomainModel):
    """Explicit generic curated-table row contract for the Task-5 boundary."""

    curated_id: str
    values: Mapping[str, object]
    layer: Literal["curated"] = "curated"


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
        self.root = Path(root).expanduser().absolute()

    def write_table(
        self,
        table_name: str,
        rows: Iterable[object],
        *,
        relative_path: str | None = None,
        schema_version: str = "staging.v1",
        layer: Literal["staging", "normalized", "audit", "quarantine", "curated"] | None = None,
        row_contract: type[BaseModel] | None = None,
        verified_snapshot: VerifiedSourceSnapshot | None = None,
        archive_limits: ArchiveLimits | None = None,
        max_decoded_bytes: int | None = None,
    ) -> ParquetArtifact:
        if not table_name or table_name.startswith("."):
            raise ValueError("table name must be a portable non-hidden name")
        if layer is None:
            raise ValueError("Parquet table persistence requires an explicit layer")
        if not isinstance(layer, str) or layer not in _PARQUET_LAYERS:
            raise ValueError("Parquet table layer is not recognized")
        contract = _require_row_contract(layer, row_contract)
        if table_name.casefold() == "audit" and layer != "audit":
            raise ValueError("audit tables require the audit layer")
        if table_name.casefold() == "quarantine" and layer != "quarantine":
            raise ValueError("quarantine tables require the quarantine layer")
        if table_name.casefold().startswith("curated") and layer != "curated":
            raise ValueError("curated tables require the curated layer")
        typed_rows = list(rows)
        _validate_source_locators(
            typed_rows,
            verified_snapshot,
            archive_limits=archive_limits,
            max_decoded_bytes=max_decoded_bytes,
        )
        normalized_rows = [_row_payload(row, contract, layer) for row in typed_rows]
        portable_path = validate_portable_relative_path(
            relative_path
            or f"{'curated' if layer == 'curated' else 'normalized'}/{table_name}.parquet"
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
        published = False
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
            published = True
            temporary_path = None
            fsync_directory(final_path.parent)
        except Exception:
            if published:
                with suppress(FileNotFoundError):
                    final_path.unlink()
            raise
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
        staging_row_contract: type[BaseModel] = StagingRecord,
        audit_row_contract: type[BaseModel] = AuditRecord,
        quarantine_row_contract: type[BaseModel] = QuarantineRecord,
        verified_snapshot: VerifiedSourceSnapshot | None = None,
        archive_limits: ArchiveLimits | None = None,
        max_decoded_bytes: int | None = None,
    ) -> tuple[ParquetArtifact, ParquetArtifact, ParquetArtifact]:
        """Write the three non-curated Task-5 layers as separate immutable tables."""

        return (
            self.write_table(
                "staging",
                staging,
                schema_version=schema_version,
                layer="normalized",
                row_contract=staging_row_contract,
                verified_snapshot=verified_snapshot,
                archive_limits=archive_limits,
                max_decoded_bytes=max_decoded_bytes,
            ),
            self.write_table(
                "audit",
                audit,
                schema_version="audit.v1",
                layer="audit",
                row_contract=audit_row_contract,
                verified_snapshot=verified_snapshot,
                archive_limits=archive_limits,
                max_decoded_bytes=max_decoded_bytes,
            ),
            self.write_table(
                "quarantine",
                quarantine,
                schema_version="quarantine.v1",
                layer="quarantine",
                row_contract=quarantine_row_contract,
                verified_snapshot=verified_snapshot,
                archive_limits=archive_limits,
                max_decoded_bytes=max_decoded_bytes,
            ),
        )

    def read_table(self, relative_path: str) -> list[dict[str, Any]]:
        path = resolve_under_root(self.root, relative_path)
        table = pq.read_table(path)
        return [json.loads(value) for value in table.column("row_json").to_pylist()]


def _require_row_contract(layer: str, contract: type[BaseModel] | None) -> type[BaseModel]:
    if contract is None:
        raise ValueError("Parquet persistence requires an explicit typed row contract")
    allowed: dict[str, tuple[type[BaseModel], ...]] = {
        "staging": (StagingRecord,),
        "normalized": (StagingRecord, CanonicalRecord),
        "audit": (AuditRecord, CardResolution, ResolutionAttempt, ProvenanceRow),
        "quarantine": (QuarantineRecord,),
        "curated": (CuratedRow, CanonicalCard, CardFace, Printing),
    }
    if contract not in allowed[layer]:
        raise ValueError(f"row contract is not valid for the {layer} layer")
    return contract


def _row_payload(
    row: object,
    contract: type[BaseModel],
    layer: str,
) -> dict[str, object]:
    if not isinstance(row, contract):
        raise TypeError("Parquet rows must match the explicit typed row contract")
    model_dump = getattr(row, "model_dump", None)
    if callable(model_dump):
        value = model_dump(mode="json")
    else:
        raise TypeError("Parquet row contract must be a Pydantic domain model")
    if not isinstance(value, dict):
        raise TypeError("Parquet row model_dump must return a mapping")
    if contract in (CanonicalCard, CardFace, Printing):
        if layer != "curated":
            raise ValueError("canonical card contracts may only be persisted in curated")
        return value
    if contract is CardResolution:
        return value
    if contract is ProvenanceRow:
        if layer != "audit" or value.get("layer") not in {"normalized", "audit"}:
            raise ValueError(f"{layer} rows must carry the validated layer metadata")
        return value
    declared_layer = value.get("layer")
    expected_layers = {"staging", "normalized"} if layer == "normalized" else {layer}
    if declared_layer not in expected_layers:
        raise ValueError(f"{layer} rows must carry the validated layer metadata")
    return value


def _validate_source_locators(
    rows: Sequence[object],
    verified_snapshot: VerifiedSourceSnapshot | None,
    *,
    archive_limits: ArchiveLimits | None,
    max_decoded_bytes: int | None,
) -> None:
    locators: list[tuple[RawLocator, str | None, str | None]] = []
    identities: list[tuple[object, ...]] = []
    for row in rows:
        if isinstance(row, StagingRecord):
            locators.append((row.raw_locator, row.source_id, None))
            identities.append(("staging", row.record_type, row.raw_locator.identity))
        elif isinstance(row, CanonicalRecord):
            locators.append((row.raw_locator, row.source_id, None))
            identities.append(("canonical", row.record_type, row.raw_locator.identity))
        elif isinstance(row, ProvenanceRow):
            locators.append((row.raw_locator, row.source_id, row.raw_sha256))
            identities.append(("provenance", row.entity_id, row.raw_locator.identity))
        elif isinstance(row, CardResolution):
            identities.append(
                ("resolution", row.resolution_id, row.source_object_id, row.raw_locator)
            )
            if verified_snapshot is None:
                raise ValueError("card resolution rows require verified raw snapshot evidence")
            validate_raw_object_against_snapshot(
                row.source_object_id,
                verified_snapshot=verified_snapshot,
                source_id=row.source_id,
                source_snapshot_id=row.source_snapshot_id,
            )
        elif isinstance(row, (ResolutionAttempt, QuarantineRecord, AuditRecord)):
            locator = getattr(row, "raw_locator", None)
            if isinstance(locator, RawLocator):
                locators.append((locator, None, None))
                if isinstance(row, ResolutionAttempt):
                    identities.append(
                        ("resolution", row.staging_record_id, row.source_field, locator.identity)
                    )
                elif isinstance(row, QuarantineRecord):
                    identities.append(
                        ("quarantine", row.staging_record_id, row.reason_code, locator.identity)
                    )
                else:
                    identities.append(("audit", row.entity_id, row.finding_code, locator.identity))
        elif isinstance(row, (CanonicalCard, CardFace, Printing)):
            if verified_snapshot is None:
                raise ValueError("canonical curated rows require verified raw snapshot evidence")
            for reference in row.provenance:
                validate_raw_object_against_snapshot(
                    reference.source_object_id,
                    verified_snapshot=verified_snapshot,
                    source_id=reference.source_id,
                    source_snapshot_id=reference.source_snapshot_id,
                    raw_sha256=reference.raw_sha256,
                )
    if len(set(identities)) != len(identities):
        raise ValueError("duplicate source-backed logical rows")
    if locators and verified_snapshot is None:
        raise ValueError("source-backed Parquet rows require verified raw snapshot evidence")
    if verified_snapshot is None:
        return
    for locator, source_id, raw_sha256 in locators:
        validate_raw_locator_against_snapshot(
            locator,
            verified_snapshot=verified_snapshot,
            source_id=source_id,
            raw_sha256=raw_sha256,
            archive_limits=archive_limits,
            max_decoded_bytes=max_decoded_bytes,
        )


def validate_parquet_table_rows(
    path: Path,
    *,
    layer: Literal["staging", "normalized", "audit", "quarantine", "curated"],
    row_contract: type[BaseModel] | None = None,
    verified_snapshot: VerifiedSourceSnapshot | None = None,
    archive_limits: ArchiveLimits | None = None,
    max_decoded_bytes: int | None = None,
) -> None:
    """Deserialize persisted rows through the same nominal layer contract."""

    contracts_by_layer: dict[str, type[BaseModel] | tuple[type[BaseModel], ...]] = {
        "staging": StagingRecord,
        "normalized": (StagingRecord, CanonicalRecord),
        "audit": (AuditRecord, CardResolution, ResolutionAttempt, ProvenanceRow),
        "quarantine": QuarantineRecord,
        "curated": (CuratedRow, CanonicalCard, CardFace, Printing),
    }
    contracts = contracts_by_layer[layer]
    if row_contract is not None:
        if row_contract not in (contracts if isinstance(contracts, tuple) else (contracts,)):
            raise ValueError("row contract is not valid for the requested Parquet layer")
        contracts = row_contract
    try:
        table = pq.read_table(path)
        raw_rows = table.column("row_json").to_pylist()
        rows: list[BaseModel] = []
        for value in raw_rows:
            payload = json.loads(value)
            matches = []
            for contract in contracts if isinstance(contracts, tuple) else (contracts,):
                try:
                    candidate = contract.model_validate(payload)
                    _row_payload(candidate, contract, layer)
                    matches.append(candidate)
                except (TypeError, ValueError):
                    continue
            if len(matches) != 1:
                raise ValueError("row does not match exactly one typed layer contract")
            rows.append(matches[0])
    except Exception as error:  # pragma: no cover - backend-specific exception types
        raise ValueError("Parquet rows do not satisfy their typed layer contract") from error
    _validate_source_locators(
        rows,
        verified_snapshot,
        archive_limits=archive_limits,
        max_decoded_bytes=max_decoded_bytes,
    )


def _temporary_path(directory: Path) -> tuple[int, str]:
    import tempfile

    return tempfile.mkstemp(prefix=".parquet-", dir=directory)


__all__ = [
    "CuratedRow",
    "ParquetArtifact",
    "ParquetTableWriter",
    "validate_parquet_table_rows",
]
