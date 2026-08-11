"""Fresh integrity verification for completed raw snapshots."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from commander_ai.domain.provenance import SourceSnapshotManifest

from .canonical_json import canonical_json_bytes
from .digests import detached_manifest_sha256, snapshot_content_sha256
from .manifest_policy import manifest_semantic_code
from .path_policy import resolve_under_root, validate_portable_relative_path


class SnapshotIntegrityError(RuntimeError):
    """Non-consumable snapshot failure with a stable integrity code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class VerifiedSnapshot:
    manifest: SourceSnapshotManifest
    snapshot_dir: Path
    object_paths: Mapping[str, Path]
    record_count: int


@dataclass(frozen=True, slots=True)
class SnapshotInspection:
    status: str | None
    consumable: bool
    issue_codes: tuple[str, ...]
    manifest: SourceSnapshotManifest | None
    record_count: int


class SnapshotVerifier:
    """Verify raw objects and manifest digests before parsing or normalization."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()

    def verify_complete_snapshot(self, source_id: str, snapshot_id: str) -> VerifiedSnapshot:
        inspection = self.inspect(source_id, snapshot_id)
        if not inspection.consumable or inspection.manifest is None:
            code = inspection.issue_codes[0] if inspection.issue_codes else "INTEGRITY_UNKNOWN"
            raise SnapshotIntegrityError(code)
        snapshot_dir = self._snapshot_dir(source_id, snapshot_id)
        paths: dict[str, Path] = {}
        for reference in inspection.manifest.objects:
            try:
                paths[reference.raw_object_id] = resolve_under_root(snapshot_dir, reference.path)
            except ValueError as error:
                raise SnapshotIntegrityError("INTEGRITY_OBJECT_PATH") from error
        return VerifiedSnapshot(
            manifest=inspection.manifest,
            snapshot_dir=snapshot_dir,
            object_paths=MappingProxyType(paths),
            record_count=inspection.record_count,
        )

    def inspect(self, source_id: str, snapshot_id: str) -> SnapshotInspection:
        try:
            snapshot_dir = self._snapshot_dir(source_id, snapshot_id)
        except (OSError, ValueError):
            return SnapshotInspection(None, False, ("INTEGRITY_SNAPSHOT_PATH",), None, 0)
        manifest_path = snapshot_dir / "manifest.json"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            return SnapshotInspection(None, False, ("INTEGRITY_MANIFEST_MISSING",), None, 0)
        try:
            manifest_bytes = manifest_path.read_bytes()
            payload = json.loads(manifest_bytes.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            return SnapshotInspection(None, False, ("INTEGRITY_MANIFEST_INVALID",), None, 0)
        if not isinstance(payload, dict):
            return SnapshotInspection(None, False, ("INTEGRITY_MANIFEST_INVALID",), None, 0)
        status = payload.get("status") if isinstance(payload.get("status"), str) else None
        duplicate_code = _duplicate_id_code(payload)
        if duplicate_code is not None:
            return SnapshotInspection(status, False, (duplicate_code,), None, 0)
        try:
            manifest = SourceSnapshotManifest.model_validate(payload)
        except ValueError as error:
            code = _manifest_validation_code(str(error))
            return SnapshotInspection(status, False, (code,), None, 0)
        if manifest.source_id != source_id or manifest.source_snapshot_id != snapshot_id:
            return SnapshotInspection(status, False, ("INTEGRITY_MANIFEST_IDENTITY",), None, 0)
        semantic_code = manifest_semantic_code(manifest)
        if semantic_code is not None:
            return SnapshotInspection(status, False, (semantic_code,), manifest, 0)
        if manifest.status != "COMPLETE" or manifest.completed_at is None:
            return SnapshotInspection(
                manifest.status,
                False,
                ("INTEGRITY_SNAPSHOT_NOT_COMPLETE",),
                manifest,
                0,
            )
        try:
            canonical_manifest_matches = canonical_json_bytes(payload) == manifest_bytes
        except (TypeError, ValueError):
            canonical_manifest_matches = False
        if not canonical_manifest_matches:
            return SnapshotInspection(
                manifest.status,
                False,
                ("INTEGRITY_MANIFEST_CANONICAL",),
                manifest,
                0,
            )
        digest_code = _verify_detached_digest(snapshot_dir, payload)
        if digest_code is not None:
            return SnapshotInspection(manifest.status, False, (digest_code,), manifest, 0)

        object_paths: dict[str, Path] = {}
        record_count = 0
        for reference in manifest.objects:
            if not reference.path.startswith("objects/"):
                return SnapshotInspection(
                    manifest.status, False, ("INTEGRITY_OBJECT_PATH",), manifest, 0
                )
            try:
                object_path = resolve_under_root(snapshot_dir, reference.path)
            except ValueError:
                return SnapshotInspection(
                    manifest.status, False, ("INTEGRITY_OBJECT_PATH",), manifest, 0
                )
            if _contains_symlink(object_path, snapshot_dir):
                return SnapshotInspection(
                    manifest.status, False, ("INTEGRITY_OBJECT_CORRUPT",), manifest, 0
                )
            if not object_path.exists():
                return SnapshotInspection(
                    manifest.status, False, ("INTEGRITY_OBJECT_MISSING",), manifest, 0
                )
            if not object_path.is_file():
                return SnapshotInspection(
                    manifest.status, False, ("INTEGRITY_OBJECT_CORRUPT",), manifest, 0
                )
            try:
                actual_size = object_path.stat().st_size
            except OSError:
                return SnapshotInspection(
                    manifest.status, False, ("INTEGRITY_OBJECT_MISSING",), manifest, 0
                )
            if actual_size != reference.bytes:
                return SnapshotInspection(
                    manifest.status,
                    False,
                    ("INTEGRITY_OBJECT_SIZE_MISMATCH",),
                    manifest,
                    0,
                )
            if _sha256_file(object_path) != reference.sha256:
                return SnapshotInspection(
                    manifest.status,
                    False,
                    ("INTEGRITY_OBJECT_HASH_MISMATCH",),
                    manifest,
                    0,
                )
            object_paths[reference.raw_object_id] = object_path
            record_count += reference.logical_record_count or 0

        try:
            expected_content_digest = snapshot_content_sha256(
                [item.model_dump(mode="json") for item in manifest.objects]
            )
        except (TypeError, ValueError):
            return SnapshotInspection(
                manifest.status,
                False,
                ("INTEGRITY_SNAPSHOT_CONTENT_DIGEST",),
                manifest,
                0,
            )
        if expected_content_digest != manifest.snapshot_content_sha256:
            return SnapshotInspection(
                manifest.status,
                False,
                ("INTEGRITY_SNAPSHOT_CONTENT_DIGEST",),
                manifest,
                0,
            )
        return SnapshotInspection(
            manifest.status,
            True,
            (),
            manifest,
            record_count,
        )

    def _snapshot_dir(self, source_id: str, snapshot_id: str) -> Path:
        if not _safe_component(source_id) or not _safe_component(snapshot_id):
            raise ValueError("snapshot identifiers must be single portable path components")
        return resolve_under_root(self.root, f"raw/{source_id}/{snapshot_id}")


def verify_complete_snapshot(
    root: Path | str, source_id: str, snapshot_id: str
) -> VerifiedSnapshot:
    """Verify one completed snapshot and return only immutable evidence paths."""

    return SnapshotVerifier(root).verify_complete_snapshot(source_id, snapshot_id)


def _verify_detached_digest(snapshot_dir: Path, payload: Mapping[str, object]) -> str | None:
    sidecar = snapshot_dir / "manifest.sha256"
    if not sidecar.is_file() or sidecar.is_symlink():
        return "INTEGRITY_MANIFEST_DIGEST_MISSING"
    try:
        value = sidecar.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return "INTEGRITY_MANIFEST_DIGEST"
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        return "INTEGRITY_MANIFEST_DIGEST"
    return None if value == detached_manifest_sha256(payload) else "INTEGRITY_MANIFEST_DIGEST"


def _duplicate_id_code(payload: Mapping[str, object]) -> str | None:
    requests = payload.get("requests")
    if isinstance(requests, list):
        ids = [item.get("request_id") for item in requests if isinstance(item, dict)]
        if _has_duplicate(ids):
            return "INTEGRITY_DUPLICATE_REQUEST_ID"
    objects = payload.get("objects")
    if isinstance(objects, list):
        ids = [item.get("raw_object_id") for item in objects if isinstance(item, dict)]
        if _has_duplicate(ids):
            return "INTEGRITY_DUPLICATE_OBJECT_ID"
        paths = [item.get("path") for item in objects if isinstance(item, dict)]
        if _has_duplicate(paths):
            return "INTEGRITY_DUPLICATE_OBJECT_PATH"
    return None


def _has_duplicate(values: list[object]) -> bool:
    return any(value == prior for index, value in enumerate(values) for prior in values[:index])


def _manifest_validation_code(message: str) -> str:
    if "request" in message or "request_id" in message:
        return "INTEGRITY_REQUEST_OBJECT_LINEAGE"
    return "INTEGRITY_MANIFEST_INVALID"


def _contains_symlink(path: Path, root: Path) -> bool:
    current = root
    try:
        relative = path.relative_to(root)
    except ValueError:
        return True
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _safe_component(value: str) -> bool:
    if not isinstance(value, str) or not value or "/" in value or "\\" in value:
        return False
    try:
        validate_portable_relative_path(f"component/{value}")
    except ValueError:
        return False
    return not value.startswith(".")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


__all__ = [
    "SnapshotInspection",
    "SnapshotIntegrityError",
    "SnapshotVerifier",
    "VerifiedSnapshot",
    "verify_complete_snapshot",
]
