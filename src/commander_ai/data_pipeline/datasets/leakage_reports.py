"""Deterministic leakage reports for task-specific dataset artifacts."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from hashlib import sha256
from itertools import combinations

from commander_ai.data_pipeline.decks.fingerprints import structural_fingerprint
from commander_ai.data_pipeline.deduplication.revisions import REVISION_GROUP_VERSION
from commander_ai.domain.dataset_contracts import DatasetManifest
from commander_ai.domain.serialization import canonical_json_bytes

DATASET_LEAKAGE_REPORT_VERSION = "dataset-leakage-report.v1"
_SPLITS = frozenset({"train", "validation", "test"})


def build_leakage_report(
    manifest: DatasetManifest,
    content_inputs: Sequence[tuple[str, Sequence[Mapping[str, object]]]],
) -> dict[str, object]:
    """Build the canonical report from the exact rows bound by a dataset."""

    group_splits: dict[str, set[str]] = {}
    event_splits: dict[str, set[str]] = {}
    row_values: list[Mapping[str, object]] = []
    for _, rows in content_inputs:
        for row in rows:
            values = row.get("values")
            if not isinstance(values, Mapping):
                raise ValueError("leakage report requires row values mappings")
            row_values.append(values)
            split = values.get("split")
            if not isinstance(split, str) or split not in _SPLITS:
                raise ValueError("leakage report requires valid row splits")
            _add_group_memberships(group_splits, values.get("group_ids"), split)
            event_id = values.get("event_id")
            if event_id is not None:
                if not isinstance(event_id, str) or not event_id:
                    raise ValueError("event_id must be a non-empty string")
                event_splits.setdefault(event_id, set()).add(split)

    _add_derived_group_memberships(group_splits, manifest, row_values)
    cross_split_groups = _cross_split_ids(group_splits)
    cross_split_events = _cross_split_ids(event_splits)
    manifest_payload = manifest.model_dump(mode="json")
    return {
        "schema_version": DATASET_LEAKAGE_REPORT_VERSION,
        "dataset_id": manifest.dataset_id,
        "dataset_kind": manifest.dataset_kind,
        "dataset_content_sha256": manifest.dataset_content_sha256,
        "input_manifests": [item.model_dump(mode="json") for item in manifest.input_manifests],
        "policy": {
            "split_policy": manifest_payload["split_policy"],
            "split_policy_version": manifest.split_policy_version,
            "near_duplicate_algorithm": manifest.near_duplicate_algorithm,
            "near_duplicate_version": manifest.near_duplicate_version,
            "near_duplicate_threshold": manifest.near_duplicate_threshold,
        },
        "group_splits": _sorted_split_map(group_splits),
        "event_splits": _sorted_split_map(event_splits),
        "cross_split_group_ids": cross_split_groups,
        "cross_split_event_ids": cross_split_events,
        "status": "PASS" if not cross_split_groups and not cross_split_events else "FAIL",
    }


def _add_group_memberships(
    memberships: dict[str, set[str]], raw_group_ids: object, split: str
) -> None:
    if raw_group_ids is None:
        return
    if not isinstance(raw_group_ids, (list, tuple)):
        raise ValueError("group_ids must be a collection")
    for group_id in raw_group_ids:
        if not isinstance(group_id, str) or not group_id:
            raise ValueError("group_ids must contain non-empty strings")
        memberships.setdefault(group_id, set()).add(split)


def _add_derived_group_memberships(
    memberships: dict[str, set[str]],
    manifest: DatasetManifest,
    rows: Sequence[Mapping[str, object]],
) -> None:
    """Reconstruct leakage groups from persisted structural values, not labels."""

    if manifest.dataset_kind == "tournament_outcomes":
        for values in rows:
            event_id = values.get("event_id")
            split = values.get("split")
            if isinstance(event_id, str) and isinstance(split, str):
                memberships.setdefault(f"event:{event_id}", set()).add(split)
        return
    if manifest.dataset_kind not in {"deck_completion", "card_cooccurrence"}:
        return

    deduplication = manifest.filters.get("deduplication")
    settings = deduplication if isinstance(deduplication, Mapping) else {}
    if settings.get("exact_fingerprint", True) is True:
        for values in rows:
            fingerprint = _structural_fingerprint(values)
            if fingerprint is None:
                _require_structure(manifest, "exact fingerprint")
                continue
            _add_value_group(memberships, values, f"exact:{fingerprint}")
    if settings.get("group_revisions", True) is True:
        for values in rows:
            source_id = values.get("source_id")
            source_deck_id = values.get("source_deck_id")
            split = values.get("split")
            if (
                isinstance(source_id, str)
                and source_id
                and isinstance(source_deck_id, str)
                and source_deck_id
                and isinstance(split, str)
            ):
                digest = sha256(
                    canonical_json_bytes(
                        {
                            "version": REVISION_GROUP_VERSION,
                            "source_id": source_id,
                            "source_deck_id": source_deck_id,
                        }
                    )
                ).hexdigest()[:32]
                memberships.setdefault(f"revision:revision-{digest}", set()).add(split)
            elif manifest.dataset_kind == "card_cooccurrence":
                _require_structure(manifest, "source revision grouping")
    if manifest.near_duplicate_algorithm is not None:
        _add_near_duplicate_groups(memberships, manifest, rows)


def _add_value_group(
    memberships: dict[str, set[str]], values: Mapping[str, object], group_id: object
) -> None:
    split = values.get("split")
    if isinstance(group_id, str) and group_id != "exact:None" and isinstance(split, str):
        memberships.setdefault(group_id, set()).add(split)


def _add_near_duplicate_groups(
    memberships: dict[str, set[str]],
    manifest: DatasetManifest,
    rows: Sequence[Mapping[str, object]],
) -> None:
    decks: dict[str, Counter[tuple[str, str]]] = {}
    row_deck_ids: list[tuple[str, str]] = []
    for values in rows:
        deck_id = _structural_fingerprint(values)
        signature = _deck_signature(values)
        if not isinstance(deck_id, str) or not deck_id or signature is None:
            _require_structure(manifest, "near-duplicate grouping")
            continue
        decks.setdefault(deck_id, signature)
        row_deck_ids.append((deck_id, str(values.get("split", ""))))
    parent = {deck_id: deck_id for deck_id in decks}
    threshold = manifest.near_duplicate_threshold
    if threshold is None or manifest.near_duplicate_version is None:
        return
    for left, right in combinations(sorted(decks), 2):
        if _jaccard(decks[left], decks[right]) >= threshold:
            _union(parent, left, right)
    components: dict[str, list[str]] = {}
    for deck_id in sorted(parent):
        components.setdefault(_find(parent, deck_id), []).append(deck_id)
    for deck_ids in components.values():
        if len(deck_ids) < 2:
            continue
        cluster_hash = sha256(
            canonical_json_bytes(
                {
                    "algorithm": manifest.near_duplicate_algorithm,
                    "version": manifest.near_duplicate_version,
                    "threshold": threshold,
                    "canonical_deck_ids": deck_ids,
                }
            )
        ).hexdigest()[:32]
        group_id = f"near:near-{cluster_hash}"
        for deck_id, split in row_deck_ids:
            if deck_id in deck_ids and split:
                memberships.setdefault(group_id, set()).add(split)


def _deck_signature(values: Mapping[str, object]) -> Counter[tuple[str, str]] | None:
    counts: Counter[tuple[str, str]] = Counter()
    if not _add_zone_cards(counts, "command_zone", values.get("command_zone")):
        return None
    card_zones = values.get("card_zones")
    if not isinstance(card_zones, (list, tuple)):
        return None
    for zone in card_zones:
        if not isinstance(zone, Mapping) or not isinstance(zone.get("zone"), str):
            return None
        if not _add_zone_cards(counts, zone["zone"], zone.get("cards")):
            return None
    return counts


def _structural_fingerprint(values: Mapping[str, object]) -> str | None:
    command_zone = values.get("command_zone")
    card_zones = values.get("card_zones")
    if not isinstance(command_zone, (list, tuple)) or not isinstance(card_zones, (list, tuple)):
        return None
    try:
        return structural_fingerprint(command_zone, card_zones)
    except (TypeError, ValueError):
        return None


def _require_structure(manifest: DatasetManifest, policy: str) -> None:
    if manifest.dataset_kind == "card_cooccurrence":
        raise ValueError(f"card co-occurrence rows lack structure for {policy} audit")


def _add_zone_cards(counts: Counter[tuple[str, str]], zone: str, raw_cards: object) -> bool:
    if not isinstance(raw_cards, (list, tuple)):
        return False
    for card in raw_cards:
        if not isinstance(card, Mapping):
            return False
        oracle_id = card.get("oracle_id")
        quantity = card.get("quantity")
        if not isinstance(oracle_id, str) or not oracle_id or not isinstance(quantity, int):
            return False
        counts[(zone, oracle_id.lower())] += quantity
    return True


def _jaccard(left: Counter[tuple[str, str]], right: Counter[tuple[str, str]]) -> float:
    keys = set(left) | set(right)
    denominator = sum(max(left[key], right[key]) for key in keys)
    return (
        1.0 if denominator == 0 else sum(min(left[key], right[key]) for key in keys) / denominator
    )


def _find(parent: dict[str, str], value: str) -> str:
    while parent[value] != value:
        parent[value] = parent[parent[value]]
        value = parent[value]
    return value


def _union(parent: dict[str, str], left: str, right: str) -> None:
    left_root = _find(parent, left)
    right_root = _find(parent, right)
    if left_root != right_root:
        parent[max(left_root, right_root)] = min(left_root, right_root)


def _cross_split_ids(memberships: Mapping[str, set[str]]) -> list[str]:
    return sorted(group_id for group_id, splits in memberships.items() if len(splits) > 1)


def _sorted_split_map(memberships: Mapping[str, set[str]]) -> dict[str, list[str]]:
    return {group_id: sorted(splits) for group_id, splits in sorted(memberships.items())}


__all__ = ["DATASET_LEAKAGE_REPORT_VERSION", "build_leakage_report"]
