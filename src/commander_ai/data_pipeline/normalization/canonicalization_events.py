"""Conservative event and pod mapping from source-shaped staging rows."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import datetime

from commander_ai.data_pipeline.events.event_records import EventRecord
from commander_ai.data_pipeline.events.pod_entries import index_complete_pods
from commander_ai.data_pipeline.provenance.rows import AuditRecord, ProvenanceRow, ResolutionAttempt
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord, quarantine_record
from commander_ai.data_pipeline.resolution.card_resolution import CardResolver
from commander_ai.data_pipeline.resolution.catalog_models import CardCatalog
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.provenance import SourceSnapshotManifest

from .canonical_records import CanonicalRecord
from .event_canonicalization_support import (
    EventCanonicalizationResult,
    audit,
    datetime_value,
    evidence_for_event,
    mapping_value,
    merge_event_result,
    standing_result,
    text_value,
)
from .topdeck_pod_mapping import canonicalize_topdeck_table


def canonicalize_event_sources(
    records: Sequence[StagingRecord],
    *,
    source_manifest: SourceSnapshotManifest,
    card_catalog: CardCatalog | None = None,
    attempted_at: datetime | None = None,
    allow_source_opaque_participant_id: bool = False,
) -> EventCanonicalizationResult:
    """Map only source records with enough semantics for safe canonicalization."""

    source_id = source_manifest.source_id
    events: dict[str, list[tuple[StagingRecord, EventRecord]]] = defaultdict(list)
    rounds: dict[str, list[tuple[str, int]]] = defaultdict(list)
    canonical: list[CanonicalRecord] = []
    audits: list[AuditRecord] = []
    quarantines: list[QuarantineRecord] = []
    findings: set[str] = set()
    resolutions: list[CardResolution] = []
    resolution_attempts: list[ResolutionAttempt] = []
    provenance: list[ProvenanceRow] = []
    deck_bindings: list[tuple[str, str, str]] = []
    observed_records = tuple(item for item in records if item.status == "OBSERVED")
    resolver = CardResolver(card_catalog) if card_catalog is not None else None
    resolution_at = attempted_at or source_manifest.completed_at or source_manifest.started_at

    for record in observed_records:
        if record.record_type != "event":
            continue
        values = mapping_value(record.original_source_values)
        event_id = text_value(values, "event_id", "eventId", "TID", "tid", "id")
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
            evidence=evidence_for_event(record, source_manifest, source_id),
            format=text_value(values, "format"),
            name=text_value(values, "tournamentName", "name"),
            observed_at=datetime_value(values, "startDate", "start_at", "event_at"),
            source_status=text_value(values, "status", "source_status"),
        )
        events[record.raw_locator.raw_object_id].append((record, event))
    for record in observed_records:
        if record.record_type != "round":
            continue
        values = mapping_value(record.original_source_values)
        round_number = _positive_int(values, "round", "round_number", "roundNumber")
        pointer = _json_pointer(record)
        if round_number is not None and pointer is not None:
            rounds[record.raw_locator.raw_object_id].append((pointer, round_number))

    for record in observed_records:
        if record.record_type == "standing":
            result = standing_result(
                record,
                source_manifest,
                events,
                resolver=resolver,
                attempted_at=resolution_at,
                allow_source_opaque_participant_id=allow_source_opaque_participant_id,
            )
            merge_event_result(
                result,
                canonical,
                audits,
                quarantines,
                findings,
                resolutions,
                resolution_attempts,
                provenance,
                deck_bindings,
            )
        elif record.record_type == "result":
            values = mapping_value(record.original_source_values)
            if source_id == "spicerack" and "pod" not in values:
                _retain_failure(
                    record,
                    "quality.spicerack_missing_pod",
                    audits,
                    quarantines,
                    findings,
                )
        elif record.record_type == "table" and source_id == "topdeck":
            table_result = canonicalize_topdeck_table(
                record,
                event_candidates=events.get(record.raw_locator.raw_object_id, ()),
                round_number=_round_for_table(record, rounds),
                source_manifest=source_manifest,
                deck_bindings={
                    (event_id, player_id): deck_id for event_id, player_id, deck_id in deck_bindings
                },
                allow_source_opaque_participant_id=allow_source_opaque_participant_id,
            )
            if table_result.records:
                canonical.extend(table_result.records)
                findings.update(table_result.finding_codes)
            else:
                _retain_failure(
                    record,
                    table_result.finding_codes[0],
                    audits,
                    quarantines,
                    findings,
                )
                findings.update(table_result.finding_codes)

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
        resolutions=tuple(sorted(resolutions, key=lambda item: item.resolution_id)),
        resolution_attempts=tuple(sorted(resolution_attempts, key=lambda item: item.attempt_id)),
        provenance=tuple(sorted(provenance, key=lambda item: item.provenance_id)),
        deck_bindings=tuple(sorted(set(deck_bindings))),
        pod_index=index_complete_pods(canonical),
    )


def _retain_failure(
    record: StagingRecord,
    code: str,
    audits: list[AuditRecord],
    quarantines: list[QuarantineRecord],
    findings: set[str],
) -> None:
    audits.append(audit(record, code))
    quarantines.append(quarantine_record(record, reason_code=code))
    findings.add(code)


def _json_pointer(record: StagingRecord) -> str | None:
    location = record.raw_locator.location
    return location.pointer if hasattr(location, "pointer") else None


def _round_for_table(
    record: StagingRecord,
    rounds: Mapping[str, Sequence[tuple[str, int]]],
) -> int | None:
    values = mapping_value(record.original_source_values)
    explicit_keys = ("round", "round_number", "roundNumber")
    if any(key in values for key in explicit_keys):
        return _positive_int(values, *explicit_keys)
    pointer = _json_pointer(record)
    if pointer is None:
        return None
    matches = [
        round_number
        for round_pointer, round_number in rounds.get(record.raw_locator.raw_object_id, ())
        if pointer.startswith(f"{round_pointer.rstrip('/')}/tables/")
    ]
    return matches[0] if len(matches) == 1 else None


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


__all__ = ["EventCanonicalizationResult", "canonicalize_event_sources"]
