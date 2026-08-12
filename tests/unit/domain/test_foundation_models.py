from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

import commander_ai.domain.decks as decks_module
from commander_ai.domain.cards import (
    CardFace,
    CardIdentity,
    CardResolution,
    CardResolutionCandidate,
    Printing,
)
from commander_ai.domain.combos import Combo, ComboCard
from commander_ai.domain.decks import (
    CanonicalDeck,
    CardQuantity,
    CardZone,
    CommandZoneEntry,
    CommandZoneRelationship,
    compute_structural_fingerprint,
)
from commander_ai.domain.evaluations import DeckLegalityEvaluation, DeckQualityEvaluation
from commander_ai.domain.observations import EventDeckObservation, ParticipantReference, PodEntry
from commander_ai.domain.provenance import (
    DatasetInputReference,
    DatasetManifest,
    DatasetOutputReference,
    NormalizedSnapshotManifest,
    ProvenanceReference,
    QuarantineReference,
    RawObjectReference,
    SourceSnapshotManifest,
    SourceSnapshotRequest,
    detached_manifest_sha256,
)

ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
ORACLE_C = "33333333-3333-4333-8333-333333333333"
PRINTING_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def provenance(
    source_id: str,
    source_object_id: str,
    *,
    source_snapshot_id: str | None = None,
) -> ProvenanceReference:
    return ProvenanceReference(
        source_id=source_id,
        source_snapshot_id=source_snapshot_id or f"{source_id}-snapshot",
        source_object_id=source_object_id,
        raw_sha256="0" * 64,
        retrieved_at=datetime(2026, 8, 10, tzinfo=UTC),
        adapter_version="fixture-v1",
        mapper_version="fixture-v1",
        approval_status="APPROVED_REDISTRIBUTION",
    )


def card_zones() -> tuple[CardZone, ...]:
    return (
        CardZone(
            zone="mainboard",
            cards=(CardQuantity(oracle_id=ORACLE_C, quantity=1, printing_id=PRINTING_A),),
        ),
    )


def make_deck(
    command_zone: tuple[CommandZoneEntry, ...],
    *,
    source_id: str = "fixture",
    source_object_id: str = "deck-1",
) -> CanonicalDeck:
    return CanonicalDeck(
        command_zone=command_zone,
        card_zones=card_zones(),
        provenance=(provenance(source_id, source_object_id),),
    )


def test_card_identity_printing_and_face_are_distinct_domain_values() -> None:
    card = CardIdentity(oracle_id=ORACLE_A, name="Fixture Card")
    printing = Printing(
        printing_id=PRINTING_A,
        oracle_id=ORACLE_A,
        card_snapshot_id="cards-fixture",
        set_code="FIX",
        collector_number="1",
        released_at="2026-08-10",
        face_ids=("face-a",),
        provenance=(provenance("fixture", "printing-a"),),
    )
    face = CardFace(
        face_id="face-a",
        oracle_id=ORACLE_A,
        face_index=0,
        name="Fixture Card",
        provenance=(provenance("fixture", "face-a"),),
    )

    assert card.oracle_id == printing.oracle_id == face.oracle_id
    assert card.oracle_id != printing.printing_id
    assert face.face_id != printing.printing_id


def test_task1_optional_fields_dump_as_explicit_nulls() -> None:
    face = CardFace(
        face_id="face-null",
        oracle_id=ORACLE_A,
        face_index=0,
        name="Fixture Card",
        mana_value=None,
        provenance=(provenance("fixture", "face-null"),),
    )
    printing = Printing(
        printing_id=PRINTING_A,
        oracle_id=ORACLE_A,
        card_snapshot_id="cards-fixture",
        set_code="FIX",
        collector_number="1",
        released_at="2026-08-10",
        language=None,
        rarity=None,
        is_foil=None,
        is_promo=None,
        face_ids=("face-null",),
        provenance=(provenance("fixture", "printing-null"),),
    )
    command_entry = CommandZoneEntry(oracle_id=ORACLE_A, quantity=1)
    reference = provenance("fixture", "metadata-null").model_copy(
        update={
            "retrieved_at": None,
            "adapter_version": None,
            "mapper_version": None,
            "approval_status": None,
        }
    )

    assert face.model_dump(mode="json")["mana_value"] is None
    assert printing.model_dump(mode="json")["language"] is None
    assert printing.model_dump(mode="json")["rarity"] is None
    assert printing.model_dump(mode="json")["is_foil"] is None
    assert printing.model_dump(mode="json")["is_promo"] is None
    assert command_entry.model_dump(mode="json")["source_declared_role"] is None
    assert reference.model_dump(mode="json")["retrieved_at"] is None
    assert reference.model_dump(mode="json")["adapter_version"] is None
    assert reference.model_dump(mode="json")["mapper_version"] is None
    assert reference.model_dump(mode="json")["approval_status"] is None


