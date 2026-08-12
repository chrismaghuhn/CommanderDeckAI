from __future__ import annotations

import json
from datetime import UTC, date, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.data_pipeline.decks.canonical_decks import (
    DeckSourceReference,
    DeckStructureInput,
    canonical_deck_from_input,
)
from commander_ai.data_pipeline.decks.quality import evaluate_deck_quality
from commander_ai.data_pipeline.decks.ruleset_evaluation import evaluate_deck_legality
from commander_ai.data_pipeline.decks.ruleset_selection import select_applicable_ruleset
from commander_ai.domain.cards import CanonicalCard
from commander_ai.domain.decks import (
    CanonicalDeck,
    CardQuantity,
    CardZone,
    CommandZoneEntry,
    CommandZoneRelationship,
)
from commander_ai.domain.provenance import ProvenanceReference
from commander_ai.domain.rulesets import CommandZonePolicy, RulesetSnapshot

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
ORACLE_C = "33333333-3333-4333-8333-333333333333"
ORACLE_CASE_VARIANT = "abcdefab-cdef-4abc-8def-abcdefabcdef"


def _provenance(source: DeckSourceReference) -> tuple[ProvenanceReference, ...]:
    return (
        ProvenanceReference(
            source_id=source.source_id,
            source_snapshot_id=source.source_snapshot_id,
            source_object_id=source.raw_object_id,
            raw_sha256=source.raw_sha256,
            retrieved_at=datetime(2026, 8, 11, tzinfo=UTC),
            adapter_version="fixture-adapter-v1",
            mapper_version="fixture-deck-mapper-v1",
            approval_status="APPROVED_LOCAL",
        ),
    )


def _source(source_deck_id: str, *, source_id: str = "fixture") -> DeckSourceReference:
    return DeckSourceReference(
        source_id=source_id,
        source_deck_id=source_deck_id,
        source_snapshot_id=f"{source_id}-snapshot",
        raw_object_id=f"{source_deck_id}.json",
        raw_sha256="0" * 64,
        observed_at=date(2026, 8, 11),
    )


def _input(
    source: DeckSourceReference,
    *,
    command_zone: tuple[CommandZoneEntry, ...] | None = None,
    card_zones: tuple[CardZone, ...] | None = None,
    command_zone_relationships: tuple[CommandZoneRelationship, ...] = (),
) -> DeckStructureInput:
    return DeckStructureInput(
        source=source,
        command_zone=command_zone
        or (CommandZoneEntry(oracle_id=ORACLE_A, quantity=1, source_declared_role="commander"),),
        card_zones=card_zones
        or (
            CardZone(
                zone="mainboard",
                cards=(CardQuantity(oracle_id=ORACLE_B, quantity=1),),
            ),
        ),
        provenance=_provenance(source),
        command_zone_relationships=command_zone_relationships,
    )


def _card(oracle_id: str, *, colors: tuple[str, ...] = ()) -> CanonicalCard:
    return CanonicalCard(
        card_snapshot_id="cards-fixture-v1",
        oracle_id=oracle_id,
        name=f"Card {oracle_id[:4]}",
        normalized_name=f"card {oracle_id[:4]}",
        layout="normal",
        mana_value=0,
        colors=colors,
        color_identity=colors,
        legalities={"commander": "legal"},
        provenance=_provenance(_source("cards", source_id="cards")),
    )


def _ruleset(
    version: str,
    *,
    effective_from: date = date(2026, 1, 1),
    banned: tuple[str, ...] = (),
    required_total_cards: int = 2,
    copy_limit_overrides: dict[str, int] | None = None,
    max_command_cards: int = 2,
) -> RulesetSnapshot:
    return RulesetSnapshot(
        ruleset_version=version,
        effective_from=effective_from,
        required_total_cards=required_total_cards,
        default_copy_limit=1,
        banned_oracle_ids=banned,
        copy_limit_overrides=copy_limit_overrides or {},
        command_zone_policy=CommandZonePolicy(
            min_cards=1,
            max_cards=max_command_cards,
            validator_version="command-zone-v1",
        ),
        source_references=("https://example.invalid/rules",),
        sha256=sha256(version.encode("utf-8")).hexdigest(),
    )


