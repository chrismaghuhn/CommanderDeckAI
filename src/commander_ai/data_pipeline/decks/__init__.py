"""Canonical Commander deck construction and ruleset-scoped evaluation."""

from .canonical_decks import (
    CanonicalDeckResult,
    DeckCanonicalizationError,
    DeckOccurrence,
    DeckSourceReference,
    DeckStructureInput,
    canonical_deck_from_input,
)
from .fingerprints import (
    STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION,
    canonical_deck_id,
    structural_fingerprint,
)
from .quality import evaluate_deck_quality
from .ruleset_evaluation import evaluate_deck_legality
from .ruleset_selection import RulesetSelection, select_applicable_ruleset

__all__ = [
    "STRUCTURAL_FINGERPRINT_ALGORITHM_VERSION",
    "CanonicalDeckResult",
    "DeckCanonicalizationError",
    "DeckOccurrence",
    "DeckSourceReference",
    "DeckStructureInput",
    "RulesetSelection",
    "canonical_deck_from_input",
    "canonical_deck_id",
    "evaluate_deck_legality",
    "evaluate_deck_quality",
    "select_applicable_ruleset",
    "structural_fingerprint",
]
