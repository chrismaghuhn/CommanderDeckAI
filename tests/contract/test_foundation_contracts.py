from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from commander_ai.domain.cards import CanonicalCard, CardFace, CardResolution, Printing
from commander_ai.domain.combos import Combo, ComboCard
from commander_ai.domain.decks import CanonicalDeck
from commander_ai.domain.evaluations import DeckLegalityEvaluation, DeckQualityEvaluation
from commander_ai.domain.observations import EventDeckObservation, ParticipantReference
from commander_ai.domain.provenance import (
    DatasetManifest,
    NormalizedSnapshotManifest,
    SourceSnapshotManifest,
    detached_manifest_sha256,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

NEW_CONTRACT_STEMS = (
    "source-snapshot-manifest.v2",
    "normalized-snapshot-manifest.v1",
    "normalized-snapshot-manifest.v2",
    "canonical-deck.v1",
    "deck-legality-evaluation.v1",
    "deck-quality-evaluation.v1",
    "card-resolution.v1",
    "card.v1",
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
    }

    assert required_fields <= example.keys()
    assert "manifest_sha256" not in example


def test_normalized_snapshot_manifest_requires_both_artifact_paths() -> None:
    schema, example = load_contract("normalized-snapshot-manifest.v1")

    for field in ("normalized_artifact_path", "audit_artifact_path"):
        candidate = copy.deepcopy(example)
        candidate.pop(field)
        errors = validation_errors(schema, candidate)
        assert any(error.validator == "required" for error in errors)  # type: ignore[attr-defined]


def test_canonical_deck_example_ids_match_the_domain_fingerprint() -> None:
    schema, example = load_contract("canonical-deck.v1")

    deck = CanonicalDeck.model_validate(example)

    assert deck.canonical_deck_id == deck.structural_fingerprint
    assert deck.canonical_deck_id == example["canonical_deck_id"]
    round_trip_errors = validation_errors(schema, deck.model_dump(mode="json"))
    assert not round_trip_errors

    for stem in (
        "deck-legality-evaluation.v1",
        "deck-quality-evaluation.v1",
        "event-deck-observation.v1",
    ):
        _, reference = load_contract(stem)
        assert reference["canonical_deck_id"] == deck.canonical_deck_id


def test_canonical_deck_duplicate_identity_rows_are_domain_rejected() -> None:
    schema, example = load_contract("canonical-deck.v1")
    candidate = copy.deepcopy(example)
    duplicate = copy.deepcopy(candidate["card_zones"][0]["cards"][0])  # type: ignore[index]
    duplicate["quantity"] = 2  # type: ignore[index]
    candidate["card_zones"][0]["cards"].append(duplicate)  # type: ignore[index]

    assert not validation_errors(schema, candidate)
    with pytest.raises(ValidationError):
        CanonicalDeck.model_validate(candidate)


def test_canonical_deck_schema_documents_unique_zone_name_rule() -> None:
    schema, _ = load_contract("canonical-deck.v1")
    card_zones = schema["properties"]["card_zones"]  # type: ignore[index]

    assert card_zones["x-unique-by"] == "zone"  # type: ignore[index]


def test_source_snapshot_summary_is_derived() -> None:
    _, example = load_contract("source-snapshot-manifest.v2")

    assert example["requests"]
    assert example["objects"]
    assert example["request_parameters_redacted"] == {
        "request_ids": ["request-001"],
        "methods": ["GET"],
        "endpoints": ["https://example.invalid/fixture/cards"],
        "formats": ["json"],
        "api_versions": [],
        "parameter_keys": ["page"],
    }
    assert example["objects"][0]["raw_object_id"]  # type: ignore[index]
    assert example["objects"][0]["request_id"]  # type: ignore[index]


def test_source_snapshot_v2_rejects_unknown_object_request_and_non_derived_summary() -> None:
    schema, example = load_contract("source-snapshot-manifest.v2")

    invalid_reference = copy.deepcopy(example)
    invalid_reference["objects"][0]["request_id"] = "missing-request"  # type: ignore[index]
    with pytest.raises(ValidationError):
        SourceSnapshotManifest.model_validate(invalid_reference)

    invalid_summary = copy.deepcopy(example)
    invalid_summary["request_parameters_redacted"]["formats"] = ["xml"]  # type: ignore[index]
    with pytest.raises(ValidationError):
        SourceSnapshotManifest.model_validate(invalid_summary)

    invalid_summary_shape = copy.deepcopy(example)
    invalid_summary_shape["request_parameters_redacted"] = {"fixture": True}
    assert validation_errors(schema, invalid_summary_shape)


@pytest.mark.parametrize(
    ("stem", "model_type"),
    (
        ("card-resolution.v1", CardResolution),
        ("card.v1", CanonicalCard),
        ("dataset-manifest.v2", DatasetManifest),
        ("source-snapshot-manifest.v2", SourceSnapshotManifest),
        ("normalized-snapshot-manifest.v1", NormalizedSnapshotManifest),
        ("canonical-deck.v1", CanonicalDeck),
        ("deck-legality-evaluation.v1", DeckLegalityEvaluation),
        ("deck-quality-evaluation.v1", DeckQualityEvaluation),
        ("card-face.v1", CardFace),
        ("printing.v1", Printing),
        ("event-deck-observation.v1", EventDeckObservation),
        ("participant-reference.v1", ParticipantReference),
        ("combo.v1", Combo),
        ("combo-card.v1", ComboCard),
    ),
)
def test_affected_domain_models_round_trip_through_their_contract(
    stem: str, model_type: type[object]
) -> None:
    schema, example = load_contract(stem)
    candidate = copy.deepcopy(example)
    if stem == "card-resolution.v1":
        candidate["finding_code"] = "resolution.exact_name"
    elif stem == "dataset-manifest.v2":
        candidate["outputs"][0]["bytes"] = 256  # type: ignore[index]
    elif stem == "card-face.v1":
        candidate["mana_value"] = None
    elif stem == "printing.v1":
        candidate["language"] = None
        candidate["rarity"] = None
        candidate["is_foil"] = None
        candidate["is_promo"] = None
    elif stem == "canonical-deck.v1":
        candidate["command_zone"][0]["source_declared_role"] = None  # type: ignore[index]

    if candidate.get("provenance") and stem != "card.v1":
        candidate["provenance"][0].update(  # type: ignore[index]
            {
                "retrieved_at": None,
                "adapter_version": None,
                "mapper_version": None,
                "approval_status": None,
            }
        )

    model = model_type.model_validate(candidate)  # type: ignore[attr-defined]
    round_trip = model.model_dump(mode="json")  # type: ignore[attr-defined]

    errors = validation_errors(schema, round_trip)
    assert not errors, f"{stem}: " + "\n".join(
        error.message
        for error in errors  # type: ignore[attr-defined]
    )
    if stem == "card-resolution.v1":
        assert round_trip["finding_code"] == "resolution.exact_name"
    elif stem == "dataset-manifest.v2":
        assert round_trip["outputs"][0]["bytes"] == 256  # type: ignore[index]


def test_persisted_domain_models_dump_json_that_matches_their_schema() -> None:
    persisted_models: tuple[tuple[str, type[object]], ...] = (
        ("card-resolution.v1", CardResolution),
        ("card.v1", CanonicalCard),
        ("dataset-manifest.v2", DatasetManifest),
        ("source-snapshot-manifest.v2", SourceSnapshotManifest),
        ("normalized-snapshot-manifest.v1", NormalizedSnapshotManifest),
        ("canonical-deck.v1", CanonicalDeck),
        ("deck-legality-evaluation.v1", DeckLegalityEvaluation),
        ("deck-quality-evaluation.v1", DeckQualityEvaluation),
        ("card-face.v1", CardFace),
        ("printing.v1", Printing),
        ("event-deck-observation.v1", EventDeckObservation),
        ("participant-reference.v1", ParticipantReference),
        ("combo.v1", Combo),
        ("combo-card.v1", ComboCard),
    )

    for stem, model_type in persisted_models:
        schema, example = load_contract(stem)
        model = model_type.model_validate(example)  # type: ignore[attr-defined]
        payload = model.model_dump(mode="json")  # type: ignore[attr-defined]

        assert json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False)) == payload
        errors = validation_errors(schema, payload)
        assert not errors, f"{stem}: " + "\n".join(
            error.message
            for error in errors  # type: ignore[attr-defined]
        )


