"""Measured-data-free source status rows for audit reports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SourceAssessment:
    """Status evidence that deliberately does not masquerade as a snapshot."""

    source_id: str
    approval_status: str
    current_use_status: str | None
    policy_code: str
    policy_allowed: bool
    research_only: bool
    reason: str
    decision_reference: str | None = None
    decision_sha256: str | None = None

    def as_source_report(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "snapshot_id": None,
            "snapshot_date": None,
            "raw_bytes": 0,
            "source_record_count": 0,
            "commander_decks": 0,
            "total_decks": 0,
            "complete_decklists": 0,
            "incomplete_decklists": 0,
            "unique_commanders": [],
            "unique_cards": [],
            "date_range": None,
            "duplicates": {"exact_decks": 0, "cross_source_overlap_decks": 0},
            "tournaments": 0,
            "event_observations": {"complete": 0},
            "resolution": {
                "total": 0,
                "resolved": 0,
                "ambiguous": 0,
                "unresolved": 0,
                "success_rate": None,
            },
            "missing_commander_count": 0,
            "legality": {"by_status": {}, "unknown": 0},
            "legality_unknown_count": 0,
            "quality": {"by_status": {}, "unknown": 0},
            "quality_unknown_count": 0,
            "mode_availability": {"casual": 0, "competitive": 0, "unknown": 0},
            "outcomes": {"usable": 0},
            "pods": {"total": 0, "complete": 0, "full": 0},
            "quarantined_records": 0,
            "finding_counts": {},
            "recommended_use": "audit_only",
            "assessment_only": True,
            "measured_data": False,
            "approval_status": self.approval_status,
            "current_use_status": self.current_use_status,
            "policy_code": self.policy_code,
            "policy_allowed": self.policy_allowed,
            "research_only": self.research_only,
            "reason": self.reason,
        }

    def as_current_use(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "operation": "audit_inspect",
            "allowed": self.policy_allowed,
            "code": self.policy_code,
            "reason": self.reason,
            "historical_status": self.approval_status,
            "current_status": self.current_use_status,
            "decision_reference": self.decision_reference,
            "decision_sha256": self.decision_sha256,
        }


__all__ = ["SourceAssessment"]
