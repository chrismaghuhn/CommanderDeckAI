"""Build source-shaped Spicerack records from one verified tournament value."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.staging.raw_locators import (
    ByteRangeLocator,
    JsonObjectEntryLocator,
    JsonPointerLocator,
    RawLocator,
    RecordIndexLocator,
)
from commander_ai.domain.provenance import DomainModel

from .dto import (
    SpicerackDecklistDTO,
    SpicerackEventDTO,
    SpicerackFinding,
    SpicerackParsedRecord,
    SpicerackPlayerDTO,
    SpicerackResultDTO,
    SpicerackStandingDTO,
)
from .json_support import contains_malformed_json_scalar
from .ndjson_locators import StandingRecordLocators
from .record_parser import sanitize_source_values
from .settings import SPICERACK_SOURCE_ID

RawLocation = str | int | ByteRangeLocator
ResolvedLocation = (
    JsonPointerLocator | JsonObjectEntryLocator | RecordIndexLocator | ByteRangeLocator
)


def event_records(
    value: object,
    verified: VerifiedSourceSnapshot,
    object_id: str,
    path: str,
    location: RawLocation,
    *,
    expand_nested: bool = True,
    nested_locations: tuple[StandingRecordLocators, ...] = (),
) -> list[SpicerackParsedRecord]:
    if not isinstance(value, Mapping):
        return [
            finding(
                "event",
                verified,
                object_id,
                path,
                location,
                "parse.spicerack_record_not_object",
                "tournament record must be an object",
            )
        ]
    records = [record("event", value, verified, object_id, path, location)]
    if not expand_nested:
        return records
    standings = value.get("standings")
    if standings is None:
        return records
    if not isinstance(standings, list):
        records.append(
            finding(
                "standing",
                verified,
                object_id,
                path,
                _field_error_location(location),
                "parse.spicerack_invalid_standings",
                "tournament standings must be an array",
            )
        )
        return records
    for index, standing in enumerate(standings):
        standing_location, player_location, decklist_location, result_location = _nested_locations(
            location, index, standing, nested_locations
        )
        if not isinstance(standing, Mapping):
            records.append(
                finding(
                    "standing",
                    verified,
                    object_id,
                    path,
                    standing_location,
                    "parse.spicerack_invalid_standing",
                    "standing record must be an object",
                )
            )
            continue
        records.append(record("standing", standing, verified, object_id, path, standing_location))
        if player_location is not None:
            records.append(record("player", standing, verified, object_id, path, standing_location))
        if decklist_location is not None and (
            "decklist" in standing or "decklist_text" in standing
        ):
            records.append(
                record(
                    "decklist",
                    {
                        key: standing[key]
                        for key in ("decklist", "decklist_text")
                        if key in standing
                    },
                    verified,
                    object_id,
                    path,
                    standing_location,
                )
            )
        if result_location is not None:
            records.append(
                record(
                    "result",
                    {
                        key: standing[key]
                        for key in (
                            "winsSwiss",
                            "lossesSwiss",
                            "draws",
                            "winsBracket",
                            "lossesBracket",
                        )
                        if key in standing
                    },
                    verified,
                    object_id,
                    path,
                    standing_location,
                )
            )
    return records


def record(
    record_type: str,
    value: object,
    verified: VerifiedSourceSnapshot,
    object_id: str,
    path: str,
    location: RawLocation,
) -> SpicerackParsedRecord:
    locator = make_locator(verified, object_id, path, location)
    if not isinstance(value, Mapping):
        return finding(
            record_type,
            verified,
            object_id,
            path,
            location,
            "parse.spicerack_record_not_object",
            "source record must be an object",
        )
    source_values = sanitize_source_values(record_type, value)
    dto_type = cast(
        type[DomainModel] | None,
        {
            "event": SpicerackEventDTO,
            "decklist": SpicerackDecklistDTO,
            "player": SpicerackPlayerDTO,
            "standing": SpicerackStandingDTO,
            "result": SpicerackResultDTO,
        }.get(record_type),
    )
    if dto_type is None:
        return SpicerackParsedRecord(
            record_type=record_type, raw_locator=locator, source_values=source_values
        )
    try:
        dto = dto_type.model_validate(source_values)
    except (TypeError, ValueError):
        return finding(
            record_type,
            verified,
            object_id,
            path,
            location,
            "parse.spicerack_invalid_record",
            "source record does not match the documented shape",
            source_values=source_values,
        )
    findings: list[SpicerackFinding] = []
    if contains_malformed_json_scalar(source_values):
        findings.append(
            SpicerackFinding(
                code="parse.spicerack_malformed_json_scalar",
                message="source contains a non-standard JSON scalar",
                raw_locator=locator,
            )
        )
    if record_type == "result" and "pod" not in source_values:
        findings.append(
            SpicerackFinding(
                code="quality.spicerack_missing_pod",
                message="source did not supply pod information",
                raw_locator=locator,
            )
        )
    return SpicerackParsedRecord(
        record_type=record_type,
        raw_locator=locator,
        source_values=source_values,
        dto=dto,
        finding_codes=tuple(item.code for item in findings),
        findings=tuple(findings),
    )


def finding(
    record_type: str,
    verified: VerifiedSourceSnapshot,
    object_id: str,
    path: str,
    location: RawLocation,
    code: str,
    message: str,
    *,
    source_values: object | None = None,
) -> SpicerackParsedRecord:
    locator = make_locator(verified, object_id, path, location)
    return SpicerackParsedRecord(
        record_type=record_type,
        raw_locator=locator,
        source_values={} if source_values is None else source_values,
        finding_codes=(code,),
        findings=(SpicerackFinding(code=code, message=message, raw_locator=locator),),
    )


def make_locator(
    verified: VerifiedSourceSnapshot,
    object_id: str,
    path: str,
    location: RawLocation,
) -> RawLocator:
    target: ResolvedLocation
    if isinstance(location, str):
        target = JsonPointerLocator(pointer=location)
    elif isinstance(location, int):
        target = RecordIndexLocator(index=location)
    else:
        target = location
    return RawLocator(
        source_id=SPICERACK_SOURCE_ID,
        source_snapshot_id=verified.manifest.source_snapshot_id,
        raw_object_id=object_id,
        raw_object_path=path,
        location=target,
    )


def _nested_locations(
    location: RawLocation,
    index: int,
    standing: object,
    nested_locations: tuple[StandingRecordLocators, ...],
) -> tuple[RawLocation, RawLocation | None, RawLocation | None, RawLocation | None]:
    if isinstance(location, str):
        base = f"{location}/standings/{index}"
        if not isinstance(standing, Mapping):
            return base, None, None, None
        return (
            base,
            _json_field_location(
                base,
                standing,
                ("player_id", "playerId", "id", "name", "display_name", "player_name"),
            ),
            _json_field_location(base, standing, ("decklist", "decklist_text")),
            _json_field_location(
                base,
                standing,
                ("winsSwiss", "lossesSwiss", "draws", "winsBracket", "lossesBracket"),
            ),
        )
    if index < len(nested_locations):
        nested = nested_locations[index]
        return nested.standing, nested.player, nested.decklist, nested.result
    return location, None, None, None


def _json_field_location(
    base: str, value: Mapping[object, object], keys: tuple[str, ...]
) -> str | None:
    for key in keys:
        if key in value:
            return f"{base}/{_escape_pointer_token(key)}"
    return None


def _escape_pointer_token(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


def _field_error_location(location: RawLocation) -> RawLocation:
    if isinstance(location, str):
        return f"{location}/standings"
    if isinstance(location, ByteRangeLocator):
        return ByteRangeLocator(start=location.start, end=location.start + 1)
    return location


__all__ = ["event_records", "finding"]
