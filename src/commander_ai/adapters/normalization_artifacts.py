"""Small persistence helpers for normalized snapshot outputs."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from commander_ai.data_pipeline.provenance.normalized_snapshot_contracts import (
    NormalizedTableArtifact,
)
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.staging.records import StagingRecord


def table_artifact(item: Any) -> NormalizedTableArtifact:
    return NormalizedTableArtifact(
        table_name=item.table_name,
        layer=item.layer,
        path=item.path,
        sha256=item.sha256,
        rows=item.rows,
        bytes=item.bytes,
    )


def audit_records(
    records: Sequence[Any], staging: Sequence[StagingRecord]
) -> tuple[AuditRecord, ...]:
    by_locator = {item.raw_locator.exact_locator: item for item in staging}
    audits: list[AuditRecord] = []
    for record in records:
        staged = by_locator.get(record.raw_locator.exact_locator)
        if staged is None:
            continue
        for finding in record.findings:
            digest = hashlib.sha256(
                f"{staged.staging_record_id}|{finding.code}|{finding.raw_locator.exact_locator}".encode()
            ).hexdigest()[:32]
            audits.append(
                AuditRecord(
                    audit_id=f"audit-{digest}",
                    entity_id=staged.staging_record_id,
                    stage=FindingCode.parse(finding.code).namespace,
                    finding_code=finding.code,
                    raw_locator=finding.raw_locator,
                    details={"record_type": record.record_type, "message": finding.message},
                )
            )
    return tuple(sorted(audits, key=lambda item: item.audit_id))


__all__ = ["audit_records", "table_artifact"]