def test_persisted_card_collections_reject_empty_values() -> None:
    source = provenance("fixture", "empty-collections")

    with pytest.raises(ValidationError):
        CardFace(
            face_id="face-empty",
            oracle_id=ORACLE_A,
            face_index=0,
            name="Fixture Card",
            provenance=(),
        )

    with pytest.raises(ValidationError):
        Printing(
            printing_id=PRINTING_A,
            oracle_id=ORACLE_A,
            card_snapshot_id="cards-fixture",
            set_code="FIX",
            collector_number="1",
            released_at="2026-08-10",
            face_ids=(),
            provenance=(source,),
        )

    with pytest.raises(ValidationError):
        Printing(
            printing_id=PRINTING_A,
            oracle_id=ORACLE_A,
            card_snapshot_id="cards-fixture",
            set_code="FIX",
            collector_number="1",
            released_at="2026-08-10",
            face_ids=("face-empty",),
            provenance=(),
        )


def test_persisted_uuid_fields_reject_non_uuid_values() -> None:
    with pytest.raises(ValidationError):
        CardFace(
            face_id="face-invalid-uuid",
            oracle_id="not-a-uuid",
            face_index=0,
            name="Fixture Card",
            provenance=(provenance("fixture", "face-invalid-uuid"),),
        )

    with pytest.raises(ValidationError):
        Printing(
            printing_id="not-a-uuid",
            oracle_id=ORACLE_A,
            card_snapshot_id="cards-fixture",
            set_code="FIX",
            collector_number="1",
            released_at="2026-08-10",
            face_ids=("face-a",),
            provenance=(provenance("fixture", "printing-invalid-uuid"),),
        )

    with pytest.raises(ValidationError):
        Printing(
            printing_id=PRINTING_A,
            oracle_id="not-a-uuid",
            card_snapshot_id="cards-fixture",
            set_code="FIX",
            collector_number="1",
            released_at="2026-08-10",
            face_ids=("face-a",),
            provenance=(provenance("fixture", "printing-invalid-oracle"),),
        )

    with pytest.raises(ValidationError):
        CardResolutionCandidate(oracle_id="not-a-uuid")

    with pytest.raises(ValidationError):
        CardResolution(
            resolution_id="resolution-invalid-uuid",
            source_id="fixture",
            source_snapshot_id="snapshot-1",
            source_object_id="object-1",
            original_value="Fixture Card",
            raw_locator="cards[0].name",
            method="exact_name",
            status="resolved",
            canonical_oracle_id="not-a-uuid",
            resolver_version="resolver-v1",
            normalization_policy_version="name-v1",
            alias_catalog_version="aliases-v1",
            alias_catalog_sha256="1" * 64,
            card_catalog_snapshot_id="cards-1",
        )

    with pytest.raises(ValidationError):
        Combo(
            combo_id="combo-invalid-uuid",
            required_cards=("not-a-uuid",),
            requirements=("Card is available.",),
            results=("Generate mana.",),
            provenance=(provenance("fixture", "combo-invalid-uuid"),),
        )

    with pytest.raises(ValidationError):
        CommandZoneRelationship(kind="partner", card_ids=("not-a-uuid", ORACLE_B))


@pytest.mark.parametrize(
    "invalid_uuid",
    (
        "11111111111141118111111111111111",
        "{11111111-1111-4111-8111-111111111111}",
        "urn:uuid:11111111-1111-4111-8111-111111111111",
    ),
)
def test_uuid_fields_reject_non_schema_uuid_forms(invalid_uuid: str) -> None:
    with pytest.raises(ValidationError):
        CardFace(
            face_id="face-non-schema-uuid",
            oracle_id=invalid_uuid,
            face_index=0,
            name="Fixture Card",
            provenance=(provenance("fixture", "face-non-schema-uuid"),),
        )


