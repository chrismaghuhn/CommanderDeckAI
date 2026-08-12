"""Semantic collection checks for the frozen normalized-snapshot v1 model."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

_FINDING_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)+$")


def validate_finding_codes(value: tuple[str, ...]) -> tuple[str, ...]:
    if any(not isinstance(item, str) or _FINDING_PATTERN.fullmatch(item) is None for item in value):
        raise ValueError("normalized finding codes must use a valid namespace")
    if len(value) != len(set(value)):
        raise ValueError("normalized finding codes must be unique")
    if tuple(value) != tuple(sorted(value)):
        raise ValueError("normalized finding codes must be sorted")
    return value


def validate_quarantine_references(value: object) -> tuple[object, ...]:
    from .provenance import QuarantineReference

    if not isinstance(value, (tuple, list)):
        raise ValueError("quarantine references must be a sequence")
    references = tuple(QuarantineReference.model_validate(item) for item in value)
    if len({item.quarantine_id for item in references}) != len(references):
        raise ValueError("quarantine references must be unique")
    expected = tuple(
        sorted(
            references,
            key=lambda item: (
                item.quarantine_id,
                item.reason_code,
                item.path or "",
                item.record_locator or "",
            ),
        )
    )
    if references != expected:
        raise ValueError("quarantine references must be sorted")
    return references


def validate_provenance_order(value: Sequence[Any]) -> Sequence[Any]:
    identities = [(item.source_object_id, item.raw_sha256) for item in value]
    if len(identities) != len(set(identities)):
        raise ValueError("provenance references must be unique")
    if identities != sorted(identities):
        raise ValueError("provenance references must be sorted")
    return value


__all__ = [
    "validate_finding_codes",
    "validate_provenance_order",
    "validate_quarantine_references",
]
