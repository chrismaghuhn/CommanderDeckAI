"""Byte-range locators for nested objects in one Spicerack NDJSON line."""

from __future__ import annotations

import json
from dataclasses import dataclass

from commander_ai.data_pipeline.staging.raw_locators import ByteRangeLocator


@dataclass(frozen=True, slots=True)
class StandingRecordLocators:
    standing: ByteRangeLocator
    player: ByteRangeLocator | None
    decklist: ByteRangeLocator | None
    result: ByteRangeLocator | None


def standing_object_ranges(
    payload: bytes, *, line_offset: int
) -> tuple[StandingRecordLocators, ...] | None:
    """Return exact byte ranges for the top-level ``standings`` objects."""

    try:
        value_range = _top_level_member_range(payload, "standings")
        if value_range is None:
            return ()
        start, end = value_range
        cursor = _skip_whitespace(payload, start)
        if cursor >= end or payload[cursor : cursor + 1] != b"[":
            return None
        cursor += 1
        ranges: list[StandingRecordLocators] = []
        while True:
            cursor = _skip_whitespace(payload, cursor)
            if cursor >= end:
                return None
            if payload[cursor : cursor + 1] == b"]":
                return tuple(ranges)
            item_start = cursor
            item_end = _skip_value(payload, item_start)
            if payload[item_start : item_start + 1] != b"{":
                return None
            standing_range = ByteRangeLocator(
                start=line_offset + item_start,
                end=line_offset + item_end,
            )
            item_payload = payload[item_start:item_end]
            ranges.append(
                StandingRecordLocators(
                    standing=standing_range,
                    player=_field_locator(
                        item_payload,
                        line_offset=line_offset + item_start,
                        keys=(
                            "player_id",
                            "playerId",
                            "id",
                            "name",
                            "display_name",
                            "player_name",
                        ),
                    ),
                    decklist=_field_locator(
                        item_payload,
                        line_offset=line_offset + item_start,
                        keys=("decklist", "decklist_text"),
                    ),
                    result=_field_locator(
                        item_payload,
                        line_offset=line_offset + item_start,
                        keys=(
                            "winsSwiss",
                            "lossesSwiss",
                            "draws",
                            "winsBracket",
                            "lossesBracket",
                        ),
                    ),
                )
            )
            cursor = _skip_whitespace(payload, item_end)
            if cursor >= end:
                return None
            token = payload[cursor : cursor + 1]
            if token == b",":
                cursor += 1
                continue
            if token == b"]":
                return tuple(ranges)
            return None
    except (IndexError, UnicodeDecodeError, ValueError, json.JSONDecodeError):
        return None


def _top_level_member_range(payload: bytes, key: str) -> tuple[int, int] | None:
    cursor = _skip_whitespace(payload, 0)
    if payload[cursor : cursor + 1] != b"{":
        return None
    cursor += 1
    while True:
        cursor = _skip_whitespace(payload, cursor)
        if payload[cursor : cursor + 1] == b"}":
            return None
        key_start = cursor
        key_end = _skip_string(payload, key_start)
        actual_key = json.loads(payload[key_start:key_end].decode("utf-8"))
        cursor = _skip_whitespace(payload, key_end)
        if payload[cursor : cursor + 1] != b":":
            return None
        value_start = _skip_whitespace(payload, cursor + 1)
        value_end = _skip_value(payload, value_start)
        if actual_key == key:
            return value_start, value_end
        cursor = _skip_whitespace(payload, value_end)
        if payload[cursor : cursor + 1] != b",":
            return None
        cursor += 1


def _field_locator(
    payload: bytes,
    *,
    line_offset: int,
    keys: tuple[str, ...],
) -> ByteRangeLocator | None:
    for key in keys:
        value_range = _top_level_member_range(payload, key)
        if value_range is not None:
            start, end = value_range
            return ByteRangeLocator(
                start=line_offset + start,
                end=line_offset + end,
            )
    return None


def _skip_value(payload: bytes, start: int) -> int:
    token = payload[start : start + 1]
    if token == b'"':
        return _skip_string(payload, start)
    if token == b"{":
        cursor = start + 1
        while True:
            cursor = _skip_whitespace(payload, cursor)
            if payload[cursor : cursor + 1] == b"}":
                return cursor + 1
            cursor = _skip_string(payload, cursor)
            cursor = _skip_whitespace(payload, cursor)
            if payload[cursor : cursor + 1] != b":":
                raise ValueError("object value is missing a colon")
            cursor = _skip_value(payload, _skip_whitespace(payload, cursor + 1))
            cursor = _skip_whitespace(payload, cursor)
            token = payload[cursor : cursor + 1]
            if token == b",":
                cursor += 1
                continue
            if token == b"}":
                return cursor + 1
            raise ValueError("object value has invalid separator")
    if token == b"[":
        cursor = start + 1
        while True:
            cursor = _skip_whitespace(payload, cursor)
            if payload[cursor : cursor + 1] == b"]":
                return cursor + 1
            cursor = _skip_value(payload, cursor)
            cursor = _skip_whitespace(payload, cursor)
            token = payload[cursor : cursor + 1]
            if token == b",":
                cursor += 1
                continue
            if token == b"]":
                return cursor + 1
            raise ValueError("array value has invalid separator")
    cursor = start
    while cursor < len(payload) and payload[cursor : cursor + 1] not in b" \t\r\n,]}:":
        cursor += 1
    if cursor == start:
        raise ValueError("JSON value is missing")
    return cursor


def _skip_string(payload: bytes, start: int) -> int:
    if payload[start : start + 1] != b'"':
        raise ValueError("JSON string is missing")
    cursor = start + 1
    while cursor < len(payload):
        token = payload[cursor : cursor + 1]
        if token == b"\\":
            cursor += 2
            continue
        if token == b'"':
            return cursor + 1
        cursor += 1
    raise ValueError("JSON string is unterminated")


def _skip_whitespace(payload: bytes, start: int) -> int:
    cursor = start
    while cursor < len(payload) and payload[cursor : cursor + 1] in b" \t\r\n":
        cursor += 1
    return cursor


__all__ = ["StandingRecordLocators", "standing_object_ranges"]
