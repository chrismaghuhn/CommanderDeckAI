"""Task-specific curated row projections for dataset Parquet artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
from typing import TYPE_CHECKING

from commander_ai.adapters.storage.parquet_tables import CuratedRow
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.data_pipeline.splitting.deck_completion_policy import (
    DeckCompletionSplitResult,
)
from commander_ai.data_pipeline.splitting.group_promotion import (
    SplitAssignment,
    TemporalCutoffs,
    TemporalRecord,
    assign_provisional_splits,
)
from commander_ai.data_pipeline.splitting.tournament_policy import TournamentSplitResult

if TYPE_CHECKING:
    from .dataset_builder import DatasetProjectionRecord

_PRIVATE_PAYLOAD_KEYS = frozenset(
    {
        "accountid",
        "accounthandle",
        "accountname",
        "discord",
        "discordid",
        "displayname",
        "displayid",
        "email",
        "emailaddress",
        "handle",
        "contactemail",
        "contactphone",
        "participantid",
        "participantname",
        "participantfullname",
        "playerhandle",
        "playerid",
        "playerdisplayname",
        "playername",
        "playerfullname",
        "playerusername",
        "rawplayername",
        "realname",
        "screenname",
        "userhandle",
        "userid",
        "username",
        "phone",
        "phonenumber",
    }
)
_PRIVATE_CONTAINER_KEYS = frozenset(
    {
        "account",
        "accounts",
        "participant",
        "participants",
        "player",
        "players",
        "user",
        "users",
    }
)
_PRIVATE_NESTED_KEYS = frozenset({"displayid", "displayname", "handle", "id", "name", "username"})


def completion_rows(
    dataset_id: str,
    result: DeckCompletionSplitResult,
    *,
    row_schema: str,
) -> tuple[CuratedRow, ...]:
    records = {record.record_id: record for record in result.eligible_records}
    rows: list[CuratedRow] = []
    for assignment in result.assignments:
        record = records[assignment.record_id]
        deck = record.occurrence.deck
        values = {
            "schema_version": row_schema,
            "record_id": record.record_id,
            "split": assignment.split,
            "canonical_deck_id": record.canonical_deck_id,
            "source_id": record.occurrence.source.source_id,
            "source_deck_id": record.occurrence.source.source_deck_id,
            "source_snapshot_id": record.occurrence.source.source_snapshot_id,
            "observed_at": record.observed_at.isoformat(),
            "mode": record.mode,
            "group_ids": list(assignment.group_ids),
            "command_zone": [entry.model_dump(mode="json") for entry in deck.command_zone],
            "card_zones": [zone.model_dump(mode="json") for zone in deck.card_zones],
            "payload": safe_payload(record.payload),
        }
        rows.append(CuratedRow(curated_id=f"{dataset_id}:{record.record_id}", values=values))
    return tuple(rows)


def cooccurrence_rows(
    dataset_id: str,
    result: DeckCompletionSplitResult,
) -> tuple[CuratedRow, ...]:
    """Project each eligible deck into commander-card and card-card relations."""

    records = {record.record_id: record for record in result.eligible_records}
    rows: list[CuratedRow] = []
    for assignment in result.assignments:
        record = records[assignment.record_id]
        deck = record.occurrence.deck
        commanders = tuple(dict.fromkeys(entry.oracle_id.lower() for entry in deck.command_zone))
        cards = tuple(
            sorted({entry.oracle_id.lower() for zone in deck.card_zones for entry in zone.cards})
        )
        base_values = {
            "schema_version": "card-cooccurrence.v1",
            "record_id": record.record_id,
            "split": assignment.split,
            "canonical_deck_id": record.canonical_deck_id,
            "source_id": record.occurrence.source.source_id,
            "observed_at": record.observed_at.isoformat(),
            "group_ids": list(assignment.group_ids),
        }
        for commander_id, card_id in (
            (commander_id, card_id) for commander_id in commanders for card_id in cards
        ):
            rows.append(
                CuratedRow(
                    curated_id=f"{dataset_id}:{record.record_id}:commander_card:{commander_id}:{card_id}",
                    values={
                        **base_values,
                        "relation_type": "commander_card",
                        "left_id": commander_id,
                        "right_id": card_id,
                    },
                )
            )
        for left_id, right_id in combinations(cards, 2):
            rows.append(
                CuratedRow(
                    curated_id=f"{dataset_id}:{record.record_id}:card_card:{left_id}:{right_id}",
                    values={
                        **base_values,
                        "relation_type": "card_card",
                        "left_id": left_id,
                        "right_id": right_id,
                    },
                )
            )
    return tuple(rows)


def tournament_rows(dataset_id: str, result: TournamentSplitResult) -> tuple[CuratedRow, ...]:
    records = {record.record_id: record for record in result.eligible_records}
    strata = dict(result.familiar_strata)
    rows: list[CuratedRow] = []
    for assignment in result.assignments:
        record = records[assignment.record_id]
        values = {
            "schema_version": "tournament-corpus.v1",
            "record_id": record.record_id,
            "split": assignment.split,
            "event_id": record.event_id,
            "canonical_deck_id": record.canonical_deck_id,
            "observed_at": record.observed_at.isoformat(),
            "familiar_stratum": strata[record.record_id],
            "group_ids": list(assignment.group_ids),
            "payload": safe_payload(record.payload),
        }
        rows.append(CuratedRow(curated_id=f"{dataset_id}:{record.record_id}", values=values))
    return tuple(rows)


def projection_rows(
    settings: DatasetSettings,
    records: tuple[DatasetProjectionRecord, ...],
    row_schema: str,
) -> tuple[tuple[CuratedRow, ...], tuple[SplitAssignment, ...]]:
    train_until = settings.split_policy.train_until
    validation_until = settings.split_policy.validation_until
    if train_until is None or validation_until is None:
        raise ValueError("dataset split policy requires explicit cutoffs")
    temporal = assign_provisional_splits(
        tuple(TemporalRecord(record.record_id, record.observed_at) for record in records),
        TemporalCutoffs(train_until, validation_until),
    )
    by_id = {record.record_id: record for record in records}
    rows = tuple(
        CuratedRow(
            curated_id=f"{settings.dataset_id}:{assignment.record_id}",
            values={
                "schema_version": row_schema,
                "record_id": assignment.record_id,
                "split": assignment.split,
                "observed_at": by_id[assignment.record_id].observed_at.isoformat(),
                "payload": safe_payload(by_id[assignment.record_id].payload),
            },
        )
        for assignment in temporal
    )
    return rows, temporal


def safe_payload(value: Mapping[str, object]) -> dict[str, object]:
    result = _safe_value(value)
    if not isinstance(result, dict):
        raise TypeError("safe payload must remain a mapping")
    return result


def _safe_value(
    value: object,
    *,
    key: str | None = None,
    private_context: bool = False,
) -> object:
    normalized_key = _privacy_key(key) if key is not None else None
    if (
        normalized_key in _PRIVATE_PAYLOAD_KEYS
        or (
            normalized_key in _PRIVATE_CONTAINER_KEYS
            and not isinstance(value, (Mapping, list, tuple))
        )
        or (private_context and normalized_key in _PRIVATE_NESTED_KEYS)
    ):
        return "[EXCLUDED]"
    if isinstance(value, Mapping):
        nested_context = private_context or normalized_key in _PRIVATE_CONTAINER_KEYS
        return {
            str(item_key): _safe_value(
                item,
                key=str(item_key),
                private_context=nested_context,
            )
            for item_key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [_safe_value(item, private_context=private_context) for item in value]
    return value


def _privacy_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


__all__ = [
    "completion_rows",
    "cooccurrence_rows",
    "projection_rows",
    "safe_payload",
    "tournament_rows",
]