def test_persisted_card_collections_enforce_schema_unique_and_max_items() -> None:
    face_values = {
        "face_id": "face-duplicate-values",
        "oracle_id": ORACLE_A,
        "face_index": 0,
        "name": "Fixture Card",
        "provenance": (provenance("fixture", "face-duplicate-values"),),
    }
    with pytest.raises(ValidationError):
        CardFace.model_validate({**face_values, "colors": ("U", "U")})
    with pytest.raises(ValidationError):
        CardFace.model_validate({**face_values, "colors": ("W", "U", "B", "R", "G", "W")})
    with pytest.raises(ValidationError):
        CardFace.model_validate({**face_values, "types": ("Artifact", "Artifact")})
    with pytest.raises(ValidationError):
        CardFace.model_validate({**face_values, "types": ("",)})

    printing_values = {
        "printing_id": PRINTING_A,
        "oracle_id": ORACLE_A,
        "card_snapshot_id": "cards-fixture",
        "set_code": "FIX",
        "collector_number": "1",
        "released_at": "2026-08-10",
        "provenance": (provenance("fixture", "printing-duplicate-values"),),
    }
    with pytest.raises(ValidationError):
        Printing.model_validate({**printing_values, "face_ids": ("face-a", "face-a")})
    with pytest.raises(ValidationError):
        Printing.model_validate({**printing_values, "face_ids": ("",)})

    candidate = CardResolutionCandidate(oracle_id=ORACLE_A)
    resolution_values = {
        "resolution_id": "resolution-duplicate-candidates",
        "source_id": "fixture",
        "source_snapshot_id": "snapshot-1",
        "source_object_id": "object-1",
        "original_value": "Fixture Card",
        "raw_locator": "cards[0].name",
        "method": "exact_name",
        "status": "resolved",
        "candidates": (candidate, candidate),
        "resolver_version": "resolver-v1",
        "normalization_policy_version": "name-v1",
        "alias_catalog_version": "aliases-v1",
        "alias_catalog_sha256": "1" * 64,
        "card_catalog_snapshot_id": "cards-1",
    }
    with pytest.raises(ValidationError):
        CardResolution.model_validate(resolution_values)


def test_persisted_number_fields_reject_non_finite_values() -> None:
    face_values = {
        "face_id": "face-non-finite-number",
        "oracle_id": ORACLE_A,
        "face_index": 0,
        "name": "Fixture Card",
        "provenance": (provenance("fixture", "face-non-finite-number"),),
    }
    for value in (math.nan, math.inf):
        with pytest.raises(ValidationError):
            CardFace.model_validate({**face_values, "mana_value": value})

    with pytest.raises(ValidationError):
        DeckQualityEvaluation(
            canonical_deck_id="d" * 64,
            evaluated_at=datetime(2026, 8, 10, tzinfo=UTC),
            quality_status="accepted",
            metrics={"win_rate": math.nan},
        )

    for value in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValidationError):
            PodEntry(
                pod_id="pod-non-finite-points",
                event_id="event-1",
                round_number=1,
                seat=1,
                canonical_deck_id="d" * 64,
                result="win",
                points=value,
                provenance=(provenance("fixture", "pod-non-finite-points"),),
            )


@pytest.mark.parametrize(
    "field_name",
    ("required_cards", "optional_cards", "requirements", "results"),
)
def test_combo_collections_reject_duplicate_schema_items(field_name: str) -> None:
    values: dict[str, object] = {
        "combo_id": "combo-duplicate-values",
        "required_cards": (ORACLE_A,),
        "optional_cards": (ORACLE_B,),
        "requirements": ("Card is available.",),
        "results": ("Generate mana.",),
        "provenance": (provenance("fixture", "combo-duplicate-values"),),
    }
    values[field_name] = (
        (ORACLE_A, ORACLE_A)
        if field_name.endswith("cards")
        else (
            "Card is available.",
            "Card is available.",
        )
    )

    with pytest.raises(ValidationError):
        Combo.model_validate(values)


def test_command_zone_relationship_rejects_duplicate_card_ids() -> None:
    with pytest.raises(ValidationError):
        CommandZoneRelationship(kind="partner", card_ids=(ORACLE_A, ORACLE_A))


