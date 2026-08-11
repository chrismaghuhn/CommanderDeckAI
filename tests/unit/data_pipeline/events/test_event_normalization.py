from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.data_pipeline.events.event_observations import (
    normalize_event_deck_observation,
)
from commander_ai.data_pipeline.events.event_records import (
    EventDeckStandingRecord,
    EventRecord,
)
from commander_ai.data_pipeline.events.participants import ParticipantInput, resolve_participant
from commander_ai.data_pipeline.events.pod_entries import (
    PodMemberInput,
    PodRecord,
    normalize_pod,
)
from commander_ai.data_pipeline.provenance.evidence import SourceEvidence, source_scoped_id
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.domain.provenance import ProvenanceReference

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DECK_ID = "a" * 64
ORACLE_IDS = (
    "11111111-1111-4111-8111-111111111111",
    "22222222-2222-4222-8222-222222222222",
    "33333333-3333-4333-8333-333333333333",
    "44444444-4444-4444-8444-444444444444",
)


def _evidence(object_id: str, source_id: str = "fixture") -> SourceEvidence:
    snapshot_id = f"{source_id}-snapshot"
    locator = RawLocator(
        source_id=source_id,
        source_snapshot_id=snapshot_id,
        raw_object_id=object_id,
        raw_object_path=f"{source_id}/{object_id}.json",
        location=JsonPointerLocator(pointer="/record"),
    )
    return SourceEvidence(
        raw_locator=locator,
        provenance=(
            ProvenanceReference(
                source_id=source_id,
                source_snapshot_id=snapshot_id,
                source_object_id=object_id,
                raw_sha256="0" * 64,
                retrieved_at=datetime(2026, 8, 11, tzinfo=UTC),
                adapter_version="fixture-v1",
                mapper_version="task12-fixture-v1",
                approval_status="APPROVED_LOCAL",
            ),
        ),
    )


def _event(event_id: str, *, date: datetime | None = None) -> EventRecord:
    return EventRecord(
        event_id=event_id,
        evidence=_evidence(f"{event_id}-event"),
        format="commander",
        name="Fixture Event",
        observed_at=date or datetime(2026, 8, 11, tzinfo=UTC),
    )


def _standing(
    event_id: str,
    *,
    observation_id: str | None = None,
    source_id: str = "fixture",
) -> EventDeckStandingRecord:
    return EventDeckStandingRecord(
        observation_id=observation_id or f"{event_id}-standing",
        event_id=event_id,
        canonical_deck_id=DECK_ID,
        evidence=_evidence(f"{event_id}-standing", source_id),
        observed_at=None,
        aggregate_wins=3,
        aggregate_losses=1,
        aggregate_draws=0,
        source_result_semantics="final standings",
        final_placement=1,
    )


def test_one_canonical_deck_can_have_many_event_observations() -> None:
    first = normalize_event_deck_observation(_event("event-a"), _standing("event-a"))
    second = normalize_event_deck_observation(_event("event-b"), _standing("event-b"))
    assert first.status == second.status == "CURATED"
    assert first.observation is not None and second.observation is not None
    assert first.observation.canonical_deck_id == second.observation.canonical_deck_id == DECK_ID
    assert first.observation.event_id != second.observation.event_id


def test_source_scoped_ids_escape_segment_delimiters() -> None:
    assert source_scoped_id("event", "a:b", "c") != source_scoped_id("event", "a", "b:c")


def test_event_and_standing_must_share_source_evidence() -> None:
    result = normalize_event_deck_observation(
        _event("event-a"), _standing("event-a", source_id="other")
    )
    assert result.status == "QUARANTINED"
    assert result.observation is None
    assert "quality.event_evidence_mismatch" in result.finding_codes


def test_name_only_participants_are_event_scoped_and_do_not_retain_names() -> None:
    participant = ParticipantInput(
        evidence=_evidence("participant"),
        display_name="Alice Example",
    )
    first = resolve_participant(participant, allow_source_opaque_id=False, event_id="event-a")
    second = resolve_participant(participant, allow_source_opaque_id=False, event_id="event-b")
    assert first.reference is not None and second.reference is not None
    assert first.reference.scope == second.reference.scope == "event"
    assert first.reference.reference_id != second.reference.reference_id
    assert "Alice" not in json.dumps(first.reference.model_dump(mode="json"))


def test_source_opaque_participant_id_is_source_scoped_only_when_allowed() -> None:
    participant = ParticipantInput(
        evidence=_evidence("participant"),
        source_opaque_id="opaque-42",
        display_name="Alice Example",
    )
    allowed = resolve_participant(participant, allow_source_opaque_id=True, event_id="event-a")
    restricted = resolve_participant(participant, allow_source_opaque_id=False, event_id="event-a")
    assert allowed.reference is not None
    assert allowed.reference.scope == "source"
    assert allowed.reference.source_id == "fixture"
    assert restricted.reference is not None
    assert restricted.reference.scope == "event"
    assert "quality.participant_source_id_not_retained" in restricted.finding_codes


