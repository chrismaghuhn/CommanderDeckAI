"""Load one explicit MTGJSON card catalog from authoritative Parquet output."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.data_pipeline.provenance.canonical_snapshot_contracts import (
    CanonicalSnapshotManifestV1,
)
from commander_ai.data_pipeline.normalization.canonical_snapshot_manifests import (
    validate_canonical_snapshot_manifest,
)
from commander_ai.data_pipeline.resolution.catalog_indexes import build_catalog_indexes
from commander_ai.data_pipeline.resolution.catalog_models import CardCatalog
from commander_ai.domain.cards import CanonicalCard, CardFace, Printing
from commander_ai.domain.serialization import sha256_hex

from .parquet_tables import ParquetTableWriter


@dataclass(frozen=True, slots=True)
class LoadedCardCatalog:
    """Card catalog plus the immutable manifest that selected its input."""

    catalog: CardCatalog
    canonical_snapshot_id: str
    manifest_path: str
    manifest_sha256: str


class ParquetCardCatalogLoader:
    """Rebuild a resolver catalog without making DuckDB authoritative."""

    def __init__(self, artifact_root: Path | str) -> None:
        self._root = Path(artifact_root).expanduser().absolute()

    def load_unique(self, snapshot_id: str | None = None) -> LoadedCardCatalog | None:
        candidates = self._manifests(snapshot_id)
        if not candidates:
            return None
        if len(candidates) != 1:
            raise ValueError("card catalog snapshot selection is ambiguous")
        manifest_path, manifest, manifest_bytes = candidates[0]
        canonical_artifact = next(
            item for item in manifest.artifacts if item.artifact_kind == "canonical"
        )
        table_path = self._root / canonical_artifact.path
        if not table_path.is_file() or table_path.is_symlink():
            raise ValueError("card catalog canonical artifact is missing")
        if table_path.stat().st_size != canonical_artifact.bytes:
            raise ValueError("card catalog canonical artifact size mismatch")
        if sha256_hex(table_path.read_bytes()) != canonical_artifact.sha256:
            raise ValueError("card catalog canonical artifact hash mismatch")
        records = tuple(
            CanonicalRecord.model_validate(row)
            for row in ParquetTableWriter(self._root).read_table(canonical_artifact.path)
        )
        cards = tuple(
            CanonicalCard.model_validate(item.payload)
            for item in records
            if item.record_type == "card"
        )
        faces = tuple(
            CardFace.model_validate(item.payload)
            for item in records
            if item.record_type == "card_face"
        )
        printings = tuple(
            Printing.model_validate(item.payload)
            for item in records
            if item.record_type == "printing"
        )
        if not cards:
            raise ValueError("card catalog contains no canonical cards")
        catalog = build_catalog_indexes(
            cards=cards,
            faces=faces,
            printings=printings,
            source_records=(),
        )
        return LoadedCardCatalog(
            catalog=catalog,
            canonical_snapshot_id=manifest.canonical_snapshot_id,
            manifest_path=manifest_path,
            manifest_sha256=sha256_hex(manifest_bytes),
        )

    def _manifests(
        self, snapshot_id: str | None
    ) -> list[tuple[str, CanonicalSnapshotManifestV1, bytes]]:
        root = self._root / "canonical"
        if not root.is_dir() or root.is_symlink():
            return []
        matches: list[tuple[str, CanonicalSnapshotManifestV1, bytes]] = []
        for path in sorted(root.rglob("manifest.json")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                payload = path.read_bytes()
                data = json.loads(payload)
                manifest = CanonicalSnapshotManifestV1.model_validate(data)
                validate_canonical_snapshot_manifest(manifest)
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError):
                continue
            if manifest.status != "COMPLETE" or manifest.source_id != "mtgjson":
                continue
            if snapshot_id is not None and manifest.canonical_snapshot_id != snapshot_id:
                continue
            matches.append((path.relative_to(self._root).as_posix(), manifest, payload))
        return matches


__all__ = ["LoadedCardCatalog", "ParquetCardCatalogLoader"]
