"""Result contract for source-agnostic canonicalization."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from typing import cast

from commander_ai.data_pipeline.events.pod_entries import PodCompletenessIndex, index_complete_pods
from commander_ai.data_pipeline.provenance.rows import AuditRecord, ProvenanceRow, ResolutionAttempt
from commander_ai.data_pipeline.quality.finding_codes import FindingNamespace
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord
from commander_ai.data_pipeline.staging.records import StagingRecord
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
    pod_index: PodCompletenessIndex = field(default_factory=PodCompletenessIndex)


def failed_canonicalization(record: StagingRecord, code: str) -> CanonicalizationResult:
    """Retain one failed staging row without constructing a canonical value."""

    from commander_ai.data_pipeline.quality.quarantine import quarantine_record

    return canonicalization_result(
        (), (), (), (), (), (quarantine_record(record, reason_code=code),), {code}
    )


def audit_for_quarantines(
    quarantines: Sequence[QuarantineRecord],
) -> tuple[AuditRecord, ...]:
    """Create deterministic audit rows for retained canonicalization failures."""

    return tuple(
        AuditRecord(
            audit_id=f"canonical-audit-{item.quarantine_id}",
            entity_id=item.staging_record_id,
            stage=cast(FindingNamespace, item.reason_code.split(".", maxsplit=1)[0]),
            finding_code=item.reason_code,
            raw_locator=item.raw_locator,
            details={"quarantine_id": item.quarantine_id},
        )
        for item in sorted(quarantines, key=lambda item: item.quarantine_id)
    )


def canonicalization_result(
    records: Sequence[CanonicalRecord],
    resolutions: Sequence[CardResolution],
    attempts: Sequence[ResolutionAttempt],
    audits: Sequence[AuditRecord],
    provenance: Sequence[ProvenanceRow],
    quarantines: Sequence[QuarantineRecord],
    findings: Iterable[str],
) -> CanonicalizationResult:
    """Normalize result ordering so identical staging inputs rebuild identically."""

    ordered_records = tuple(sorted(records, key=lambda item: item.record_id))
    return CanonicalizationResult(
        records=ordered_records,
        resolutions=tuple(sorted(resolutions, key=lambda item: item.resolution_id)),
        resolution_attempts=tuple(sorted(attempts, key=lambda item: item.attempt_id)),
        audits=tuple(sorted(audits, key=lambda item: item.audit_id)),
        provenance=tuple(sorted(provenance, key=lambda item: item.provenance_id)),
        quarantines=tuple(
            sorted(
                {item.quarantine_id: item for item in quarantines}.values(),
                key=lambda item: item.quarantine_id,
            )
        ),
        finding_codes=tuple(sorted(set(findings))),
        pod_index=index_complete_pods(ordered_records),
    )


__all__ = [
    "CanonicalizationResult",
    "audit_for_quarantines",
    "canonicalization_result",
    "failed_canonicalization",
]
