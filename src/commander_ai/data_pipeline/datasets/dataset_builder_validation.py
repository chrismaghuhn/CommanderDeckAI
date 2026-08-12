"""Validation failures and input checks shared by the dataset builder."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .dataset_builder import DatasetBuildRequest


class DatasetBuildError(ValueError):
    """Stable data-pipeline failure that can be promoted to an application code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_ruleset_binding(request: DatasetBuildRequest) -> None:
    """Require explicit, non-unknown rulesets for legal-only projections."""

    versions = tuple(request.ruleset_versions)
    if any(not version.strip() or version.strip().casefold() == "unknown" for version in versions):
        raise DatasetBuildError("LEGAL_RULESET_BINDING_INVALID")
    if request.settings.inputs.legal_decks_only and not versions:
        raise DatasetBuildError("LEGAL_RULESET_BINDING_REQUIRED")


__all__ = ["DatasetBuildError", "validate_ruleset_binding"]
