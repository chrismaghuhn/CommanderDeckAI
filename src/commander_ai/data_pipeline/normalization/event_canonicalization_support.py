"""Focused helpers for standing-to-observation canonicalization."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from commander_ai.data_pipeline.events.event_observations import normalize_event_deck_observation
from commander_ai.data_pipeline.events.event_records import EventDeckStandingRecord, EventRecord
from commander_ai.data_pipeline.events.participants import ParticipantInput
from commander_ai.data_pipeline.provenance.evidence import SourceEvidence
from commander_ai.data_pipeline.provenance.rows import AuditRecord, ProvenanceRow, ResolutionAttempt
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord, quarantine_record
from commander_ai.data_pipeline.resolution.card_resolution import CardResolver
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.provenance import SourceSnapshotManifest

from .canonical_records import CanonicalRecord, canonical_record_from_domain
from .canonicalization_support import observed_at, provenance_for
from .event_canonicalization_types import EventCanonicalizationResult
from .event_deck_canonicalization import EventDeckResult, canonicalize_event_deck

_DECK_ID = re.compile(r"^[a-f0-9]{64}$")


def standing_result(
    record: StagingRecord,
    manifest: SourceSnapshotManifest,
    events: Mapping[str, Sequence[tuple[StagingRecord, EventRecord]]],
    *,
    resolver: CardResolver | None,
    attempted_at: datetime,
) -> EventCanonicalizationResult:
    """Resolve one final-standing row and retain its deck evidence."""

    values = _mapping(record.original_source_values)
    candidates = events.get(record.raw_locator.raw_object_id, ())
    event_id = _text(values, "event_id", "eventId", "TID", "tid")
    if event_id is not None:
        candidates = tuple(item for item in candidates if item[1].event_id == event_id)
    if len(candidates) != 1:
        return failure_result(record, "quality.event_context_ambiguous")
    event_record, event = candidates[0]
    canonical_deck_id = _canonical_deck_id(values)
    deck_result = EventDeckResult(record=None, canonical_deck_id=canonical_deck_id)
    if canonical_deck_id is None and _has_deck_values(values):
        deck_result = canonicalize_event_deck(
            record,
            values,
            source_manifest=manifest,
            resolver=resolver,
            observed_at=event.observed_at or observed_at(record, manifest),
            attempted_at=attempted_at,
        )
        canonical_deck_id = deck_result.canonical_deck_id
        if canonical_deck_id is None:
            return event_deck_failure(record, deck_result)
    event_result = event_deck_records(deck_result)
    participant = _participant(values, _evidence(record, manifest, manifest.source_id))
    standing = EventDeckStandingRecord(
        observation_id=_text(values, "standing_id", "id", "player_id") or record.staging_record_id,
        event_id=event.event_id,
        canonical_deck_id=canonical_deck_id,
        evidence=_evidence(record, manifest, manifest.source_id),
        observed_at=_datetime(values, "observed_at") or event.observed_at,
        aggregate_wins=_nonnegative_int(values, "wins", "winsSwiss"),
        aggregate_losses=_nonnegative_int(values, "losses", "lossesSwiss"),
        aggregate_draws=_nonnegative_int(values, "draws", "drawsSwiss"),
        source_result_semantics=_text(values, "record", "result", "result_code")
        or ("aggregate standing record" if "wins" in values else None),
        final_placement=_positive_int(values, "place", "rank", "standing"),
        participant=participant,
    )
    normalized = normalize_event_deck_observation(
        EventRecord(
            event_id=event.event_id,
            evidence=_evidence(event_record, manifest, manifest.source_id),
            format=event.format,
            name=event.name,
            observed_at=event.observed_at,
            source_status=event.source_status,
        ),
        standing,
        allow_source_opaque_participant_id=True,
    )
    if normalized.observation is None:
        return merge_result_values(
            event_result,
            failure_result(
                record,
                normalized.finding_codes[0]
                if normalized.finding_codes
                else "quality.observation_contract_invalid",
                extra_findings=normalized.finding_codes,
            ),
        )
    canonical = canonical_record_from_domain(
        normalized.observation,
        source_record_id=record.staging_record_id,
        raw_locator=record.raw_locator,
        provenance=provenance_for(record, manifest, f"{manifest.source_id}-event-mapper-v1"),
        observed_at=normalized.observation.observed_at,
    )
    player_id = _player_id(values)
    bindings = event_result.deck_bindings
    if player_id is not None and canonical_deck_id is not None:
        bindings = (*bindings, (event.event_id, player_id, canonical_deck_id))
    return EventCanonicalizationResult(
        records=(*event_result.records, canonical),
        audits=event_result.audits,
        quarantines=event_result.quarantines,
        finding_codes=tuple(sorted({*event_result.finding_codes, *normalized.finding_codes})),
        resolutions=event_result.resolutions,
        resolution_attempts=event_result.resolution_attempts,
        provenance=event_result.provenance,
        deck_bindings=bindings,
    )


def merge_event_result(
    result: EventCanonicalizationResult,
    records: list[CanonicalRecord],
    audits: list[AuditRecord],
    quarantines: list[QuarantineRecord],
    findings: set[str],
    resolutions: list[CardResolution],
    resolution_attempts: list[ResolutionAttempt],
    provenance: list[ProvenanceRow],
    deck_bindings: list[tuple[str, str, str]],
) -> None:
    records.extend(result.records)
    audits.extend(result.audits)
    quarantines.extend(result.quarantines)
    findings.update(result.finding_codes)
    resolutions.extend(result.resolutions)
    resolution_attempts.extend(result.resolution_attempts)
    provenance.extend(result.provenance)
    deck_bindings.extend(result.deck_bindings)


def failure_result(
    record: StagingRecord,
    code: str,
    *,
    extra_findings: Sequence[str] = (),
) -> EventCanonicalizationResult:
    findings = tuple(sorted({code, *extra_findings}))
    return EventCanonicalizationResult(
        records=(),
        audits=(audit(record, findings[0]),),
        quarantines=(quarantine_record(record, reason_code=findings[0]),),
        finding_codes=findings,
    )


def event_deck_records(deck_result: EventDeckResult) -> EventCanonicalizationResult:
    return EventCanonicalizationResult(
        records=() if deck_result.record is None else (deck_result.record,),
        audits=(),
        quarantines=deck_result.quarantines,
        finding_codes=deck_result.finding_codes,
        resolutions=deck_result.resolutions,
        resolution_attempts=deck_result.resolution_attempts,
    )


def event_deck_failure(
    record: StagingRecord, deck_result: EventDeckResult
) -> EventCanonicalizationResult:
    code = (
        deck_result.finding_codes[0] if deck_result.finding_codes else "quality.event_deck_invalid"
    )
    return EventCanonicalizationResult(
        records=(),
        audits=(audit(record, code),),
        quarantines=deck_result.quarantines,
        finding_codes=deck_result.finding_codes or (code,),
        resolutions=deck_result.resolutions,
        resolution_attempts=deck_result.resolution_attempts,
    )


def merge_result_values(
    first: EventCanonicalizationResult, second: EventCanonicalizationResult
) -> EventCanonicalizationResult:
    return EventCanonicalizationResult(
        records=(*first.records, *second.records),
        audits=(*first.audits, *second.audits),
        quarantines=(*first.quarantines, *second.quarantines),
        finding_codes=tuple(sorted({*first.finding_codes, *second.finding_codes})),
        resolutions=(*first.resolutions, *second.resolutions),
        resolution_attempts=(*first.resolution_attempts, *second.resolution_attempts),
        provenance=(*first.provenance, *second.provenance),
        deck_bindings=(*first.deck_bindings, *second.deck_bindings),
    )


def audit(record: StagingRecord, code: str) -> AuditRecord:
    digest = hashlib.sha256(f"{record.staging_record_id}|{code}".encode()).hexdigest()[:32]
    return AuditRecord(
        audit_id=f"canonical-event-audit-{digest}",
        entity_id=record.staging_record_id,
        stage="quality",
        finding_code=code,
        raw_locator=record.raw_locator,
        details={"record_type": record.record_type},
    )


def _evidence(
    record: StagingRecord, manifest: SourceSnapshotManifest, source_id: str
) -> SourceEvidence:
    from .canonicalization_support import source_evidence

    return source_evidence(record, manifest, f"{source_id}-event-mapper-v1")


def _participant(values: Mapping[str, object], evidence: SourceEvidence) -> ParticipantInput | None:
    raw_player = values.get("player")
    display_name = _text(values, "name")
    if isinstance(raw_player, Mapping):
        display_name = display_name or _text(raw_player, "name", "display_name")
    elif isinstance(raw_player, str):
        display_name = display_name or raw_player
    opaque = _text(values, "player_id", "playerId")
    if opaque is None and isinstance(raw_player, Mapping):
        opaque = _text(raw_player, "player_id", "playerId", "id")
    return (
        ParticipantInput(evidence=evidence, source_opaque_id=opaque, display_name=display_name)
        if opaque is not None or display_name is not None
        else None
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _has_deck_values(values: Mapping[str, object]) -> bool:
    return any(
        key in values
        for key in (
            "deckObj",
            "deck_obj",
            "deck",
            "decklist",
            "deckList",
            "decklist_text",
            "cards",
            "mainboard",
            "mainBoard",
        )
    )


def _canonical_deck_id(values: Mapping[str, object]) -> str | None:
    value = _text(values, "canonical_deck_id", "canonicalDeckId")
    return value if value is not None and _DECK_ID.fullmatch(value) else None


def _player_id(values: Mapping[str, object]) -> str | None:
    direct = _text(values, "player_id", "playerId", "player")
    if direct is not None:
        return direct
    return _text(_mapping(values.get("player")), "player_id", "playerId", "id")


def _text(values: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            text = str(value).strip()
            if text:
                return text
    return None


def _datetime(values: Mapping[str, object], *keys: str) -> datetime | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            try:
                return datetime.fromtimestamp(float(value), tz=UTC)
            except (OverflowError, OSError, ValueError):
                continue
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                continue
            return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def _positive_int(values: Mapping[str, object], *keys: str) -> int | None:
    value = _nonnegative_int(values, *keys)
    return value if value is not None and value > 0 else None


def _nonnegative_int(values: Mapping[str, object], *keys: str) -> int | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value >= 0:
            return value
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError:
                continue
            if parsed >= 0:
                return parsed
    return None


mapping_value = _mapping
text_value = _text
datetime_value = _datetime
evidence_for_event = _evidence


__all__ = [
    "EventCanonicalizationResult",
    "audit",
    "datetime_value",
    "evidence_for_event",
    "failure_result",
    "mapping_value",
    "merge_event_result",
    "standing_result",
    "text_value",
]
