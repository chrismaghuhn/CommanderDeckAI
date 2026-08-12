"""Canonical content-digest calculation shared by dataset build and inspection."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex


def compute_dataset_content_sha256(
    *,
    dataset_id: str,
    dataset_kind: str,
    table_name: str,
    rows: Sequence[Mapping[str, object]],
) -> str:
    """Hash the exact logical row payload used by ``dataset-manifest.v2``."""

    payload = {
        "dataset_id": dataset_id,
        "dataset_kind": dataset_kind,
        "table_name": table_name,
        "rows": list(rows),
    }
    return sha256_hex(canonical_json_bytes(payload))


__all__ = ["compute_dataset_content_sha256"]
