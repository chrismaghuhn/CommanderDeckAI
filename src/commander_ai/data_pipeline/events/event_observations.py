"""Map final event standings into the versioned observation contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from commander_ai.data_pipeline.provenance.evidence import SourceEvidence, source_scoped_id
from commander_ai.domain.observations import EventDeckObservation

from .event_records import EventDeckStandingRecord, EventRecord
from .participants import ParticipantResolution, resolve_participant

_COMMANDER_FORMATS = frozenset({"commander", "edh", "cedh", "c-edh"})


@dataclass(frozen=True, slots=True)
class EventObservationNormalization:
    """Curated observation or a retained quarantine decision with raw evidence."""

    observation: EventDeckObservation | None
    evidence: SourceEvidence
    participant: ParticipantResolution
    finding_codes: tuple[str, ...]
    status: Literal["CURATED", "QUARANTINED"]


def normalize_event_deck_observation(
    event: EventRecord,
    standing: EventDeckStandingRecord,
    *,
    allow_source_opaque_participant_id: bool = False,
) -> EventObservationNormalization:
    """Create only complete event-level observations; never infer missing results."""

    findings: set[str] = set()
    if event.event_id != standing.event_id:
        findings.add("quality.event_id_mismatch")
    if (
        event.evidence.source_id != standing.evidence.source_id
        or event.evidence.source_snapshot_id != standing.evidence.source_snapshot_id
    ):
        findings.add("quality.event_evidence_mismatch")
    if event.format is None:
        findings.add("quality.event_format_unknown")
    elif event.format.casefold().strip() not in _COMMANDER_FORMATS:
        findings.add("quality.non_commander_event")

    participant = resolve_participant(
        standing.participant,
        allow_source_opaque_id=allow_source_opaque_participant_id,
        event_id=event.event_id,
    )
    findings.update(participant.finding_codes)
    observed_at = standing.observed_at or event.observed_at
    if observed_at is None:
        findings.add("quality.observation_time_missing")
    if standing.canonical_deck_id is None:
        findings.add("quality.canonical_deck_missing")
    if standing.source_result_semantics is None:
        findings.add("quality.result_semantics_missing")
    if any(
        value is None
        for value in (
            standing.aggregate_wins,
            standing.aggregate_losses,
            standing.aggregate_draws,
        )
    ):
        findings.add("quality.aggregate_record_incomplete")

    blocking = {
        "quality.event_id_mismatch",
        "quality.event_evidence_mismatch",
        "quality.event_format_unknown",
        "quality.non_commander_event",
        "quality.observation_time_missing",
        "quality.canonical_deck_missing",
        "quality.result_semantics_missing",
        "quality.aggregate_record_incomplete",
    }
    if findings.intersection(blocking):
        return EventObservationNormalization(
            observation=None,
            evidence=standing.evidence,
            participant=participant,
            finding_codes=tuple(sorted(findings)),
            status="QUARANTINED",
        )

    assert observed_at is not None
    assert standing.canonical_deck_id is not None
    assert standing.aggregate_wins is not None
    assert standing.aggregate_losses is not None
    assert standing.aggregate_draws is not None
    assert standing.source_result_semantics is not None
    try:
        observation = EventDeckObservation(
            observation_id=source_scoped_id(
                "observation", standing.evidence.source_id, standing.observation_id
            ),
            event_id=event.canonical_event_id,
            canonical_deck_id=standing.canonical_deck_id,
            observed_at=observed_at,
            participant_reference=participant.reference,
            participant_reference_scope=(
                participant.reference.scope if participant.reference is not None else "none"
            ),
            final_placement=standing.final_placement,
            aggregate_wins=standing.aggregate_wins,
            aggregate_losses=standing.aggregate_losses,
            aggregate_draws=standing.aggregate_draws,
            source_result_semantics=standing.source_result_semantics,
            provenance=standing.evidence.provenance,
        )
    except ValueError:
        findings.add("quality.observation_contract_invalid")
        return EventObservationNormalization(
            observation=None,
            evidence=standing.evidence,
            participant=participant,
            finding_codes=tuple(sorted(findings)),
            status="QUARANTINED",
        )
    return EventObservationNormalization(
        observation=observation,
        evidence=standing.evidence,
        participant=participant,
        finding_codes=tuple(sorted(findings)),
        status="CURATED",
    )


__all__ = ["EventObservationNormalization", "normalize_event_deck_observation"]
