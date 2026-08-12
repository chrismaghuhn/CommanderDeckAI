"""Conservative event and pod mapping from source-shaped staging rows."""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from commander_ai.data_pipeline.events.event_observations import normalize_event_deck_observation
from commander_ai.data_pipeline.events.event_records import EventDeckStandingRecord, EventRecord
from commander_ai.data_pipeline.events.participants import ParticipantInput
from commander_ai.data_pipeline.provenance.evidence import SourceEvidence
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord, quarantine_record
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.provenance import SourceSnapshotManifest

from .canonical_records import CanonicalRecord, canonical_record_from_domain
from .canonicalization_support import provenance_for

_DECK_ID = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True, slots=True)
class EventCanonicalizationResult:
    """Canonical observations plus retained event/pod quality outcomes."""

    records: tuple[CanonicalRecord, ...]
    audits: tuple[AuditRecord, ...]
    quarantines: tuple[QuarantineRecord, ...]
    finding_codes: tuple[str, ...]


def canonicalize_event_sources(
    records: Sequence[StagingRecord],
    *,
    source_manifest: SourceSnapshotManifest,
) -> EventCanonicalizationResult:
    """Map only source records with enough semantics for safe canonicalization."""

    source_id = source_manifest.source_id
    events: dict[str, list[tuple[StagingRecord, EventRecord]]] = defaultdict(list)
    canonical: list[CanonicalRecord] = []
    audits: list[AuditRecord] = []
    quarantines: list[QuarantineRecord] = []
    findings: set[str] = set()
    observed_records = tuple(item for item in records if item.status == "OBSERVED")

    for record in observed_records:
        if record.record_type != "event":
            continue
        values = _mapping(record.original_source_values)
        event_id = _text(values, "event_id", "eventId", "TID", "tid", "id")
        if event_id is None:
            _retain_failure(
                record,
                "quality.event_id_missing",
                audits,
                quarantines,
                findings,
            )
            continue
        event = EventRecord(
            event_id=event_id,
            evidence=_evidence(record, source_manifest, source_id),
            format=_text(values, "format"),
            name=_text(values, "tournamentName", "name"),
            observed_at=_datetime(values, "startDate", "start_at", "event_at"),
            source_status=_text(values, "status", "source_status"),
        )
        events[record.raw_locator.raw_object_id].append((record, event))

    for record in observed_records:
        if record.record_type == "standing":
            result = _standing_result(record, source_manifest, events)
            _merge_event_result(result, canonical, audits, quarantines, findings)
        elif record.record_type == "result":
            values = _mapping(record.original_source_values)
            if source_id == "spicerack" and "pod" not in values:
                _retain_failure(
                    record,
                    "quality.spicerack_missing_pod",
                    audits,
                    quarantines,
                    findings,
                )
        elif record.record_type == "table" and source_id == "topdeck":
            _retain_topdeck_table_quality(record, audits, quarantines, findings)

    return EventCanonicalizationResult(
        records=tuple(sorted(canonical, key=lambda item: item.record_id)),
        audits=tuple(sorted(audits, key=lambda item: item.audit_id)),
        quarantines=tuple(
            sorted(
                {item.quarantine_id: item for item in quarantines}.values(),
                key=lambda item: item.quarantine_id,
            )
        ),
        finding_codes=tuple(sorted(findings)),
    )


