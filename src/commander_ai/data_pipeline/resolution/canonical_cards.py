"""Map observed card staging rows into source-agnostic card contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Literal, cast
from uuid import UUID

from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CanonicalCard, CardFace
from commander_ai.domain.provenance import ProvenanceReference

from .card_faces import face_index, source_sequence, source_text

CARD_MAPPING_VERSION = "mtgjson-card-mapper-v1"
ColorCode = Literal["W", "U", "B", "R", "G"]
Legality = Literal["legal", "not_legal", "banned", "restricted", "unknown"]

_LEGALITY_VALUES: dict[str, Legality] = {
    "legal": "legal",
    "not legal": "not_legal",
    "not_legal": "not_legal",
    "banned": "banned",
    "restricted": "restricted",
}
_COLORS = frozenset("WUBRG")


class CardMappingError(ValueError):
    """A semantic card mapping failure retained by the caller as quarantine."""

    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def canonical_card_from_staging(
    record: StagingRecord,
    *,
    card_snapshot_id: str,
    provenance: tuple[ProvenanceReference, ...],
) -> CanonicalCard:
    """Build one canonical card concept from an observed source row."""

    values = _source_mapping(record)
    oracle_id = _source_uuid(values, "scryfallOracleId", "oracleId", "oracle_id")
    if oracle_id is None:
        raise CardMappingError(
            "quality.missing_canonical_identifier",
            "card row has no canonical oracle identifier",
        )
    name = _canonical_name(values)
    mana_value = _required_number(values.get("manaValue", values.get("mana_value")))
    return CanonicalCard(
        card_snapshot_id=card_snapshot_id,
        oracle_id=oracle_id,
        name=name,
        normalized_name=normalize_card_name(name),
        layout=source_text(values, "layout") or "normal",
        mana_value=mana_value,
        mana_cost=source_text(values, "manaCost", "mana_cost"),
        colors=_colors(values, "colors"),
        color_identity=_colors(values, "colorIdentity", "color_identity"),
        supertypes=_unique_text(values, "supertypes") or _type_line_parts(values).supertypes,
        types=_unique_text(values, "types") or _type_line_parts(values).types,
        subtypes=_unique_text(values, "subtypes") or _type_line_parts(values).subtypes,
        keywords=_unique_text(values, "keywords"),
        oracle_text=source_text(values, "oracleText", "oracle_text", "text"),
        power=source_text(values, "power"),
        toughness=source_text(values, "toughness"),
        loyalty=source_text(values, "loyalty"),
        legalities=_legalities(values.get("legalities")),
        is_basic_land=_is_basic_land(values),
        is_token=_boolean(values.get("isToken", values.get("is_token")), default=False),
        is_digital=_boolean(values.get("isDigital", values.get("is_digital")), default=False),
        released_at=_release_date(values),
        provenance=provenance,
    )


def card_face_from_staging(
    record: StagingRecord,
    *,
    oracle_id: str,
    layout: str,
    provenance: tuple[ProvenanceReference, ...],
    face_id_override: str | None = None,
    face_name_override: str | None = None,
    face_index_override: int | None = None,
) -> CardFace:
    """Build a face while retaining source face/related-face identity."""

    values = _source_mapping(record)
    face_id = face_id_override or source_text(values, "uuid", "faceId", "face_id")
    if face_id is None:
        raise CardMappingError("quality.missing_face_identifier", "face row has no face identifier")
    name = face_name_override or source_text(values, "faceName", "face_name", "name")
    if name is None:
        raise CardMappingError("quality.missing_face_name", "face row has no face name")
    return CardFace(
        face_id=face_id,
        oracle_id=oracle_id,
        face_index=face_index(values) if face_index_override is None else face_index_override,
        name=name,
        normalized_name=normalize_card_name(name),
        layout=source_text(values, "layout") or layout,
        mana_value=_number(
            values.get("faceManaValue", values.get("manaValue", values.get("mana_value")))
        ),
        mana_cost=source_text(values, "manaCost", "mana_cost"),
        colors=_colors(values, "colors"),
        color_identity=_colors(values, "colorIdentity", "color_identity"),
        supertypes=_unique_text(values, "supertypes"),
        types=_unique_text(values, "types"),
        subtypes=_unique_text(values, "subtypes"),
        keywords=_unique_text(values, "keywords"),
        oracle_text=source_text(values, "oracleText", "oracle_text", "text"),
        power=source_text(values, "power"),
        toughness=source_text(values, "toughness"),
        loyalty=source_text(values, "loyalty"),
        provenance=provenance,
    )


def normalize_card_name(value: str) -> str:
    """Apply the versioned name policy used by the deterministic resolver."""

    import unicodedata

    return " ".join(unicodedata.normalize("NFKC", value).casefold().split())


def source_identifiers(values: Mapping[str, object]) -> tuple[tuple[str, str], ...]:
    """Return source identifiers in explicit, stable priority order."""

    identifiers: list[tuple[str, str]] = []
    names = (
        "uuid",
        "scryfallId",
        "scryfallOracleId",
        "mtgjsonV4Id",
        "mtgjsonId",
        "cardKingdomId",
        "oracleId",
        "oracle_id",
        "printingId",
    )
    nested = values.get("identifiers")
    for name in names:
        for candidate in (
            values.get(name),
            nested.get(name) if isinstance(nested, Mapping) else None,
        ):
            if isinstance(candidate, str) and candidate.strip():
                pair = (name, candidate.strip())
                if pair not in identifiers:
                    identifiers.append(pair)
    return tuple(identifiers)


def _source_mapping(record: StagingRecord) -> Mapping[str, object]:
    values = record.original_source_values
    if not isinstance(values, Mapping):
        raise CardMappingError(
            "quality.source_value_not_object", "card source values are not an object"
        )
    return values


def _required_text(values: Mapping[str, object], name: str) -> str:
    value = source_text(values, name)
    if value is None:
        raise CardMappingError("quality.missing_card_field", f"card row has no {name}")
    return value


def _canonical_name(values: Mapping[str, object]) -> str:
    parts = source_sequence(values, "cardParts") or source_sequence(values, "card_parts")
    if len(parts) > 1:
        return " // ".join(parts)
    return _required_text(values, "name")


def _source_uuid(values: Mapping[str, object], *names: str) -> str | None:
    nested = values.get("identifiers")
    candidates: list[str] = []
    for name in names:
        for value in (
            values.get(name),
            nested.get(name) if isinstance(nested, Mapping) else None,
        ):
            if not isinstance(value, str):
                continue
            try:
                candidate = str(UUID(value))
            except ValueError:
                continue
            if candidate not in candidates:
                candidates.append(candidate)
    if len(candidates) > 1:
        raise CardMappingError(
            "quality.conflicting_canonical_identifiers",
            "card row contains contradictory canonical oracle identifiers",
        )
    return candidates[0] if candidates else None


def _number(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CardMappingError(
            "quality.invalid_numeric_card_field", "card numeric field is invalid"
        )
    if value < 0:
        raise CardMappingError(
            "quality.invalid_numeric_card_field", "card numeric field is negative"
        )
    return float(value)


def _required_number(value: object) -> float:
    number = _number(value)
    if number is None:
        raise CardMappingError("quality.missing_card_field", "card row has no manaValue")
    return number


def _colors(values: Mapping[str, object], *names: str) -> tuple[ColorCode, ...]:
    value: object = None
    for name in names:
        if name in values:
            value = values[name]
            break
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise CardMappingError("quality.invalid_color_collection", "card colors are not an array")
    result = tuple(str(item).upper() for item in value)
    if any(item not in _COLORS for item in result):
        raise CardMappingError("quality.invalid_color_collection", "card contains an invalid color")
    if len(result) != len(set(result)):
        raise CardMappingError(
            "quality.duplicate_color", "card color collection contains duplicates"
        )
    return tuple(cast(ColorCode, item) for item in result)


def _unique_text(values: Mapping[str, object], name: str) -> tuple[str, ...]:
    result = source_sequence(values, name)
    if len(result) != len(set(result)):
        raise CardMappingError(
            "quality.duplicate_card_field", f"card field {name} contains duplicates"
        )
    return result


def _legalities(value: object) -> dict[str, Legality]:
    if value is None:
        return {"commander": "unknown"}
    if not isinstance(value, Mapping):
        raise CardMappingError("quality.invalid_legalities", "card legalities are not an object")
    result: dict[str, Legality] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        normalized = str(raw).strip().casefold() if isinstance(raw, str) else "unknown"
        result[key] = _LEGALITY_VALUES.get(normalized, "unknown")
    result.setdefault("commander", "unknown")
    return result


def _boolean(value: object, *, default: bool) -> bool:
    if value is None:
        return default
    if not isinstance(value, bool):
        raise CardMappingError(
            "quality.invalid_boolean_card_field", "card boolean field is invalid"
        )
    return value


def _is_basic_land(values: Mapping[str, object]) -> bool:
    types = _unique_text(values, "types")
    supertypes = _unique_text(values, "supertypes")
    type_line = source_text(values, "type") or ""
    return "Basic" in types or "Basic" in supertypes or "Basic Land" in type_line


def _release_date(values: Mapping[str, object]) -> date | None:
    value = source_text(values, "releaseDate", "releasedAt", "released_at")
    if value is None:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CardMappingError(
            "quality.invalid_release_date", "card release date is invalid"
        ) from error


class _TypeLineParts:
    def __init__(
        self, supertypes: tuple[str, ...], types: tuple[str, ...], subtypes: tuple[str, ...]
    ):
        self.supertypes = supertypes
        self.types = types
        self.subtypes = subtypes


def _type_line_parts(values: Mapping[str, object]) -> _TypeLineParts:
    line = source_text(values, "type") or ""
    if not line:
        return _TypeLineParts((), (), ())
    sections = line.split("—", maxsplit=1)
    if len(sections) == 1:
        sections = line.split("-", maxsplit=1)
    left = sections[0].strip()
    right = sections[1].strip() if len(sections) == 2 else ""
    words = tuple(item for item in left.split() if item)
    supertypes = tuple(item for item in words if item in {"Basic", "Legendary", "Snow", "World"})
    types = tuple(item for item in words if item not in supertypes)
    subtypes = tuple(item for item in right.replace("//", " ").split() if item)
    return _TypeLineParts(supertypes, types, subtypes)


__all__ = [
    "CARD_MAPPING_VERSION",
    "CardMappingError",
    "canonical_card_from_staging",
    "card_face_from_staging",
    "normalize_card_name",
    "source_identifiers",
]