def test_evaluations_enforce_namespaced_unique_finding_codes() -> None:
    legality_values = {
        "canonical_deck_id": "d" * 64,
        "ruleset_version": "commander-2026-01",
        "evaluated_at": datetime(2026, 8, 10, tzinfo=UTC),
        "legal_status": "illegal",
    }
    with pytest.raises(ValidationError):
        DeckLegalityEvaluation.model_validate(
            {**legality_values, "finding_codes": ("quality.bad",)}
        )
    with pytest.raises(ValidationError):
        DeckLegalityEvaluation.model_validate(
            {**legality_values, "finding_codes": ("legality.bad", "legality.bad")}
        )

    quality_values = {
        "canonical_deck_id": "d" * 64,
        "evaluated_at": datetime(2026, 8, 10, tzinfo=UTC),
        "quality_status": "quarantined",
    }
    with pytest.raises(ValidationError):
        DeckQualityEvaluation.model_validate({**quality_values, "finding_codes": ("legality.bad",)})
    with pytest.raises(ValidationError):
        DeckQualityEvaluation.model_validate(
            {**quality_values, "finding_codes": ("quality.bad", "quality.bad")}
        )


def test_quality_evaluation_requires_quality_quarantine_reason_codes() -> None:
    with pytest.raises(ValidationError):
        DeckQualityEvaluation(
            canonical_deck_id="d" * 64,
            evaluated_at=datetime(2026, 8, 10, tzinfo=UTC),
            quality_status="quarantined",
            quarantine_references=(
                QuarantineReference(
                    quarantine_id="quarantine-1",
                    reason_code="integrity.bad",
                ),
            ),
        )


@pytest.mark.parametrize(
    "endpoint",
    (
        "not a uri",
        "/relative/path",
        "",
        "https://example.invalid/a b",
        "https://example.invalid/a\\b",
        "https://example.invalid/a|b",
    ),
)
def test_source_snapshot_request_rejects_invalid_uri(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        SourceSnapshotRequest(
            request_id="request-invalid-uri",
            sanitized_method="GET",
            sanitized_endpoint=endpoint,
            format="json",
        )


def test_persisted_request_parameters_reject_non_json_values() -> None:
    with pytest.raises(ValidationError):
        SourceSnapshotRequest(
            request_id="request-non-json-value",
            sanitized_method="GET",
            sanitized_endpoint="https://example.invalid/cards",
            format="json",
            sanitized_parameters={"unsupported": object()},
        )


def test_persisted_evaluation_and_observation_timestamps_require_timezone() -> None:
    with pytest.raises(ValidationError):
        DeckLegalityEvaluation(
            canonical_deck_id="d" * 64,
            ruleset_version="commander-2026-01",
            evaluated_at=datetime(2026, 8, 10),
            legal_status="legal",
        )
    with pytest.raises(ValidationError):
        DeckQualityEvaluation(
            canonical_deck_id="d" * 64,
            evaluated_at=datetime(2026, 8, 10),
            quality_status="accepted",
        )
    with pytest.raises(ValidationError):
        EventDeckObservation(
            observation_id="observation-naive-time",
            event_id="event-1",
            canonical_deck_id="d" * 64,
            observed_at=datetime(2026, 8, 10),
            participant_reference=None,
            participant_reference_scope="none",
            aggregate_wins=0,
            aggregate_losses=0,
            aggregate_draws=0,
            source_result_semantics="fixture standings",
            provenance=(provenance("fixture", "event-1"),),
        )


def test_canonical_deck_accepts_one_commander_partner_pair_and_background_relationship() -> None:
    one_commander = make_deck(
        (CommandZoneEntry(oracle_id=ORACLE_A, quantity=1, source_declared_role="commander"),)
    )
    partner_pair = make_deck(
        (
            CommandZoneEntry(oracle_id=ORACLE_A, quantity=1, source_declared_role="partner"),
            CommandZoneEntry(oracle_id=ORACLE_B, quantity=1, source_declared_role="partner"),
        ),
        source_object_id="deck-2",
    )
    background_relationship = make_deck(
        (
            CommandZoneEntry(oracle_id=ORACLE_A, quantity=1, source_declared_role="commander"),
            CommandZoneEntry(oracle_id=ORACLE_B, quantity=1, source_declared_role="background"),
        ),
        source_object_id="deck-3",
    ).model_copy(
        update={
            "command_zone_relationships": (
                CommandZoneRelationship(
                    kind="background",
                    card_ids=(ORACLE_A, ORACLE_B),
                ),
            )
        }
    )

    assert len(one_commander.command_zone) == 1
    assert len(partner_pair.command_zone) == 2
    assert len(background_relationship.command_zone) == 2
    assert background_relationship.command_zone_relationships[0].kind == "background"


def test_canonical_deck_requires_non_empty_command_and_card_zones() -> None:
    with pytest.raises(ValidationError):
        CanonicalDeck(
            command_zone=(),
            card_zones=card_zones(),
            provenance=(provenance("fixture", "empty-command"),),
        )

    with pytest.raises(ValidationError):
        CanonicalDeck(
            command_zone=(CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),),
            card_zones=(),
            provenance=(provenance("fixture", "empty-zones"),),
        )


