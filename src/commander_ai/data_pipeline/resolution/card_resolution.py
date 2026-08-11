"""Deterministic, auditable card identity resolution."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Literal

from commander_ai.data_pipeline.provenance.rows import ResolutionAttempt
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord, quarantine_record
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CardResolution, CardResolutionCandidate
from commander_ai.domain.provenance import ProvenanceReference
from commander_ai.domain.serialization import canonical_json_bytes

from .canonical_cards import normalize_card_name, source_identifiers
from .card_catalog import AliasCatalog, CardCatalog

RESOLVER_VERSION = "card-resolver-v1"
NORMALIZATION_POLICY_VERSION = "unicode_nfkc_casefold_whitespace_v1"
EMPTY_ALIAS_CATALOG = AliasCatalog.create("aliases-empty-v1", {})
ResolutionMethod = Literal[
    "source_identifier", "exact_identifier", "exact_name", "alias", "split_face", "none"
]
ResolutionStatus = Literal["resolved", "ambiguous", "unresolved", "rejected"]
AttemptStatus = Literal["RESOLVED", "AMBIGUOUS", "UNRESOLVED"]


@dataclass(frozen=True, slots=True)
class CardResolutionInput:
    """One source card value plus its exact staging evidence."""

    staging_record: StagingRecord
    original_value: str
    source_field: str = "name"
    requested_quantity: int | None = None

    def __post_init__(self) -> None:
        if not self.original_value:
            raise ValueError("original_value cannot be empty")
        if not self.source_field:
            raise ValueError("source_field cannot be empty")
        if self.requested_quantity is not None and (
            isinstance(self.requested_quantity, bool) or self.requested_quantity < 1
        ):
            raise ValueError("requested_quantity must be a positive integer")


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    """Canonical resolution plus the always-retained attempt and optional quarantine."""

    resolution: CardResolution
    attempt: ResolutionAttempt
    quarantine: QuarantineRecord | None


class CardResolver:
    """Resolve source values by identifiers, exact names, then reviewed aliases."""

    def __init__(
        self,
        catalog: CardCatalog,
        *,
        alias_catalog: AliasCatalog | None = None,
        resolver_version: str = RESOLVER_VERSION,
        normalization_policy_version: str = NORMALIZATION_POLICY_VERSION,
    ) -> None:
        self._catalog = catalog
        self._aliases = alias_catalog or EMPTY_ALIAS_CATALOG
        self._resolver_version = resolver_version
        self._normalization_policy_version = normalization_policy_version

    def resolve(
        self,
        item: CardResolutionInput,
        *,
        attempted_at: datetime | None = None,
    ) -> ResolutionResult:
        attempted_at = attempted_at or datetime.now(UTC)
        if attempted_at.tzinfo is None or attempted_at.utcoffset() is None:
            raise ValueError("attempted_at must include a timezone")
        values = item.staging_record.original_source_values
        if item.staging_record.status != "OBSERVED":
            raise ValueError("resolution requires an OBSERVED staging record")
        identifier_match = self._identifier_match(values)
        method: ResolutionMethod
        status: ResolutionStatus
        finding: str | None
        if identifier_match is not None:
            method, candidates, finding = identifier_match
            status = _resolution_status(candidates)
            if status == "resolved":
                finding = None
            elif finding is None:
                finding = "resolution.ambiguous_identifier"
        else:
            method, candidates, finding = self._name_match(item.original_value)
            status = _resolution_status(candidates)
            if status == "resolved":
                finding = None
            elif finding is None:
                finding = (
                    "resolution.ambiguous_name"
                    if status == "ambiguous"
                    else "resolution.unresolved"
                )

        canonical = candidates[0] if status == "resolved" else None
        resolution = CardResolution(
            resolution_id=_stable_id("resolution", item, self._catalog.catalog_snapshot_id),
            source_id=item.staging_record.source_id,
            source_snapshot_id=item.staging_record.raw_locator.source_snapshot_id,
            source_object_id=item.staging_record.raw_locator.raw_object_id,
            original_value=item.original_value,
            raw_locator=item.staging_record.raw_locator.exact_locator,
            method=method,
            status=status,
            candidates=candidates,
            canonical_oracle_id=canonical.oracle_id if canonical else None,
            canonical_printing_id=canonical.printing_id if canonical else None,
            canonical_face_id=canonical.face_id if canonical else None,
            resolver_version=self._resolver_version,
            normalization_policy_version=self._normalization_policy_version,
            alias_catalog_version=self._aliases.version,
            alias_catalog_sha256=self._aliases.sha256,
            card_catalog_snapshot_id=self._catalog.catalog_snapshot_id,
            finding_code=finding,
            provenance=self._provenance_for(canonical),
        )
        attempt_status: AttemptStatus = (
            "RESOLVED"
            if status == "resolved"
            else "AMBIGUOUS"
            if status == "ambiguous"
            else "UNRESOLVED"
        )
        attempt = ResolutionAttempt(
            attempt_id=_stable_id("attempt", item, self._catalog.catalog_snapshot_id),
            staging_record_id=item.staging_record.staging_record_id,
            raw_locator=item.staging_record.raw_locator,
            source_field=item.source_field,
            original_source_value={
                "value": item.original_value,
                "requested_quantity": item.requested_quantity,
                "source_values": values,
            },
            resolver_version=self._resolver_version,
            normalization_policy_version=self._normalization_policy_version,
            alias_catalog_version=self._aliases.version,
            card_catalog_snapshot_id=self._catalog.catalog_snapshot_id,
            status=attempt_status,
            candidate_canonical_ids=tuple(
                sorted({candidate.oracle_id for candidate in candidates})
            ),
            canonical_id=canonical.oracle_id if canonical else None,
            finding_codes=() if finding is None else (finding,),
            attempted_at=attempted_at,
        )
        quarantine = None
        if finding is not None:
            quarantine = quarantine_record(item.staging_record, reason_code=finding)
        return ResolutionResult(resolution=resolution, attempt=attempt, quarantine=quarantine)

    def resolve_many(
        self,
        items: Iterable[CardResolutionInput],
        *,
        attempted_at: datetime | None = None,
    ) -> tuple[ResolutionResult, ...]:
        """Resolve a batch without changing input order or hiding failed attempts."""

        return tuple(self.resolve(item, attempted_at=attempted_at) for item in items)

    def _identifier_match(
        self, values: object
    ) -> tuple[ResolutionMethod, tuple[CardResolutionCandidate, ...], str | None] | None:
        if not isinstance(values, Mapping):
            return None
        matches: list[tuple[ResolutionMethod, tuple[CardResolutionCandidate, ...]]] = []
        for identifier_name, identifier in source_identifiers(values):
            candidates = self._catalog.identifier_index.get(identifier, ())
            if not candidates:
                continue
            method: ResolutionMethod = (
                "source_identifier" if identifier_name == "uuid" else "exact_identifier"
            )
            matches.append((method, candidates))
        if not matches:
            return None
        method = matches[0][0]
        candidates = tuple(
            sorted(
                {
                    (
                        candidate.oracle_id,
                        candidate.printing_id or "",
                        candidate.face_id or "",
                    ): candidate
                    for _, matched in matches
                    for candidate in matched
                }.values(),
                key=lambda candidate: (
                    candidate.oracle_id,
                    candidate.printing_id or "",
                    candidate.face_id or "",
                ),
            )
        )
        oracle_ids = {candidate.oracle_id for candidate in candidates}
        printings_by_oracle = {
            oracle_id: {
                candidate.printing_id
                for candidate in candidates
                if candidate.oracle_id == oracle_id and candidate.printing_id
            }
            for oracle_id in oracle_ids
        }
        faces_by_oracle = {
            oracle_id: {
                candidate.face_id
                for candidate in candidates
                if candidate.oracle_id == oracle_id and candidate.face_id
            }
            for oracle_id in oracle_ids
        }
        if (
            len(oracle_ids) > 1
            or any(len(values) > 1 for values in printings_by_oracle.values())
            or any(len(values) > 1 for values in faces_by_oracle.values())
        ):
            return method, candidates, "resolution.conflicting_identifiers"
        selected = max(
            candidates,
            key=lambda candidate: (
                candidate.printing_id is not None,
                candidate.face_id is not None,
                candidate.oracle_id,
            ),
        )
        return method, (selected,), None

    def _name_match(
        self, value: str
    ) -> tuple[ResolutionMethod, tuple[CardResolutionCandidate, ...], str | None]:
        normalized = normalize_card_name(value)
        candidates = self._catalog.name_index.get(normalized, ())
        face_candidates = self._catalog.face_name_index.get(normalized, ())
        if candidates and face_candidates:
            candidate_oracles = {candidate.oracle_id for candidate in candidates}
            face_oracles = {candidate.oracle_id for candidate in face_candidates}
            if candidate_oracles != face_oracles or len(candidates) > 1 or len(face_candidates) > 1:
                combined = _unique_candidates((*candidates, *face_candidates))
                return "exact_name", combined, "resolution.ambiguous_name"
            return "exact_name", candidates, None
        if candidates:
            return "exact_name", candidates, None
        if face_candidates:
            return "split_face", face_candidates, None
        alias_candidates = self._aliases.aliases.get(normalized, ())
        if alias_candidates:
            if not all(self._candidate_exists(candidate) for candidate in alias_candidates):
                return "alias", (), "resolution.alias_target_unresolved"
            return "alias", alias_candidates, None
        return "none", (), "resolution.unresolved_name"

    def _candidate_exists(self, candidate: CardResolutionCandidate) -> bool:
        if not any(card.oracle_id == candidate.oracle_id for card in self._catalog.cards):
            return False
        printing = None
        if candidate.printing_id is not None:
            printing = next(
                (
                    printing
                    for printing in self._catalog.printings
                    if printing.printing_id == candidate.printing_id
                ),
                None,
            )
            if printing is None or printing.oracle_id != candidate.oracle_id:
                return False
        if candidate.face_id is None:
            return True
        face = next(
            (face for face in self._catalog.faces if face.face_id == candidate.face_id),
            None,
        )
        if face is None or face.oracle_id != candidate.oracle_id:
            return False
        return printing is None or candidate.face_id in printing.face_ids

    def _provenance_for(
        self, candidate: CardResolutionCandidate | None
    ) -> tuple[ProvenanceReference, ...]:
        if candidate is None:
            return ()
        for card in self._catalog.cards:
            if card.oracle_id == candidate.oracle_id:
                return card.provenance
        return ()


def _resolution_status(candidates: tuple[CardResolutionCandidate, ...]) -> ResolutionStatus:
    if len(candidates) == 1:
        return "resolved"
    if candidates:
        return "ambiguous"
    return "unresolved"


def _stable_id(prefix: str, item: CardResolutionInput, catalog_snapshot_id: str) -> str:
    payload = {
        "staging_record_id": item.staging_record.staging_record_id,
        "source_field": item.source_field,
        "original_value": item.original_value,
        "requested_quantity": item.requested_quantity,
        "catalog_snapshot_id": catalog_snapshot_id,
    }
    digest = sha256(canonical_json_bytes(payload)).hexdigest()
    return f"{prefix}-{digest[:32]}"


def _unique_candidates(
    candidates: Iterable[CardResolutionCandidate],
) -> tuple[CardResolutionCandidate, ...]:
    return tuple(
        sorted(
            {
                (
                    candidate.oracle_id,
                    candidate.printing_id or "",
                    candidate.face_id or "",
                ): candidate
                for candidate in candidates
            }.values(),
            key=lambda candidate: (
                candidate.oracle_id,
                candidate.printing_id or "",
                candidate.face_id or "",
            ),
        )
    )


__all__ = [
    "NORMALIZATION_POLICY_VERSION",
    "RESOLVER_VERSION",
    "CardResolutionInput",
    "CardResolver",
    "ResolutionResult",
]
