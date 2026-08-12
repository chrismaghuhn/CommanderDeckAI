"""Safe selection of canonical snapshot manifests for dataset projections."""

from __future__ import annotations

import json
from pathlib import Path


def select_canonical_manifests(root: Path, selector: str) -> tuple[str, ...]:
    """Return portable manifest paths whose source matches the selector."""

    canonical_root = root / "canonical"
    paths: list[str] = []
    if not canonical_root.is_dir() or canonical_root.is_symlink():
        return ()
    for path in canonical_root.rglob("manifest.json"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if selector == "all" or payload.get("source_id") == selector:
            paths.append(path.relative_to(root).as_posix())
    return tuple(sorted(paths))


__all__ = ["select_canonical_manifests"]
