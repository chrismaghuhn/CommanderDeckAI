"""Source-shaped TopDeck Tournaments v2 DTOs; no canonical semantics."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from pydantic import (
    AwareDatetime,
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


class _TopDeckModel(DomainModel):
    """Allow documented source evolution without changing canonical contracts."""

    model_config = ConfigDict(
        extra="allow",
        frozen=True,
        populate_by_name=True,
        hide_input_in_errors=True,
    )

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        extra = getattr(self, "model_extra", None)
        if extra is not None:
            object.__setattr__(
                self,
                "__pydantic_extra__",
                FrozenDict({str(key): _freeze_value(value) for key, value in extra.items()}),
            )


class TopDeckEventDTO(_TopDeckModel):
    event_id: StrictStr | StrictInt
    tournament_name: StrictStr | None = None
    game: StrictStr | None = None
    format: StrictStr | None = None
    start_date: object | None = None
    event_at: AwareDatetime | None = None
    event_data: object | None = None
    standings: object | None = None
    rounds: object | None = None
    top_cut: object | None = None


class TopDeckStandingDTO(_TopDeckModel):
    player_id: StrictStr | StrictInt | None = None
    player: object | None = None
    deck: object | None = None
    decklist: object | None = None
    deck_obj: object | None = None
    commander: object | None = None
    place: object | None = None
    wins: object | None = None
    losses: object | None = None
    draws: object | None = None
    record: object | None = None


class TopDeckDeckDTO(_TopDeckModel):
    commander: object | None = None
    decklist: object | None = None
    deck_obj: object | None = None


class TopDeckRoundDTO(_TopDeckModel):
    round_number: object | None = None
    tables: object | None = None


class TopDeckTableDTO(_TopDeckModel):
    table_id: object | None = None
    players: object | None = None
    winner: object | None = None
    winner_id: object | None = None
    status: object | None = None
    result: object | None = None


class TopDeckPlayerDTO(_TopDeckModel):
    player_id: StrictStr | StrictInt | None = None
    name: object | None = None
    seat: object | None = None
    result: object | None = None
    winner: object | None = None


class TopDeckFinding(DomainModel):
    """Parse/integrity finding tied to the exact raw response locator."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    raw_locator: RawLocator

    @field_validator("code")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        code = validate_finding_code(value)
        if code.split(".", maxsplit=1)[0] not in {"parse", "integrity"}:
            raise ValueError("TopDeck findings require parse or integrity namespaces")
        return code


class TopDeckParsedRecord(DomainModel):
    """One source record before canonical event/pod interpretation."""

    record_type: str = Field(min_length=1)
    raw_locator: RawLocator
    source_values: object
    dto: object | None = None
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    findings: tuple[TopDeckFinding, ...] = Field(default_factory=tuple)

    @field_validator("source_values", mode="before")
    @classmethod
    def make_json_safe(cls, value: object) -> object:
        return json_safe_source_value(value)

    @field_validator("finding_codes")
    @classmethod
    def validate_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(validate_finding_code(code) for code in value)
        if any(code.split(".", maxsplit=1)[0] not in {"parse", "integrity"} for code in normalized):
            raise ValueError("TopDeck findings require parse or integrity namespaces")
        if len(normalized) != len(set(normalized)):
            raise ValueError("TopDeck finding codes must be unique")
        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def validate_finding_alignment(self) -> TopDeckParsedRecord:
        expected = tuple(sorted({finding.code for finding in self.findings}))
        if len(expected) != len(self.findings) or self.finding_codes != expected:
            raise ValueError("TopDeck finding codes must match unique finding records")
        return self


def parse_event_datetime(value: object) -> datetime | None:
    """Parse documented Unix-second or ISO-8601 event timestamps."""

    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            timestamp = float(value)
            if timestamp > 100_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)
    return None


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return FrozenDict({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return value


__all__ = [
    "TopDeckDeckDTO",
    "TopDeckEventDTO",
    "TopDeckFinding",
    "TopDeckParsedRecord",
    "TopDeckPlayerDTO",
    "TopDeckRoundDTO",
    "TopDeckStandingDTO",
    "TopDeckTableDTO",
    "parse_event_datetime",
]
