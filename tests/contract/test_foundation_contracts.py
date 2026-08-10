from __future__ import annotations

import copy
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

PROJECT_ROOT = Path(__file__).resolve().parents[2]

NEW_CONTRACT_STEMS = (
    "source-snapshot-manifest.v2",
    "normalized-snapshot-manifest.v1",
    "canonical-deck.v1",
    "deck-legality-evaluation.v1",
    "deck-quality-evaluation.v1",
    "card-resolution.v1",
    "printing.v1",
    "card-face.v1",
    "event-deck-observation.v1",
    "participant-reference.v1",
    "combo.v1",
    "combo-card.v1",
    "dataset-manifest.v2",
)


def load_contract(stem: str) -> tuple[dict[str, object], dict[str, object]]:
    schema_path = PROJECT_ROOT / "schemas" / f"{stem}.schema.json"
    example_path = PROJECT_ROOT / "examples" / f"{stem}.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    example = json.loads(example_path.read_text(encoding="utf-8"))
    return schema, example


def validation_errors(schema: dict[str, object], instance: dict[str, object]) -> list[object]:
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return list(validator.iter_errors(instance))


def test_every_new_example_validates_against_its_schema() -> None:
    for stem in NEW_CONTRACT_STEMS:
        schema_path = PROJECT_ROOT / "schemas" / f"{stem}.schema.json"
        example_path = PROJECT_ROOT / "examples" / f"{stem}.json"
        assert schema_path.is_file(), f"missing schema: {schema_path}"
        assert example_path.is_file(), f"missing example: {example_path}"

        schema, example = load_contract(stem)
        Draft202012Validator.check_schema(schema)
        errors = validation_errors(schema, example)
        assert not errors, f"{stem}: " + "\n".join(error.message for error in errors)  # type: ignore[attr-defined]


def test_closed_contracts_reject_unknown_fields_at_top_level_and_nested_level() -> None:
    schema, example = load_contract("canonical-deck.v1")

    top_level_candidate = copy.deepcopy(example)
    top_level_candidate["unexpected_field"] = True
    top_level_errors = validation_errors(schema, top_level_candidate)
    assert any(error.validator == "additionalProperties" for error in top_level_errors)  # type: ignore[attr-defined]

    nested_candidate = copy.deepcopy(example)
    nested_candidate["command_zone"][0]["unexpected_field"] = True  # type: ignore[index]
    nested_errors = validation_errors(schema, nested_candidate)
    assert any(error.validator == "additionalProperties" for error in nested_errors)  # type: ignore[attr-defined]


def test_normalized_snapshot_manifest_binds_identity_provenance_and_two_digest_domains() -> None:
    _, example = load_contract("normalized-snapshot-manifest.v1")

    required_fields = {
        "normalized_snapshot_id",
        "producing_run_id",
        "input_source_snapshot_manifest_id",
        "input_source_snapshot_manifest_sha256",
        "source_id",
        "status",
        "normalized_schema_version",
        "mapper_version",
        "transform_version",
        "normalized_artifact_sha256",
        "audit_artifact_sha256",
        "counts",
        "finding_codes",
        "quarantine_references",
        "provenance",
        "created_at",
        "started_at",
        "completed_at",
        "normalized_content_sha256",
        "manifest_sha256",
    }

    assert required_fields <= example.keys()
    assert example["normalized_content_sha256"] != example["manifest_sha256"]


def test_source_snapshot_v2_keeps_compatibility_summary_derived_alongside_authoritative_records(
) -> None:
    _, example = load_contract("source-snapshot-manifest.v2")

    assert example["requests"]
    assert example["objects"]
    assert "request_parameters_redacted" in example
    assert example["objects"][0]["raw_object_id"]  # type: ignore[index]
    assert example["objects"][0]["request_id"]  # type: ignore[index]


def test_existing_v1_examples_remain_valid() -> None:
    for schema_path in sorted((PROJECT_ROOT / "schemas").glob("*.v1.schema.json")):
        stem = schema_path.name.removesuffix(".schema.json")
        example_path = PROJECT_ROOT / "examples" / f"{stem}.json"
        assert example_path.is_file(), f"missing existing example: {example_path}"

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        example = json.loads(example_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)
        errors = validation_errors(schema, example)
        assert not errors, f"{stem}: " + "\n".join(error.message for error in errors)  # type: ignore[attr-defined]
