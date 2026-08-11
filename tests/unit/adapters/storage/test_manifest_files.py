from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from commander_ai.adapters.storage import manifest_files
from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.data_pipeline.provenance.run_manifests import (
    build_run_manifest,
    configuration_snapshot_bytes,
)

NOW = datetime(2026, 8, 11, 10, 0, tzinfo=UTC)


def test_manifest_writer_publishes_portable_hashed_secret_free_files(tmp_path: Path) -> None:
    manifest = build_run_manifest(
        run_id="run-1",
        run_kind="normalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/run.json",
        configuration_snapshot={"api_key": "secret", "source": "fixture"},
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    written, config = ManifestFileWriter(tmp_path).write_run_manifest(
        manifest,
        manifest_path="runs/run-1/manifest.json",
        configuration_snapshot={"api_key": "secret", "source": "fixture"},
    )

    assert written.path == "runs/run-1/manifest.json"
    assert config.path == "configs/run.json"
    assert b"secret" not in (tmp_path / config.path).read_bytes()
    assert written.sha256 == _sha256((tmp_path / written.path).read_bytes())
    assert (
        configuration_snapshot_bytes({"api_key": "secret", "source": "fixture"})
        == (tmp_path / config.path).read_bytes()
    )


def test_manifest_writer_rejects_a_configuration_hash_mismatch_before_publication(
    tmp_path: Path,
) -> None:
    manifest = build_run_manifest(
        run_id="run-mismatch",
        run_kind="normalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/run.json",
        configuration_snapshot={"source": "fixture"},
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )

    with pytest.raises(ValueError, match="configuration snapshot hash"):
        ManifestFileWriter(tmp_path).write_run_manifest(
            manifest,
            manifest_path="runs/run-mismatch/manifest.json",
            configuration_snapshot={"source": "changed"},
        )

    assert not (tmp_path / "runs/run-mismatch/manifest.json").exists()
    assert not (tmp_path / "configs/run.json").exists()


def test_manifest_writer_removes_published_file_when_directory_fsync_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_fsync(_directory: Path) -> None:
        raise OSError("directory durability failure")

    monkeypatch.setattr(manifest_files, "fsync_directory", fail_fsync)

    with pytest.raises(OSError, match="directory durability failure"):
        ManifestFileWriter(tmp_path).write_json("reports/report.json", b"report")

    assert not (tmp_path / "reports/report.json").exists()


def test_manifest_writer_cleans_configuration_when_manifest_publication_fails(
    tmp_path: Path,
) -> None:
    manifest = build_run_manifest(
        run_id="run-collision",
        run_kind="normalize",
        stage="data",
        status="succeeded",
        git_commit="a" * 40,
        git_dirty=False,
        dependency_lock_hash="b" * 64,
        configuration_path="configs/run.json",
        configuration_snapshot={"source": "fixture"},
        created_at=NOW,
        started_at=NOW,
        finished_at=NOW,
    )
    manifest_path = tmp_path / "runs/run-collision/manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        ManifestFileWriter(tmp_path).write_run_manifest(
            manifest,
            manifest_path="runs/run-collision/manifest.json",
            configuration_snapshot={"source": "fixture"},
        )

    assert not (tmp_path / "configs/run.json").exists()


def _sha256(value: bytes) -> str:
    import hashlib

    return hashlib.sha256(value).hexdigest()