def _standing_result(
    record: StagingRecord,
    manifest: SourceSnapshotManifest,
    events: Mapping[str, Sequence[tuple[StagingRecord, EventRecord]]],
) -> EventCanonicalizationResult:
    values = _mapping(record.original_source_values)
    candidates = events.get(record.raw_locator.raw_object_id, ())
    event_id = _text(values, "event_id", "eventId", "TID", "tid")
    if event_id is not None:
        candidates = tuple(item for item in candidates if item[1].event_id == event_id)
    if len(candidates) != 1:
        return _failure_result(record, "quality.event_context_ambiguous")
    event_record, event = candidates[0]
    canonical_deck_id = _canonical_deck_id(values)
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
        return _failure_result(
            record,
            normalized.finding_codes[0]
            if normalized.finding_codes
            else "quality.observation_contract_invalid",
            extra_findings=normalized.finding_codes,
        )
    canonical = canonical_record_from_domain(
        normalized.observation,
        source_record_id=record.staging_record_id,
        raw_locator=record.raw_locator,
        provenance=provenance_for(record, manifest, f"{manifest.source_id}-event-mapper-v1"),
        observed_at=normalized.observation.observed_at,
    )
    return EventCanonicalizationResult((canonical,), (), (), normalized.finding_codes)


def _retain_topdeck_table_quality(
    record: StagingRecord,
    audits: list[AuditRecord],
    quarantines: list[QuarantineRecord],
    findings: set[str],
) -> None:
    values = _mapping(record.original_source_values)
    players = values.get("players")
    if not isinstance(players, list) or not _text(values, "event_id", "eventId"):
        _retain_failure(record, "quality.pod_context_missing", audits, quarantines, findings)
        return
    if not _positive_int(values, "round", "round_number"):
        _retain_failure(record, "quality.pod_round_missing", audits, quarantines, findings)
        return
    if any(not isinstance(item, Mapping) or _canonical_deck_id(item) is None for item in players):
        _retain_failure(record, "quality.pod_deck_unresolved", audits, quarantines, findings)


def _merge_event_result(
    result: EventCanonicalizationResult,
    records: list[CanonicalRecord],
    audits: list[AuditRecord],
    quarantines: list[QuarantineRecord],
    findings: set[str],
) -> None:
    records.extend(result.records)
    audits.extend(result.audits)
    quarantines.extend(result.quarantines)
    findings.update(result.finding_codes)


def _failure_result(
    record: StagingRecord,
    code: str,
    *,
    extra_findings: Sequence[str] = (),
) -> EventCanonicalizationResult:
    findings = tuple(sorted({code, *extra_findings}))
    return EventCanonicalizationResult(
        records=(),
        audits=(_audit(record, findings[0]),),
        quarantines=(quarantine_record(record, reason_code=findings[0]),),
        finding_codes=findings,
    )


def _retain_failure(
    record: StagingRecord,
    code: str,
    audits: list[AuditRecord],
    quarantines: list[QuarantineRecord],
    findings: set[str],
) -> None:
    audits.append(_audit(record, code))
    quarantines.append(quarantine_record(record, reason_code=code))
    findings.add(code)


def _audit(record: StagingRecord, code: str) -> AuditRecord:
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
    return SourceEvidence(
        raw_locator=record.raw_locator,
        provenance=provenance_for(record, manifest, f"{source_id}-event-mapper-v1"),
    )


def _participant(values: Mapping[str, object], evidence: SourceEvidence) -> ParticipantInput | None:
    raw_player = values.get("player")
    display_name = _text(values, "name")
    if isinstance(raw_player, Mapping):
        display_name = display_name or _text(raw_player, "name", "display_name")
    elif isinstance(raw_player, str):
        display_name = display_name or raw_player
    opaque = _text(values, "player_id", "playerId", "player_id")
    if opaque is None and isinstance(raw_player, Mapping):
        opaque = _text(raw_player, "player_id", "playerId", "id")
    return (
        ParticipantInput(
            evidence=evidence,
            source_opaque_id=opaque,
            display_name=display_name,
        )
        if opaque is not None or display_name is not None
        else None
    )


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _text(values: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            text = str(value).strip()
            if text:
                return text
    return None


def _canonical_deck_id(values: Mapping[str, object]) -> str | None:
    value = _text(values, "canonical_deck_id", "canonicalDeckId")
    return value if value is not None and _DECK_ID.fullmatch(value) else None


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


__all__ = ["EventCanonicalizationResult", "canonicalize_event_sources"]