@pytest.mark.parametrize(
    ("stem", "field", "model_type"),
    (
        ("source-snapshot-manifest.v2", "started_at", SourceSnapshotManifest),
        ("deck-legality-evaluation.v1", "evaluated_at", DeckLegalityEvaluation),
        ("deck-quality-evaluation.v1", "evaluated_at", DeckQualityEvaluation),
        ("event-deck-observation.v1", "observed_at", EventDeckObservation),
        ("dataset-manifest.v2", "created_at", DatasetManifest),
    ),
)
def test_persisted_date_time_fields_reject_naive_timestamps(
    stem: str, field: str, model_type: type[object]
) -> None:
    schema, example = load_contract(stem)
    candidate = copy.deepcopy(example)
    candidate[field] = "2026-08-10T18:00:30"

    assert validation_errors(schema, candidate)
    with pytest.raises(ValidationError):
        model_type.model_validate(candidate)  # type: ignore[attr-defined]


def test_source_snapshot_manifest_rejects_invalid_terms_uri() -> None:
    schema, example = load_contract("source-snapshot-manifest.v2")
    candidate = copy.deepcopy(example)
    candidate["terms_reference"] = "not a uri"

    assert validation_errors(schema, candidate)
    with pytest.raises(ValidationError):
        SourceSnapshotManifest.model_validate(candidate)


