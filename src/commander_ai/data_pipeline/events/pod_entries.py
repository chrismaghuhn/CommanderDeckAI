"""Normalize complete multiplayer pods into grouped PodEntry rows."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, ClassVar, Literal, cast

from commander_ai.data_pipeline.provenance.evidence import SourceEvidence, source_scoped_id
from commander_ai.domain.observations import PodEntry

if TYPE_CHECKING:
    from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord

from .participants import ParticipantInput, ParticipantResolution, resolve_participant

PodStatus = Literal["complete", "incomplete", "cancelled", "unknown"]


@dataclass(frozen=True, slots=True)
class PodMemberInput:
    """One source table member before canonical deck and participant mapping."""

    seat: int | None
    canonical_deck_id: str | None
    result: str | None
    participant: ParticipantInput | None = None
    points: float | None = None
    placement: int | None = None


@dataclass(frozen=True, slots=True)
class PodRecord:
    """One source table with all members preserved as one multiplayer unit."""

    pod_id: str
    event_id: str
    round_number: int
    occurred_at: datetime | None
    source_status: str | None
    members: tuple[PodMemberInput, ...]
    evidence: SourceEvidence

    def __post_init__(self) -> None:
        if not self.pod_id.strip() or not self.event_id.strip():
            raise ValueError("pod_id and event_id must be non-empty")
        if self.round_number < 1:
            raise ValueError("round_number must be positive")
        if self.occurred_at is not None and (
            self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None
        ):
            raise ValueError("occurred_at must include a timezone")


@dataclass(frozen=True, slots=True)
class NormalizedPod:
    """Grouped normalized pod metadata and its per-seat rows."""

    schema_version: ClassVar[Literal["pod.v2"]] = "pod.v2"
    pod_id: str
    event_id: str
    round_number: int
    occurred_at: datetime | None
    status: PodStatus
    entries: tuple[PodEntry, ...]
    evidence: SourceEvidence
    finding_codes: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        """Serialize the versioned pod successor with one grouped evidence link."""

        return {
            "schema_version": self.schema_version,
            "pod_id": self.pod_id,
            "event_id": self.event_id,
            "round_number": self.round_number,
            "occurred_at": None if self.occurred_at is None else self.occurred_at.isoformat(),
            "status": self.status,
            "entries": [
                {
                    "seat": entry.seat,
                    "canonical_deck_id": entry.canonical_deck_id,
                    "result": entry.result,
                    "points": entry.points,
                    "placement": entry.placement,
                    "participant_reference": (
                        None
                        if entry.participant_reference is None
                        else entry.participant_reference.model_dump(mode="json")
                    ),
                }
                for entry in self.entries
            ],
            "raw_locator": self.evidence.raw_locator.exact_locator,
            "provenance": [item.model_dump(mode="json") for item in self.evidence.provenance],
            "finding_codes": list(self.finding_codes),
        }


@dataclass(frozen=True, slots=True)
class PodNormalization:
    """Curated grouped pod or retained quarantine evidence."""

    pod: NormalizedPod | None
    evidence: SourceEvidence
    participant_resolutions: tuple[ParticipantResolution, ...]
    finding_codes: tuple[str, ...]
    status: Literal["CURATED", "QUARANTINED"]


@dataclass(frozen=True, slots=True)
class PodCompletenessIndex:
    """Deterministic completeness keys derived from canonical pod entries."""

    complete_pod_ids: tuple[str, ...] = ()
    complete_event_deck_keys: tuple[tuple[str, str], ...] = ()


def index_complete_pods(
    records: tuple[CanonicalRecord, ...] | list[CanonicalRecord],
) -> PodCompletenessIndex:
    """Group canonical pod entries without flattening their multiplayer unit."""

    grouped: defaultdict[tuple[str, str, int], list[PodEntry]] = defaultdict(list)
    for record in records:
        if record.record_type != "pod_entry":
            continue
        entry = PodEntry.model_validate(record.payload)
        grouped[(entry.pod_id, entry.event_id, entry.round_number)].append(entry)

    complete_groups = {
        key: entries
        for key, entries in grouped.items()
        if len(entries) >= 2 and len({entry.seat for entry in entries}) == len(entries)
    }
    return PodCompletenessIndex(
        complete_pod_ids=tuple(sorted({key[0] for key in complete_groups})),
        complete_event_deck_keys=tuple(
            sorted(
                {
                    (event_id, entry.canonical_deck_id)
                    for (_, event_id, _), entries in complete_groups.items()
                    for entry in entries
                }
            )
        ),
    )


def normalize_pod(
    record: PodRecord,
    *,
    allow_source_opaque_participant_id: bool = False,
) -> PodNormalization:
    """Require a complete multiplayer structure before emitting PodEntry rows."""

    findings: set[str] = set()
    scoped_pod_id = source_scoped_id("pod", record.evidence.source_id, record.pod_id)
    scoped_event_id = source_scoped_id("event", record.evidence.source_id, record.event_id)
    if len(record.members) < 2:
        findings.add("quality.pod_not_multiplayer")
    seats = [member.seat for member in record.members]
    if any(seat is None or seat < 1 for seat in seats):
        findings.add("quality.pod_seat_missing")
    elif len(seats) != len(set(seats)):
        findings.add("quality.pod_seat_duplicate")
    if any(member.canonical_deck_id is None for member in record.members):
        findings.add("quality.pod_deck_unresolved")

    status = _pod_status(record.source_status, findings)
    if status in {"incomplete", "cancelled"}:
        findings.add("quality.pod_source_not_complete")
    resolutions: list[ParticipantResolution] = []
    entries: list[PodEntry] = []
    for member in record.members:
        resolution = resolve_participant(
            member.participant,
            allow_source_opaque_id=allow_source_opaque_participant_id,
            event_id=record.event_id,
        )
        resolutions.append(resolution)
        findings.update(resolution.finding_codes)
        if member.result not in {"win", "loss", "draw", "bye", "unknown"}:
            findings.add("quality.pod_result_ambiguous")
        if member.points is not None and not math.isfinite(member.points):
            findings.add("quality.pod_points_invalid")
        if member.placement is not None and member.placement < 1:
            findings.add("quality.pod_placement_invalid")

    blocking = {
        "quality.pod_not_multiplayer",
        "quality.pod_seat_missing",
        "quality.pod_seat_duplicate",
        "quality.pod_deck_unresolved",
        "quality.pod_status_unknown",
        "quality.pod_source_not_complete",
        "quality.pod_result_ambiguous",
    }
    if findings.intersection(blocking):
        return PodNormalization(
            pod=None,
            evidence=record.evidence,
            participant_resolutions=tuple(resolutions),
            finding_codes=tuple(sorted(findings)),
            status="QUARANTINED",
        )

    for member, resolution in zip(record.members, resolutions, strict=True):
        result = cast(
            Literal["win", "loss", "draw", "bye", "unknown"],
            member.result
            if member.result in {"win", "loss", "draw", "bye", "unknown"}
            else "unknown",
        )
        points = member.points if member.points is None or math.isfinite(member.points) else None
        placement = member.placement if member.placement is None or member.placement >= 1 else None
        assert member.seat is not None
        assert member.canonical_deck_id is not None
        try:
            entries.append(
                PodEntry(
                    pod_id=scoped_pod_id,
                    event_id=scoped_event_id,
                    round_number=record.round_number,
                    seat=member.seat,
                    canonical_deck_id=member.canonical_deck_id,
                    result=result,
                    points=points,
                    placement=placement,
                    participant_reference=resolution.reference,
                    provenance=record.evidence.provenance,
                )
            )
        except ValueError:
            findings.add("quality.pod_entry_contract_invalid")

    if len(entries) != len(record.members):
        return PodNormalization(
            pod=None,
            evidence=record.evidence,
            participant_resolutions=tuple(resolutions),
            finding_codes=tuple(sorted(findings)),
            status="QUARANTINED",
        )
    return PodNormalization(
        pod=NormalizedPod(
            pod_id=scoped_pod_id,
            event_id=scoped_event_id,
            round_number=record.round_number,
            occurred_at=record.occurred_at,
            status=status,
            entries=tuple(entries),
            evidence=record.evidence,
            finding_codes=tuple(sorted(findings)),
        ),
        evidence=record.evidence,
        participant_resolutions=tuple(resolutions),
        finding_codes=tuple(sorted(findings)),
        status="CURATED",
    )


def _pod_status(source_status: str | None, findings: set[str]) -> PodStatus:
    if source_status is None:
        findings.add("quality.pod_status_unknown")
        return "unknown"
    normalized = source_status.casefold().strip()
    if normalized in {"complete", "incomplete", "cancelled", "unknown"}:
        return normalized  # type: ignore[return-value]
    findings.add("quality.pod_status_unknown")
    return "unknown"


__all__ = [
    "NormalizedPod",
    "PodCompletenessIndex",
    "PodMemberInput",
    "PodNormalization",
    "PodRecord",
    "index_complete_pods",
    "normalize_pod",
]
