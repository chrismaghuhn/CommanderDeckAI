"""Privacy-minimized participant references for normalized event data."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from commander_ai.data_pipeline.provenance.evidence import SourceEvidence, source_scoped_id
from commander_ai.domain.observations import ParticipantReference
from commander_ai.domain.serialization import canonical_json_bytes


@dataclass(frozen=True, slots=True)
class ParticipantInput:
    """Source participant hints; display names never leave this mapping stage."""

    evidence: SourceEvidence
    event_id: str | None = None
    source_opaque_id: str | None = None
    display_name: str | None = None

    def __post_init__(self) -> None:
        if self.event_id is not None and not self.event_id.strip():
            raise ValueError("event_id must be non-empty when supplied")
        if self.source_opaque_id is not None and not self.source_opaque_id.strip():
            raise ValueError("source_opaque_id must be non-empty when supplied")
        if self.display_name is not None and not self.display_name.strip():
            raise ValueError("display_name must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class ParticipantResolution:
    """Reference plus quality findings; no raw name is retained."""

    reference: ParticipantReference | None
    finding_codes: tuple[str, ...] = ()


def resolve_participant(
    participant: ParticipantInput | None,
    *,
    allow_source_opaque_id: bool,
    event_id: str | None,
) -> ParticipantResolution:
    """Create a source/event/snapshot-scoped reference without global name hashes."""

    if participant is None:
        return ParticipantResolution(None, ("quality.participant_missing",))
    selected_event_id = event_id or participant.event_id
    if allow_source_opaque_id and participant.source_opaque_id is not None:
        reference = ParticipantReference(
            reference_id=source_scoped_id(
                "participant", participant.evidence.source_id, participant.source_opaque_id
            ),
            scope="source",
            source_id=participant.evidence.source_id,
        )
        return ParticipantResolution(reference)

    findings: list[str] = []
    if participant.source_opaque_id is not None:
        findings.append("quality.participant_source_id_not_retained")
    normalized_name = _normalized_name(participant.display_name)
    if normalized_name is not None and selected_event_id is not None:
        canonical_event_id = _canonical_event_id(participant.evidence.source_id, selected_event_id)
        digest = _scoped_digest("event", canonical_event_id, normalized_name)
        reference = ParticipantReference(
            reference_id=f"event:{digest}",
            scope="event",
            event_id=canonical_event_id,
        )
        return ParticipantResolution(reference, tuple(sorted(findings)))
    if normalized_name is not None:
        digest = _scoped_digest(
            "snapshot_object",
            participant.evidence.source_id,
            participant.evidence.source_snapshot_id,
            participant.evidence.raw_object_id,
            normalized_name,
        )
        reference = ParticipantReference(
            reference_id=f"snapshot-object:{digest}",
            scope="snapshot_object",
            source_snapshot_id=participant.evidence.source_snapshot_id,
        )
        return ParticipantResolution(reference, tuple(sorted(findings)))
    findings.append("quality.participant_missing")
    return ParticipantResolution(None, tuple(sorted(set(findings))))


def _normalized_name(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.casefold().split())
    return normalized or None


def _scoped_digest(*values: str) -> str:
    return sha256(canonical_json_bytes(values)).hexdigest()[:32]


def _canonical_event_id(source_id: str, event_id: str) -> str:
    return source_scoped_id("event", source_id, event_id)


__all__ = ["ParticipantInput", "ParticipantResolution", "resolve_participant"]