def test_deck_identity_ignores_source_and_observation_context() -> None:
    first = make_deck((CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),))
    second = make_deck(
        (CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),),
        source_id="other-source",
        source_object_id="different-deck",
    )

    assert first.canonical_deck_id == second.canonical_deck_id
    assert first.structural_fingerprint == second.structural_fingerprint

    first_observation = EventDeckObservation(
        observation_id="observation-1",
        event_id="event-1",
        canonical_deck_id=first.canonical_deck_id,
        observed_at=datetime(2026, 8, 10, tzinfo=UTC),
        participant_reference=ParticipantReference(
            reference_id="participant-1",
            scope="event",
            event_id="event-1",
        ),
        participant_reference_scope="event",
        final_placement=1,
        aggregate_wins=3,
        aggregate_losses=0,
        aggregate_draws=0,
        source_result_semantics="fixture standings",
        provenance=(provenance("fixture", "event-1"),),
    )
    second_observation = first_observation.model_copy(
        update={
            "observation_id": "observation-2",
            "event_id": "event-2",
            "observed_at": datetime(2026, 8, 11, tzinfo=UTC),
            "participant_reference": ParticipantReference(
                reference_id="participant-2",
                scope="event",
                event_id="event-2",
            ),
            "provenance": (provenance("other-source", "event-2"),),
        }
    )
    legality = DeckLegalityEvaluation(
        canonical_deck_id=first.canonical_deck_id,
        ruleset_version="commander-2026-01",
        evaluated_at=first_observation.observed_at,
        legal_status="legal",
        finding_codes=(),
    )
    other_legality = legality.model_copy(
        update={
            "ruleset_version": "commander-2027-01",
            "legal_status": "illegal",
        }
    )
    quality = DeckQualityEvaluation(
        canonical_deck_id=first.canonical_deck_id,
        evaluated_at=first_observation.observed_at,
        quality_status="accepted",
        finding_codes=(),
    )

    assert second_observation.canonical_deck_id == first_observation.canonical_deck_id
    assert other_legality.canonical_deck_id == legality.canonical_deck_id
    assert quality.canonical_deck_id == first.canonical_deck_id


def test_structural_fingerprint_uses_the_shared_canonical_json_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[object] = []

    def fake_canonical_json_bytes(value: object) -> bytes:
        calls.append(value)
        return b"canonical-deck-bytes"

    monkeypatch.setattr(
        decks_module,
        "canonical_json_bytes",
        fake_canonical_json_bytes,
        raising=False,
    )

    fingerprint = compute_structural_fingerprint(
        (CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),),
        card_zones(),
    )

    assert calls
    assert fingerprint == hashlib.sha256(b"canonical-deck-bytes").hexdigest()


def test_event_observations_repeat_decks_while_pod_entries_keep_round_and_seat() -> None:
    observation = EventDeckObservation(
        observation_id="observation-1",
        event_id="event-1",
        canonical_deck_id="d" * 64,
        observed_at=datetime(2026, 8, 10, tzinfo=UTC),
        participant_reference=None,
        participant_reference_scope="none",
        final_placement=2,
        aggregate_wins=2,
        aggregate_losses=1,
        aggregate_draws=0,
        source_result_semantics="final standings",
        provenance=(provenance("fixture", "event-1"),),
    )
    pod_entry = PodEntry(
        pod_id="pod-1",
        event_id="event-1",
        round_number=3,
        seat=2,
        canonical_deck_id=observation.canonical_deck_id,
        result="win",
        points=3,
        placement=1,
        provenance=(provenance("fixture", "pod-1"),),
    )

    assert observation.canonical_deck_id == pod_entry.canonical_deck_id
    assert (pod_entry.round_number, pod_entry.seat) == (3, 2)
    pod_payload = pod_entry.model_dump(mode="json")
    assert "schema_version" not in pod_payload
    with pytest.raises(ValidationError):
        PodEntry.model_validate({**pod_payload, "schema_version": "pod.v1"})


