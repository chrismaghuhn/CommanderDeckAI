from __future__ import annotations

from datetime import UTC, datetime

from commander_ai.data_pipeline.decks.ruleset_inputs import RulesetSnapshotInput
from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.data_pipeline.normalization.canonicalization import canonicalize_staging
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.provenance import (
    RawObjectReference,
    SourceSnapshotManifest,
    SourceSnapshotRequest,
    derive_request_parameters_summary,
)
from commander_ai.domain.rulesets import RulesetSnapshot

NOW = datetime(2026, 8, 10, 18, 0, tzinfo=UTC)
ORACLE_ID = "11111111-1111-4111-8111-111111111111"
PRINTING_ID = "22222222-2222-4222-8222-222222222222"


def _manifest() -> SourceSnapshotManifest:
    request = SourceSnapshotRequest(
        request_id="request-1",
        sanitized_method="GET",
        sanitized_endpoint="https://fixture.invalid/AllPrintings.json",
        format="json",
        sanitized_parameters={},
    )
    return SourceSnapshotManifest(
        source_id="mtgjson",
        source_snapshot_id="snapshot-1",
        status="COMPLETE",
        approval_status="APPROVED_LOCAL",
        adapter_version="mtgjson-adapter-v1",
        started_at=NOW,
        completed_at=NOW,
        usage_status="local-only",
        request_parameters_redacted=derive_request_parameters_summary((request,)),
        requests=(request,),
        objects=(
            RawObjectReference(
                raw_object_id="response.json",
                request_id="request-1",
                retrieved_at=NOW,
                path="objects/response.json",
                bytes=1,
                content_type="application/json",
                sha256="a" * 64,
                checksum_verification_status="not_checked",
            ),
        ),
        attribution_required=True,
        redistribution_status="derived_only",
        snapshot_content_sha256="b" * 64,
    )


def _record(record_type: str, values: object, pointer: str) -> StagingRecord:
    locator = RawLocator(
        source_id="mtgjson",
        source_snapshot_id="snapshot-1",
        raw_object_id="response.json",
        raw_object_path="objects/response.json",
        location=JsonPointerLocator(pointer=pointer),
    )
    return StagingRecord(
        staging_record_id=f"staging-{record_type}",
        source_id="mtgjson",
        record_type=record_type,
        raw_locator=locator,
        original_source_values=values,
        status="OBSERVED",
    )


def _card_values() -> dict[str, object]:
    return {
        "uuid": PRINTING_ID,
        "name": "Fixture Commander",
        "setCode": "TST",
        "number": "1",
        "releaseDate": "2026-08-10",
        "layout": "normal",
        "manaValue": 1,
        "colors": [],
        "colorIdentity": [],
        "types": ["Creature"],
        "legalities": {"commander": "Legal"},
        "identifiers": {
            "scryfallOracleId": ORACLE_ID,
            "scryfallId": PRINTING_ID,
        },
    }


def test_mtgjson_canonicalization_emits_deterministic_evaluations() -> None:
    card_values = _card_values()
    deck_values = {
        "name": "Fixture Deck",
        "fileName": "fixture-deck",
        "code": "TST",
        "type": "commander",
        "commander": [{"name": "Fixture Commander", "count": 1}],
        "mainBoard": [{"name": "Fixture Commander", "count": 1}],
        "sideBoard": [],
    }

    result = canonicalize_staging(
        (
            _record("card", card_values, "/cards/0"),
            _record("card_face", card_values, "/cards/0/face"),
            _record("printing", card_values, "/cards/0/printing"),
            _record("deck_product", deck_values, "/decks/0"),
        ),
        source_manifest=_manifest(),
    )

    decks = [item for item in result.records if item.record_type == "canonical_deck"]
    assert len(decks) == 1
    evaluations = {
        item.record_type: item
        for item in result.records
        if item.record_type in {"deck_legality_evaluation", "deck_quality_evaluation"}
    }
    assert evaluations["deck_legality_evaluation"].payload["legal_status"] == "unknown"
    assert evaluations["deck_legality_evaluation"].payload["finding_codes"] == (
        "legality.ruleset_unresolved",
    )
    assert evaluations["deck_quality_evaluation"].payload["quality_status"] == "accepted"
    assert evaluations["deck_legality_evaluation"].observed_at == NOW
    assert evaluations["deck_quality_evaluation"].observed_at == NOW
    for evaluation in evaluations.values():
        assert CanonicalRecord.model_validate(evaluation.model_dump(mode="json")) == evaluation


