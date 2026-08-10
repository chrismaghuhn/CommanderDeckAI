from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "schemas" / "run-manifest.v1.schema.json"
EXAMPLE_PATH = PROJECT_ROOT / "examples" / "run-manifest.v1.json"


def load_contract() -> tuple[dict[str, object], dict[str, object]]:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    instance = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    return schema, instance


def validation_errors(schema: dict[str, object], instance: dict[str, object]) -> list[object]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return list(validator.iter_errors(instance))


def canonical_manifest_sha256(manifest: dict[str, object]) -> str:
    payload = {key: value for key, value in manifest.items() if key != "sha256"}
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def test_run_manifest_fixture_matches_schema() -> None:
    assert SCHEMA_PATH.is_file(), f"missing schema: {SCHEMA_PATH}"
    assert EXAMPLE_PATH.is_file(), f"missing example: {EXAMPLE_PATH}"

    schema, instance = load_contract()
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    errors = sorted(validator.iter_errors(instance), key=lambda error: list(error.path))
    assert not errors, "\n".join(error.message for error in errors)


def test_run_manifest_rejects_unknown_top_level_fields() -> None:
    schema, instance = load_contract()
    invalid_instance = copy.deepcopy(instance)
    invalid_instance["unexpected_field"] = True

    errors = validation_errors(schema, invalid_instance)

    assert any(error.validator == "additionalProperties" for error in errors)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("status", "removed_fields"),
    [
        ("created", ("started_at", "finished_at")),
        ("running", ("finished_at",)),
        ("succeeded", ()),
        ("failed", ()),
        ("cancelled", ("started_at",)),
    ],
)
def test_run_manifest_lifecycle_timestamps_are_conditionally_required(
    status: str, removed_fields: tuple[str, ...]
) -> None:
    schema, instance = load_contract()
    candidate = copy.deepcopy(instance)
    candidate["status"] = status
    for field in removed_fields:
        candidate.pop(field, None)

    assert not validation_errors(schema, candidate), status


@pytest.mark.parametrize(
    ("status", "removed_fields"),
    [
        ("running", ("started_at",)),
        ("succeeded", ("started_at",)),
        ("succeeded", ("finished_at",)),
        ("failed", ("started_at",)),
        ("failed", ("finished_at",)),
        ("cancelled", ("finished_at",)),
    ],
)
def test_run_manifest_rejects_missing_required_lifecycle_timestamps(
    status: str, removed_fields: tuple[str, ...]
) -> None:
    schema, instance = load_contract()
    candidate = copy.deepcopy(instance)
    candidate["status"] = status
    for field in removed_fields:
        candidate.pop(field, None)

    assert validation_errors(schema, candidate), (status, removed_fields)


def test_created_run_rejects_started_or_finished_timestamps() -> None:
    schema, instance = load_contract()

    for retained_field in ("started_at", "finished_at"):
        candidate = copy.deepcopy(instance)
        candidate["status"] = "created"
        candidate.pop("started_at" if retained_field == "finished_at" else "finished_at")

        assert validation_errors(schema, candidate), retained_field


def test_running_run_rejects_finished_timestamp() -> None:
    schema, instance = load_contract()
    candidate = copy.deepcopy(instance)
    candidate["status"] = "running"

    assert validation_errors(schema, candidate)


def test_run_manifest_requires_full_git_object_id() -> None:
    schema, instance = load_contract()
    candidate = copy.deepcopy(instance)
    candidate["git_commit"] = "abcdef1234567890"

    errors = validation_errors(schema, candidate)

    assert any(
        error.validator == "pattern" and list(error.path) == ["git_commit"]  # type: ignore[attr-defined]
        for error in errors
    )


def test_dirty_run_requires_worktree_state_hash_and_artifact() -> None:
    schema, instance = load_contract()
    dirty = copy.deepcopy(instance)
    dirty["determinism"] = "BEST_EFFORT"
    dirty["git_dirty"] = True

    assert validation_errors(schema, dirty)

    dirty["git_worktree_sha256"] = "a" * 64
    assert validation_errors(schema, dirty)

    dirty["artifacts"].append(  # type: ignore[attr-defined]
        {
            "path": "artifacts/git-worktree-state.v1.json",
            "sha256": "a" * 64,
            "kind": "git_worktree_state",
        }
    )
    assert not validation_errors(schema, dirty)


def test_clean_run_rejects_worktree_state_hash() -> None:
    schema, instance = load_contract()
    clean = copy.deepcopy(instance)
    clean["git_worktree_sha256"] = "a" * 64

    assert validation_errors(schema, clean)


def test_strict_run_rejects_dirty_worktree_even_when_captured() -> None:
    schema, instance = load_contract()
    strict_dirty = copy.deepcopy(instance)
    strict_dirty["git_dirty"] = True
    strict_dirty["git_worktree_sha256"] = "a" * 64
    strict_dirty["artifacts"].append(  # type: ignore[attr-defined]
        {
            "path": "artifacts/git-worktree-state.v1.json",
            "sha256": "a" * 64,
            "kind": "git_worktree_state",
        }
    )

    assert validation_errors(schema, strict_dirty)


def test_git_worktree_state_digest_covers_head_index_worktree_and_untracked() -> None:
    state = {
        "schema_version": "git-worktree-state.v1",
        "head": "abcdef1234567890abcdef1234567890abcdef12",
        "index": [
            {
                "path": "src/staged.txt",
                "mode": "100644",
                "stage": 0,
                "git_object_id": "1111111111111111111111111111111111111111",
            }
        ],
        "worktree": [
            {
                "path": "src/staged.txt",
                "kind": "tracked",
                "state": "present",
                "mode": "100644",
                "sha256": "2222222222222222222222222222222222222222222222222222222222222222",
            },
            {
                "path": "src/unstaged.txt",
                "kind": "tracked",
                "state": "present",
                "mode": "100644",
                "sha256": "3333333333333333333333333333333333333333333333333333333333333333",
            },
            {
                "path": "notes/untracked.txt",
                "kind": "untracked",
                "state": "present",
                "mode": "100644",
                "sha256": "4444444444444444444444444444444444444444444444444444444444444444",
            },
        ],
    }

    expected = hashlib.sha256(
        json.dumps(
            state,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    assert expected == "c734051374b7e68cbf3b8da3bc262dac96fce15b06a48860f8e931c09d650e2c"

    for section, field in (("index", "git_object_id"), ("worktree", "sha256")):
        changed = copy.deepcopy(state)
        changed[section][0][field] = "f" * len(changed[section][0][field])  # type: ignore[index]
        assert (
            hashlib.sha256(
                json.dumps(
                    changed,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            != expected
        )


def test_run_manifest_uses_open_generic_input_references() -> None:
    schema, instance = load_contract()
    candidate = copy.deepcopy(instance)
    candidate.pop("dataset_manifests", None)
    candidate["inputs"] = [
        {
            "kind": "future_manifest_type",
            "id": "future-input-v1",
            "path": "inputs/future.json",
            "sha256": "a" * 64,
        }
    ]

    assert not validation_errors(schema, candidate)


def test_run_manifest_top_level_hash_is_deterministic_and_verifiable() -> None:
    _, instance = load_contract()
    expected = canonical_manifest_sha256(instance)

    assert instance["sha256"] == expected

    round_tripped = json.loads(json.dumps(instance, ensure_ascii=False))
    assert canonical_manifest_sha256(round_tripped) == expected

    changed_self_hash = copy.deepcopy(instance)
    changed_self_hash["sha256"] = "0" * 64
    assert canonical_manifest_sha256(changed_self_hash) == expected
