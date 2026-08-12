from __future__ import annotations

import hashlib
import io
import json
import shutil
import threading
import zipfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from typer.testing import CliRunner

from commander_ai.cli.main import app

PROJECT_ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)


def test_cli_composition_runs_offline_workflow_and_replays_deterministically(
    tmp_path: Path, monkeypatch
) -> None:
    fixture_objects = _mtgjson_fixture_objects()
    with _fixture_server(fixture_objects) as endpoint:
        registry_path = _write_registry(tmp_path / "registry.json", endpoint)
        dataset_config = _write_dataset_config(tmp_path / "dataset.yaml")
        runner = CliRunner()

        first_root = tmp_path / "first"
        _set_runtime(monkeypatch, first_root, registry_path)
        synced = _invoke_json(
            runner,
            ["source", "sync", "mtgjson", "--config", str(registry_path), "--json"],
        )
        assert synced["status"] == "COMPLETE"
        snapshot_id = synced["snapshot_id"]

        first = _run_downstream_commands(runner, snapshot_id, dataset_config)
        assert first["validated"]["status"] == "VALID"
        assert first["reported"]["status"] == "COMPLETE"
        assert first["built"]["status"] == "COMPLETE"
        assert first["inspected"]["dataset_id"] == "offline-deck-completion"

        second_root = tmp_path / "second"
        shutil.copytree(first_root / "data" / "raw", second_root / "data" / "raw")
        _set_runtime(monkeypatch, second_root, registry_path)
        second = _run_downstream_commands(runner, snapshot_id, dataset_config)

        for operation in ("normalized", "validated", "reported", "built", "inspected"):
            assert first[operation] == second[operation]

        blocked_registry = _write_registry(
            tmp_path / "blocked-registry.json", endpoint, approval_status="PROPOSED"
        )
        blocked = runner.invoke(
            app,
            [
                "source",
                "sync",
                "mtgjson",
                "--config",
                str(blocked_registry),
                "--json",
            ],
        )
        assert blocked.exit_code == 3
        assert json.loads(blocked.stdout) == {"error_code": "POLICY_SOURCE_NOT_APPROVED"}


def _run_downstream_commands(
    runner: CliRunner, snapshot_id: str, dataset_config: Path
) -> dict[str, dict[str, object]]:
    normalized = _invoke_json(runner, ["data", "normalize", snapshot_id, "--json"])
    normalized_id = normalized["normalized_snapshot_id"]
    validated = _invoke_json(runner, ["data", "validate", normalized_id, "--json"])
    reported = _invoke_json(runner, ["data", "report", "all", "--json"])
    built = _invoke_json(runner, ["dataset", "build", "--config", str(dataset_config), "--json"])
    inspected = _invoke_json(runner, ["dataset", "inspect", built["dataset_id"], "--json"])
    return {
        "normalized": normalized,
        "validated": validated,
        "reported": reported,
        "built": built,
        "inspected": inspected,
    }


def _invoke_json(runner: CliRunner, arguments: list[str]) -> dict[str, object]:
    result = runner.invoke(app, arguments)
    assert result.exit_code == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert isinstance(payload, dict)
    return payload


def _set_runtime(monkeypatch, root: Path, registry_path: Path) -> None:
    monkeypatch.setenv("COMMANDER_AI_DATA_DIR", str(root / "data"))
    monkeypatch.setenv("COMMANDER_AI_ARTIFACT_DIR", str(root / "artifacts"))
    monkeypatch.setenv("COMMANDER_AI_SOURCE_REGISTRY", str(registry_path))


def _write_dataset_config(path: Path) -> Path:
    path.write_text(
        """
dataset_id: offline-deck-completion
dataset_kind: deck_completion
inputs:
  source_ids: [mtgjson]
  require_approved_sources: true
split_policy:
  strategy: temporal_grouped
  version: offline-cli-split-v1
  train_until: 2099-01-01T00:00:00Z
  validation_until: 2100-01-01T00:00:00Z
""".lstrip(),
        encoding="utf-8",
    )
    return path


