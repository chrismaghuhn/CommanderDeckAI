"""Source-neutral canonicalization after the source-specific staging boundary."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import Literal, cast

from commander_ai.data_pipeline.combos.normalized import normalize_combo
from commander_ai.data_pipeline.decks.canonical_decks import (
    DeckCanonicalizationError,
    DeckSourceReference,
    DeckStructureInput,
    canonical_deck_from_input,
)
from commander_ai.data_pipeline.provenance.rows import AuditRecord, ProvenanceRow, ResolutionAttempt
from commander_ai.data_pipeline.quality.finding_codes import FindingNamespace
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord, quarantine_record
from commander_ai.data_pipeline.resolution.card_catalog import build_card_catalog
from commander_ai.data_pipeline.resolution.card_resolution import CardResolver
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.decks import (
    CardZone,
    CommandZoneEntry,
    CommandZoneRelationship,
)
from commander_ai.domain.provenance import SourceSnapshotManifest

from .canonical_records import CanonicalRecord, canonical_record_from_domain
from .canonicalization_events import canonicalize_event_sources
from .canonicalization_result import CanonicalizationResult
from .canonicalization_support import (
    domain_combo_card,
    items,
    observed_at,
    provenance_for,
    record_for_value,
    resolve_item,
    resolve_zone,
    source_deck_id,
    source_manifest_object,
    spellbook_combo_record,
)


def canonicalize_staging(
    records: Sequence[StagingRecord],
    *,
    source_manifest: SourceSnapshotManifest,
    attempted_at: datetime | None = None,
) -> CanonicalizationResult:
    """Canonicalize only observed staging rows with source-specific mappings."""

    if source_manifest.status != "COMPLETE":
        raise ValueError("canonicalization requires a COMPLETE source manifest")
    resolution_at = attempted_at or source_manifest.completed_at or source_manifest.started_at
    if source_manifest.source_id == "mtgjson":
        return _canonicalize_mtgjson(records, source_manifest, resolution_at)
    if source_manifest.source_id == "commander_spellbook":
        return _canonicalize_spellbook(records, source_manifest)
    if source_manifest.source_id in {"topdeck", "spicerack"}:
        event_result = canonicalize_event_sources(
            records,
            source_manifest=source_manifest,
        )
        return CanonicalizationResult(
            records=event_result.records,
            resolutions=(),
            resolution_attempts=(),
            audits=event_result.audits,
            provenance=(),
            quarantines=event_result.quarantines,
            finding_codes=event_result.finding_codes,
        )
    return CanonicalizationResult((), (), (), (), (), (), ())


def _canonicalize_mtgjson(
    records: Sequence[StagingRecord],
    source_manifest: SourceSnapshotManifest,
    attempted_at: datetime,
) -> CanonicalizationResult:
    card_mapper = "mtgjson-card-mapper-v1"
    catalog_result = build_card_catalog(
        records,
        card_snapshot_id=f"card-snapshot-{source_manifest.source_snapshot_id}",
        provenance_for=lambda record: provenance_for(record, source_manifest, card_mapper),
        mapper_version=card_mapper,
    )
    by_object_type: dict[tuple[str, str], list[StagingRecord]] = defaultdict(list)
    for record in records:
        if record.status == "OBSERVED":
            by_object_type[(record.raw_locator.raw_object_id, record.record_type)].append(record)
    canonical: list[CanonicalRecord] = []
    findings: set[str] = set(catalog_result.finding_codes)
    for value in (
        *catalog_result.catalog.cards,
        *catalog_result.catalog.faces,
        *catalog_result.catalog.printings,
    ):
        record_type = {
            "CanonicalCard": "card",
            "CardFace": "card_face",
            "Printing": "printing",
        }[type(value).__name__]
        source_record = record_for_value(value, by_object_type, record_type)
        if source_record is None:
            findings.add("quality.canonical_source_record_missing")
            continue
        canonical.append(
            canonical_record_from_domain(
                value,
                source_record_id=source_record.staging_record_id,
                raw_locator=source_record.raw_locator,
                provenance=provenance_for(source_record, source_manifest, card_mapper),
                observed_at=observed_at(source_record, source_manifest),
            )
        )

    resolutions: list[CardResolution] = []
    attempts: list[ResolutionAttempt] = []
    quarantines = list(catalog_result.quarantines)
    deck_records = [
        record
        for record in records
        if record.record_type == "deck_product" and record.status == "OBSERVED"
    ]
    resolver = CardResolver(catalog_result.catalog)
    for deck_record in deck_records:
        deck_result = _canonicalize_deck(
            deck_record,
            source_manifest=source_manifest,
            resolver=resolver,
            attempted_at=attempted_at,
        )
        canonical.extend(deck_result.records)
        resolutions.extend(deck_result.resolutions)
        attempts.extend(deck_result.resolution_attempts)
        quarantines.extend(deck_result.quarantines)
        findings.update(deck_result.finding_codes)

    audits = _audit_for_quarantines(quarantines)
    return _result(
        canonical,
        resolutions,
        attempts,
        audits,
        catalog_result.provenance_rows,
        quarantines,
        findings,
    )


def _canonicalize_deck(
    record: StagingRecord,
    *,
    source_manifest: SourceSnapshotManifest,
    resolver: CardResolver,
    attempted_at: datetime,
) -> CanonicalizationResult:
    values = record.original_source_values
    if not isinstance(values, Mapping):
        return _failed_record(record, "quality.deck_source_values_not_object")
    resolutions: list[CardResolution] = []
    attempts: list[ResolutionAttempt] = []
    quarantines: list[QuarantineRecord] = []
    findings: set[str] = set()

    command_values = items(values.get("commander"))
    partner_values = items(values.get("partner"))
    background_values = items(values.get("background"))
    command_entries: list[CommandZoneEntry] = []
    role_ids: dict[str, list[str]] = defaultdict(list)
    role_entries: tuple[
        tuple[Literal["commander", "partner", "background"], tuple[Mapping[str, object], ...]],
        ...,
    ] = (
        ("commander", command_values),
        ("partner", partner_values),
        ("background", background_values),
    )
    for role, entries in role_entries:
        for index, entry in enumerate(entries):
            resolved = resolve_item(
                record,
                entry,
                field_name=f"{role}[{index}]",
                resolver=resolver,
                attempted_at=attempted_at,
            )
            if resolved is None:
                findings.add("resolution.deck_card_unresolved")
                continue
            quantity, resolution_result = resolved
            resolution = resolution_result.resolution
            attempt = resolution_result.attempt
            resolutions.append(resolution)
            attempts.append(attempt)
            if resolution_result.quarantine is not None:
                quarantines.append(resolution_result.quarantine)
            if resolution.canonical_oracle_id is None:
                findings.add("resolution.deck_card_unresolved")
                continue
            command_entries.append(
                CommandZoneEntry(
                    oracle_id=resolution.canonical_oracle_id,
                    quantity=quantity,
                    printing_id=resolution.canonical_printing_id,
                    source_declared_role=role,
                )
            )
            role_ids[role].append(resolution.canonical_oracle_id)

    zones: list[CardZone] = []
    for zone_name, raw_value in (
        ("main_deck", values.get("mainBoard")),
        ("sideboard", values.get("sideBoard")),
    ):
        zone_cards = resolve_zone(
            record,
            raw_value,
            field_name=zone_name,
            resolver=resolver,
            resolutions=resolutions,
            attempts=attempts,
            findings=findings,
            quarantines=quarantines,
            attempted_at=attempted_at,
        )
        if zone_cards:
            zones.append(CardZone(zone=zone_name, cards=zone_cards))
    if not command_entries:
        findings.add("quality.command_zone_missing")
    if not zones:
        findings.add("quality.card_zones_missing")
    if findings:
        quarantines.append(quarantine_record(record, reason_code=sorted(findings)[0]))
        return _result((), resolutions, attempts, (), (), quarantines, findings)

    relationships: list[CommandZoneRelationship] = []
    if len(role_ids["partner"]) == 1 and len(role_ids["commander"]) == 1:
        relationships.append(
            CommandZoneRelationship(
                kind="partner", card_ids=(role_ids["commander"][0], role_ids["partner"][0])
            )
        )
    if len(role_ids["background"]) == 1 and len(role_ids["commander"]) == 1:
        relationships.append(
            CommandZoneRelationship(
                kind="background", card_ids=(role_ids["commander"][0], role_ids["background"][0])
            )
        )
    object_reference = source_manifest_object(record, source_manifest)
    source = DeckSourceReference(
        source_id=record.source_id,
        source_deck_id=source_deck_id(values, record),
        source_snapshot_id=record.raw_locator.source_snapshot_id,
        raw_object_id=record.raw_locator.raw_object_id,
        raw_sha256=object_reference.sha256,
        observed_at=observed_at(record, source_manifest),
    )
    try:
        deck = canonical_deck_from_input(
            DeckStructureInput(
                source=source,
                command_zone=tuple(command_entries),
                card_zones=tuple(zones),
                command_zone_relationships=tuple(relationships),
                provenance=provenance_for(record, source_manifest, "mtgjson-deck-mapper-v1"),
            )
        ).deck
    except (DeckCanonicalizationError, ValueError) as error:
        code = getattr(error, "reason_code", "quality.invalid_deck_structure")
        quarantines.append(quarantine_record(record, reason_code=code))
        findings.add(code)
        return _result((), resolutions, attempts, (), (), quarantines, findings)
    canonical = canonical_record_from_domain(
        deck,
        source_record_id=record.staging_record_id,
        raw_locator=record.raw_locator,
        provenance=provenance_for(record, source_manifest, "mtgjson-deck-mapper-v1"),
        observed_at=observed_at(record, source_manifest),
    )
    return _result((canonical,), resolutions, attempts, (), (), quarantines, findings)


def _canonicalize_spellbook(
    records: Sequence[StagingRecord], source_manifest: SourceSnapshotManifest
) -> CanonicalizationResult:
    canonical: list[CanonicalRecord] = []
    quarantines: list[QuarantineRecord] = []
    findings: set[str] = set()
    mapper = "commander-spellbook-combo-mapper-v1"
    for record in records:
        if record.record_type != "variant" or record.status != "OBSERVED":
            continue
        values = record.original_source_values
        if not isinstance(values, Mapping):
            quarantines.append(
                quarantine_record(record, reason_code="quality.combo_source_invalid")
            )
            findings.add("quality.combo_source_invalid")
            continue
        combo_result = normalize_combo(spellbook_combo_record(record, values, source_manifest))
        findings.update(combo_result.finding_codes)
        if combo_result.combo is None:
            quarantines.append(
                quarantine_record(
                    record,
                    reason_code=combo_result.finding_codes[0]
                    if combo_result.finding_codes
                    else "quality.combo_contract_invalid",
                )
            )
            continue
        canonical.append(
            canonical_record_from_domain(
                combo_result.combo,
                source_record_id=record.staging_record_id,
                raw_locator=record.raw_locator,
                provenance=provenance_for(record, source_manifest, mapper),
                observed_at=observed_at(record, source_manifest),
            )
        )
        for card in combo_result.cards:
            canonical.append(
                canonical_record_from_domain(
                    domain_combo_card(card),
                    source_record_id=record.staging_record_id,
                    raw_locator=record.raw_locator,
                    provenance=provenance_for(record, source_manifest, mapper),
                    observed_at=observed_at(record, source_manifest),
                )
            )
    return _result(
        canonical,
        (),
        (),
        _audit_for_quarantines(quarantines),
        (),
        quarantines,
        findings,
    )


def _failed_record(record: StagingRecord, code: str) -> CanonicalizationResult:
    return _result((), (), (), (), (), (quarantine_record(record, reason_code=code),), {code})


def _audit_for_quarantines(quarantines: Sequence[QuarantineRecord]) -> tuple[AuditRecord, ...]:
    return tuple(
        AuditRecord(
            audit_id=f"canonical-audit-{item.quarantine_id}",
            entity_id=item.staging_record_id,
            stage=cast(FindingNamespace, item.reason_code.split(".", maxsplit=1)[0]),
            finding_code=item.reason_code,
            raw_locator=item.raw_locator,
            details={"quarantine_id": item.quarantine_id},
        )
        for item in sorted(quarantines, key=lambda item: item.quarantine_id)
    )


def _result(
    records: Sequence[CanonicalRecord],
    resolutions: Sequence[CardResolution],
    attempts: Sequence[ResolutionAttempt],
    audits: Sequence[AuditRecord],
    provenance: Sequence[ProvenanceRow],
    quarantines: Sequence[QuarantineRecord],
    findings: Iterable[str],
) -> CanonicalizationResult:
    return CanonicalizationResult(
        records=tuple(sorted(records, key=lambda item: item.record_id)),
        resolutions=tuple(sorted(resolutions, key=lambda item: item.resolution_id)),
        resolution_attempts=tuple(sorted(attempts, key=lambda item: item.attempt_id)),
        audits=tuple(sorted(audits, key=lambda item: item.audit_id)),
        provenance=tuple(sorted(provenance, key=lambda item: item.provenance_id)),
        quarantines=tuple(
            sorted(
                {item.quarantine_id: item for item in quarantines}.values(),
                key=lambda item: item.quarantine_id,
            )
        ),
        finding_codes=tuple(sorted(set(findings))),
    )


__all__ = ["CanonicalizationResult", "canonicalize_staging", "source_manifest_object"]
