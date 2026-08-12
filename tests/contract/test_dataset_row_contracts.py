from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from pydantic import ValidationError

from commander_ai.domain.dataset_row_contracts import (
    CardCooccurrenceRow,
    CardCooccurrenceV2Row,
    ComboCorpusRow,
    DeckCorpusRow,
    TournamentCorpusRow,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CONTRACTS = {
    "deck-corpus.v1": DeckCorpusRow,
    "card-cooccurrence.v1": CardCooccurrenceRow,
    "card-cooccurrence.v2": CardCooccurrenceV2Row,
    "tournament-corpus.v1": TournamentCorpusRow,
    "combo-corpus.v1": ComboCorpusRow,
}


def _contract(stem: str) -> tuple[dict[str, object], dict[str, object]]:
    schema = json.loads(
        (PROJECT_ROOT / "schemas" / f"{stem}.schema.json").read_text(encoding="utf-8")
    )
    example = json.loads((PROJECT_ROOT / "examples" / f"{stem}.json").read_text(encoding="utf-8"))
    return schema, example


@pytest.mark.parametrize("stem", tuple(CONTRACTS))
def test_dataset_row_examples_round_trip_through_domain_and_schema(stem: str) -> None:
    schema, example = _contract(stem)
    Draft202012Validator.check_schema(schema)
    model = CONTRACTS[stem].model_validate(example)
    payload = model.model_dump(mode="json")

    errors = list(Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload))
    assert errors == []


@pytest.mark.parametrize("stem", tuple(CONTRACTS))
@pytest.mark.parametrize("mutation", ("missing_curated_id", "invalid_split", "invalid_schema"))
def test_dataset_row_contracts_reject_missing_ids_and_control_fields(
    stem: str, mutation: str
) -> None:
    schema, candidate = _contract(stem)
    if mutation == "missing_curated_id":
        candidate.pop("curated_id")
    elif mutation == "invalid_split":
        candidate["values"]["split"] = "holdout"  # type: ignore[index]
    else:
        candidate["values"]["schema_version"] = "curated.v1"  # type: ignore[index]

    schema_errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(candidate)
    )
    assert schema_errors
    with pytest.raises(ValidationError):
        CONTRACTS[stem].model_validate(candidate)


def test_deck_corpus_rejects_invalid_nested_card_identifier() -> None:
    _, candidate = _contract("deck-corpus.v1")
    candidate["values"]["command_zone"][0]["oracle_id"] = "not-a-uuid"  # type: ignore[index]

    with pytest.raises(ValidationError):
        DeckCorpusRow.model_validate(candidate)


def test_deck_corpus_rejects_canonical_id_mismatched_with_persisted_structure() -> None:
    _, candidate = _contract("deck-corpus.v1")
    candidate["values"]["canonical_deck_id"] = "b" * 64  # type: ignore[index]

    with pytest.raises(ValidationError, match="canonical_deck_id"):
        DeckCorpusRow.model_validate(candidate)


def test_card_cooccurrence_v2_rejects_relation_outside_persisted_zones() -> None:
    _, candidate = _contract("card-cooccurrence.v2")
    candidate["values"]["right_id"] = "33333333-3333-4333-8333-333333333333"  # type: ignore[index]

    with pytest.raises(ValidationError, match="must reference command and card zones"):
        CardCooccurrenceV2Row.model_validate(candidate)


@pytest.mark.parametrize("field", ("command_zone", "card_zones"))
def test_deck_corpus_rejects_duplicate_outer_collection_items(field: str) -> None:
    _, candidate = _contract("deck-corpus.v1")
    values = candidate["values"]  # type: ignore[assignment]
    collection = values[field]  # type: ignore[index]
    collection.append(copy.deepcopy(collection[0]))

    with pytest.raises(ValidationError, match="collection items must be unique"):
        DeckCorpusRow.model_validate(candidate)


def test_dataset_rows_reject_unsanitized_participant_payload() -> None:
    _, candidate = _contract("deck-corpus.v1")
    candidate["values"]["payload"] = {"player_name": "Alice"}  # type: ignore[index]

    with pytest.raises(ValidationError):
        DeckCorpusRow.model_validate(candidate)


def test_dataset_row_contracts_keep_examples_independent() -> None:
    _, original = _contract("combo-corpus.v1")
    candidate = copy.deepcopy(original)
    candidate["values"]["record_id"] = ""  # type: ignore[index]

    with pytest.raises(ValidationError):
        ComboCorpusRow.model_validate(candidate)
