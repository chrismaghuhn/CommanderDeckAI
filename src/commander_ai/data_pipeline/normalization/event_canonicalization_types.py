"""Internal result values shared by event canonicalization stages."""

from __future__ import annotations

from dataclasses import dataclass, field

from commander_ai.data_pipeline.events.pod_entries import PodCompletenessIndex
from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.data_pipeline.provenance.rows import AuditRecord, ProvenanceRow, ResolutionAttempt
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.domain.cards import CardResolution


@dataclass(frozen=True, slots=True)
class EventCanonicalizationResult:
    """Canonical observations plus retained event/pod quality outcomes."""

    records: tuple[CanonicalRecord, ...]
    audits: tuple[AuditRecord, ...]
    quarantines: tuple[QuarantineRecord, ...]
    finding_codes: tuple[str, ...]
    resolutions: tuple[CardResolution, ...] = ()
    resolution_attempts: tuple[ResolutionAttempt, ...] = ()
    provenance: tuple[ProvenanceRow, ...] = ()
    deck_bindings: tuple[tuple[str, str, str], ...] = ()
    pod_index: PodCompletenessIndex = field(default_factory=PodCompletenessIndex)


__all__ = ["EventCanonicalizationResult"]
