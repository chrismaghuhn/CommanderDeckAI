"""Immutable value objects for the card catalog and its build output."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from commander_ai.data_pipeline.provenance.rows import ProvenanceRow
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.domain.cards import (
    CanonicalCard,
    CardFace,
    CardResolutionCandidate,
    Printing,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .canonical_cards import normalize_card_name


@dataclass(frozen=True, slots=True)
class AliasCatalog:
    """Versioned, deterministic aliases supplied by reviewed project data."""

    version: str
    aliases: Mapping[str, tuple[CardResolutionCandidate, ...]]
    sha256: str

    @classmethod
    def create(
        cls,
        version: str,
        aliases: Mapping[str, Iterable[CardResolutionCandidate]],
    ) -> AliasCatalog:
        grouped: dict[str, list[CardResolutionCandidate]] = {}
        for alias, candidates in aliases.items():
            normalized_alias = normalize_card_name(alias)
            if not normalized_alias:
                raise ValueError("alias cannot normalize to an empty name")
            grouped.setdefault(normalized_alias, []).extend(candidates)
        normalized = {alias: sorted_candidates(candidates) for alias, candidates in grouped.items()}
        if not version:
            raise ValueError("alias catalog version cannot be empty")
        payload = {
            "version": version,
            "aliases": {
                key: [candidate.model_dump(mode="json") for candidate in normalized[key]]
                for key in sorted(normalized)
            },
        }
        digest = sha256_hex(canonical_json_bytes(payload))
        return cls(version, MappingProxyType(dict(sorted(normalized.items()))), digest)


@dataclass(frozen=True, slots=True)
class CardCatalog:
    """Immutable card, face, printing, and resolution indexes."""

    catalog_snapshot_id: str
    cards: tuple[CanonicalCard, ...]
    faces: tuple[CardFace, ...]
    printings: tuple[Printing, ...]
    identifier_index: Mapping[str, tuple[CardResolutionCandidate, ...]]
    name_index: Mapping[str, tuple[CardResolutionCandidate, ...]]
    face_name_index: Mapping[str, tuple[CardResolutionCandidate, ...]]
    related_face_ids: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "identifier_index", freeze_index(self.identifier_index))
        object.__setattr__(self, "name_index", freeze_index(self.name_index))
        object.__setattr__(self, "face_name_index", freeze_index(self.face_name_index))
        object.__setattr__(
            self,
            "related_face_ids",
            MappingProxyType(
                {
                    key: tuple(sorted(set(value)))
                    for key, value in sorted(self.related_face_ids.items())
                }
            ),
        )


@dataclass(frozen=True, slots=True)
class CatalogBuildResult:
    """Canonical catalog plus retained failures from the staging boundary."""

    catalog: CardCatalog
    quarantines: tuple[QuarantineRecord, ...]
    finding_codes: tuple[str, ...]
    provenance_rows: tuple[ProvenanceRow, ...] = ()


def sorted_candidates(
    candidates: Iterable[CardResolutionCandidate],
) -> tuple[CardResolutionCandidate, ...]:
    unique: dict[tuple[str, str, str], CardResolutionCandidate] = {}
    for candidate in candidates:
        key = (candidate.oracle_id, candidate.printing_id or "", candidate.face_id or "")
        unique[key] = candidate
    return tuple(
        sorted(
            unique.values(),
            key=lambda candidate: (
                candidate.oracle_id,
                candidate.printing_id or "",
                candidate.face_id or "",
            ),
        )
    )


def freeze_index(
    index: Mapping[str, tuple[CardResolutionCandidate, ...]],
) -> Mapping[str, tuple[CardResolutionCandidate, ...]]:
    return MappingProxyType({key: sorted_candidates(value) for key, value in sorted(index.items())})
