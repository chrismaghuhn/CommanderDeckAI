"""Resolve source-shaped tournament decklists into structural deck records."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, cast

from commander_ai.data_pipeline.decks.canonical_decks import (
    DeckCanonicalizationError,
    DeckSourceReference,
    DeckStructureInput,
    canonical_deck_from_input,
)
from commander_ai.data_pipeline.provenance.rows import ResolutionAttempt
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord, quarantine_record
from commander_ai.data_pipeline.resolution.card_resolution import CardResolver, ResolutionResult
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.decks import CardQuantity, CardZone, CommandZoneEntry
from commander_ai.domain.provenance import SourceSnapshotManifest

from .canonical_records import CanonicalRecord, canonical_record_from_domain
from .canonicalization_support import (
    first,
    items,
    provenance_for,
    resolve_item,
    source_manifest_object,
)

_DECKLIST_LINE = re.compile(r"^\s*(?P<quantity>[1-9][0-9]*)\s+(?P<name>\S.+?)\s*$")
_COMMANDER_KEYS = ("commander", "commanders")
_DECK_ID_KEYS = ("deck_id", "deckId", "decklist_id", "decklistId")


@dataclass(frozen=True, slots=True)
class EventDeckResult:
    """One deck resolution result and all retained resolution evidence."""

    record: CanonicalRecord | None
    canonical_deck_id: str | None
    resolutions: tuple[CardResolution, ...] = ()
    resolution_attempts: tuple[ResolutionAttempt, ...] = ()
    quarantines: tuple[QuarantineRecord, ...] = ()
    finding_codes: tuple[str, ...] = ()


def canonicalize_event_deck(
    record: StagingRecord,
    values: Mapping[str, object],
    *,
    source_manifest: SourceSnapshotManifest,
    resolver: CardResolver | None,
    observed_at: datetime,
    attempted_at: datetime,
) -> EventDeckResult:
    """Create a canonical deck only when every source card resolves deterministically."""

    if _explicit_deck_id(values) is not None:
        return EventDeckResult(record=None, canonical_deck_id=_explicit_deck_id(values))
    if resolver is None:
        return _failure(record, "resolution.event_deck_card_catalog_missing")

    deck_values = _deck_values(values)
    command_entries: list[CommandZoneEntry] = []
    resolutions: list[CardResolution] = []
    attempts: list[ResolutionAttempt] = []
    quarantines: list[QuarantineRecord] = []
    findings: set[str] = set()
    for role, raw_items in _command_items(deck_values):
        for index, item in enumerate(raw_items):
            resolved = _resolve(
                record,
                item,
                field_name=f"{role}[{index}]",
                resolver=resolver,
                attempted_at=attempted_at,
                resolutions=resolutions,
                attempts=attempts,
                quarantines=quarantines,
                findings=findings,
            )
            if resolved is None:
                continue
            quantity, result = resolved
            resolution = result.resolution
            if resolution.canonical_oracle_id is None:
                findings.add("resolution.event_deck_card_unresolved")
                continue
            command_entries.append(
                CommandZoneEntry(
                    oracle_id=resolution.canonical_oracle_id,
                    printing_id=resolution.canonical_printing_id,
                    quantity=quantity,
                    source_declared_role=cast(
                        Literal["commander", "partner", "background", "companion", "unknown"],
                        role,
                    ),
                )
            )

    raw_mainboard = _mainboard(deck_values)
    if raw_mainboard is None:
        findings.add("quality.event_decklist_missing")
        mainboard_items: tuple[Mapping[str, object], ...] = ()
    else:
        mainboard_items, parse_finding = raw_mainboard
        if parse_finding is not None:
            findings.add(parse_finding)
    mainboard: list[CardQuantity] = []
    for index, item in enumerate(mainboard_items):
        resolved = _resolve(
            record,
            item,
            field_name=f"mainboard[{index}]",
            resolver=resolver,
            attempted_at=attempted_at,
            resolutions=resolutions,
            attempts=attempts,
            quarantines=quarantines,
            findings=findings,
        )
        if resolved is None:
            continue
        quantity, result = resolved
        resolution = result.resolution
        if resolution.canonical_oracle_id is None:
            findings.add("resolution.event_deck_card_unresolved")
            continue
        mainboard.append(
            CardQuantity(
                oracle_id=resolution.canonical_oracle_id,
                printing_id=resolution.canonical_printing_id,
                quantity=quantity,
            )
        )

    if not command_entries:
        findings.add("quality.command_zone_missing")
    if not mainboard:
        findings.add("quality.card_zones_missing")
    if findings:
        failed = _failure(record, sorted(findings)[0], extra_findings=tuple(findings))
        return EventDeckResult(
            record=None,
            canonical_deck_id=None,
            resolutions=tuple(resolutions),
            resolution_attempts=tuple(attempts),
            quarantines=tuple((*quarantines, *failed.quarantines)),
            finding_codes=tuple(sorted({*findings, *failed.finding_codes})),
        )

    reference = source_manifest_object(record, source_manifest)
    source_deck_id = _source_deck_id(
        deck_values,
        record,
        allow_generic_id=deck_values is not values,
    )
    source = DeckSourceReference(
        source_id=record.source_id,
        source_deck_id=source_deck_id,
        source_snapshot_id=record.raw_locator.source_snapshot_id,
        raw_object_id=record.raw_locator.raw_object_id,
        raw_sha256=reference.sha256,
        observed_at=observed_at,
    )
    try:
        deck = canonical_deck_from_input(
            DeckStructureInput(
                source=source,
                command_zone=tuple(command_entries),
                card_zones=(CardZone(zone="mainboard", cards=tuple(mainboard)),),
                provenance=provenance_for(record, source_manifest, "event-deck-mapper-v1"),
            )
        ).deck
    except (DeckCanonicalizationError, ValueError) as error:
        code = getattr(error, "reason_code", "quality.invalid_deck_structure")
        failed = _failure(record, code)
        return EventDeckResult(
            record=None,
            canonical_deck_id=None,
            resolutions=tuple(resolutions),
            resolution_attempts=tuple(attempts),
            quarantines=tuple((*quarantines, *failed.quarantines)),
            finding_codes=tuple(sorted({*findings, *failed.finding_codes})),
        )
    canonical = canonical_record_from_domain(
        deck,
        source_record_id=source.source_deck_id,
        raw_locator=record.raw_locator,
        provenance=provenance_for(record, source_manifest, "event-deck-mapper-v1"),
        observed_at=observed_at,
    )
    return EventDeckResult(
        record=canonical,
        canonical_deck_id=deck.canonical_deck_id,
        resolutions=tuple(resolutions),
        resolution_attempts=tuple(attempts),
        quarantines=tuple(quarantines),
        finding_codes=tuple(sorted(findings)),
    )


def _resolve(
    record: StagingRecord,
    item: Mapping[str, object],
    *,
    field_name: str,
    resolver: CardResolver,
    attempted_at: datetime,
    resolutions: list[CardResolution],
    attempts: list[ResolutionAttempt],
    quarantines: list[QuarantineRecord],
    findings: set[str],
) -> tuple[int, ResolutionResult] | None:
    result = resolve_item(
        record,
        item,
        field_name=field_name,
        resolver=resolver,
        attempted_at=attempted_at,
    )
    if result is None:
        findings.add("resolution.event_deck_card_unresolved")
        return None
    quantity, resolution_result = result
    resolutions.append(resolution_result.resolution)
    attempts.append(resolution_result.attempt)
    if resolution_result.quarantine is not None:
        quarantines.append(resolution_result.quarantine)
    return quantity, resolution_result


def _deck_values(values: Mapping[str, object]) -> Mapping[str, object]:
    nested = first(values, "deckObj", "deck_obj", "deck", default=None)
    if not isinstance(nested, Mapping):
        return values
    merged = dict(nested)
    for key in (
        *_COMMANDER_KEYS,
        "partner",
        "background",
        "decklist",
        "deckList",
        *_DECK_ID_KEYS,
    ):
        if key in values:
            value = values[key]
            if key in _DECK_ID_KEYS and (
                not isinstance(value, (str, int)) or not str(value).strip()
            ):
                continue
            merged[key] = value
    return merged


def _command_items(
    values: Mapping[str, object],
) -> tuple[tuple[str, tuple[Mapping[str, object], ...]], ...]:
    return tuple(
        (role, items(values.get(key)))
        for role, key in (
            ("commander", "commander"),
            ("commander", "commanders"),
            ("partner", "partner"),
            ("background", "background"),
        )
        if key in values
    )


def _mainboard(
    values: Mapping[str, object],
) -> tuple[tuple[Mapping[str, object], ...], str | None] | None:
    for key in ("cards", "mainboard", "mainBoard", "decklist_text", "decklist"):
        if key not in values:
            continue
        raw = values[key]
        if isinstance(raw, str):
            return _parse_text_decklist(raw)
        return items(raw), None
    return None


def _parse_text_decklist(value: str) -> tuple[tuple[Mapping[str, object], ...], str | None]:
    rows: list[Mapping[str, object]] = []
    nonempty = [line.strip() for line in value.splitlines() if line.strip()]
    if not nonempty:
        return (), "quality.event_decklist_empty"
    for line in nonempty:
        match = _DECKLIST_LINE.fullmatch(line)
        if match is None:
            return (), "parse.event_decklist_line_invalid"
        rows.append({"name": match.group("name"), "quantity": int(match.group("quantity"))})
    return tuple(rows), None


def _source_deck_id(
    values: Mapping[str, object], record: StagingRecord, *, allow_generic_id: bool = False
) -> str:
    keys: tuple[str, ...] = _DECK_ID_KEYS
    if allow_generic_id:
        keys += ("id",)
    keys += ("name",)
    for key in keys:
        value = values.get(key)
        if isinstance(value, (str, int)) and str(value).strip():
            return str(value).strip()
    return record.staging_record_id


def _explicit_deck_id(values: Mapping[str, object]) -> str | None:
    value = first(values, "canonical_deck_id", "canonicalDeckId", default=None)
    return (
        value.strip() if isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) else None
    )


def _failure(
    record: StagingRecord,
    code: str,
    *,
    extra_findings: Sequence[str] = (),
) -> EventDeckResult:
    findings = tuple(sorted({code, *extra_findings}))
    return EventDeckResult(
        record=None,
        canonical_deck_id=None,
        quarantines=(quarantine_record(record, reason_code=code),),
        finding_codes=findings,
    )


__all__ = ["EventDeckResult", "canonicalize_event_deck"]
