from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from commander_ai.adapters.ruleset_snapshots import (
    FileRulesetSnapshotProvider,
    RulesetSnapshotInputError,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]


def _write_ruleset(root: Path, name: str, version: str, effective_from: str) -> bytes:
    payload = json.loads((PROJECT_ROOT / "examples" / "ruleset.v1.json").read_text())
    payload["ruleset_version"] = version
    payload["effective_from"] = effective_from
    payload["effective_until"] = None
    path = root / "rulesets" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    raw_bytes = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
    path.write_bytes(raw_bytes)
    return raw_bytes


def test_file_provider_returns_effective_dated_inputs_with_exact_file_hash(tmp_path: Path) -> None:
    old_bytes = _write_ruleset(tmp_path, "old.json", "commander-old", "2025-01-01")
    current_bytes = _write_ruleset(tmp_path, "current.json", "commander-current", "2026-01-01")

    inputs = FileRulesetSnapshotProvider(tmp_path).load()

    assert [item.snapshot_id for item in inputs] == ["commander-old", "commander-current"]
    assert inputs[0].path == "rulesets/old.json"
    assert inputs[0].input_sha256 == hashlib.sha256(old_bytes).hexdigest()
    assert inputs[1].input_sha256 == hashlib.sha256(current_bytes).hexdigest()
    assert inputs[0].snapshot.effective_from == date(2025, 1, 1)


def test_file_provider_has_no_implicit_current_snapshot(tmp_path: Path) -> None:
    assert FileRulesetSnapshotProvider(tmp_path).load() == ()


def test_file_provider_rejects_duplicate_ruleset_versions(tmp_path: Path) -> None:
    _write_ruleset(tmp_path, "first.json", "commander-duplicate", "2025-01-01")
    _write_ruleset(tmp_path, "second.json", "commander-duplicate", "2026-01-01")

    with pytest.raises(RulesetSnapshotInputError, match="INTEGRITY_RULESET_INPUT_DUPLICATE"):
        FileRulesetSnapshotProvider(tmp_path).load()


def test_file_provider_rejects_malformed_ruleset_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "rulesets" / "broken.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"schema_version":"ruleset.v1"}')

    with pytest.raises(RulesetSnapshotInputError, match="INTEGRITY_RULESET_INPUT_INVALID"):
        FileRulesetSnapshotProvider(tmp_path).load()