@pytest.mark.parametrize(
    "field",
    (
        "schema_versions",
        "transform_versions",
        "policy_versions",
        "ruleset_versions",
        "card_snapshot_ids",
        "source_snapshots",
        "random_seeds",
    ),
)
def test_dataset_manifest_rejects_duplicate_or_invalid_unique_collections(field: str) -> None:
    schema, example = load_contract("dataset-manifest.v2")
    candidate = copy.deepcopy(example)
    if field == "random_seeds":
        candidate[field] = [0, 0]
    else:
        values = candidate[field]
        candidate[field] = [values[0], values[0]]

    assert validation_errors(schema, candidate)
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(candidate)


def test_dataset_manifest_rejects_negative_counts_and_random_seeds() -> None:
    schema, example = load_contract("dataset-manifest.v2")

    negative_count = copy.deepcopy(example)
    negative_count["counts"] = {"train": -1}
    assert validation_errors(schema, negative_count)
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(negative_count)

    negative_seed = copy.deepcopy(example)
    negative_seed["random_seeds"] = [-1]
    assert validation_errors(schema, negative_seed)
    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(negative_seed)


@pytest.mark.parametrize("field", ("pagination_state",))
def test_source_snapshot_manifest_rejects_non_json_mapping_values(field: str) -> None:
    _, example = load_contract("source-snapshot-manifest.v2")
    candidate = copy.deepcopy(example)
    candidate[field] = {"unsupported": object()}

    with pytest.raises(ValidationError):
        SourceSnapshotManifest.model_validate(candidate)


@pytest.mark.parametrize("field", ("filters", "split_policy"))
def test_dataset_manifest_rejects_non_json_mapping_values(field: str) -> None:
    _, example = load_contract("dataset-manifest.v2")
    candidate = copy.deepcopy(example)
    candidate[field] = {"unsupported": object()}

    with pytest.raises(ValidationError):
        DatasetManifest.model_validate(candidate)


