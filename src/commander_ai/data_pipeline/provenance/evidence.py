"""Source evidence shared by normalized event and combo mappings."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote

from commander_ai.data_pipeline.staging.raw_locators import RawLocator
from commander_ai.domain.provenance import ProvenanceReference


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    """One exact raw locator plus the matching normalized provenance."""

    raw_locator: RawLocator
    provenance: tuple[ProvenanceReference, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.raw_locator, RawLocator):
            raise TypeError("source evidence requires a RawLocator")
        if not self.provenance:
            raise ValueError("source evidence requires provenance")
        if not any(
            reference.source_id == self.raw_locator.source_id
            and reference.source_snapshot_id == self.raw_locator.source_snapshot_id
            and reference.source_object_id == self.raw_locator.raw_object_id
            for reference in self.provenance
        ):
            raise ValueError("source evidence provenance must match its raw locator")

    @property
    def source_id(self) -> str:
        return self.raw_locator.source_id

    @property
    def source_snapshot_id(self) -> str:
        return self.raw_locator.source_snapshot_id

    @property
    def raw_object_id(self) -> str:
        return self.raw_locator.raw_object_id


def source_scoped_id(kind: str, source_id: str, source_value: str) -> str:
    """Namespace an external identifier with injective portable segments.

    Each segment uses RFC 3986 unreserved characters only, so delimiters in a
    source identifier or source value cannot create an alternate parse.
    """

    if not kind.strip() or not source_id.strip() or not source_value.strip():
        raise ValueError("scoped identifiers require non-empty values")
    return ":".join(quote(value, safe="-._~") for value in (kind, source_id, source_value))


__all__ = ["SourceEvidence", "source_scoped_id"]