def test_resolution_and_combo_models_keep_identity_and_feature_facts_separate() -> None:
    resolution = CardResolution(
        resolution_id="resolution-1",
        source_id="fixture",
        source_snapshot_id="snapshot-1",
        source_object_id="object-1",
        original_value="Fixture Card",
        raw_locator="cards[0].name",
        method="exact_name",
        status="resolved",
        candidates=(CardResolutionCandidate(oracle_id=ORACLE_A),),
        canonical_oracle_id=ORACLE_A,
        resolver_version="resolver-v1",
        normalization_policy_version="name-v1",
        alias_catalog_version="aliases-v1",
        alias_catalog_sha256="1" * 64,
        card_catalog_snapshot_id="cards-1",
        finding_code="resolution.exact_name",
    )
    combo_card = ComboCard(
        combo_id="combo-1",
        oracle_id=ORACLE_A,
        role="required",
        quantity=1,
        provenance=(provenance("fixture", "combo-1"),),
    )
    combo = Combo(
        combo_id="combo-1",
        required_cards=(ORACLE_A,),
        requirements=("Card is available.",),
        results=("Generate mana.",),
        provenance=(provenance("fixture", "combo-1"),),
    )

    assert resolution.canonical_oracle_id == combo.required_cards[0]
    assert resolution.finding_code == "resolution.exact_name"
    assert combo_card.role == "required"
    assert "legal_status" not in combo.model_dump()


def test_manifest_models_bind_authoritative_requests_objects_and_digest_domains() -> None:
    request = SourceSnapshotRequest(
        request_id="request-1",
        sanitized_method="GET",
        sanitized_endpoint="https://example.invalid/cards",
        format="json",
        sanitized_parameters={"page": 1},
    )
    raw_object = RawObjectReference(
        raw_object_id="object-1",
        request_id="request-1",
        retrieved_at=datetime(2026, 8, 10, tzinfo=UTC),
        path="objects/object-1.json",
        bytes=1,
        content_type="application/json",
        sha256="2" * 64,
        checksum_verification_status="not_provided",
    )
    source_manifest = SourceSnapshotManifest(
        source_id="fixture",
        source_snapshot_id="snapshot-1",
        status="COMPLETE",
        approval_status="APPROVED_REDISTRIBUTION",
        adapter_version="adapter-v1",
        started_at=datetime(2026, 8, 10, tzinfo=UTC),
        completed_at=datetime(2026, 8, 10, 0, 1, tzinfo=UTC),
        usage_status="APPROVED_REDISTRIBUTION",
        requests=(request,),
        objects=(raw_object,),
        attribution_required=False,
        redistribution_status="approved",
        snapshot_content_sha256="3" * 64,
        request_parameters_redacted={
            "request_ids": ["request-1"],
            "methods": ["GET"],
            "endpoints": ["https://example.invalid/cards"],
            "formats": ["json"],
            "api_versions": [],
            "parameter_keys": ["page"],
        },
    )
    normalized_manifest = NormalizedSnapshotManifest(
        normalized_snapshot_id="normalized-1",
        producing_run_id="run-1",
        input_source_snapshot_manifest_id=source_manifest.source_snapshot_id,
        input_source_snapshot_manifest_sha256=detached_manifest_sha256(
            source_manifest.model_dump(mode="json")
        ),
        source_id="fixture",
        status="COMPLETE",
        normalized_schema_version="records-v1",
        mapper_version="mapper-v1",
        transform_version="transform-v1",
        normalized_artifact_path="normalized/records.parquet",
        normalized_artifact_sha256="5" * 64,
        audit_artifact_path="audit/findings.parquet",
        audit_artifact_sha256="6" * 64,
        counts={"normalized_records": 1},
        created_at=datetime(2026, 8, 10, 0, 2, tzinfo=UTC),
        started_at=datetime(2026, 8, 10, 0, 1, tzinfo=UTC),
        completed_at=datetime(2026, 8, 10, 0, 2, tzinfo=UTC),
        normalized_content_sha256="7" * 64,
        provenance=(provenance("fixture", "object-1", source_snapshot_id="snapshot-1"),),
    )
    dataset_manifest = DatasetManifest(
        dataset_id="dataset-1",
        created_at=datetime(2026, 8, 10, tzinfo=UTC),
        builder_version="builder-v1",
        code_commit="a" * 40,
        dependency_lock_hash="9" * 64,
        input_manifests=(
            DatasetInputReference(
                kind="normalized_snapshot_manifest",
                id=normalized_manifest.normalized_snapshot_id,
                sha256=detached_manifest_sha256(normalized_manifest.model_dump(mode="json")),
            ),
        ),
        schema_versions=("canonical-deck.v1",),
        transform_versions=("transform-v1",),
        policy_versions=("split-v1",),
        counts={"train": 1},
        outputs=(
            DatasetOutputReference(
                name="train",
                path="dataset/train.parquet",
                sha256="a" * 64,
                rows=1,
                bytes=256,
            ),
        ),
        dataset_content_sha256="b" * 64,
        manifest_sha256="c" * 64,
    )

    assert source_manifest.requests[0].request_id == "request-1"
    assert source_manifest.objects[0].raw_object_id == "object-1"
    assert "manifest_sha256" not in source_manifest.model_dump(mode="json")
    assert "manifest_sha256" not in normalized_manifest.model_dump(mode="json")
    assert dataset_manifest.input_manifests[0].id == "normalized-1"
    assert dataset_manifest.outputs[0].bytes == 256