@pytest.mark.parametrize(
    ("stem", "field", "model_type"),
    (
        ("card-face.v1", "provenance", CardFace),
        ("printing.v1", "face_ids", Printing),
        ("printing.v1", "provenance", Printing),
        ("canonical-deck.v1", "provenance", CanonicalDeck),
        ("event-deck-observation.v1", "provenance", EventDeckObservation),
        ("combo.v1", "provenance", Combo),
        ("combo-card.v1", "provenance", ComboCard),
        ("normalized-snapshot-manifest.v1", "provenance", NormalizedSnapshotManifest),
        ("dataset-manifest.v2", "input_manifests", DatasetManifest),
        ("dataset-manifest.v2", "schema_versions", DatasetManifest),
        ("dataset-manifest.v2", "transform_versions", DatasetManifest),
        ("dataset-manifest.v2", "policy_versions", DatasetManifest),
        ("dataset-manifest.v2", "outputs", DatasetManifest),
    ),
)
def test_schema_required_collections_match_domain_non_empty_rules(
    stem: str, field: str, model_type: type[object]
) -> None:
    schema, example = load_contract(stem)
    candidate = copy.deepcopy(example)
    candidate[field] = []

    errors = validation_errors(schema, candidate)
    assert any(error.validator == "minItems" for error in errors)  # type: ignore[attr-defined]
    with pytest.raises(ValidationError):
        model_type.model_validate(candidate)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("stem", "mutate", "model_type"),
    (
        (
            "card-face.v1",
            lambda candidate: candidate.__setitem__("mana_value", -1),
            CardFace,
        ),
        (
            "printing.v1",
            lambda candidate: candidate.__setitem__("language", ""),
            Printing,
        ),
        (
            "canonical-deck.v1",
            lambda candidate: candidate["command_zone"][0].__setitem__(
                "source_declared_role", "invalid"
            ),
            CanonicalDeck,
        ),
        (
            "card-face.v1",
            lambda candidate: candidate["provenance"][0].__setitem__("approval_status", "UNKNOWN"),
            CardFace,
        ),
    ),
)
def test_task1_optional_fields_reject_invalid_values(
    stem: str, mutate: object, model_type: type[object]
) -> None:
    schema, example = load_contract(stem)
    candidate = copy.deepcopy(example)
    mutate(candidate)  # type: ignore[operator]

    assert validation_errors(schema, candidate)
    with pytest.raises(ValidationError):
        model_type.model_validate(candidate)  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("stem", "path_setter"),
    (
        (
            "normalized-snapshot-manifest.v1",
            lambda instance, value: instance.__setitem__("normalized_artifact_path", value),
        ),
        (
            "normalized-snapshot-manifest.v1",
            lambda instance, value: instance.__setitem__("audit_artifact_path", value),
        ),
        (
            "source-snapshot-manifest.v2",
            lambda instance, value: instance["objects"][0].__setitem__("path", value),
        ),
        (
            "normalized-snapshot-manifest.v1",
            lambda instance, value: instance["quarantine_references"].append(
                {"quarantine_id": "q-1", "reason_code": "integrity.bad", "path": value}
            ),
        ),
        (
            "dataset-manifest.v2",
            lambda instance, value: instance["input_manifests"][0].__setitem__("path", value),
        ),
        (
            "dataset-manifest.v2",
            lambda instance, value: instance["outputs"][0].__setitem__("path", value),
        ),
        (
            "dataset-manifest.v2",
            lambda instance, value: instance["quality_report"].__setitem__("path", value),
        ),
        (
            "dataset-manifest.v2",
            lambda instance, value: instance["leakage_report"].__setitem__("path", value),
        ),
    ),
)
@pytest.mark.parametrize(
    "invalid_path",
    ("C:/data/file", "\\\\server\\share", "/root/file", "a/../file", "a/./file", "."),
)
def test_contracts_reject_non_portable_persisted_paths(
    stem: str, path_setter: object, invalid_path: str
) -> None:
    schema, example = load_contract(stem)
    candidate = copy.deepcopy(example)
    path_setter(candidate, invalid_path)  # type: ignore[operator]

    errors = validation_errors(schema, candidate)
    assert any(error.validator == "pattern" for error in errors)  # type: ignore[attr-defined]

    model_type = {
        "normalized-snapshot-manifest.v1": NormalizedSnapshotManifest,
        "source-snapshot-manifest.v2": SourceSnapshotManifest,
        "dataset-manifest.v2": DatasetManifest,
    }[stem]
    with pytest.raises(ValidationError):
        model_type.model_validate(candidate)


