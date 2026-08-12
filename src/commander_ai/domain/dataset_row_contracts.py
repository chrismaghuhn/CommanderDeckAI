"""Versioned contracts for task-specific curated dataset rows."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Annotated, Literal

from pydantic import AfterValidator, AwareDatetime, Field, model_validator

from .contract_validation import (
    JSONMapping,
    NonEmptyString,
    UniqueTuple,
    UUIDString,
    validate_json_mapping,
    validate_unique_items,
)
from .decks import CardZone, CommandZoneEntry, compute_structural_fingerprint
from .provenance import DomainModel

_EXCLUDED = "[EXCLUDED]"
_PRIVATE_KEYS = frozenset(
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
_PRIVATE_CONTAINERS = frozenset(
    {
        "account",
        "accounts",
        "participant",
        "participants",
        "player",
        "players",
        "user",
        "users",
        "items",
    }
)
_PRIVATE_NESTED_KEYS = frozenset({"displayid", "displayname", "handle", "id", "name", "username"})
_PRIVATE_MARKERS = (
    "address",
    "birth",
    "email",
    "firstname",
    "givenname",
    "familyname",
    "fullname",
    "ipaddress",
    "lastname",
    "legalname",
    "middlename",
    "passport",
    "phone",
    "postal",
    "realname",
    "socialsecurity",
    "street",
    "surname",
    "taxid",
    "zipcode",
)

UniqueNonEmptyStrings = Annotated[tuple[NonEmptyString, ...], AfterValidator(validate_unique_items)]
PrivacySafePayload = Annotated[
    JSONMapping, AfterValidator(lambda value: _validate_privacy_safe_payload(value))
]


def _privacy_key(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _is_private_key(value: str) -> bool:
    return any(marker in value for marker in _PRIVATE_MARKERS)


def _validate_privacy_safe_value(
    value: object,
    *,
    key: str | None = None,
    private_context: bool = False,
) -> None:
    normalized_key = _privacy_key(key) if key is not None else None
    private = (
        normalized_key in _PRIVATE_KEYS
        or (normalized_key is not None and _is_private_key(normalized_key))
        or (private_context and normalized_key in _PRIVATE_NESTED_KEYS)
    )
    if private:
        if value != _EXCLUDED:
            raise ValueError("dataset payload contains unsanitized participant data")
        return
    if isinstance(value, Mapping):
        nested_context = private_context or normalized_key in _PRIVATE_CONTAINERS
        for item_key, item in value.items():
            _validate_privacy_safe_value(item, key=str(item_key), private_context=nested_context)
    elif isinstance(value, (list, tuple)):
        nested_context = private_context or normalized_key in _PRIVATE_CONTAINERS
        for item in value:
            _validate_privacy_safe_value(item, private_context=nested_context)


def _validate_privacy_safe_payload(value: Mapping[str, object]) -> Mapping[str, object]:
    validate_json_mapping(value)
    _validate_privacy_safe_value(value)
    return value


class DatasetRow(DomainModel):
    """Common persisted envelope for a curated task row."""

    curated_id: NonEmptyString
    layer: Literal["curated"] = "curated"


class DeckCorpusValues(DomainModel):
    schema_version: Literal["deck-corpus.v1"] = "deck-corpus.v1"
    record_id: NonEmptyString
    split: Literal["train", "validation", "test"]
    canonical_deck_id: NonEmptyString
    source_id: NonEmptyString
    source_deck_id: NonEmptyString
    source_snapshot_id: NonEmptyString
    observed_at: AwareDatetime
    mode: NonEmptyString | None = None
    group_ids: UniqueNonEmptyStrings = Field(default_factory=tuple)
    command_zone: UniqueTuple[CommandZoneEntry] = Field(min_length=1)
    card_zones: UniqueTuple[CardZone] = Field(min_length=1)
    payload: PrivacySafePayload = Field(default_factory=dict)

    @model_validator(mode="after")
    def verify_structural_identity(self) -> DeckCorpusValues:
        _verify_structural_identity(self.canonical_deck_id, self.command_zone, self.card_zones)
        return self


class DeckCorpusRow(DatasetRow):
    values: DeckCorpusValues


class CardCooccurrenceValues(DomainModel):
    schema_version: Literal["card-cooccurrence.v1"] = "card-cooccurrence.v1"
    record_id: NonEmptyString
    split: Literal["train", "validation", "test"]
    canonical_deck_id: NonEmptyString
    source_id: NonEmptyString
    observed_at: AwareDatetime
    group_ids: UniqueNonEmptyStrings = Field(default_factory=tuple)
    relation_type: Literal["commander_card", "card_card"]
    left_id: UUIDString
    right_id: UUIDString

    @model_validator(mode="after")
    def reject_self_relation(self) -> CardCooccurrenceValues:
        if self.relation_type == "card_card" and self.left_id == self.right_id:
            raise ValueError("card-card relations must contain two distinct cards")
        return self


class CardCooccurrenceRow(DatasetRow):
    values: CardCooccurrenceValues


class CardCooccurrenceV2Values(DomainModel):
    """Co-occurrence row with the structure needed to audit split leakage."""

    schema_version: Literal["card-cooccurrence.v2"] = "card-cooccurrence.v2"
    record_id: NonEmptyString
    split: Literal["train", "validation", "test"]
    canonical_deck_id: NonEmptyString
    source_id: NonEmptyString
    source_deck_id: NonEmptyString
    source_snapshot_id: NonEmptyString
    observed_at: AwareDatetime
    group_ids: UniqueNonEmptyStrings = Field(default_factory=tuple)
    command_zone: UniqueTuple[CommandZoneEntry] = Field(min_length=1)
    card_zones: UniqueTuple[CardZone] = Field(min_length=1)
    relation_type: Literal["commander_card", "card_card"]
    left_id: UUIDString
    right_id: UUIDString

    @model_validator(mode="after")
    def reject_self_relation(self) -> CardCooccurrenceV2Values:
        _verify_structural_identity(self.canonical_deck_id, self.command_zone, self.card_zones)
        command_ids = {entry.oracle_id.lower() for entry in self.command_zone}
        card_ids = {card.oracle_id.lower() for zone in self.card_zones for card in zone.cards}
        if self.relation_type == "commander_card" and (
            self.left_id.lower() not in command_ids or self.right_id.lower() not in card_ids
        ):
            raise ValueError("commander-card relation must reference command and card zones")
        if self.relation_type == "card_card" and (
            self.left_id.lower() not in card_ids or self.right_id.lower() not in card_ids
        ):
            raise ValueError("card-card relation must reference cards in card zones")
        if self.relation_type == "card_card" and self.left_id == self.right_id:
            raise ValueError("card-card relations must contain two distinct cards")
        return self


class CardCooccurrenceV2Row(DatasetRow):
    values: CardCooccurrenceV2Values


def _verify_structural_identity(
    canonical_deck_id: str,
    command_zone: tuple[CommandZoneEntry, ...],
    card_zones: tuple[CardZone, ...],
) -> None:
    expected = compute_structural_fingerprint(command_zone, card_zones)
    if canonical_deck_id != expected:
        raise ValueError("canonical_deck_id must match persisted deck structure")


class TournamentCorpusValues(DomainModel):
    schema_version: Literal["tournament-corpus.v1"] = "tournament-corpus.v1"
    record_id: NonEmptyString
    split: Literal["train", "validation", "test"]
    event_id: NonEmptyString
    canonical_deck_id: NonEmptyString
    observed_at: AwareDatetime
    familiar_stratum: Literal["familiar", "unseen"]
    group_ids: UniqueNonEmptyStrings = Field(default_factory=tuple)
    payload: PrivacySafePayload = Field(default_factory=dict)


class TournamentCorpusRow(DatasetRow):
    values: TournamentCorpusValues


class ComboCorpusValues(DomainModel):
    schema_version: Literal["combo-corpus.v1"] = "combo-corpus.v1"
    record_id: NonEmptyString
    split: Literal["train", "validation", "test"]
    observed_at: AwareDatetime
    payload: PrivacySafePayload = Field(default_factory=dict)


class ComboCorpusRow(DatasetRow):
    values: ComboCorpusValues


_ROW_CONTRACTS: dict[str, type[DatasetRow]] = {
    "deck-corpus.v1": DeckCorpusRow,
    "card-cooccurrence.v1": CardCooccurrenceRow,
    "card-cooccurrence.v2": CardCooccurrenceV2Row,
    "tournament-corpus.v1": TournamentCorpusRow,
    "combo-corpus.v1": ComboCorpusRow,
}
TASK_DATASET_ROW_CONTRACTS: tuple[type[DatasetRow], ...] = tuple(_ROW_CONTRACTS.values())


def row_contract_for_schema(schema_version: str) -> type[DatasetRow]:
    """Return the strict persisted row contract for one dataset schema."""

    try:
        return _ROW_CONTRACTS[schema_version]
    except KeyError as error:
        raise ValueError(f"unsupported task-specific row schema: {schema_version}") from error


__all__ = [
    "TASK_DATASET_ROW_CONTRACTS",
    "CardCooccurrenceRow",
    "CardCooccurrenceV2Row",
    "CardCooccurrenceV2Values",
    "CardCooccurrenceValues",
    "ComboCorpusRow",
    "ComboCorpusValues",
    "DatasetRow",
    "DeckCorpusRow",
    "DeckCorpusValues",
    "TournamentCorpusRow",
    "TournamentCorpusValues",
    "row_contract_for_schema",
]