def test_structural_identity_is_order_independent_and_excludes_source_metadata() -> None:
    first = canonical_deck_from_input(_input(_source("deck-a"))).deck
    second = canonical_deck_from_input(
        _input(
            _source("deck-b", source_id="other"),
            card_zones=(
                CardZone(
                    zone="sideboard",
                    cards=(CardQuantity(oracle_id=ORACLE_C, quantity=1),),
                ),
                CardZone(
                    zone="mainboard",
                    cards=(CardQuantity(oracle_id=ORACLE_B, quantity=1),),
                ),
            ),
        )
    ).deck
    assert first.canonical_deck_id != second.canonical_deck_id

    reordered = canonical_deck_from_input(
        _input(
            _source("deck-c"),
            card_zones=(
                CardZone(
                    zone="mainboard",
                    cards=(CardQuantity(oracle_id=ORACLE_B, quantity=1),),
                ),
            ),
        )
    ).deck
    assert first.canonical_deck_id == reordered.canonical_deck_id
    assert "source_id" not in first.model_dump(mode="json")


def test_uuid_spelling_does_not_change_structural_identity() -> None:
    lower = canonical_deck_from_input(
        _input(
            _source("lower"),
            command_zone=(CommandZoneEntry(oracle_id=ORACLE_CASE_VARIANT, quantity=1),),
        )
    ).deck
    upper = canonical_deck_from_input(
        _input(
            _source("upper"),
            command_zone=(CommandZoneEntry(oracle_id=ORACLE_CASE_VARIANT.upper(), quantity=1),),
        )
    ).deck
    assert lower.canonical_deck_id == upper.canonical_deck_id


def test_uuid_case_variants_cannot_duplicate_a_card_within_one_zone() -> None:
    with pytest.raises(ValueError):
        CardZone(
            zone="mainboard",
            cards=(
                CardQuantity(oracle_id=ORACLE_CASE_VARIANT, quantity=1),
                CardQuantity(oracle_id=ORACLE_CASE_VARIANT.upper(), quantity=1),
            ),
        )


def test_unknown_fingerprint_algorithm_version_is_rejected() -> None:
    deck = canonical_deck_from_input(_input(_source("algorithm-version"))).deck
    payload = deck.model_dump(mode="json")
    payload["fingerprint_algorithm_version"] = "future-algorithm"
    with pytest.raises(ValueError):
        CanonicalDeck.model_validate(payload)


def test_partner_background_roles_and_relationships_are_preserved() -> None:
    source = _source("partner-deck")
    command_zone = (
        CommandZoneEntry(oracle_id=ORACLE_A, quantity=1, source_declared_role="commander"),
        CommandZoneEntry(oracle_id=ORACLE_B, quantity=1, source_declared_role="background"),
    )
    relationship = CommandZoneRelationship(kind="background", card_ids=(ORACLE_A, ORACLE_B))
    result = canonical_deck_from_input(
        _input(
            source,
            command_zone=command_zone,
            command_zone_relationships=(relationship,),
        )
    )
    deck = result.deck
    assert len(deck.command_zone) == 2
    assert deck.command_zone[1].source_declared_role == "background"
    assert deck.command_zone_relationships[0].kind == "background"


def test_command_zone_relationships_must_reference_command_zone_cards() -> None:
    relationship = CommandZoneRelationship(kind="partner", card_ids=(ORACLE_A, ORACLE_C))
    try:
        canonical_deck_from_input(
            _input(_source("invalid-relationship"), command_zone_relationships=(relationship,))
        )
    except ValueError as error:
        assert "command-zone relationships" in str(error)
    else:
        raise AssertionError("invalid command-zone relationship was accepted")


def test_ruleset_selection_is_effective_dated_and_has_no_current_fallback() -> None:
    old = _ruleset("old", effective_from=date(2025, 1, 1))
    current = _ruleset("current", effective_from=date(2026, 1, 1))
    selected = select_applicable_ruleset((old, current), date(2025, 8, 1))
    assert selected.status == "selected"
    assert selected.ruleset is old
    assert select_applicable_ruleset((old, current), date(2024, 12, 31)).finding_code == (
        "legality.ruleset_unresolved"
    )


def test_ambiguous_ruleset_selection_preserves_its_audit_finding() -> None:
    first = _ruleset("same-date-a")
    second = _ruleset("same-date-b")
    selection = select_applicable_ruleset((first, second), date(2026, 8, 11))
    deck = canonical_deck_from_input(_input(_source("ambiguous-rules"))).deck
    evaluation = evaluate_deck_legality(deck, {}, selection)
    assert evaluation.legal_status == "unknown"
    assert evaluation.finding_codes == ("legality.ruleset_ambiguous",)