def test_missing_participant_linkage_is_a_finding_not_a_global_identity() -> None:
    result = normalize_event_deck_observation(_event("event-a"), _standing("event-a"))
    assert result.observation is not None
    assert result.observation.participant_reference is None
    assert "quality.participant_missing" in result.finding_codes


def test_four_player_pod_remains_one_group_of_four_entries() -> None:
    members = tuple(
        PodMemberInput(
            seat=index,
            canonical_deck_id=f"{index:x}" * 64,
            result="win" if index == 1 else "loss",
            placement=index,
        )
        for index in range(1, 5)
    )
    result = normalize_pod(
        PodRecord(
            pod_id="pod-1",
            event_id="event-1",
            round_number=2,
            occurred_at=datetime(2026, 8, 11, tzinfo=UTC),
            source_status="complete",
            members=members,
            evidence=_evidence("pod-1"),
        )
    )
    assert result.status == "CURATED"
    assert result.pod is not None
    assert len(result.pod.entries) == 4
    assert {entry.seat for entry in result.pod.entries} == {1, 2, 3, 4}
    assert not hasattr(result.pod, "opponents")


def test_pod_result_ambiguity_is_quarantined_without_synthetic_result() -> None:
    result = normalize_pod(
        PodRecord(
            pod_id="pod-unknown",
            event_id="event-1",
            round_number=1,
            occurred_at=None,
            source_status="complete",
            members=(
                PodMemberInput(seat=1, canonical_deck_id=DECK_ID, result="source-value"),
                PodMemberInput(seat=2, canonical_deck_id=DECK_ID, result="loss"),
            ),
            evidence=_evidence("pod-unknown"),
        )
    )
    assert result.pod is None
    assert result.status == "QUARANTINED"
    assert "quality.pod_result_ambiguous" in result.finding_codes


def test_incomplete_pod_is_quarantined_without_synthetic_deck_rows() -> None:
    result = normalize_pod(
        PodRecord(
            pod_id="pod-incomplete",
            event_id="event-1",
            round_number=1,
            occurred_at=None,
            source_status="incomplete",
            members=(
                PodMemberInput(seat=1, canonical_deck_id=DECK_ID, result="win"),
                PodMemberInput(seat=2, canonical_deck_id=None, result="loss"),
            ),
            evidence=_evidence("pod-incomplete"),
        )
    )
    assert result.status == "QUARANTINED"
    assert result.pod is None
    assert "quality.pod_deck_unresolved" in result.finding_codes


def test_event_observation_contract_serializes_to_existing_schema() -> None:
    result = normalize_event_deck_observation(_event("event-schema"), _standing("event-schema"))
    assert result.observation is not None
    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "event-deck-observation.v1.schema.json").read_text()
    )
    errors = Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
        result.observation.model_dump(mode="json")
    )
    assert not list(errors)


def test_event_record_contract_serializes_to_versioned_schema() -> None:
    event = _event("event-schema")
    schema = json.loads((PROJECT_ROOT / "schemas" / "event.v1.schema.json").read_text())
    errors = Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
        event.as_dict()
    )
    assert not list(errors)


def test_pod_successor_contract_serializes_to_versioned_schema() -> None:
    result = normalize_pod(
        PodRecord(
            pod_id="pod-schema",
            event_id="event-schema",
            round_number=1,
            occurred_at=datetime(2026, 8, 11, tzinfo=UTC),
            source_status="complete",
            members=tuple(
                PodMemberInput(
                    seat=index,
                    canonical_deck_id=f"{index:x}" * 64,
                    result="win" if index == 1 else "loss",
                )
                for index in range(1, 5)
            ),
            evidence=_evidence("pod-schema"),
        )
    )
    assert result.pod is not None
    schema = json.loads((PROJECT_ROOT / "schemas" / "pod.v2.schema.json").read_text())
    errors = Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
        result.pod.as_dict()
    )
    assert not list(errors)


def test_participant_reference_contract_serializes_to_existing_schema() -> None:
    resolution = resolve_participant(
        ParticipantInput(evidence=_evidence("participant"), display_name="Alice"),
        allow_source_opaque_id=False,
        event_id="event-1",
    )
    assert resolution.reference is not None
    schema = json.loads(
        (PROJECT_ROOT / "schemas" / "participant-reference.v1.schema.json").read_text()
    )
    errors = Draft202012Validator(schema).iter_errors(resolution.reference.model_dump(mode="json"))
    assert not list(errors)