def _set_versioned_path_values(
    stem: str,
    candidate: dict[str, object],
    value: str,
) -> None:
    if stem == "source-snapshot-manifest.v2":
        candidate["objects"][0]["path"] = value  # type: ignore[index]
    elif stem == "normalized-snapshot-manifest.v2":
        candidate["normalized_artifact_path"] = value
        candidate["audit_artifact_path"] = value
        candidate["quarantine_references"] = [
            {"quarantine_id": "q-1", "reason_code": "integrity.bad", "path": value}
        ]
    elif stem == "dataset-manifest.v2":
        candidate["input_manifests"][0]["path"] = value  # type: ignore[index]
        candidate["outputs"][0]["path"] = value  # type: ignore[index]
        candidate["quality_report"]["path"] = value  # type: ignore[index]
        candidate["leakage_report"]["path"] = value  # type: ignore[index]
    else:
        raise AssertionError(f"unsupported path contract: {stem}")


@pytest.mark.parametrize(
    "stem",
    (
        "source-snapshot-manifest.v2",
        "normalized-snapshot-manifest.v2",
        "dataset-manifest.v2",
    ),
)
@pytest.mark.parametrize(
    "invalid_path",
    (
        "/root/file",
        "//server/share/file",
        "C:/data/file",
        "objects\\file.bin",
        "objects\x00file.bin",
        "objects/../file.bin",
        "objects/./file.bin",
        "objects/~",
        "objects/~user/file.bin",
        "~/machine-specific/file.bin",
        "<external-root>",
        "objects/<repository-root>/file.bin",
    ),
)
def test_authoritative_versioned_path_schemas_reject_nonportable_values(
    stem: str, invalid_path: str
) -> None:
    schema, example = load_contract(stem)
    candidate = copy.deepcopy(example)
    _set_versioned_path_values(stem, candidate, invalid_path)

    assert validation_errors(schema, candidate), f"{stem} accepted {invalid_path!r}"


def test_frozen_v1_path_contracts_keep_their_legacy_compatibility_boundary() -> None:
    legacy_path = "<external-root>"

    source_v1_schema, source_v1_example = load_contract("source-snapshot-manifest.v1")
    source_v1_candidate = copy.deepcopy(source_v1_example)
    source_v1_candidate["objects"][0]["path"] = legacy_path  # type: ignore[index]
    assert not validation_errors(source_v1_schema, source_v1_candidate)

    normalized_v1_schema, normalized_v1_example = load_contract("normalized-snapshot-manifest.v1")
    normalized_v1_candidate = copy.deepcopy(normalized_v1_example)
    normalized_v1_candidate["normalized_artifact_path"] = legacy_path
    assert not validation_errors(normalized_v1_schema, normalized_v1_candidate)

    dataset_v1_schema, dataset_v1_example = load_contract("dataset-manifest.v1")
    dataset_v1_candidate = copy.deepcopy(dataset_v1_example)
    dataset_v1_candidate["tables"][0]["path"] = legacy_path  # type: ignore[index]
    assert not validation_errors(dataset_v1_schema, dataset_v1_candidate)

    for stem in (
        "source-snapshot-manifest.v2",
        "normalized-snapshot-manifest.v2",
        "dataset-manifest.v2",
    ):
        schema, example = load_contract(stem)
        candidate = copy.deepcopy(example)
        _set_versioned_path_values(stem, candidate, legacy_path)
        assert validation_errors(schema, candidate), f"{stem} accepted legacy path syntax"