def test_invalid_ruleset_copy_limit_is_rejected_before_persistence() -> None:
    with pytest.raises(ValueError):
        _ruleset("invalid", copy_limit_overrides={ORACLE_A: 0})


def test_legality_is_separate_and_ruleset_changes_do_not_change_deck_identity() -> None:
    deck = canonical_deck_from_input(_input(_source("legal-deck"))).deck
    facts = {ORACLE_A: _card(ORACLE_A, colors=("U",)), ORACLE_B: _card(ORACLE_B, colors=("R",))}
    first = evaluate_deck_legality(
        deck,
        facts,
        _ruleset("rules-a"),
        evaluated_at=datetime(2026, 8, 11, tzinfo=UTC),
        command_zone_validator=lambda *_: (),
    )
    second = evaluate_deck_legality(
        deck,
        facts,
        _ruleset("rules-b", banned=(ORACLE_B,)),
        evaluated_at=datetime(2026, 8, 11, tzinfo=UTC),
        command_zone_validator=lambda *_: (),
    )
    assert first.canonical_deck_id == second.canonical_deck_id == deck.canonical_deck_id
    assert first.legal_status == "illegal"
    assert second.legal_status == "illegal"
    assert "legality.color_identity_violation" in first.finding_codes
    assert "legality.banned_card" in second.finding_codes


def test_unresolved_ruleset_and_unverified_multi_card_command_zone_are_unknown() -> None:
    command_zone = (
        CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),
        CommandZoneEntry(oracle_id=ORACLE_C, quantity=1),
    )
    deck = canonical_deck_from_input(
        _input(_source("partner-deck"), command_zone=command_zone)
    ).deck
    facts = {ORACLE_A: _card(ORACLE_A), ORACLE_B: _card(ORACLE_B), ORACLE_C: _card(ORACLE_C)}
    unresolved = evaluate_deck_legality(deck, facts, None)
    assert unresolved.legal_status == "unknown"
    checked = evaluate_deck_legality(
        deck,
        facts,
        _ruleset("rules", required_total_cards=3),
        command_zone_validator=lambda *_: (),
    )
    assert checked.legal_status == "legal"
    unverified = evaluate_deck_legality(deck, facts, _ruleset("rules", required_total_cards=3))
    assert unverified.legal_status == "unknown"


def test_command_zone_size_counts_card_quantities() -> None:
    deck = canonical_deck_from_input(
        _input(
            _source("quantity-command-zone"),
            command_zone=(CommandZoneEntry(oracle_id=ORACLE_A, quantity=2),),
        )
    ).deck
    result = evaluate_deck_legality(
        deck,
        {ORACLE_A: _card(ORACLE_A), ORACLE_B: _card(ORACLE_B)},
        _ruleset("rules", required_total_cards=3, max_command_cards=1),
        command_zone_validator=lambda *_: (),
    )
    assert "legality.command_zone_size_invalid" in result.finding_codes


def test_single_card_command_zone_without_authoritative_validator_is_unknown() -> None:
    deck = canonical_deck_from_input(_input(_source("unverified-single"))).deck
    result = evaluate_deck_legality(
        deck,
        {ORACLE_A: _card(ORACLE_A), ORACLE_B: _card(ORACLE_B)},
        _ruleset("rules"),
    )
    assert result.legal_status == "unknown"
    assert "legality.command_zone_unverified" in result.finding_codes


def test_quality_evaluation_does_not_mutate_or_repeat_legality() -> None:
    deck = canonical_deck_from_input(_input(_source("quality-deck"))).deck
    quality = evaluate_deck_quality(deck, resolution_rate=0.5)
    assert quality.canonical_deck_id == deck.canonical_deck_id
    assert quality.quality_status == "review"
    assert "quality.card_resolution_incomplete" in quality.finding_codes
    assert "legal_status" not in quality.model_dump(mode="json")


def test_ruleset_domain_model_matches_existing_schema_example() -> None:
    schema = json.loads((PROJECT_ROOT / "schemas" / "ruleset.v1.schema.json").read_text())
    example = json.loads((PROJECT_ROOT / "examples" / "ruleset.v1.json").read_text())
    payload = RulesetSnapshot.model_validate(example).model_dump(mode="json")
    assert not list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(payload)
    )
