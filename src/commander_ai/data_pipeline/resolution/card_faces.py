"""Source-neutral helpers for preserving card-face relationships."""

from __future__ import annotations

from collections.abc import Mapping, Sequence


class SourceCollectionError(ValueError):
    """Source collection could not be preserved without coercion."""

    reason_code = "quality.invalid_card_collection"


def source_text(values: Mapping[str, object], *names: str) -> str | None:
    """Return the first non-empty text value from source aliases."""

    for name in names:
        value = values.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def source_sequence(values: Mapping[str, object], name: str) -> tuple[str, ...]:
    """Read a source sequence without inventing values or coercing scalars."""

    value = values.get(name)
    if value is None:
        return ()
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise SourceCollectionError(f"card field {name} is not a source sequence")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise SourceCollectionError(f"card field {name} contains a non-text value")
    return tuple(item.strip() for item in value)


def split_face_id(source_id: str, index: int) -> str:
    """Return a deterministic derived face id for a source-declared split part."""

    return f"{source_id}#part-{index}"


def face_index(values: Mapping[str, object], *, default: int = 0) -> int:
    """Map documented MTGJSON side markers to deterministic zero-based indices."""

    side = source_text(values, "side")
    if side is None:
        return default
    normalized = side.casefold()
    if normalized in {"a", "front", "front face", "1"}:
        return 0
    if normalized in {"b", "back", "back face", "2"}:
        return 1
    return default


def explicit_face(values: Mapping[str, object]) -> bool:
    """Whether a source row explicitly represents one face of a card."""

    return source_text(values, "faceName", "face_name", "side") is not None


def related_face_ids(values: Mapping[str, object]) -> tuple[str, ...]:
    """Preserve source-declared related face identifiers in source order."""

    return source_sequence(values, "otherFaceIds") or source_sequence(values, "other_face_ids")


__all__ = [
    "SourceCollectionError",
    "explicit_face",
    "face_index",
    "related_face_ids",
    "source_sequence",
    "source_text",
    "split_face_id",
]