def test_source_snapshot_contract_marks_lineage_constraints_as_authoritative() -> None:
    schema, example = load_contract("source-snapshot-manifest.v2")

    duplicate_request = copy.deepcopy(example)
    duplicate_request["requests"][0]["sanitized_parameters"] = {"page": 2}  # type: ignore[index]
    duplicate_request_copy = copy.deepcopy(duplicate_request["requests"][0])  # type: ignore[index]
    duplicate_request_copy["sanitized_parameters"] = {"page": 3}  # type: ignore[index]
    duplicate_request["requests"].append(duplicate_request_copy)  # type: ignore[index]
    assert not validation_errors(schema, duplicate_request)
    with pytest.raises(ValidationError):
        SourceSnapshotManifest.model_validate(duplicate_request)

    duplicate_object = copy.deepcopy(example)
    duplicate_object["objects"][0]["path"] = "objects/object-002.json"  # type: ignore[index]
    duplicate_object_copy = copy.deepcopy(duplicate_object["objects"][0])  # type: ignore[index]
    duplicate_object_copy["path"] = "objects/object-003.json"  # type: ignore[index]
    duplicate_object["objects"].append(duplicate_object_copy)  # type: ignore[index]
    assert not validation_errors(schema, duplicate_object)
    with pytest.raises(ValidationError):
        SourceSnapshotManifest.model_validate(duplicate_object)

    unknown_request = copy.deepcopy(example)
    unknown_request["objects"][0]["request_id"] = "missing-request"  # type: ignore[index]
    assert not validation_errors(schema, unknown_request)
    with pytest.raises(ValidationError):
        SourceSnapshotManifest.model_validate(unknown_request)


def test_normalized_provenance_must_match_manifest_scope() -> None:
    _, example = load_contract("normalized-snapshot-manifest.v1")

    wrong_source = copy.deepcopy(example)
    wrong_source["provenance"][0]["source_id"] = "other-source"  # type: ignore[index]
    with pytest.raises(ValidationError):
        NormalizedSnapshotManifest.model_validate(wrong_source)

    wrong_snapshot = copy.deepcopy(example)
    wrong_snapshot["provenance"][0]["source_snapshot_id"] = "other-snapshot"  # type: ignore[index]
    with pytest.raises(ValidationError):
        NormalizedSnapshotManifest.model_validate(wrong_snapshot)


def test_participant_contract_requires_scope_fields_and_rejects_incompatible_fields() -> None:
    schema, example = load_contract("participant-reference.v1")

    missing_scope_field = copy.deepcopy(example)
    missing_scope_field.pop("event_id")
    assert validation_errors(schema, missing_scope_field)

    incompatible_scope_field = copy.deepcopy(example)
    incompatible_scope_field["source_id"] = "source-1"
    assert validation_errors(schema, incompatible_scope_field)


@pytest.mark.parametrize("stem", ("source-snapshot-manifest.v2", "normalized-snapshot-manifest.v1"))
def test_manifest_digest_is_detached_from_manifest_json(stem: str) -> None:
    schema, example = load_contract(stem)
    model_type = (
        SourceSnapshotManifest
        if stem == "source-snapshot-manifest.v2"
        else NormalizedSnapshotManifest
    )
    model = model_type.model_validate(example)
    payload = model.model_dump(mode="json")

    assert "manifest_sha256" not in payload
    assert schema["x-detached-digest"] == {  # type: ignore[comparison-overlap]
        "sidecar_filename": "manifest.sha256",
        "algorithm": "SHA-256",
        "canonical_payload": "manifest JSON without a self-digest field",
    }
    expected = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    assert detached_manifest_sha256(payload) == expected
    expected_sidecars = {
        "source-snapshot-manifest.v2": (
            "f4e386eb9979be5eafc88b92d1a3d50ea9d04d0a2f488fed35d29360b150016a"
        ),
        "normalized-snapshot-manifest.v1": (
            "ca5f3e104d6f9d5dc7a0cac0a8314bd12390819e62f276dc6e2986f55d60aa26"
        ),
    }
    assert detached_manifest_sha256(payload) == expected_sidecars[stem]

    sidecar_payload = dict(payload, manifest_sha256="0" * 64)
    assert detached_manifest_sha256(sidecar_payload) == expected


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
