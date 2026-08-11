"""Immutable MTGJSON parse findings and logical-record result contracts."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from pydantic import Field, field_validator

from commander_ai.data_pipeline.quality.finding_codes import validate_finding_code
from commander_ai.data_pipeline.staging.raw_locators import RawLocator
from commander_ai.domain.provenance import DomainModel
from commander_ai.domain.serialization import canonical_json_bytes

from .dto import MTGJSONModel
from .scalar_safety import (
    MalformedJSONScalar,
    sanitize_json_scalars,
    scalar_envelope,
)


class MTGJSONFinding(DomainModel):
    """A source parse/structural finding retaining the exact raw locator."""

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    raw_locator: RawLocator

    @field_validator("code")
    @classmethod
    def validate_parse_namespace(cls, value: str) -> str:
        code = validate_finding_code(value)
        if code.split(".", maxsplit=1)[0] not in {"parse", "integrity"}:
            raise ValueError("MTGJSON findings must use parse or integrity namespaces")
        return code


class MTGJSONParsedRecord(DomainModel):
    """One source observation, including malformed values and its DTO projection."""

    record_type: str = Field(min_length=1)
    raw_locator: RawLocator
    source_values: object
    dto: object | None = None
    finding_codes: tuple[str, ...] = Field(default_factory=tuple)
    findings: tuple[MTGJSONFinding, ...] = Field(default_factory=tuple)

    @field_validator("source_values", mode="before")
    @classmethod
    def encode_non_text_source_values(cls, value: object) -> object:
        return _json_safe_source_value(value)

    @field_validator("finding_codes")
    @classmethod
    def validate_codes(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(validate_finding_code(code) for code in value)
        if any(code.split(".", maxsplit=1)[0] not in {"parse", "integrity"} for code in normalized):
            raise ValueError("MTGJSON record findings must use parse or integrity namespaces")
        if len(normalized) != len(set(normalized)):
            raise ValueError("MTGJSON record findings must be unique")
        return tuple(sorted(normalized))


@dataclass(frozen=True, slots=True)
class MTGJSONParseResult:
    records: tuple[MTGJSONParsedRecord, ...]
    extracted_root: Path


def record_with_findings(
    record_type: str,
    locator: RawLocator,
    source_values: object,
    dto: MTGJSONModel | None,
    findings: list[MTGJSONFinding],
) -> MTGJSONParsedRecord:
    codes = tuple(sorted({finding.code for finding in findings}))
    return MTGJSONParsedRecord(
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
) -> MTGJSONParsedRecord:
    finding = MTGJSONFinding(code=code, message=message, raw_locator=locator)
    return record_with_findings(record_type, locator, source_values, None, [finding])


def _json_safe_source_value(value: object) -> object:
    value = sanitize_json_scalars(value)
    if isinstance(value, MalformedJSONScalar):
        return scalar_envelope(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        raw = bytes(value)
        return {
            "encoding": "base64",
            "data": base64.b64encode(raw).decode("ascii"),
            "byte_length": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
    if isinstance(value, Mapping):
        if any(isinstance(key, MalformedJSONScalar) for key in value):
            return _json_safe_mapping_envelope(value)
        return {str(key): _json_safe_source_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_source_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return [_json_safe_source_value(item) for item in sorted(value, key=str)]
    return value


def _json_safe_mapping_envelope(value: Mapping[object, object]) -> dict[str, object]:
    entries: list[dict[str, object]] = []
    for key, item in value.items():
        if isinstance(key, MalformedJSONScalar):
            key_payload: dict[str, object] = {
                **scalar_envelope(key),
                "role": "object_key",
            }
        else:
            key_payload = {"role": "text", "value": str(key)}
        entries.append(
            {
                "key": key_payload,
                "value": _json_safe_source_value(item),
            }
        )
    entry_payload = {"entries": entries}
    return {
        "encoding": "json_object_entries",
        "entries": entries,
        "entry_count": len(entries),
        "sha256": hashlib.sha256(canonical_json_bytes(entry_payload)).hexdigest(),
    }


__all__ = [
    "MTGJSONFinding",
    "MTGJSONParseResult",
    "MTGJSONParsedRecord",
    "finding_record",
    "record_with_findings",
]
