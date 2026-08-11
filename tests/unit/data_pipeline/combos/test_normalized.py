from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.data_pipeline.combos.normalized import (
    ComboCardInput,
    ComboRecord,
    normalize_combo,
)
from commander_ai.data_pipeline.provenance.evidence import SourceEvidence
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.domain.provenance import ProvenanceReference

PROJECT_ROOT = Path(__file__).resolve().parents[4]
CARD_A = "11111111-1111-4111-8111-111111111111"
CARD_B = "22222222-2222-4222-8222-222222222222"
COMMANDER = "33333333-3333-4333-8333-333333333333"


def _evidence() -> SourceEvidence:
    locator = RawLocator(
        source_id="commander_spellbook",
        source_snapshot_id="spellbook-snapshot",
        raw_object_id="variants-page-1",
        raw_object_path="commander_spellbook/variants-page-1.json",
        location=JsonPointerLocator(pointer="/results/0"),
    )
    return SourceEvidence(
        raw_locator=locator,
        provenance=(
            ProvenanceReference(
                source_id="commander_spellbook",
                source_snapshot_id="spellbook-snapshot",
                source_object_id="variants-page-1",
                raw_sha256="0" * 64,
                retrieved_at=datetime(2026, 8, 11, tzinfo=UTC),
                adapter_version="spellbook-v1",
                mapper_version="task12-v1",
                approval_status="APPROVED_LOCAL",
            ),
        ),
    )


def test_combo_and_card_relationships_normalize_as_feature_data() -> None:
    result = normalize_combo(
        ComboRecord(
            combo_id="combo-1",
            evidence=_evidence(),
            name="Fixture combo",
            cards=(
                ComboCardInput(oracle_id=CARD_A, role="required", quantity=1),
                ComboCardInput(oracle_id=CARD_A.upper(), role="required", quantity=1),
                ComboCardInput(oracle_id=CARD_B, role="result", quantity=1),
            ),
            requirements=("Card A is on the battlefield.",),
            results=("Create a result.",),
            steps=("Activate the ability.",),
            source_status="active",
            commander_compatible=True,
            commander_oracle_ids=(COMMANDER,),
        )
    )
    assert result.status == "CURATED"
    assert result.combo is not None
    assert result.combo.required_cards == (CARD_A,)
    assert len(result.cards) == 2
    assert result.cards[0].quantity == 2
    assert result.commander_compatibility[0].commander_oracle_id == COMMANDER
    assert "legal_status" not in result.combo.model_dump(mode="json")


def test_missing_combo_requirements_are_quarantined_with_evidence() -> None:
    result = normalize_combo(
        ComboRecord(
            combo_id="combo-incomplete",
            evidence=_evidence(),
            cards=(ComboCardInput(oracle_id=CARD_A, role="required", quantity=1),),
            requirements=(),
            results=("A result",),
        )
    )
    assert result.status == "QUARANTINED"
    assert result.combo is None
    assert result.evidence.raw_locator.raw_object_id == "variants-page-1"
    assert "quality.combo_requirements_missing" in result.finding_codes


def test_invalid_card_resolution_is_quarantined_not_guessed() -> None:
    result = normalize_combo(
        ComboRecord(
            combo_id="combo-invalid",
            evidence=_evidence(),
            cards=(ComboCardInput(oracle_id="not-a-uuid", role="required", quantity=1),),
            requirements=("A requirement",),
            results=("A result",),
        )
    )
    assert result.status == "QUARANTINED"
    assert result.combo is None
    assert "quality.combo_card_invalid" in result.finding_codes


def test_combo_contracts_serialize_to_existing_schemas() -> None:
    result = normalize_combo(
        ComboRecord(
            combo_id="combo-schema",
            evidence=_evidence(),
            cards=(ComboCardInput(oracle_id=CARD_A, role="required", quantity=1),),
            requirements=("A requirement",),
            results=("A result",),
        )
    )
    assert result.combo is not None
    combo_schema = json.loads((PROJECT_ROOT / "schemas" / "combo.v1.schema.json").read_text())
    combo_errors = Draft202012Validator(combo_schema, format_checker=FormatChecker()).iter_errors(
        result.combo.model_dump(mode="json")
    )
    assert not list(combo_errors)
    card_schema = json.loads((PROJECT_ROOT / "schemas" / "combo-card.v1.schema.json").read_text())
    card_errors = Draft202012Validator(card_schema, format_checker=FormatChecker()).iter_errors(
        result.cards[0].model_dump(mode="json")
    )
    assert not list(card_errors)


def test_commander_compatibility_contract_serializes_to_versioned_schema() -> None:
    result = normalize_combo(
        ComboRecord(
            combo_id="combo-compatibility-schema",
            evidence=_evidence(),
            cards=(ComboCardInput(oracle_id=CARD_A, role="required", quantity=1),),
            requirements=("A requirement",),
            results=("A result",),
            commander_compatible=True,
            commander_oracle_ids=(COMMANDER,),
        )
    )
    assert result.commander_compatibility
    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "combo-commander-compatibility.v1.schema.json").read_text()
    )
    errors = Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
        result.commander_compatibility[0].as_dict()
    )
    assert not list(errors)


def test_commander_compatibility_order_is_deterministic() -> None:
    base = dict(
        combo_id="combo-order",
        evidence=_evidence(),
        cards=(ComboCardInput(oracle_id=CARD_A, role="required", quantity=1),),
        requirements=("A requirement",),
        results=("A result",),
        commander_compatible=True,
    )
    first = normalize_combo(ComboRecord(**base, commander_oracle_ids=(COMMANDER, CARD_B)))
    second = normalize_combo(ComboRecord(**base, commander_oracle_ids=(CARD_B, COMMANDER)))
    assert first.status == second.status == "CURATED"
    assert [item.as_dict() for item in first.commander_compatibility] == [
        item.as_dict() for item in second.commander_compatibility
    ]


def test_invalid_commander_compatibility_is_quarantined() -> None:
    result = normalize_combo(
        ComboRecord(
            combo_id="combo-invalid-commander",
            evidence=_evidence(),
            cards=(ComboCardInput(oracle_id=CARD_A, role="required", quantity=1),),
            requirements=("A requirement",),
            results=("A result",),
            commander_compatible=True,
            commander_oracle_ids=("not-a-uuid",),
        )
    )
    assert result.status == "QUARANTINED"
    assert result.combo is None
    assert "quality.combo_commander_id_invalid" in result.finding_codes
