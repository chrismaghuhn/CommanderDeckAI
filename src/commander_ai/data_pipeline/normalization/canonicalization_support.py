"""Small source-neutral helpers shared by canonicalization mappers."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from commander_ai.data_pipeline.combos.normalized import ComboCardInput, ComboRecord
from commander_ai.data_pipeline.provenance.evidence import SourceEvidence
from commander_ai.data_pipeline.provenance.rows import ResolutionAttempt
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.data_pipeline.resolution.card_resolution import (
    CardResolutionInput,
    CardResolver,
    ResolutionResult,
)
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CardResolution
from commander_ai.domain.combos import ComboCard
from commander_ai.domain.decks import CardQuantity
from commander_ai.domain.provenance import (
    ProvenanceReference,
    RawObjectReference,
    SourceSnapshotManifest,
)


def record_for_value(
    value: object,
    by_object_type: Mapping[tuple[str, str], list[StagingRecord]],
    record_type: str,
) -> StagingRecord | None:
    provenance = getattr(value, "provenance", ())
    object_ids = {item.source_object_id for item in provenance}
    candidates = [
        record
        for object_id in object_ids
        for record in by_object_type.get((object_id, record_type), ())
    ]
    return sorted(candidates, key=lambda item: item.staging_record_id)[0] if candidates else None


def provenance_for(
    record: StagingRecord,
    manifest: SourceSnapshotManifest,
    mapper_version: str,
) -> tuple[ProvenanceReference, ...]:
    reference = source_manifest_object(record, manifest)
    return (
        ProvenanceReference(
            source_id=record.source_id,
            source_snapshot_id=record.raw_locator.source_snapshot_id,
            source_object_id=reference.raw_object_id,
            raw_sha256=reference.sha256,
            retrieved_at=reference.retrieved_at,
            adapter_version=manifest.adapter_version,
            mapper_version=mapper_version,
            approval_status=manifest.approval_status,
        ),
    )


def source_manifest_object(
    record: StagingRecord,
    manifest: SourceSnapshotManifest,
) -> RawObjectReference:
    for reference in manifest.objects:
        if reference.raw_object_id == record.raw_locator.raw_object_id:
            return reference
    raise ValueError("staging record references an unknown source object")


def observed_at(record: StagingRecord, manifest: SourceSnapshotManifest) -> datetime:
    reference = source_manifest_object(record, manifest)
    return reference.retrieved_at or manifest.completed_at or manifest.started_at


def source_deck_id(values: Mapping[str, object], record: StagingRecord) -> str:
    for key in ("fileName", "file_name", "code", "name"):
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return record.staging_record_id


def items(value: object) -> tuple[Mapping[str, object], ...]:
    if isinstance(value, Mapping):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(item if isinstance(item, Mapping) else {"name": item} for item in value)
    if value is None:
        return ()
    return ({"name": value},)


def first(values: Mapping[str, object], *keys: str, default: object) -> object:
    for key in keys:
        if key in values:
            return values[key]
    return default


def positive_int(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = int(value)
        except ValueError:
            return 0
    else:
        return 0
    return parsed if parsed > 0 else 0


def feature_text(value: object) -> str:
    if isinstance(value, Mapping):
        nested = value.get("card") or value.get("feature") or value.get("template")
        if isinstance(nested, Mapping):
            return str(nested.get("name") or nested.get("id") or "").strip()
        return str(value.get("name") or value.get("id") or "").strip()
    return str(value).strip()


def spellbook_combo_record(
    record: StagingRecord,
    values: Mapping[str, object],
    manifest: SourceSnapshotManifest,
) -> ComboRecord:
    cards: list[ComboCardInput] = []
    for item in items(values.get("uses")):
        card = item.get("card")
        card_values = card if isinstance(card, Mapping) else item
        cards.append(
            ComboCardInput(
                oracle_id=str(first(card_values, "oracleId", "oracle_id", "id", default="unknown")),
                role="required",
                quantity=positive_int(first(item, "quantity", default=1)),
            )
        )
    requirements = tuple(feature_text(item) for item in items(values.get("requires")))
    results = tuple(feature_text(item) for item in items(values.get("produces")))
    commander_compatible = values.get("commanderCompatible")
    if not isinstance(commander_compatible, bool):
        commander_compatible = None
    return ComboRecord(
        combo_id=str(values.get("id", record.staging_record_id)),
        evidence=source_evidence(record, manifest),
        cards=tuple(cards),
        requirements=tuple(item for item in requirements if item),
        results=tuple(item for item in results if item),
        name=str(values.get("description")) if values.get("description") else None,
        source_status=str(values.get("status")) if values.get("status") else None,
        commander_compatible=commander_compatible,
    )


def source_evidence(
    record: StagingRecord,
    manifest: SourceSnapshotManifest,
    mapper_version: str = "canonicalizer-v1",
) -> SourceEvidence:
    return SourceEvidence(
        raw_locator=record.raw_locator,
        provenance=provenance_for(record, manifest, mapper_version),
    )


def domain_combo_card(value: ComboCard) -> ComboCard:
    return ComboCard.model_validate(value.model_dump(mode="json"))


def resolve_zone(
    record: StagingRecord,
    raw_value: object,
    *,
    field_name: str,
    resolver: CardResolver,
    resolutions: list[CardResolution],
    attempts: list[ResolutionAttempt],
    findings: set[str],
    quarantines: list[QuarantineRecord],
    attempted_at: datetime,
) -> tuple[CardQuantity, ...]:
    resolved: dict[tuple[str, str | None], int] = {}
    for index, item in enumerate(items(raw_value)):
        value = resolve_item(
            record,
            item,
            field_name=f"{field_name}[{index}]",
            resolver=resolver,
            attempted_at=attempted_at,
        )
        if value is None:
            findings.add("resolution.deck_card_unresolved")
            continue
        quantity, resolution_result = value
        resolution = resolution_result.resolution
        resolutions.append(resolution)
        attempts.append(resolution_result.attempt)
        if resolution_result.quarantine is not None:
            quarantines.append(resolution_result.quarantine)
        if resolution.canonical_oracle_id is None:
            findings.add("resolution.deck_card_unresolved")
            continue
        key = (resolution.canonical_oracle_id, resolution.canonical_printing_id)
        resolved[key] = resolved.get(key, 0) + quantity
    return tuple(
        CardQuantity(oracle_id=oracle_id, printing_id=printing_id, quantity=quantity)
        for (oracle_id, printing_id), quantity in sorted(resolved.items())
    )


def resolve_item(
    record: StagingRecord,
    item: object,
    *,
    field_name: str,
    resolver: CardResolver,
    attempted_at: datetime,
) -> tuple[int, ResolutionResult] | None:
    values = item if isinstance(item, Mapping) else {"name": item}
    name = first(
        values,
        "name",
        "cardName",
        "card",
        "oracleId",
        "oracle_id",
        "scryfallOracleId",
        "uuid",
        "printingId",
        "scryfallId",
        "mtgjsonId",
        default=None,
    )
    if not isinstance(name, str) or not name.strip():
        return None
    quantity = positive_int(first(values, "count", "quantity", default=1))
    if quantity < 1:
        return None
    result = resolver.resolve(
        CardResolutionInput(
            staging_record=record,
            original_value=name.strip(),
            source_field=field_name,
            requested_quantity=quantity,
            source_values=values,
        ),
        attempted_at=attempted_at,
    )
    return quantity, result


__all__ = [
    "domain_combo_card",
    "first",
    "items",
    "observed_at",
    "positive_int",
    "provenance_for",
    "record_for_value",
    "resolve_item",
    "resolve_zone",
    "source_deck_id",
    "source_evidence",
    "source_manifest_object",
    "spellbook_combo_record",
]
