"""Conservative TopDeck table-to-pod canonicalization."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from commander_ai.data_pipeline.events.event_records import EventRecord
from commander_ai.data_pipeline.events.participants import ParticipantInput
from commander_ai.data_pipeline.events.pod_entries import PodMemberInput, PodRecord, normalize_pod
from commander_ai.data_pipeline.provenance.evidence import SourceEvidence
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.provenance import SourceSnapshotManifest

from .canonical_records import CanonicalRecord, canonical_record_from_domain
from .canonicalization_support import observed_at, source_evidence

_DECK_ID = re.compile(r"^[a-f0-9]{64}$")
_DIRECT_RESULTS: dict[str, Literal["win", "loss", "draw", "bye", "unknown"]] = {
    "win": "win",
    "won": "win",
    "loss": "loss",
    "lost": "loss",
    "draw": "draw",
    "tie": "draw",
    "bye": "bye",
    "unknown": "unknown",
}
_PLACED_RESULTS: dict[str, tuple[Literal["win", "loss"], int]] = {
    "winner": ("win", 1),
    "first": ("win", 1),
    "second": ("loss", 2),
    "third": ("loss", 3),
    "fourth": ("loss", 4),
}


@dataclass(frozen=True, slots=True)
class TopDeckPodMapping:
    """Canonical pod records or fail-closed findings for one table."""

    records: tuple[CanonicalRecord, ...]
    finding_codes: tuple[str, ...]


def canonicalize_topdeck_table(
    record: StagingRecord,
    *,
    event_candidates: Sequence[tuple[StagingRecord, EventRecord]],
    round_number: int | None,
    source_manifest: SourceSnapshotManifest,
    deck_bindings: Mapping[tuple[str, str], str] | None = None,
) -> TopDeckPodMapping:
    """Map one complete TopDeck table to grouped PodEntry records."""

    values = _mapping(record.original_source_values)
    if not event_candidates:
        return _failure("quality.pod_context_missing")
    event = _select_event(values, event_candidates)
    if event is None:
        return _failure("quality.event_context_ambiguous")
    pod_id = _text(values, "pod_id", "podId", "table_id", "tableId", "table", "id")
    players = _mapping_sequence(values.get("players"))
    if pod_id is None or round_number is None or players is None:
        return _failure("quality.pod_context_missing")
    if len(players) < 2:
        return _failure("quality.pod_not_multiplayer")

    evidence = source_evidence(record, source_manifest, "topdeck-pod-mapper-v1")
    members = tuple(
        _member(
            player,
            values,
            players,
            evidence,
            event_id=event.event_id,
            deck_bindings=deck_bindings or {},
        )
        for player in players
    )
    normalized = normalize_pod(
        PodRecord(
            pod_id=pod_id,
            event_id=event.event_id,
            round_number=round_number,
            occurred_at=event.observed_at or observed_at(record, source_manifest),
            source_status=_text(values, "status"),
            members=members,
            evidence=evidence,
        ),
        allow_source_opaque_participant_id=True,
    )
    if normalized.pod is None:
        return _failure(*normalized.finding_codes)

    canonical = tuple(
        canonical_record_from_domain(
            entry,
            source_record_id=f"{record.staging_record_id}:seat:{entry.seat}",
            raw_locator=record.raw_locator,
            provenance=evidence.provenance,
            observed_at=event.observed_at or observed_at(record, source_manifest),
        )
        for entry in normalized.pod.entries
    )
    return TopDeckPodMapping(canonical, normalized.finding_codes)


def _select_event(
    values: Mapping[str, object],
    candidates: Sequence[tuple[StagingRecord, EventRecord]],
) -> EventRecord | None:
    event_id = _text(values, "event_id", "eventId", "TID", "tid")
    selected = tuple(
        item for item in candidates if event_id is None or item[1].event_id == event_id
    )
    return selected[0][1] if len(selected) == 1 else None


def _member(
    values: Mapping[str, object],
    table_values: Mapping[str, object],
    players: Sequence[Mapping[str, object]],
    evidence: SourceEvidence,
    *,
    event_id: str,
    deck_bindings: Mapping[tuple[str, str], str],
) -> PodMemberInput:
    player_id = _player_id(values)
    player_name = _player_name(values)
    raw_result = _text(values, "result", "outcome")
    result, mapped_placement, ambiguous = _result(
        raw_result,
        player_id=player_id,
        table_values=table_values,
        players=players,
    )
    if ambiguous:
        result = "ambiguous"
    placement = _positive_int(values, "placement", "place", "rank") or mapped_placement
    points = _finite_float(values.get("points"))
    canonical_deck_id = _canonical_deck_id(values) or (
        deck_bindings.get((event_id, player_id)) if player_id is not None else None
    )
    participant = (
        ParticipantInput(
            evidence=evidence,
            source_opaque_id=player_id,
            display_name=player_name,
        )
        if player_id is not None or player_name is not None
        else None
    )
    return PodMemberInput(
        seat=_positive_int(values, "seat"),
        canonical_deck_id=canonical_deck_id,
        result=result,
        participant=participant,
        points=points,
        placement=placement,
    )


def _result(
    raw_result: str | None,
    *,
    player_id: str | None,
    table_values: Mapping[str, object],
    players: Sequence[Mapping[str, object]],
) -> tuple[str, int | None, bool]:
    normalized = raw_result.casefold().strip() if raw_result is not None else None
    if normalized is None or normalized == "unknown":
        winner_id = _text(table_values, "winner_id", "winnerId")
        player_ids = tuple(_player_id(item) for item in players)
        if winner_id is not None and player_id is not None and player_ids.count(winner_id) == 1:
            return ("win" if player_id == winner_id else "loss", None, False)
        return ("unknown", None, False)
    if normalized in _DIRECT_RESULTS:
        return (_DIRECT_RESULTS[normalized], None, False)
    placed = _PLACED_RESULTS.get(normalized)
    if placed is not None:
        return placed[0], placed[1], False
    return "unknown", None, True


def _mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _mapping_sequence(value: object) -> tuple[Mapping[str, object], ...] | None:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        return None
    if not all(isinstance(item, Mapping) for item in value):
        return None
    return tuple(item for item in value if isinstance(item, Mapping))


def _text(values: Mapping[str, object], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, (str, int)) and not isinstance(value, bool):
            text = str(value).strip()
            if text:
                return text
    return None


def _player_id(values: Mapping[str, object]) -> str | None:
    direct = _text(values, "player_id", "playerId", "id")
    if direct is not None:
        return direct
    nested = values.get("player")
    return _text(_mapping(nested), "player_id", "playerId", "id")


def _player_name(values: Mapping[str, object]) -> str | None:
    direct = _text(values, "name", "display_name", "displayName", "handle", "username")
    if direct is not None:
        return direct
    nested = values.get("player")
    if isinstance(nested, str):
        return nested.strip() or None
    return _text(
        _mapping(nested),
        "name",
        "display_name",
        "displayName",
        "handle",
        "username",
    )


def _canonical_deck_id(values: Mapping[str, object]) -> str | None:
    value = _text(values, "canonical_deck_id", "canonicalDeckId")
    return value if value is not None and _DECK_ID.fullmatch(value) else None


def _positive_int(values: Mapping[str, object], *keys: str) -> int | None:
    for key in keys:
        value = values.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError:
                continue
            if parsed > 0:
                return parsed
    return None


def _finite_float(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    parsed = float(value)
    return parsed if math.isfinite(parsed) else None


def _failure(*codes: str) -> TopDeckPodMapping:
    findings = tuple(sorted(set(codes)))
    return TopDeckPodMapping((), findings or ("quality.pod_context_missing",))


__all__ = ["TopDeckPodMapping", "canonicalize_topdeck_table"]
