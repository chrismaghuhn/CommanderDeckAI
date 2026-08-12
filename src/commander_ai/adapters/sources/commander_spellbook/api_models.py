"""Immutable, source-shaped Commander Spellbook DTO and parse contracts."""

from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass

from pydantic import (
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from commander_ai.data_pipeline.quality.finding_codes import validate_finding_code
from commander_ai.data_pipeline.staging.raw_locators import RawLocator
from commander_ai.domain.provenance import DomainModel, FrozenDict
from commander_ai.domain.serialization import canonical_json_bytes


class _SpellbookModel(DomainModel):
    """Allow source evolution while retaining immutable nested values."""

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


class SpellbookCard(_SpellbookModel):
    """Documented card DTO; it is not a canonical card entity."""

    id: StrictInt | StrictStr
    name: StrictStr
    oracle_id: StrictStr | None = Field(default=None, alias="oracleId")
    color_identity: tuple[StrictStr, ...] | None = Field(default=None, alias="colorIdentity")
    type_line: StrictStr | None = Field(default=None, alias="typeLine")
    status: StrictStr | None = None


class SpellbookComboReference(_SpellbookModel):
    """Source combo reference retained on a variant."""

    id: StrictInt | StrictStr


class SpellbookTemplate(_SpellbookModel):
    """Source requirement template DTO."""

    id: StrictInt | StrictStr
    name: StrictStr | None = None


class SpellbookFeature(_SpellbookModel):
    """Source result/feature DTO."""

    id: StrictInt | StrictStr
    name: StrictStr | None = None
    status: StrictStr | None = None


class SpellbookVariantUse(_SpellbookModel):
    """Card involvement with source ordering, role, and condition fields."""

    card: SpellbookCard | None = None
    quantity: StrictInt | StrictFloat | None = None
    zone_locations: tuple[StrictStr, ...] | None = Field(default=None, alias="zoneLocations")
    battlefield_card_state: object | None = Field(default=None, alias="battlefieldCardState")
    exile_card_state: object | None = Field(default=None, alias="exileCardState")
    library_card_state: object | None = Field(default=None, alias="libraryCardState")
    graveyard_card_state: object | None = Field(default=None, alias="graveyardCardState")
    must_be_commander: StrictBool | None = Field(default=None, alias="mustBeCommander")
    used_face: StrictStr | None = Field(default=None, alias="usedFace")


class SpellbookVariantRequirement(_SpellbookModel):
    """Prerequisite/requirement DTO, including either card or template roles."""

    card: SpellbookCard | None = None
    template: SpellbookTemplate | None = None
    quantity: StrictInt | StrictFloat | None = None
    zone_locations: tuple[StrictStr, ...] | None = Field(default=None, alias="zoneLocations")
    battlefield_card_state: object | None = Field(default=None, alias="battlefieldCardState")
    exile_card_state: object | None = Field(default=None, alias="exileCardState")
    library_card_state: object | None = Field(default=None, alias="libraryCardState")
    graveyard_card_state: object | None = Field(default=None, alias="graveyardCardState")
    must_be_commander: StrictBool | None = Field(default=None, alias="mustBeCommander")
    used_face: StrictStr | None = Field(default=None, alias="usedFace")


class SpellbookVariantResult(_SpellbookModel):
    """Result/effect feature DTO."""

    feature: SpellbookFeature | None = None
    quantity: StrictInt | StrictFloat | None = None


class SpellbookVariant(_SpellbookModel):
    """Documented variant DTO with combo relationships kept source-shaped."""

    id: StrictInt | StrictStr
    uses: tuple[SpellbookVariantUse, ...] = Field(default_factory=tuple)
    requires: tuple[SpellbookVariantRequirement, ...] = Field(default_factory=tuple)
    produces: tuple[SpellbookVariantResult, ...] = Field(default_factory=tuple)
    of: tuple[SpellbookComboReference, ...] = Field(default_factory=tuple)
    includes: tuple[SpellbookComboReference, ...] = Field(default_factory=tuple)
    color_identity: tuple[StrictStr, ...] | None = Field(default=None, alias="colorIdentity")
    commander_compatible: StrictBool | None = Field(default=None, alias="commanderCompatible")
    easy_prerequisites: object | None = Field(default=None, alias="easyPrerequisites")
    notable_prerequisites: object | None = Field(default=None, alias="notablePrerequisites")
    mana_needed: object | None = Field(default=None, alias="manaNeeded")
    mana_value_needed: object | None = Field(default=None, alias="manaValueNeeded")
    description: StrictStr | None = None
    notes: StrictStr | None = None
    status: StrictStr | None = None
    legalities: Mapping[str, object] | None = None
    prices: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class MalformedJSONScalar:
    """Marker used while decoding JSON constants that are not valid JSON."""

    token: str


class CommanderSpellbookFinding(DomainModel):
    """A parse/structural finding with an exact raw locator."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    raw_locator: RawLocator

    @field_validator("code")
    @classmethod
    def validate_parse_namespace(cls, value: str) -> str:
        code = validate_finding_code(value)
        if code.split(".", maxsplit=1)[0] not in {"parse", "integrity"}:
            raise ValueError("Commander Spellbook findings require parse or integrity namespaces")
        return code


class CommanderSpellbookParsedRecord(DomainModel):
    """One source record or lossless malformed-record envelope."""

    record_type: str = Field(min_length=1)
    raw_locator: RawLocator
    source_values: object
    dto: object | None = None
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    findings: tuple[CommanderSpellbookFinding, ...] = Field(default_factory=tuple)

    @field_validator("source_values", mode="before")
    @classmethod
    def make_json_safe(cls, value: object) -> object:
        return json_safe_source_value(value)

    @field_validator("finding_codes")
    @classmethod
    def validate_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(validate_finding_code(code) for code in value)
        if any(code.split(".", maxsplit=1)[0] not in {"parse", "integrity"} for code in normalized):
            raise ValueError("Commander Spellbook findings require parse or integrity namespaces")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Commander Spellbook findings must be unique")
        return tuple(sorted(normalized))

    @model_validator(mode="after")
    def validate_finding_alignment(self) -> CommanderSpellbookParsedRecord:
        expected = tuple(sorted({finding.code for finding in self.findings}))
        if len(expected) != len(self.findings):
            raise ValueError("Commander Spellbook findings must use unique codes")
        if self.finding_codes != expected:
            raise ValueError("Commander Spellbook finding codes must match findings")
        return self


@dataclass(frozen=True, slots=True)
class CommanderSpellbookParseResult:
    records: tuple[CommanderSpellbookParsedRecord, ...]


def record_with_findings(
    record_type: str,
    locator: RawLocator,
    source_values: object,
    dto: object | None,
    findings: list[CommanderSpellbookFinding],
) -> CommanderSpellbookParsedRecord:
    codes = tuple(sorted({finding.code for finding in findings}))
    return CommanderSpellbookParsedRecord(
        record_type=record_type,
        raw_locator=locator,
        source_values=source_values,
        dto=dto,
        finding_codes=codes,
        findings=tuple(sorted(findings, key=lambda finding: (finding.code, finding.message))),
    )


def finding_record(
    record_type: str,
    locator: RawLocator,
    source_values: object,
    *,
    code: str,
    message: str,
) -> CommanderSpellbookParsedRecord:
    finding = CommanderSpellbookFinding(code=code, message=message, raw_locator=locator)
    return record_with_findings(record_type, locator, source_values, None, [finding])


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return FrozenDict({str(key): _freeze_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_value(item) for item in value)
    return value


def json_safe_source_value(value: object) -> object:
    if isinstance(value, MalformedJSONScalar):
        raw = value.token.encode("ascii")
        return {
            "encoding": "base64",
            "data": base64.b64encode(raw).decode("ascii"),
            "byte_length": len(raw),
            "scalar_type": "non_finite_number",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {
            "encoding": "base64",
            "data": base64.b64encode(raw).decode("ascii"),
            "byte_length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if isinstance(value, str) and _has_surrogate(value):
        raw = json.dumps(value, ensure_ascii=True, separators=(",", ":")).encode("ascii")
        return {
            "encoding": "base64",
            "data": base64.b64encode(raw).decode("ascii"),
            "byte_length": len(raw),
            "scalar_type": "invalid_unicode_scalar",
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if isinstance(value, Mapping):
        if any(isinstance(key, str) and _has_surrogate(key) for key in value):
            return _json_object_entries(value)
        return {str(key): json_safe_source_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_source_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [json_safe_source_value(item) for item in sorted(value, key=str)]
    return value


def _json_object_entries(value: Mapping[object, object]) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for key, item in value.items():
        if isinstance(key, str) and _has_surrogate(key):
            raw_key = json.dumps(key, ensure_ascii=True, separators=(",", ":")).encode("ascii")
            key_payload: object = {
                "role": "object_key",
                "encoding": "base64",
                "data": base64.b64encode(raw_key).decode("ascii"),
                "scalar_type": "invalid_unicode_scalar",
            }
        else:
            key_payload = {"role": "text", "value": str(key)}
        entries.append({"key": key_payload, "value": json_safe_source_value(item)})
    payload = {"entries": entries}
    return {
        "encoding": "json_object_entries",
        "entries": entries,
        "entry_count": len(entries),
        "sha256": hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    }


def _has_surrogate(value: str) -> bool:
    return any(0xD800 <= ord(character) <= 0xDFFF for character in value)


__all__ = [
    "CommanderSpellbookFinding",
    "CommanderSpellbookParseResult",
    "CommanderSpellbookParsedRecord",
    "MalformedJSONScalar",
    "SpellbookCard",
    "SpellbookComboReference",
    "SpellbookFeature",
    "SpellbookTemplate",
    "SpellbookVariant",
    "SpellbookVariantRequirement",
    "SpellbookVariantResult",
    "SpellbookVariantUse",
    "finding_record",
    "json_safe_source_value",
    "record_with_findings",
]
