"""Source-shaped Spicerack DTOs; no canonical event, deck, or pod semantics."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import (
    AliasChoices,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from commander_ai.data_pipeline.quality.finding_codes import validate_finding_code
from commander_ai.data_pipeline.staging.raw_locators import RawLocator
from commander_ai.domain.provenance import DomainModel, FrozenDict

from .json_support import json_safe_source_value


class _SpicerackModel(DomainModel):
    model_config = ConfigDict(
        extra="allow", frozen=True, populate_by_name=True, hide_input_in_errors=True
    )

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        extra = getattr(self, "model_extra", None)
        if extra is not None:
            object.__setattr__(
                self,
                "__pydantic_extra__",
                FrozenDict({str(key): _freeze(item) for key, item in extra.items()}),
            )


class SpicerackEventDTO(_SpicerackModel):
    event_id: StrictStr | StrictInt | None = Field(
        default=None, validation_alias=AliasChoices("id", "TID", "event_id")
    )
    name: StrictStr | None = Field(
        default=None, validation_alias=AliasChoices("name", "tournamentName")
    )
    format: StrictStr | None = None
    start_at: object | None = Field(
        default=None, validation_alias=AliasChoices("start_at", "startDate")
    )
    status: object | None = None
    source_status: object | None = None


class SpicerackDecklistDTO(_SpicerackModel):
    decklist_id: StrictStr | StrictInt | None = Field(
        default=None, validation_alias=AliasChoices("id", "decklist_id")
    )
    event_id: StrictStr | StrictInt | None = None
    player_id: StrictStr | StrictInt | None = None
    commander: object | None = None
    cards: object | None = None
    status: object | None = None
    source_status: object | None = None


class SpicerackPlayerDTO(_SpicerackModel):
    player_id: StrictStr | StrictInt | None = Field(
        default=None, validation_alias=AliasChoices("id", "player_id")
    )
    reference: object | None = None
    source_status: object | None = None


class SpicerackStandingDTO(_SpicerackModel):
    standing_id: StrictStr | StrictInt | None = Field(
        default=None, validation_alias=AliasChoices("id", "standing_id")
    )
    event_id: StrictStr | StrictInt | None = None
    player_id: StrictStr | StrictInt | None = None
    rank: object | None = None
    wins: object | None = None
    losses: object | None = None
    draws: object | None = None
    points: object | None = None
    status: object | None = None
    result_code: object | None = None


class SpicerackResultDTO(_SpicerackModel):
    result_id: StrictStr | StrictInt | None = Field(
        default=None, validation_alias=AliasChoices("id", "result_id")
    )
    event_id: StrictStr | StrictInt | None = None
    player_id: StrictStr | StrictInt | None = None
    round: object | None = None
    seat: object | None = None
    status: object | None = None
    result: object | None = None
    result_code: object | None = None
    source_status: object | None = None
    winner: object | None = None
    pod: object | None = None


class SpicerackFinding(DomainModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    raw_locator: RawLocator

    @field_validator("code")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        code = validate_finding_code(value)
        if code.split(".", maxsplit=1)[0] not in {"parse", "integrity", "quality"}:
            raise ValueError("Spicerack findings require parse, integrity, or quality namespaces")
        return code


class SpicerackParsedRecord(DomainModel):
    record_type: str = Field(min_length=1)
    raw_locator: RawLocator
    source_values: object
    dto: object | None = None
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    findings: tuple[SpicerackFinding, ...] = Field(default_factory=tuple)

    @field_validator("source_values", mode="before")
    @classmethod
    def make_json_safe(cls, value: object) -> object:
        return json_safe_source_value(value)

    @field_validator("finding_codes")
    @classmethod
    def validate_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(validate_finding_code(code) for code in value)
        if any(
            code.split(".", maxsplit=1)[0] not in {"parse", "integrity", "quality"}
            for code in normalized
        ):
            raise ValueError("Spicerack findings require parse, integrity, or quality namespaces")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Spicerack finding codes must be unique")
        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def validate_finding_alignment(self) -> SpicerackParsedRecord:
        expected = tuple(sorted({finding.code for finding in self.findings}))
        if len(expected) != len(self.findings) or self.finding_codes != expected:
            raise ValueError("Spicerack finding codes must match unique finding records")
        return self


def _freeze(value: object) -> object:
    if isinstance(value, Mapping):
        return FrozenDict({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze(item) for item in value)
    return value


__all__ = [
    "SpicerackDecklistDTO",
    "SpicerackEventDTO",
    "SpicerackFinding",
    "SpicerackParsedRecord",
    "SpicerackPlayerDTO",
    "SpicerackResultDTO",
    "SpicerackStandingDTO",
]