@pytest.mark.parametrize(
    "invalid_path",
    ("C:/data/file", "\\\\server\\share", "/root/file", "a/../file"),
)
def test_domain_rejects_non_portable_persisted_paths(invalid_path: str) -> None:
    with pytest.raises(ValidationError):
        RawObjectReference(
            raw_object_id="object-1",
            request_id="request-1",
            retrieved_at=datetime(2026, 8, 10, tzinfo=UTC),
            path=invalid_path,
            bytes=1,
            sha256="2" * 64,
            checksum_verification_status="not_provided",
        )
    with pytest.raises(ValidationError):
        QuarantineReference(
            quarantine_id="quarantine-1",
            reason_code="integrity.invalid_path",
            path=invalid_path,
        )
    with pytest.raises(ValidationError):
        DatasetInputReference(
            kind="normalized_snapshot_manifest",
            id="normalized-1",
            path=invalid_path,
            sha256="3" * 64,
        )
    with pytest.raises(ValidationError):
        DatasetOutputReference(
            name="train",
            path=invalid_path,
            sha256="4" * 64,
            rows=1,
        )


def test_nested_persisted_values_are_deeply_immutable_and_serializable() -> None:
    request = SourceSnapshotRequest(
        request_id="request-1",
        sanitized_method="GET",
        sanitized_endpoint="https://example.invalid/cards",
        format="json",
        sanitized_parameters={"nested": {"values": [1, 2]}},
    )

    with pytest.raises(TypeError):
        request.sanitized_parameters["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        request.sanitized_parameters["nested"]["new"] = "value"  # type: ignore[index]
    with pytest.raises(TypeError):
        request.sanitized_parameters["nested"]["values"] += (3,)  # type: ignore[index]

    assert request.model_dump(mode="json")["sanitized_parameters"] == {
        "nested": {"values": [1, 2]},
    }
    assert json.loads(request.model_dump_json())["sanitized_parameters"] == {
        "nested": {"values": [1, 2]},
    }
    json.dumps(request.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def test_model_copy_update_revalidates_and_deep_freezes_nested_values() -> None:
    request = SourceSnapshotRequest(
        request_id="request-1",
        sanitized_method="GET",
        sanitized_endpoint="https://example.invalid/cards",
        format="json",
        sanitized_parameters={"nested": {"values": [1, 2]}},
    )
    update = {"nested": {"values": [3, 4]}}
    copied = request.model_copy(update={"sanitized_parameters": update})
    update["nested"]["values"].append(5)

    assert request.sanitized_parameters["nested"]["values"] == (1, 2)
    assert copied.sanitized_parameters["nested"]["values"] == (3, 4)
    for model in (request, copied):
        with pytest.raises(TypeError):
            model.sanitized_parameters["nested"]["values"][0] = 9  # type: ignore[index]
        json.dumps(model.model_dump(mode="json"), ensure_ascii=False, sort_keys=True)


def test_structural_fingerprint_rejects_duplicate_identity_rows_before_persistence() -> None:
    with pytest.raises(ValueError, match="card identity may occur only once"):
        compute_structural_fingerprint(
            ({"oracle_id": ORACLE_A, "quantity": 1},),
            (
                {
                    "zone": "mainboard",
                    "cards": [
                        {"oracle_id": ORACLE_C, "quantity": 1},
                        {"oracle_id": ORACLE_C, "quantity": 2},
                    ],
                },
            ),
        )


def test_structural_fingerprint_rejects_duplicate_zone_names_in_any_order() -> None:
    zones = (
        {
            "zone": "mainboard",
            "cards": [{"oracle_id": ORACLE_C, "quantity": 1}],
        },
        {
            "zone": "mainboard",
            "cards": [{"oracle_id": ORACLE_B, "quantity": 1}],
        },
    )

    for ordered_zones in (zones, tuple(reversed(zones))):
        with pytest.raises(ValueError, match="zone names must be unique"):
            compute_structural_fingerprint(
                ({"oracle_id": ORACLE_A, "quantity": 1},),
                ordered_zones,
            )


def test_canonical_deck_rejects_duplicate_zone_names() -> None:
    zones = (
        CardZone(
            zone="mainboard",
            cards=(CardQuantity(oracle_id=ORACLE_B, quantity=1),),
        ),
        CardZone(
            zone="mainboard",
            cards=(CardQuantity(oracle_id=ORACLE_C, quantity=1),),
        ),
    )

    with pytest.raises(ValidationError, match="zone names must be unique"):
        CanonicalDeck(
            command_zone=(CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),),
            card_zones=zones,
            provenance=(provenance("fixture", "duplicate-zones"),),
        )


def test_structural_decks_reject_duplicate_card_identity_rows() -> None:
    duplicate_cards = (
        CardQuantity(oracle_id=ORACLE_C, quantity=1),
        CardQuantity(oracle_id=ORACLE_C, quantity=2),
    )
    with pytest.raises(ValidationError):
        CardZone(zone="mainboard", cards=duplicate_cards)

    with pytest.raises(ValidationError):
        make_deck(
            (
                CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),
                CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),
            )
        )


