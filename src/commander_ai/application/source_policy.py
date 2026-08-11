"""Application source gate backed by typed registry data and policy ports."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from commander_ai.config.current_use_policy import (
    CurrentUsePolicy,
    CurrentUseResult,
    CurrentUseStatus,
    PolicyOperation,
)
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import (
    SourceApprovalStatus,
    SourceSettings,
    normalize_source_id,
)


@dataclass(frozen=True, slots=True)
class SourcePolicyDecision:
    source_id: str
    operation: PolicyOperation
    allowed: bool
    code: str
    reason: str
    historical_status: SourceApprovalStatus | None
    current_status: CurrentUseStatus | None
    decision_reference: str | None = None
    decision_sha256: str | None = None


@dataclass(frozen=True, slots=True)
class SourceAdapterConfiguration:
    """Typed adapter inputs; creating this value does not instantiate an adapter."""

    source: SourceSettings
    historical_approval: HistoricalApprovalMetadata


class SourcePolicyError(ValueError):
    """Safe policy failure carrying a stable code but no source secrets."""

    def __init__(self, decision: SourcePolicyDecision) -> None:
        self.code = decision.code
        super().__init__(f"{decision.code}: source policy denied for {decision.source_id}")


@runtime_checkable
class SourcePolicyPort(Protocol):
    def check_operation(
        self, source_id: str, operation: PolicyOperation | str
    ) -> SourcePolicyDecision:
        """Return a source-policy decision without performing source I/O."""


class SourcePolicy:
    """Exact historical allowlists plus independent current-use evaluation."""

    LOCAL_SYNC_ALLOWLIST = frozenset(
        {SourceApprovalStatus.APPROVED_LOCAL, SourceApprovalStatus.APPROVED_REDISTRIBUTION}
    )
    PUBLIC_EXPORT_ALLOWLIST = frozenset({SourceApprovalStatus.APPROVED_REDISTRIBUTION})

    def __init__(self, registry: SourceRegistry) -> None:
        self._registry = registry

    def local_sync_allowed(self, source_id: str) -> bool:
        return self.check_local_sync(source_id).allowed

    def public_export_allowed(self, source_id: str) -> bool:
        return self.check_operation(source_id, PolicyOperation.PUBLIC_EXPORT).allowed

    def operation_allowed(self, source_id: str, operation: PolicyOperation | str) -> bool:
        return self.check_operation(source_id, operation).allowed

    def check_local_sync(self, source_id: str) -> SourcePolicyDecision:
        normalized = normalize_source_id(source_id)
        entry = self._registry.get(normalized)
        if entry is None:
            return self._unknown_source(normalized, PolicyOperation.SOURCE_SYNC)
        historical_status = entry.historical_approval.approval_status
        if historical_status not in self.LOCAL_SYNC_ALLOWLIST:
            return self._blocked_historical(entry, PolicyOperation.SOURCE_SYNC)
        current = CurrentUsePolicy.check(
            source_id=normalized,
            historical_status=historical_status,
            current_use=entry.current_use,
            operation=PolicyOperation.SOURCE_SYNC,
        )
        if not current.allowed:
            return self._from_current(current)
        return SourcePolicyDecision(
            source_id=normalized,
            operation=PolicyOperation.SOURCE_SYNC,
            allowed=True,
            code="POLICY_LOCAL_SYNC_ALLOWED",
            reason="historical source status is locally allowlisted",
            historical_status=historical_status,
            current_status=current.current_status,
            decision_reference=current.decision_reference,
            decision_sha256=current.decision_sha256,
        )

    def check_operation(
        self, source_id: str, operation: PolicyOperation | str
    ) -> SourcePolicyDecision:
        normalized = normalize_source_id(source_id)
        normalized_operation = PolicyOperation.normalize(operation)
        entry = self._registry.get(normalized)
        if entry is None:
            return self._unknown_source(normalized, normalized_operation)
        historical_status = entry.historical_approval.approval_status
        if normalized_operation.is_audit_only:
            current = CurrentUsePolicy.check(
                source_id=normalized,
                historical_status=historical_status,
                current_use=entry.current_use,
                operation=normalized_operation,
            )
            return self._from_current(current)
        if historical_status not in self.LOCAL_SYNC_ALLOWLIST:
            return self._blocked_historical(entry, normalized_operation)

        current = CurrentUsePolicy.check(
            source_id=normalized,
            historical_status=historical_status,
            current_use=entry.current_use,
            operation=normalized_operation,
        )
        if not current.allowed:
            return self._from_current(current)
        if (
            normalized_operation is PolicyOperation.PUBLIC_EXPORT
            and historical_status not in self.PUBLIC_EXPORT_ALLOWLIST
        ):
            return SourcePolicyDecision(
                source_id=normalized,
                operation=normalized_operation,
                allowed=False,
                code="POLICY_REDISTRIBUTION_NOT_APPROVED",
                reason="historical redistribution approval is required for public export",
                historical_status=historical_status,
                current_status=current.current_status,
                decision_reference=current.decision_reference,
                decision_sha256=current.decision_sha256,
            )
        return SourcePolicyDecision(
            source_id=normalized,
            operation=normalized_operation,
            allowed=True,
            code="POLICY_OPERATION_ALLOWED",
            reason="source and current-use policy allow the operation",
            historical_status=historical_status,
            current_status=current.current_status,
            decision_reference=current.decision_reference,
            decision_sha256=current.decision_sha256,
        )

    def require_operation(
        self, source_id: str, operation: PolicyOperation | str
    ) -> SourcePolicyDecision:
        decision = self.check_operation(source_id, operation)
        if not decision.allowed:
            raise SourcePolicyError(decision)
        return decision

    def adapter_configuration(self, source_id: str) -> SourceAdapterConfiguration:
        normalized = normalize_source_id(source_id)
        entry = self._registry.get(normalized)
        if entry is None:
            raise SourcePolicyError(self._unknown_source(normalized, PolicyOperation.SOURCE_SYNC))
        acquisition = self.check_local_sync(normalized)
        if not acquisition.allowed:
            raise SourcePolicyError(acquisition)
        if entry.settings.review_path is None:
            decision = SourcePolicyDecision(
                source_id=normalized,
                operation=PolicyOperation.SOURCE_SYNC,
                allowed=False,
                code="POLICY_SOURCE_REVIEW_REQUIRED",
                reason="an explicit source review path is required",
                historical_status=entry.historical_approval.approval_status,
                current_status=entry.current_use.status if entry.current_use else None,
            )
            raise SourcePolicyError(decision)
        if entry.settings.review_path != entry.historical_approval.review_path:
            decision = SourcePolicyDecision(
                source_id=normalized,
                operation=PolicyOperation.SOURCE_SYNC,
                allowed=False,
                code="POLICY_SOURCE_REVIEW_MISMATCH",
                reason="source config and historical review path must match",
                historical_status=entry.historical_approval.approval_status,
                current_status=entry.current_use.status if entry.current_use else None,
            )
            raise SourcePolicyError(decision)
        return SourceAdapterConfiguration(
            source=entry.settings,
            historical_approval=entry.historical_approval,
        )

    @staticmethod
    def _unknown_source(source_id: str, operation: PolicyOperation) -> SourcePolicyDecision:
        return SourcePolicyDecision(
            source_id=source_id,
            operation=operation,
            allowed=False,
            code="POLICY_UNKNOWN_SOURCE",
            reason="source is not present in the registry",
            historical_status=None,
            current_status=None,
        )

    @staticmethod
    def _blocked_historical(
        entry: SourceRegistryEntry, operation: PolicyOperation
    ) -> SourcePolicyDecision:
        return SourcePolicyDecision(
            source_id=entry.source_id,
            operation=operation,
            allowed=False,
            code="POLICY_SOURCE_NOT_APPROVED",
            reason="historical source status is not in the operation allowlist",
            historical_status=entry.historical_approval.approval_status,
            current_status=entry.current_use.status if entry.current_use else None,
        )

    @staticmethod
    def _from_current(result: CurrentUseResult) -> SourcePolicyDecision:
        return SourcePolicyDecision(
            source_id=result.source_id,
            operation=result.operation,
            allowed=result.allowed,
            code=result.code,
            reason=result.reason,
            historical_status=result.historical_status,
            current_status=result.current_status,
            decision_reference=result.decision_reference,
            decision_sha256=result.decision_sha256,
        )
