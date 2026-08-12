"""Preserve TopDeck round/table/player source records without flattening pods."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from commander_ai.data_pipeline.staging.raw_locators import RawLocator

from .dto import TopDeckParsedRecord, TopDeckPlayerDTO, TopDeckRoundDTO, TopDeckTableDTO
from .record_parser import TopDeckRecordFactory


class TopDeckRoundParser:
    """Append source round, table, and participant records to an event list."""

    def __init__(self, factory: TopDeckRecordFactory) -> None:
        self.factory = factory

    def append_records(
        self,
        records: list[TopDeckParsedRecord],
        event: Mapping[str, object],
        parent: RawLocator,
    ) -> None:
        if "rounds" not in event:
            return
        rounds = event["rounds"]
        if not isinstance(rounds, list):
            records.append(
                self.factory.finding_record(
                    "round_collection",
                    self.factory.child(parent, "rounds"),
                    rounds,
                    "parse.topdeck_invalid_rounds",
                    "rounds is not an array",
                )
            )
            return
        for round_index, raw_round in enumerate(rounds):
            self._append_round(records, raw_round, parent, round_index)

    def _append_round(
        self,
        records: list[TopDeckParsedRecord],
        raw_round: object,
        parent: RawLocator,
        round_index: int,
    ) -> None:
        round_locator = self.factory.child(parent, "rounds", round_index)
        if not isinstance(raw_round, Mapping):
            records.append(
                self.factory.finding_record(
                    "round",
                    round_locator,
                    raw_round,
                    "parse.topdeck_record_not_object",
                    "round record is not an object",
                )
            )
            return
        round_values = dict(raw_round)
        records.append(
            self.factory.record(
                "round",
                round_locator,
                round_values,
                TopDeckRoundDTO(
                    round_number=_pick(round_values, "round", "roundNumber"),
                    tables=_pick(round_values, "tables"),
                ),
                [],
            )
        )
        tables = round_values.get("tables")
        if not isinstance(tables, list):
            return
        for table_index, raw_table in enumerate(tables):
            self._append_table(records, raw_table, parent, round_index, table_index)

    def _append_table(
        self,
        records: list[TopDeckParsedRecord],
        raw_table: object,
        parent: RawLocator,
        round_index: int,
        table_index: int,
    ) -> None:
        table_locator = self.factory.child(parent, "rounds", round_index, "tables", table_index)
        if not isinstance(raw_table, Mapping):
            records.append(
                self.factory.finding_record(
                    "table",
                    table_locator,
                    raw_table,
                    "parse.topdeck_record_not_object",
                    "table record is not an object",
                )
            )
            return
        table_values = dict(raw_table)
        findings = (
            []
            if any(
                key in table_values
                for key in ("winner", "winner_id", "winnerId", "status", "result")
            )
            else [
                (
                    "parse.topdeck_ambiguous_result_semantics",
                    "table has no explicit winner or result status",
                )
            ]
        )
        records.append(
            self.factory.record(
                "table",
                table_locator,
                table_values,
                TopDeckTableDTO(
                    table_id=_pick(table_values, "table", "tableId", "id"),
                    players=_pick(table_values, "players"),
                    winner=_pick(table_values, "winner"),
                    winner_id=_pick(table_values, "winner_id", "winnerId"),
                    status=_pick(table_values, "status"),
                    result=_pick(table_values, "result"),
                ),
                findings,
            )
        )
        players = table_values.get("players")
        if not isinstance(players, list):
            return
        for player_index, raw_player in enumerate(players):
            player_locator = self.factory.child(
                parent,
                "rounds",
                round_index,
                "tables",
                table_index,
                "players",
                player_index,
            )
            values = raw_player if isinstance(raw_player, Mapping) else {"player_id": raw_player}
            records.append(
                self.factory.record(
                    "table_player",
                    player_locator,
                    raw_player,
                    TopDeckPlayerDTO(
                        player_id=cast(
                            str | int | None, _pick(values, "player_id", "playerId", "id")
                        ),
                        name=_pick(values, "name", "displayName"),
                        seat=_pick(values, "seat"),
                        result=_pick(values, "result"),
                        winner=_pick(values, "winner"),
                    ),
                    [],
                )
            )


def _pick(values: Mapping[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in values:
            return values[key]
    return None


__all__ = ["TopDeckRoundParser"]
