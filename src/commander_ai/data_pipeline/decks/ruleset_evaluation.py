"""Ruleset-authoritative Commander legality evaluation."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Literal

from commander_ai.domain.cards import CanonicalCard
from commander_ai.domain.decks import CanonicalDeck, CardQuantity, CardZone
from commander_ai.domain.evaluations import DeckLegalityEvaluation
from commander_ai.domain.rulesets import RulesetSnapshot

from .ruleset_selection import RulesetSelection

CommandZoneValidator = Callable[[CanonicalDeck, RulesetSnapshot], Sequence[str]]


def evaluate_deck_legality(
    deck: CanonicalDeck,
    card_facts: Mapping[str, CanonicalCard],
    ruleset: RulesetSnapshot | RulesetSelection | None,
    *,
    evaluated_at: datetime | None = None,
    validator_version: str = "commander-legality-v1",
    command_zone_validator: CommandZoneValidator | None = None,
) -> DeckLegalityEvaluation:
    """Evaluate card/ruleset facts without changing structural deck identity."""

    when = evaluated_at or datetime.now(UTC)
    selection_finding: str | None = None
    if isinstance(ruleset, RulesetSelection):
        selection_finding = ruleset.finding_code
        ruleset = ruleset.ruleset
    if ruleset is None:
        return _evaluation(
            deck,
            ruleset_version="unknown",
            ruleset_snapshot_sha256=None,
            when=when,
            validator_version=validator_version,
            findings=(selection_finding or "legality.ruleset_unresolved",),
        )

    findings: set[str] = set()
    command_entries = tuple(deck.command_zone)
    mainboard = _zone(deck, "mainboard")
    if mainboard is None:
        findings.add("legality.mainboard_missing")
        mainboard_cards: tuple[CardQuantity, ...] = ()
    else:
        mainboard_cards = mainboard.cards

    command_card_count = sum(entry.quantity for entry in command_entries)
    if not (
        ruleset.command_zone_policy.min_cards
        <= command_card_count
        <= ruleset.command_zone_policy.max_cards
    ):
        findings.add("legality.command_zone_size_invalid")
    if command_zone_validator is None:
        findings.add("legality.command_zone_unverified")
    else:
        findings.update(command_zone_validator(deck, ruleset))

    total_cards = sum(item.quantity for item in command_entries) + sum(
        item.quantity for item in mainboard_cards
    )
    if total_cards != ruleset.required_total_cards:
        findings.add("legality.deck_size_invalid")

    all_cards = (*command_entries, *mainboard_cards)
    missing_fact_ids = {item.oracle_id for item in all_cards if item.oracle_id not in card_facts}
    if missing_fact_ids:
        findings.add("legality.card_fact_missing")

    counts = Counter(item.oracle_id for item in all_cards for _ in range(item.quantity))
    command_colors = _command_colors(command_entries, card_facts)
    for oracle_id, quantity in counts.items():
        fact = card_facts.get(oracle_id)
        if fact is None:
            continue
        if oracle_id not in ruleset.unlimited_copy_oracle_ids:
            limit = ruleset.copy_limit_overrides.get(oracle_id, ruleset.default_copy_limit)
            if not fact.is_basic_land and quantity > limit:
                findings.add("legality.singleton_violation")
        if fact.legalities.get("commander") != "legal":
            findings.add("legality.card_not_commander_legal")
        if not set(fact.color_identity).issubset(command_colors):
            findings.add("legality.color_identity_violation")
        if oracle_id in ruleset.banned_oracle_ids:
            findings.add("legality.banned_card")

    for entry in command_entries:
        if entry.oracle_id in ruleset.banned_oracle_ids:
            findings.add("legality.commander_banned")
    companion_zone = _zone(deck, "companion")
    if companion_zone is not None:
        for companion in companion_zone.cards:
            if companion.oracle_id in ruleset.banned_as_companion_oracle_ids:
                findings.add("legality.banned_as_companion")

    return _evaluation(
        deck,
        ruleset_version=ruleset.ruleset_version,
        ruleset_snapshot_sha256=ruleset.sha256,
        when=when,
        validator_version=validator_version,
        findings=tuple(sorted(findings)),
    )


def _zone(deck: CanonicalDeck, name: str) -> CardZone | None:
    return next((zone for zone in deck.card_zones if zone.zone == name), None)


def _command_colors(
    entries: Sequence[CardQuantity], card_facts: Mapping[str, CanonicalCard]
) -> set[str]:
    colors: set[str] = set()
    for entry in entries:
        fact = card_facts.get(entry.oracle_id)
        if fact is None:
            continue
        colors.update(fact.color_identity)
    return colors


def _evaluation(
    deck: CanonicalDeck,
    *,
    ruleset_version: str,
    ruleset_snapshot_sha256: str | None,
    when: datetime,
    validator_version: str,
    findings: Sequence[str],
) -> DeckLegalityEvaluation:
    finding_tuple = tuple(sorted(set(findings)))
    unknown = {
        "legality.ruleset_unresolved",
        "legality.ruleset_ambiguous",
        "legality.card_fact_missing",
        "legality.command_zone_unverified",
    }
    status: Literal["legal", "illegal", "unknown", "quarantined"] = (
        "unknown"
        if any(code in unknown for code in finding_tuple)
        else ("illegal" if finding_tuple else "legal")
    )
    return DeckLegalityEvaluation(
        canonical_deck_id=deck.canonical_deck_id,
        ruleset_version=ruleset_version,
        ruleset_snapshot_sha256=ruleset_snapshot_sha256,
        evaluated_at=when,
        validator_version=validator_version,
        legal_status=status,
        finding_codes=finding_tuple,
        provenance=deck.provenance,
    )


__all__ = ["CommandZoneValidator", "evaluate_deck_legality"]