def test_mtgjson_canonicalization_selects_effective_ruleset_input() -> None:
    card_values = _card_values()
    deck_values = {
        "name": "Fixture Deck",
        "fileName": "fixture-deck",
        "code": "TST",
        "type": "commander",
        "commander": [{"name": "Fixture Commander", "count": 1}],
        "mainBoard": [{"name": "Fixture Commander", "count": 1}],
        "sideBoard": [],
    }
    ruleset_payload = {
        "schema_version": "ruleset.v1",
        "ruleset_version": "commander-historical",
        "format": "commander",
        "effective_from": "2026-01-01",
        "required_total_cards": 2,
        "default_copy_limit": 2,
        "banned_oracle_ids": [],
        "banned_as_companion_oracle_ids": [],
        "copy_limit_overrides": {},
        "unlimited_copy_oracle_ids": [],
        "command_zone_policy": {
            "min_cards": 1,
            "max_cards": 2,
            "validator_version": "command-zone-v1",
        },
        "source_references": ["https://fixture.invalid/ruleset"],
        "sha256": "c" * 64,
    }

    result = canonicalize_staging(
        (
            _record("card", card_values, "/cards/0"),
            _record("card_face", card_values, "/cards/0/face"),
            _record("printing", card_values, "/cards/0/printing"),
            _record("deck_product", deck_values, "/decks/0"),
        ),
        source_manifest=_manifest(),
        ruleset_inputs=(
            RulesetSnapshotInput(
                snapshot=RulesetSnapshot.model_validate(ruleset_payload),
                path="rulesets/commander-historical.json",
                input_sha256="d" * 64,
            ),
        ),
    )

    legality = next(
        item for item in result.records if item.record_type == "deck_legality_evaluation"
    )
    assert legality.payload["ruleset_version"] == "commander-historical"
    assert legality.payload["ruleset_snapshot_sha256"] == "c" * 64
    assert legality.payload["legal_status"] == "unknown"
    assert legality.payload["finding_codes"] == ("legality.command_zone_unverified",)


def test_mtgjson_deck_release_date_controls_historical_ruleset_selection() -> None:
    card_values = _card_values()
    deck_values = {
        "name": "Fixture Deck",
        "fileName": "fixture-deck",
        "code": "TST",
        "releaseDate": "2025-01-01",
        "type": "commander",
        "commander": [{"name": "Fixture Commander", "count": 1}],
        "mainBoard": [{"name": "Fixture Commander", "count": 1}],
        "sideBoard": [],
    }
    old = RulesetSnapshot.model_validate(
        {
            "schema_version": "ruleset.v1",
            "ruleset_version": "commander-historical",
            "format": "commander",
            "effective_from": "2025-01-01",
            "required_total_cards": 2,
            "default_copy_limit": 1,
            "banned_oracle_ids": [],
            "banned_as_companion_oracle_ids": [],
            "copy_limit_overrides": {},
            "unlimited_copy_oracle_ids": [],
            "command_zone_policy": {
                "min_cards": 1,
                "max_cards": 2,
                "validator_version": "command-zone-v1",
            },
            "source_references": ["https://fixture.invalid/ruleset-old"],
            "sha256": "c" * 64,
        }
    )
    current = old.model_copy(
        update={
            "ruleset_version": "commander-current",
            "effective_from": "2026-01-01",
            "source_references": ("https://fixture.invalid/ruleset-current",),
            "sha256": "d" * 64,
        }
    )

    result = canonicalize_staging(
        (
            _record("card", card_values, "/cards/0"),
            _record("card_face", card_values, "/cards/0/face"),
            _record("printing", card_values, "/cards/0/printing"),
            _record("deck_product", deck_values, "/decks/0"),
        ),
        source_manifest=_manifest(),
        ruleset_inputs=(
            RulesetSnapshotInput(snapshot=old, path="rulesets/old.json", input_sha256="e" * 64),
            RulesetSnapshotInput(
                snapshot=current,
                path="rulesets/current.json",
                input_sha256="f" * 64,
            ),
        ),
    )

    legality = next(
        item for item in result.records if item.record_type == "deck_legality_evaluation"
    )
    assert legality.payload["ruleset_version"] == "commander-historical"


def test_mtgjson_canonicalization_does_not_use_future_ruleset_as_current_fallback() -> None:
    card_values = _card_values()
    deck_values = {
        "name": "Fixture Deck",
        "fileName": "fixture-deck",
        "code": "TST",
        "type": "commander",
        "commander": [{"name": "Fixture Commander", "count": 1}],
        "mainBoard": [{"name": "Fixture Commander", "count": 1}],
        "sideBoard": [],
    }
    future = RulesetSnapshot.model_validate(
        {
            "schema_version": "ruleset.v1",
            "ruleset_version": "commander-future",
            "format": "commander",
            "effective_from": "2027-01-01",
            "required_total_cards": 2,
            "default_copy_limit": 1,
            "banned_oracle_ids": [],
            "banned_as_companion_oracle_ids": [],
            "copy_limit_overrides": {},
            "unlimited_copy_oracle_ids": [],
            "command_zone_policy": {
                "min_cards": 1,
                "max_cards": 2,
                "validator_version": "command-zone-v1",
            },
            "source_references": ["https://fixture.invalid/ruleset"],
            "sha256": "e" * 64,
        }
    )

    result = canonicalize_staging(
        (
            _record("card", card_values, "/cards/0"),
            _record("card_face", card_values, "/cards/0/face"),
            _record("printing", card_values, "/cards/0/printing"),
            _record("deck_product", deck_values, "/decks/0"),
        ),
        source_manifest=_manifest(),
        ruleset_inputs=(
            RulesetSnapshotInput(
                snapshot=future,
                path="rulesets/commander-future.json",
                input_sha256="f" * 64,
            ),
        ),
    )

    legality = next(
        item for item in result.records if item.record_type == "deck_legality_evaluation"
    )
    assert legality.payload["ruleset_version"] == "unknown"
    assert legality.payload["finding_codes"] == ("legality.ruleset_unresolved",)