def _write_registry(
    path: Path,
    endpoint: str,
    *,
    approval_status: str = "APPROVED_LOCAL",
) -> Path:
    source = {
        "source_id": "mtgjson",
        "approval_status": approval_status,
        "access_method": "bulk_file",
        "review_path": "docs/03-data/source-reviews/mtgjson.md",
        "endpoints": [endpoint],
        "host_allowlist": [urlparse(endpoint).hostname],
        "timeout_seconds": 5,
        "max_retries": 0,
        "rate_limit_per_minute": 10000,
        "respect_retry_after": True,
        "max_pages": 1,
        "max_download_bytes": 10_000_000,
        "files": ["AllDeckFiles", "AllPrintings"],
        "sync_policy": "explicit",
        "attribution_required": True,
        "raw_storage": "allowed_local",
        "redistribution": "review_required",
        "filters": {
            "archive_extension": ".json.zip",
            "checksum_suffix": ".sha256",
            "checksum_required": True,
            "checksum_max_bytes": 4096,
            "files": ["AllDeckFiles", "AllPrintings"],
        },
    }
    historical = {
        "source_id": "mtgjson",
        "approval_status": approval_status,
        "review_path": "docs/03-data/source-reviews/mtgjson.md",
        "reviewed_at": NOW.isoformat(),
        "effective_at": NOW.isoformat(),
        "reason": "offline fixture contract",
        "official_docs": ["https://mtgjson.com/docs/"],
        "terms_reference": "https://mtgjson.com/terms/",
        "attribution_required": True,
        "raw_local_storage": "allowed_local",
        "normalized_local_storage": "allowed_local",
        "redistribution_raw": "review_required",
        "redistribution_derived": "review_required",
    }
    current_use = {
        "source_id": "mtgjson",
        "status": "ALLOWED",
        "approval_status": approval_status,
        "reason": "offline fixture only",
        "effective_at": NOW.isoformat(),
    }
    path.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "source_id": "mtgjson",
                        "settings": source,
                        "historical_approval": historical,
                        "current_use": current_use,
                    }
                ]
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


@contextmanager
def _fixture_server(objects: Mapping[str, bytes]) -> Iterator[str]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            name = Path(urlparse(self.path).path).name
            body = objects.get(name)
            if body is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header(
                "Content-Type", "text/plain" if name.endswith("sha256") else "application/zip"
            )
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/api/v5/"
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()


def _mtgjson_fixture_objects() -> dict[str, bytes]:
    card_id = "00000000-0000-0000-0000-000000000001"
    printings = {
        "meta": {"version": "5.2.0", "date": "2026-08-10"},
        "data": {
            "TST": {
                "code": "TST",
                "name": "Task Test Set",
                "releaseDate": "2026-08-10",
                "type": "expansion",
                "cards": [
                    {
                        "uuid": "normal-printing-1",
                        "name": "Test Adept",
                        "setCode": "TST",
                        "setName": "Task Test Set",
                        "number": "1",
                        "layout": "normal",
                        "manaCost": "{2}{U}",
                        "manaValue": 3,
                        "colorIdentity": ["U"],
                        "colors": ["U"],
                        "type": "Creature — Wizard",
                        "types": ["Creature"],
                        "subtypes": ["Wizard"],
                        "oracleText": "Draw a card.",
                        "keywords": ["Flying"],
                        "legalities": {"commander": "Legal"},
                        "identifiers": {
                            "scryfallId": "00000000-0000-0000-0000-000000000002",
                            "scryfallOracleId": card_id,
                        },
                    }
                ],
            }
        },
    }
    deck = {
        "name": "Task Test Commander Deck",
        "fileName": "TST-commander.json",
        "code": "TST",
        "releaseDate": "2026-08-10",
        "type": "commander",
        "commander": [{"name": "Test Adept", "count": 1}],
        "mainBoard": [{"name": "Test Adept", "count": 1}],
        "sideBoard": [],
    }
    raw_archives = {
        "AllPrintings.json.zip": {"AllPrintings.json": json.dumps(printings).encode("utf-8")},
        "AllDeckFiles.json.zip": {"decks/TST-commander.json": json.dumps(deck).encode("utf-8")},
    }
    objects: dict[str, bytes] = {}
    for archive_name, members in raw_archives.items():
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for member_name, content in members.items():
                archive.writestr(member_name, content)
        archive_bytes = output.getvalue()
        objects[archive_name] = archive_bytes
        objects[f"{archive_name}.sha256"] = (
            f"{hashlib.sha256(archive_bytes).hexdigest()}  {archive_name}\n".encode("ascii")
        )
    return objects
