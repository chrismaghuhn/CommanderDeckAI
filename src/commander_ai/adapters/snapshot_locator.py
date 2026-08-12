"""Locate one source-owned raw snapshot without reading source contents."""

from __future__ import annotations

from pathlib import Path

from .storage.snapshot_identity import validate_snapshot_component


def find_source_for_snapshot(data_root: Path, snapshot_id: str) -> str:
    """Return the unique source directory containing a snapshot manifest."""

    validate_snapshot_component(snapshot_id)
    raw_root = data_root / "raw"
    matches = (
        [
            source_root.name
            for source_root in raw_root.iterdir()
            if source_root.is_dir()
            and not source_root.is_symlink()
            and (source_root / snapshot_id / "manifest.json").is_file()
        ]
        if raw_root.is_dir()
        else []
    )
    if len(matches) != 1:
        raise ValueError("snapshot id is missing or ambiguous")
    return matches[0]


__all__ = ["find_source_for_snapshot"]
