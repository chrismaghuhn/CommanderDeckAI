"""Deterministic leakage reports for task-specific dataset artifacts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from commander_ai.domain.dataset_contracts import DatasetManifest

DATASET_LEAKAGE_REPORT_VERSION = "dataset-leakage-report.v1"
_SPLITS = frozenset({"train", "validation", "test"})


def build_leakage_report(
    manifest: DatasetManifest,
    content_inputs: Sequence[tuple[str, Sequence[Mapping[str, object]]]],
) -> dict[str, object]:
    """Build the canonical report from the exact rows bound by a dataset."""

    group_splits: dict[str, set[str]] = {}
    event_splits: dict[str, set[str]] = {}
    for _, rows in content_inputs:
        for row in rows:
            values = row.get("values")
            if not isinstance(values, Mapping):
                raise ValueError("leakage report requires row values mappings")
            split = values.get("split")
            if not isinstance(split, str) or split not in _SPLITS:
                raise ValueError("leakage report requires valid row splits")
            _add_group_memberships(group_splits, values.get("group_ids"), split)
            event_id = values.get("event_id")
            if event_id is not None:
                if not isinstance(event_id, str) or not event_id:
                    raise ValueError("event_id must be a non-empty string")
                event_splits.setdefault(event_id, set()).add(split)

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


def _cross_split_ids(memberships: Mapping[str, set[str]]) -> list[str]:
    return sorted(group_id for group_id, splits in memberships.items() if len(splits) > 1)


def _sorted_split_map(memberships: Mapping[str, set[str]]) -> dict[str, list[str]]:
    return {group_id: sorted(splits) for group_id, splits in sorted(memberships.items())}


__all__ = ["DATASET_LEAKAGE_REPORT_VERSION", "build_leakage_report"]
