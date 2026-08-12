"""Expand a decoded TopDeck tournament payload into source records."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
from typing import cast

from pydantic import ValidationError

from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    RawLocator,
)

from .dto import (
    TopDeckDeckDTO,
    TopDeckEventDTO,
    TopDeckFinding,
    TopDeckParsedRecord,
    TopDeckPlayerDTO,
    TopDeckStandingDTO,
)
from .json_support import contains_malformed_value, json_safe_source_value

LocatorFactory = Callable[[str], RawLocator]


class TopDeckRecordFactory:
    """Create records and locators from one verified raw-object context."""

    def __init__(self, locator_factory: LocatorFactory) -> None:
        self._locator_factory = locator_factory

    def locator(self, pointer: str) -> RawLocator:
        return self._locator_factory(pointer)

    def child(self, parent: RawLocator, *tokens: int | str) -> RawLocator:
        parent_pointer = (
            parent.location.pointer if isinstance(parent.location, JsonPointerLocator) else ""
        )
        pieces = [piece for piece in parent_pointer.strip("/").split("/") if piece]
        pieces.extend(str(token) for token in tokens)
        pointer = "".join(f"/{piece.replace('~', '~0').replace('/', '~1')}" for piece in pieces)
        return self.locator(pointer)

    def record(
        self,
        record_type: str,
        locator: RawLocator,
        source_values: object,
        dto: object | None,
        findings: list[tuple[str, str]],
    ) -> TopDeckParsedRecord:
        ordered = sorted(findings, key=lambda item: item[0])
        finding_records = tuple(
            TopDeckFinding(code=code, message=message, raw_locator=locator)
            for code, message in ordered
        )
        return TopDeckParsedRecord(
            record_type=record_type,
            raw_locator=locator,
            source_values=json_safe_source_value(
                _sanitize_staging_value(record_type, source_values)
            ),
            dto=dto,
            finding_codes=tuple(code for code, _ in ordered),
            findings=finding_records,
        )

    def finding_record(
        self,
        record_type: str,
        locator: RawLocator,
        source_values: object,
        code: str,
        message: str,
    ) -> TopDeckParsedRecord:
        return self.record(record_type, locator, source_values, None, [(code, message)])


class TopDeckRecordParser:
    """Parse events, standings, decks, and round tables without canonicalizing."""

    def __init__(self, factory: TopDeckRecordFactory) -> None:
        self.factory = factory
        from .round_parser import TopDeckRoundParser

        self.round_parser = TopDeckRoundParser(factory)

    def parse(self, payload: object) -> tuple[TopDeckParsedRecord, ...]:
        root = self.factory.locator("")
        if not isinstance(payload, list):
            return (
                self.factory.finding_record(
                    "response",
                    root,
                    payload,
                    "parse.topdeck_invalid_response_envelope",
                    "TopDeck response must be an array of tournaments",
                ),
            )
        records: list[TopDeckParsedRecord] = []
        for event_index, event in enumerate(payload):
            records.extend(self._parse_event(event, self.factory.locator(f"/{event_index}")))
        return tuple(records)

    def _parse_event(self, event: object, locator: RawLocator) -> list[TopDeckParsedRecord]:
        if not isinstance(event, Mapping):
            return [
                self.factory.finding_record(
                    "event",
                    locator,
                    event,
                    "parse.topdeck_record_not_object",
                    "tournament record is not an object",
                )
            ]
        values = dict(event)
        try:
            dto: TopDeckEventDTO | None = TopDeckEventDTO(
                event_id=cast(str | int, _pick(values, "TID", "tid", "eventId", "event_id")),
                tournament_name=cast(str | None, _pick(values, "tournamentName", "name")),
                game=cast(str | None, _pick(values, "game")),
                format=cast(str | None, _pick(values, "format")),
                start_date=_pick(values, "startDate", "start_date"),
                event_at=_event_at(values),
                event_data=_pick(values, "eventData", "event_data"),
                standings=_pick(values, "standings"),
                rounds=_pick(values, "rounds"),
                top_cut=_pick(values, "topCut", "top_cut"),
            )
            findings: list[tuple[str, str]] = []
            if _pick(values, "format") is None:
                findings.append(("parse.topdeck_missing_format", "tournament format is missing"))
            if _pick(values, "startDate", "start_date") is None:
                findings.append(
                    ("parse.topdeck_missing_start_date", "tournament start date is missing")
                )
        except (TypeError, ValueError, ValidationError):
            dto = None
            findings = [
                ("parse.topdeck_invalid_event_shape", "tournament record is missing a valid TID")
            ]
        if dto is not None and contains_malformed_value(values):
            findings.append(
                (
                    "parse.topdeck_malformed_scalar",
                    "tournament record contains a non-standard JSON scalar",
                )
            )
        records = [self.factory.record("event", locator, values, dto, findings)]
        if dto is None:
            return records
        self._parse_standings(records, values, locator)
        self.round_parser.append_records(records, values, locator)
        return records

    def _parse_standings(
        self,
        records: list[TopDeckParsedRecord],
        event: Mapping[str, object],
        parent: RawLocator,
    ) -> None:
        if "standings" not in event:
            return
        standings = event["standings"]
        if not isinstance(standings, list):
            records.append(
                self.factory.finding_record(
                    "standing_collection",
                    self.factory.child(parent, "standings"),
                    standings,
                    "parse.topdeck_invalid_standings",
                    "standings is not an array",
                )
            )
            return
        for index, standing in enumerate(standings):
            locator = self.factory.child(parent, "standings", index)
            if not isinstance(standing, Mapping):
                records.append(
                    self.factory.finding_record(
                        "standing",
                        locator,
                        standing,
                        "parse.topdeck_record_not_object",
                        "standing record is not an object",
                    )
                )
                continue
            values = dict(standing)
            try:
                dto: TopDeckStandingDTO | None = TopDeckStandingDTO(
                    player_id=cast(str | int | None, _pick(values, "player_id", "playerId", "id")),
                    player=_pick(values, "player"),
                    deck=_pick(values, "deck"),
                    decklist=_pick(values, "decklist", "deckList"),
                    deck_obj=_pick(values, "deckObj", "deck_obj"),
                    commander=_pick(values, "commander", "commanders"),
                    place=_pick(values, "place", "standing", "rank"),
                    wins=_pick(values, "wins"),
                    losses=_pick(values, "losses"),
                    draws=_pick(values, "draws"),
                    record=_pick(values, "record"),
                )
                findings: list[tuple[str, str]] = []
            except (TypeError, ValueError, ValidationError):
                dto = None
                findings = [
                    ("parse.topdeck_invalid_standing_shape", "standing record has invalid fields")
                ]
            records.append(self.factory.record("standing", locator, values, dto, findings))
            self._parse_deck_and_player(records, values, locator)

    def _parse_deck_and_player(
        self,
        records: list[TopDeckParsedRecord],
        standing: Mapping[str, object],
        parent: RawLocator,
    ) -> None:
        deck_key = next((key for key in ("deckObj", "decklist", "deck") if key in standing), None)
        if deck_key is not None:
            raw_deck = standing[deck_key]
            deck_values = raw_deck if isinstance(raw_deck, Mapping) else {"value": raw_deck}
            records.append(
                self.factory.record(
                    "deck",
                    self.factory.child(parent, deck_key),
                    raw_deck,
                    TopDeckDeckDTO(
                        commander=_pick(deck_values, "commander", "commanders"),
                        decklist=_pick(deck_values, "decklist", "deckList", "cards"),
                        deck_obj=raw_deck if deck_key == "deckObj" else None,
                    ),
                    [],
                )
            )
        player_key = next(
            (key for key in ("player", "player_id", "playerId", "id") if key in standing), None
        )
        if player_key is None:
            return
        player_value = standing[player_key]
        player_values = (
            player_value if isinstance(player_value, Mapping) else {"player_id": player_value}
        )
        records.append(
            self.factory.record(
                "player",
                self.factory.child(parent, player_key),
                player_value,
                TopDeckPlayerDTO(
                    player_id=cast(
                        str | int | None, _pick(player_values, "player_id", "playerId", "id")
                    ),
                    name=_pick(player_values, "name", "displayName"),
                ),
                [],
            )
        )


def _pick(values: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in values:
            return values[key]
    return None


_PRIVATE_KEYS = frozenset({"email", "discord", "discordid", "discord_id", "attendees", "staff"})
_PARTICIPANT_NAME_KEYS = frozenset({"name", "displayname", "display_name"})


def _sanitize_staging_value(record_type: str, value: object) -> object:
    """Keep raw bytes as the evidence source while minimizing staged PII."""

    participant = record_type in {"player", "table_player"}
    if isinstance(value, Mapping):
        result: dict[str, object] = {}
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized in _PRIVATE_KEYS or (
                participant and normalized in _PARTICIPANT_NAME_KEYS
            ):
                continue
            child_participant = participant or (
                record_type == "standing" and normalized == "player"
            )
            result[str(key)] = _sanitize_nested(item, child_participant)
        return result
    return _sanitize_nested(value, participant)


def _sanitize_nested(value: object, participant: bool) -> object:
    if isinstance(value, Mapping):
        return {
            str(key): _sanitize_nested(item, participant)
            for key, item in value.items()
            if str(key).casefold() not in _PRIVATE_KEYS
            and not (participant and str(key).casefold() in _PARTICIPANT_NAME_KEYS)
        }
    if isinstance(value, list):
        return [_sanitize_nested(item, participant) for item in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_nested(item, participant) for item in value)
    return value


def _event_at(values: Mapping[str, object]) -> datetime | None:
    from .dto import parse_event_datetime

    return parse_event_datetime(_pick(values, "startDate", "start_date"))


__all__ = ["TopDeckRecordFactory", "TopDeckRecordParser"]
