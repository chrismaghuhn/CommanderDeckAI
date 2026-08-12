"""Shared local run provenance for CLI data operations."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from commander_ai.adapters.storage.manifest_files import JsonArtifact, ManifestFileWriter
from commander_ai.data_pipeline.provenance.run_manifests import RunArtifactReference
from commander_ai.domain.serialization import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class OperationContext:
    git_commit: str
    git_dirty: bool
    git_worktree_sha256: str | None
    dependency_lock_hash: str
    determinism: Literal["STRICT", "BEST_EFFORT", "EXTERNAL"]
    artifacts: tuple[RunArtifactReference, ...]


def operation_context(artifact_root: Path, run_id: str) -> OperationContext:
    """Capture safe local provenance and persist only a worktree digest."""

    repository_root = _repository_root()
    git_commit = _git_output(repository_root, "rev-parse", "HEAD")
    status = _git_output(repository_root, "status", "--porcelain")
    diff = _git_bytes(repository_root, "diff", "--binary", "HEAD")
    untracked = _untracked_file_digests(repository_root)
    worktree_payload = (
        status.encode("utf-8") + b"\0" + diff + b"\0" + canonical_json_bytes(untracked)
    )
    dirty = bool(status or diff or untracked)
    worktree_digest = hashlib.sha256(worktree_payload).hexdigest() if dirty else None
    artifacts: tuple[RunArtifactReference, ...] = ()
    if dirty and worktree_digest is not None:
        writer = ManifestFileWriter(artifact_root)
        path = f"runs/{run_id}/git-worktree-state.json"
        artifact = writer.write_json(
            path,
            canonical_json_bytes({"worktree_sha256": worktree_digest}),
        )
        artifacts = (_run_artifact(artifact, "git_worktree_state"),)
    return OperationContext(
        git_commit=git_commit if _is_git_commit(git_commit) else "0" * 40,
        git_dirty=dirty,
        git_worktree_sha256=worktree_digest,
        dependency_lock_hash=_lock_hash(repository_root / "uv.lock"),
        determinism="BEST_EFFORT" if dirty else "STRICT",
        artifacts=artifacts,
    )


def _run_artifact(artifact: JsonArtifact, kind: str) -> RunArtifactReference:
    return RunArtifactReference(path=artifact.path, sha256=artifact.sha256, kind=kind)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _git_output(root: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _git_bytes(root: Path, *arguments: str) -> bytes:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return b""
    return result.stdout


def _lock_hash(path: Path) -> str:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "0" * 64


def _untracked_file_digests(root: Path) -> list[dict[str, str]]:
    raw_paths = _git_bytes(root, "ls-files", "--others", "--exclude-standard", "-z")
    values: list[dict[str, str]] = []
    for raw_path in sorted(path for path in raw_paths.split(b"\0") if path):
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            continue
        path = (root / Path(relative)).resolve()
        try:
            path.relative_to(root.resolve())
        except ValueError:
            continue
        if path.is_file() and not path.is_symlink():
            values.append(
                {
                    "path_sha256": hashlib.sha256(relative.encode("utf-8")).hexdigest(),
                    "content_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    return values


def _is_git_commit(value: str) -> bool:
    return len(value) in {40, 64} and all(character in "0123456789abcdef" for character in value)


__all__ = ["OperationContext", "operation_context"]
