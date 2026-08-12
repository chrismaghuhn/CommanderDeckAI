"""Versioned, auditable quantity-weighted near-duplicate clustering."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from itertools import combinations

from commander_ai.data_pipeline.decks.canonical_decks import DeckOccurrence
from commander_ai.domain.decks import CanonicalDeck
from commander_ai.domain.serialization import canonical_json_bytes

NEAR_DUPLICATE_ALGORITHM = "quantity_weighted_jaccard"
NEAR_DUPLICATE_VERSION = "near-duplicate-v1"


@dataclass(frozen=True, slots=True)
class NearDuplicatePolicy:
    threshold: float = 0.92
    algorithm: str = NEAR_DUPLICATE_ALGORITHM
    version: str = NEAR_DUPLICATE_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("near-duplicate policy version must be non-empty")
        if not 0 <= self.threshold <= 1:
            raise ValueError("near-duplicate threshold must be between zero and one")
        if self.algorithm != NEAR_DUPLICATE_ALGORITHM:
            raise ValueError("unsupported near-duplicate algorithm")


@dataclass(frozen=True, slots=True)
class NearDuplicateCluster:
    cluster_id: str
    canonical_deck_ids: tuple[str, ...]
    policy: NearDuplicatePolicy


def cluster_near_duplicates(
    occurrences: tuple[DeckOccurrence, ...] | list[DeckOccurrence],
    *,
    policy: NearDuplicatePolicy | None = None,
) -> tuple[NearDuplicateCluster, ...]:
    policy = policy or NearDuplicatePolicy()
    by_deck_id = {occurrence.deck.canonical_deck_id: occurrence.deck for occurrence in occurrences}
    parent = {deck_id: deck_id for deck_id in by_deck_id}
    for left, right in combinations(sorted(by_deck_id), 2):
        if (
            _jaccard(_deck_multiset(by_deck_id[left]), _deck_multiset(by_deck_id[right]))
            < policy.threshold
        ):
            continue
        _union(parent, left, right)
    members: dict[str, list[str]] = {}
    for deck_id in sorted(parent):
        members.setdefault(_find(parent, deck_id), []).append(deck_id)
    clusters: list[NearDuplicateCluster] = []
    for deck_ids in sorted(members.values(), key=lambda values: tuple(values)):
        if len(deck_ids) < 2:
            continue
        cluster_hash = sha256(
            canonical_json_bytes(
                {
                    "algorithm": policy.algorithm,
                    "version": policy.version,
                    "threshold": policy.threshold,
                    "canonical_deck_ids": deck_ids,
                }
            )
        ).hexdigest()[:32]
        clusters.append(
            NearDuplicateCluster(
                cluster_id=f"near-{cluster_hash}",
                canonical_deck_ids=tuple(deck_ids),
                policy=policy,
            )
        )
    return tuple(clusters)


def _deck_multiset(deck: CanonicalDeck) -> Counter[tuple[str, str]]:
    counts: Counter[tuple[str, str]] = Counter()
    for command_entry in deck.command_zone:
        counts[("command_zone", command_entry.oracle_id.lower())] += command_entry.quantity
    for zone in deck.card_zones:
        for card_entry in zone.cards:
            counts[(zone.zone, card_entry.oracle_id.lower())] += card_entry.quantity
    return counts


def _jaccard(left: Counter[tuple[str, str]], right: Counter[tuple[str, str]]) -> float:
    keys = set(left) | set(right)
    denominator = sum(max(left[key], right[key]) for key in keys)
    if denominator == 0:
        return 1.0
    return sum(min(left[key], right[key]) for key in keys) / denominator


def _find(parent: dict[str, str], value: str) -> str:
    while parent[value] != value:
        parent[value] = parent[parent[value]]
        value = parent[value]
    return value


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root == right_root:
        return
    parent[max(left_root, right_root)] = min(left_root, right_root)


__all__ = [
    "NEAR_DUPLICATE_ALGORITHM",
    "NEAR_DUPLICATE_VERSION",
    "NearDuplicateCluster",
    "NearDuplicatePolicy",
    "cluster_near_duplicates",
]
