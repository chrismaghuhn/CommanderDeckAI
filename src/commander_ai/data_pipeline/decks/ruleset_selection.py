"""Effective-date selection for historical Commander rulesets."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal

from commander_ai.domain.rulesets import RulesetSnapshot


@dataclass(frozen=True, slots=True)
class RulesetSelection:
    """Selection result that makes unresolved historical context explicit."""

    status: Literal["selected", "unknown", "ambiguous"]
    ruleset: RulesetSnapshot | None
    finding_code: str | None


def select_applicable_ruleset(
    snapshots: Iterable[RulesetSnapshot], observed_at: date | datetime
) -> RulesetSelection:
    """Select by effective date; never fall back to the newest/current snapshot."""

    observed_date = observed_at.date() if isinstance(observed_at, datetime) else observed_at
    applicable = tuple(
        snapshot
        for snapshot in snapshots
        if snapshot.effective_from <= observed_date
        and (snapshot.effective_until is None or observed_date < snapshot.effective_until)
    )
    if not applicable:
        return RulesetSelection("unknown", None, "legality.ruleset_unresolved")
    latest_date = max(snapshot.effective_from for snapshot in applicable)
    latest = tuple(snapshot for snapshot in applicable if snapshot.effective_from == latest_date)
    if len(latest) != 1:
        return RulesetSelection("ambiguous", None, "legality.ruleset_ambiguous")
    return RulesetSelection("selected", latest[0], None)


__all__ = ["RulesetSelection", "select_applicable_ruleset"]
