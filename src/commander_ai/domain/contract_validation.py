"""Reusable value and collection validators for persisted domain contracts."""

from __future__ import annotations

import re
from collections.abc import Mapping
from math import isfinite
from typing import Annotated, TypeVar
from uuid import UUID

from pydantic import AfterValidator, AnyUrl, Field, TypeAdapter, ValidationError

T = TypeVar("T")

_URI_ADAPTER = TypeAdapter(AnyUrl)
_URI_ALLOWED_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~:/?#[]@!$&'()*+,;=%"
)
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")


def validate_uuid(value: str) -> str:
    """Keep string ergonomics while enforcing JSON Schema UUID values."""

    try:
        parsed = UUID(value)
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("value must be a valid UUID") from error
    if str(parsed) != value.lower():
        raise ValueError("value must use the schema UUID representation")
    return value


def validate_uri(value: str) -> str:
    """Keep string ergonomics while enforcing JSON Schema URI values."""

    if any(char not in _URI_ALLOWED_CHARS for char in value):
        raise ValueError("value must be a valid URI")
    for index, char in enumerate(value):
        if char == "%" and (
            index + 2 >= len(value)
            or value[index + 1] not in _HEX_DIGITS
            or value[index + 2] not in _HEX_DIGITS
        ):
            raise ValueError("value must be a valid URI")
    try:
        _URI_ADAPTER.validate_python(value)
    except ValidationError as error:
        raise ValueError("value must be a valid URI") from error
    return value


def validate_finite_float(value: float) -> float:
    """Reject non-finite JSON number values such as NaN and infinity."""

    if not isfinite(value):
        raise ValueError("number must be finite")
    return value


def validate_json_value(value: object) -> object:
    """Accept only values that can be represented as JSON primitives."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return validate_finite_float(value)
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            validate_json_value(item)
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            validate_json_value(item)
        return value
    raise ValueError("value must be JSON-compatible")


def validate_json_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    """Accept a JSON-compatible object while preserving mapping ergonomics."""

    validate_json_value(value)
    return value


def validate_unique_items[Item](value: tuple[Item, ...]) -> tuple[Item, ...]:
    """Enforce JSON Schema ``uniqueItems`` semantics without hashability needs."""

    for index, item in enumerate(value):
        if item in value[:index]:
            raise ValueError("collection items must be unique")
    return value


def validate_namespaced_codes(value: tuple[str, ...], namespace: str) -> tuple[str, ...]:
    """Validate unique machine-readable codes within one exact namespace."""

    pattern = re.compile(rf"^{re.escape(namespace)}\.[a-z0-9_]+$")
    if any(pattern.fullmatch(item) is None for item in value):
        raise ValueError(f"finding codes must use the {namespace} namespace")
    return validate_unique_items(value)


def validate_non_negative_counts(value: Mapping[str, int]) -> Mapping[str, int]:
    """Validate persisted count mappings and return deterministic key order."""

    if any(
        not isinstance(key, str) or not key or type(count) is not int or count < 0
        for key, count in value.items()
    ):
        raise ValueError("counts must contain non-negative integers")
    return dict(sorted(value.items()))


def validate_non_empty_counts(value: Mapping[str, int]) -> Mapping[str, int]:
    """Require a normalized manifest to report at least one count."""

    if not value:
        raise ValueError("counts cannot be empty")
    return validate_non_negative_counts(value)


NonEmptyString = Annotated[str, Field(min_length=1)]
UUIDString = Annotated[str, AfterValidator(validate_uuid)]
URIString = Annotated[str, AfterValidator(validate_uri)]
FiniteFloat = Annotated[float, AfterValidator(validate_finite_float)]
NonNegativeInt = Annotated[int, Field(ge=0)]
JSONMapping = Annotated[Mapping[str, object], AfterValidator(validate_json_mapping)]
NonEmptyCounts = Annotated[Mapping[str, int], AfterValidator(validate_non_empty_counts)]
NonNegativeCounts = Annotated[Mapping[str, int], AfterValidator(validate_non_negative_counts)]
UniqueTuple = Annotated[tuple[T, ...], AfterValidator(validate_unique_items)]


__all__ = [
    "FiniteFloat",
    "JSONMapping",
    "NonEmptyCounts",
    "NonEmptyString",
    "NonNegativeCounts",
    "NonNegativeInt",
    "URIString",
    "UUIDString",
    "UniqueTuple",
    "validate_json_mapping",
    "validate_namespaced_codes",
    "validate_non_negative_counts",
]
