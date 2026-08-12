"""Result contract for source-agnostic canonicalization."""

from __future__ import annotations

from dataclasses import dataclass

from commander_ai.data_pipeline.provenance.rows import AuditRecord, ProvenanceRow, ResolutionAttempt
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.domain.cards import CardResolution

from .canonical_records import CanonicalRecord


@dataclass(frozen=True, slots=True)
class CanonicalizationResult:
    """Canonical rows plus every retained resolution/audit outcome."""

    records: tuple[CanonicalRecord, ...]
    resolutions: tuple[CardResolution, ...]
    resolution_attempts: tuple[ResolutionAttempt, ...]
    audits: tuple[AuditRecord, ...]
    provenance: tuple[ProvenanceRow, ...]
    quarantines: tuple[QuarantineRecord, ...]
    finding_codes: tuple[str, ...]


__all__ = ["CanonicalizationResult"]
