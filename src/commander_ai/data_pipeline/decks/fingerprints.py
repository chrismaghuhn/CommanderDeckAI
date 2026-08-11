"""Deterministic structural identity for Commander decks."""

from __future__ import annotations

from collections.abc import Sequence

from commander_ai.domain.decks import (
    STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION,
    CanonicalDeck,
    CardZone,
    CommandZoneEntry,
    compute_structural_fingerprint,
)


def structural_fingerprint(
    command_zone: Sequence[CommandZoneEntry | dict[str, object]],
    card_zones: Sequence[CardZone | dict[str, object]],
) -> str:
    """Hash only stable Commander structure, never ruleset or observation metadata."""

    return compute_structural_fingerprint(command_zone, card_zones)


def canonical_deck_id(deck: CanonicalDeck) -> str:
    """Return the deterministic identity already bound into a canonical deck."""

    expected = structural_fingerprint(deck.command_zone, deck.card_zones)
    if expected != deck.structural_fingerprint:
        raise ValueError("deck structural fingerprint is not reproducible")
    return expected


__all__ = [
    "STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION",
    "canonical_deck_id",
    "structural_fingerprint",
]