@pytest.mark.parametrize(
    "reference_data",
    (
        {"reference_id": "source", "scope": "source"},
        {"reference_id": "event", "scope": "event"},
        {"reference_id": "snapshot", "scope": "snapshot_object"},
        {
            "reference_id": "event-with-source",
            "scope": "event",
            "event_id": "event-1",
            "source_id": "fixture",
        },
    ),
)
def test_participant_reference_requires_compatible_scope_fields(
    reference_data: dict[str, str],
) -> None:
    with pytest.raises(ValidationError):
        ParticipantReference.model_validate(reference_data)


def test_participant_reference_scope_fields_are_validated() -> None:
    assert (
        ParticipantReference(
            reference_id="source",
            scope="source",
            source_id="fixture",
        ).source_id
        == "fixture"
    )
    assert (
        ParticipantReference(
            reference_id="event",
            scope="event",
            event_id="event-1",
        ).event_id
        == "event-1"
    )
    assert (
        ParticipantReference(
            reference_id="snapshot",
            scope="snapshot_object",
            source_snapshot_id="snapshot-1",
        ).source_snapshot_id
        == "snapshot-1"
    )


def test_pod_entry_rejects_event_participant_from_another_event() -> None:
    with pytest.raises(ValidationError, match="event participant reference must match event_id"):
        PodEntry(
            pod_id="pod-1",
            event_id="event-1",
            round_number=1,
            seat=1,
            canonical_deck_id="d" * 64,
            result="win",
            participant_reference=ParticipantReference(
                reference_id="participant-1",
                scope="event",
                event_id="event-2",
            ),
            provenance=(provenance("fixture", "pod-1"),),
        )
