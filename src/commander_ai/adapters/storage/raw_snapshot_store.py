"""Filesystem repository and snapshot-ID owner for raw snapshots."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from commander_ai.domain.provenance import SourceSnapshotManifest

from .path_policy import (
    resolve_under_root,
    to_portable_relative_path,
    validate_portable_relative_path,
)
from .raw_snapshot_errors import RawSnapshotError
from .snapshot_identity import validate_snapshot_component

if TYPE_CHECKING:
    from .raw_snapshots import RawSnapshotWriter


class RawSnapshotStore:
    """Filesystem repository for immutable raw snapshots and their manifests."""

    def __init__(self, root: Path | str, *, max_object_bytes: int = 20_000_000_000) -> None:
        self.root = Path(root).expanduser().absolute()
        if (
            not isinstance(max_object_bytes, int)
            or isinstance(max_object_bytes, bool)
            or max_object_bytes < 1
        ):
            raise ValueError("max_object_bytes must be positive")
        self.max_object_bytes = max_object_bytes

    def start_snapshot(
        self,
        *,
        source_id: str,
        approval_status: Literal["APPROVED_LOCAL", "APPROVED_REDISTRIBUTION"] | str,
        adapter_version: str,
        usage_status: str,
        attribution_required: bool = False,
        redistribution_status: Literal["not_approved", "derived_only", "approved"] = "not_approved",
        snapshot_id: str | None = None,
        started_at: datetime | None = None,
        terms_reference: str | None = None,
        pagination_state: Mapping[str, object] | None = None,
        max_object_bytes: int | None = None,
    ) -> RawSnapshotWriter:
        from .raw_snapshots import RawSnapshotWriter

        source_id = self._component(source_id, "ACQ_SOURCE_ID_INVALID")
        adapter_version = self._nonempty(adapter_version, "ACQ_ADAPTER_VERSION_INVALID")
        selected_id = (
            self._generated_snapshot_id(source_id, adapter_version)
            if snapshot_id is None
            else snapshot_id
        )
        selected_id = self._component(selected_id, "ACQ_SNAPSHOT_ID_INVALID")
        object_limit = self.max_object_bytes if max_object_bytes is None else max_object_bytes
        if not isinstance(object_limit, int) or isinstance(object_limit, bool) or object_limit < 1:
            raise RawSnapshotError("ACQ_OBJECT_LIMIT_INVALID")
        snapshot_dir = self.snapshot_dir(source_id, selected_id)
        try:
            snapshot_dir.parent.mkdir(parents=True, exist_ok=True)
            resolve_under_root(self.root, to_portable_relative_path(snapshot_dir.parent, self.root))
            snapshot_dir.mkdir()
            resolve_under_root(self.root, to_portable_relative_path(snapshot_dir, self.root))
            (snapshot_dir / "objects").mkdir()
        except FileExistsError as error:
            raise RawSnapshotError("ACQ_SNAPSHOT_COLLISION") from error
        except (OSError, ValueError) as error:
            raise RawSnapshotError("ACQ_SNAPSHOT_CREATE_FAILED") from error
        try:
            return RawSnapshotWriter(
                self,
                source_id=source_id,
                snapshot_id=selected_id,
                approval_status=str(approval_status),
                adapter_version=adapter_version,
                usage_status=usage_status,
                attribution_required=attribution_required,
                redistribution_status=redistribution_status,
                started_at=started_at or datetime.now(UTC),
                terms_reference=terms_reference,
                pagination_state=pagination_state,
                max_object_bytes=object_limit,
            )
        except RawSnapshotError:
            raise
        except (OSError, TypeError, ValueError) as error:
            raise RawSnapshotError("ACQ_MANIFEST_WRITE_FAILED") from error

    def snapshot_dir(self, source_id: str, snapshot_id: str) -> Path:
        source = self._component(source_id, "ACQ_SOURCE_ID_INVALID")
        snapshot = self._component(snapshot_id, "ACQ_SNAPSHOT_ID_INVALID")
        relative = validate_portable_relative_path(f"raw/{source}/{snapshot}")
        return resolve_under_root(self.root, relative)

    def load_manifest(self, source_id: str, snapshot_id: str) -> SourceSnapshotManifest:
        path = self.snapshot_dir(source_id, snapshot_id) / "manifest.json"
        try:
            if path.is_symlink() or not path.is_file():
                raise OSError("manifest path is not a regular file")
            payload = json.loads(path.read_text(encoding="utf-8"))
            manifest = SourceSnapshotManifest.model_validate(payload)
        except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
            raise RawSnapshotError("ACQ_MANIFEST_INVALID") from error
        if manifest.source_id != source_id or manifest.source_snapshot_id != snapshot_id:
            raise RawSnapshotError("ACQ_MANIFEST_IDENTITY")
        return manifest

    def _generated_snapshot_id(self, source_id: str, adapter_version: str) -> str:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        version = "".join(
            char if char.isalnum() or char in "._-" else "-" for char in adapter_version
        )
        candidate = f"{source_id}-{stamp}-{version}"
        suffix = 1
        while os.path.lexists(self.snapshot_dir(source_id, candidate)):
            suffix += 1
            candidate = f"{source_id}-{stamp}-{version}-{suffix}"
        return candidate

    @staticmethod
    def _component(value: str, code: str) -> str:
        try:
            return validate_snapshot_component(value)
        except ValueError as error:
            raise RawSnapshotError(code) from error

    @staticmethod
    def _nonempty(value: str, code: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise RawSnapshotError(code)
        return value


__all__ = ["RawSnapshotStore"]
