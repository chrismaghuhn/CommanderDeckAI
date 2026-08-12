"""Construction and publication payloads for dataset-manifest.v2."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from commander_ai.adapters.storage.parquet_tables import CuratedRow
from commander_ai.adapters.storage.path_policy import resolve_under_root
from commander_ai.adapters.storage.raw_snapshot_io import sha256_file
from commander_ai.config.current_use_policy import (
    current_use_decision_binding,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_manifests import (
    validate_normalized_snapshot_manifest_bytes,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    configuration_snapshot_bytes,
    run_manifest_bytes,
    validate_run_manifest_bytes,
)
from commander_ai.domain.dataset_contracts import (
    DatasetExclusion,
    DatasetInputReference,
    DatasetManifest,
    DatasetOutputReference,
)
from commander_ai.domain.provenance import detached_manifest_sha256
from commander_ai.domain.serialization import sha256_hex

from .dataset_content import compute_dataset_content_sha256

if TYPE_CHECKING:
    from commander_ai.data_pipeline.deduplication.near_duplicates import NearDuplicatePolicy

    from .dataset_builder import DatasetBuildRequest

DATASET_TRANSFORM_VERSION = "dataset-transform-v1"
DATASET_EXCLUSION_POLICY_VERSION = "dataset-exclusions-v1"


def build_dataset_manifest(
    *,
    request: DatasetBuildRequest,
    row_schema: str,
    table_name: str,
    rows: tuple[CuratedRow, ...],
    output: DatasetOutputReference,
    exclusions: tuple[DatasetExclusion, ...],
    counts: dict[str, int],
    near_duplicate_policy: NearDuplicatePolicy | None,
) -> DatasetManifest:
    input_refs = dataset_input_references(request)
    producing_run_id = None if request.producing_run is None else request.producing_run.run_id
    policy_versions = set(request.policy_versions)
    policy_versions.update(
        {
            request.settings.split_policy.version,
            DATASET_EXCLUSION_POLICY_VERSION,
        }
    )
    if near_duplicate_policy is not None:
        policy_versions.add(near_duplicate_policy.version)
    schema_versions = tuple(sorted(set((*request.schema_versions, row_schema))))
    transform_versions = tuple(
        sorted(set((*request.transform_versions, DATASET_TRANSFORM_VERSION)))
    )
    content_digest = compute_dataset_content_sha256(
        dataset_id=request.settings.dataset_id,
        dataset_kind=request.settings.dataset_kind,
        table_name=table_name,
        rows=tuple(row.model_dump(mode="json") for row in rows),
    )
    manifest = DatasetManifest(
        dataset_id=request.settings.dataset_id,
        dataset_kind=request.settings.dataset_kind,
        config_version=request.settings.schema_version,
        producing_run_id=producing_run_id,
        created_at=request.created_at or datetime.now(UTC),
        builder_version=request.builder_version,
        code_commit=request.code_commit,
        dependency_lock_hash=request.dependency_lock_hash,
        input_manifests=input_refs,
        schema_versions=schema_versions,
        transform_versions=transform_versions,
        policy_versions=tuple(sorted(policy_versions)),
        ruleset_versions=tuple(sorted(set(request.ruleset_versions))),
        card_snapshot_ids=tuple(sorted(set(request.card_snapshot_ids))),
        source_snapshots=tuple(sorted(set(request.source_snapshot_ids))),
        filters={
            "inputs": request.settings.inputs.model_dump(mode="json"),
            "filters": request.settings.filters.model_dump(mode="json"),
            "inclusions": list(request.settings.inclusions),
            "exclusions": list(request.settings.exclusions),
            "masking": request.settings.masking.model_dump(mode="json"),
            "quality": request.settings.quality.model_dump(mode="json"),
            "privacy": request.settings.privacy.model_dump(mode="json"),
            "deduplication": request.settings.deduplication.model_dump(mode="json"),
        },
        split_policy=request.settings.split_policy.model_dump(mode="json"),
        split_policy_version=request.settings.split_policy.version,
        near_duplicate_algorithm=(
            None if near_duplicate_policy is None else near_duplicate_policy.algorithm
        ),
        near_duplicate_version=(
            None if near_duplicate_policy is None else near_duplicate_policy.version
        ),
        near_duplicate_threshold=(
            None if near_duplicate_policy is None else near_duplicate_policy.threshold
        ),
        exclusion_policy_version=DATASET_EXCLUSION_POLICY_VERSION,
        exclusions=exclusions,
        counts=counts,
        outputs=(output,),
        random_seeds=() if request.settings.seed is None else (request.settings.seed,),
        redistribution_status="local_only",
        dataset_content_sha256=content_digest,
        manifest_sha256="0" * 64,
    )
    return manifest.model_copy(
        update={"manifest_sha256": detached_manifest_sha256(manifest_payload(manifest))}
    )


def manifest_payload(manifest: DatasetManifest) -> dict[str, object]:
    """Return the exact schema-valid payload published for a dataset manifest."""

    payload = manifest.model_dump(mode="json", exclude_none=True)
    if not isinstance(payload, dict):
        raise TypeError("dataset manifest payload must be a mapping")
    return payload


def dataset_input_references(request: DatasetBuildRequest) -> tuple[DatasetInputReference, ...]:
    """Derive all file, configuration, run, and policy input bindings."""

    if request.configuration_path is None or request.configuration_snapshot is None:
        raise ValueError("dataset build requires a configuration path and snapshot")
    input_manifests = list(request.input_manifests)
    configuration = _configuration_reference(request)
    policy_inputs = _current_use_references(request)
    supplied_policy_inputs = {
        (reference.kind, reference.id, reference.sha256)
        for reference in input_manifests
        if reference.kind == "current_use_decision"
    }
    expected_policy_inputs = {
        (reference.kind, reference.id, reference.sha256) for reference in policy_inputs
    }
    if supplied_policy_inputs - expected_policy_inputs:
        raise ValueError("dataset input contains an unbound current-use decision")
    input_manifests.append(configuration)
    input_manifests.extend(policy_inputs)
    if request.producing_run is not None:
        if request.producing_run.status != "succeeded":
            raise ValueError("dataset manifest requires a succeeded producing run")
        try:
            serialized_run = run_manifest_bytes(request.producing_run)
        except ValueError as error:
            raise ValueError("dataset manifest requires a verified producing run") from error
        if request.producing_run_path is not None:
            input_manifests.append(
                DatasetInputReference(
                    kind="run_manifest",
                    id=request.producing_run.run_id,
                    path=request.producing_run_path,
                    sha256=sha256_hex(serialized_run),
                )
            )
    return _unique_input_manifests(input_manifests)


def verify_dataset_inputs(request: DatasetBuildRequest) -> None:
    """Verify all file-backed dataset inputs before any curated output is written."""

    root = Path(request.input_root or request.output_root).expanduser().absolute()
    references = dataset_input_references(request)
    _verify_producing_run_binding(request, references)
    for reference in references:
        if reference.kind == "current_use_decision":
            continue
        if reference.path is None:
            raise ValueError(f"dataset input requires a portable path: {reference.kind}")
        path = resolve_under_root(root, reference.path)
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(reference.path)
        payload = path.read_bytes()
        if sha256_file(path) != reference.sha256:
            raise ValueError(f"dataset input hash mismatch: {reference.path}")
        if reference.kind == "run_manifest":
            parsed = validate_run_manifest_bytes(payload)
            if request.producing_run is None or parsed.run_id != request.producing_run.run_id:
                raise ValueError("dataset run input does not match producing run")
        elif reference.kind == "normalized_snapshot_manifest":
            normalized_parsed = validate_normalized_snapshot_manifest_bytes(payload)
            if normalized_parsed.status != "COMPLETE":
                raise ValueError("dataset normalized input must be COMPLETE")
            if normalized_parsed.normalized_snapshot_id != reference.id:
                raise ValueError("dataset normalized input id does not match manifest")


def _configuration_reference(request: DatasetBuildRequest) -> DatasetInputReference:
    if request.configuration_path is None or request.configuration_snapshot is None:
        raise ValueError("dataset build requires a configuration path and snapshot")
    return DatasetInputReference(
        kind="dataset_config",
        id=request.settings.dataset_id,
        path=request.configuration_path,
        sha256=sha256_hex(configuration_snapshot_bytes(request.configuration_snapshot)),
    )


def _current_use_references(
    request: DatasetBuildRequest,
) -> tuple[DatasetInputReference, ...]:
    references: list[DatasetInputReference] = []
    historical_statuses = dict(request.historical_approval_statuses)
    for decision in request.current_use_decisions:
        source_id = decision.source_id
        historical_status = historical_statuses.get(source_id, decision.approval_status)
        if historical_status is None:
            raise ValueError(
                "POLICY_HISTORICAL_APPROVAL_REQUIRED: dataset build requires source history"
            )
        reference, digest = current_use_decision_binding(
            source_id=decision.source_id,
            historical_status=historical_status,
            current_use=decision,
            operation="dataset_build",
        )
        references.append(
            DatasetInputReference(kind="current_use_decision", id=reference, sha256=digest)
        )
    return tuple(references)


def _verify_producing_run_binding(
    request: DatasetBuildRequest,
    references: Sequence[DatasetInputReference],
) -> None:
    run = request.producing_run
    if run is None:
        raise ValueError("dataset build requires a producing run")
    if run.run_kind != "dataset_build" or run.stage != "data":
        raise ValueError("dataset producing run must be a data-stage dataset_build run")
    configuration = _configuration_reference(request)
    if (
        run.configuration.path != configuration.path
        or run.configuration.sha256 != configuration.sha256
    ):
        raise ValueError("dataset producing run configuration binding mismatch")
    run_inputs = {
        (reference.kind, reference.id, reference.path, reference.sha256) for reference in run.inputs
    }
    required_inputs = {
        (reference.kind, reference.id, reference.path, reference.sha256)
        for reference in references
        if reference.kind not in {"dataset_config", "run_manifest"}
    }
    if not required_inputs.issubset(run_inputs):
        raise ValueError("dataset producing run input binding mismatch")


def _unique_input_manifests(
    values: Sequence[DatasetInputReference],
) -> tuple[DatasetInputReference, ...]:
    if not values:
        raise ValueError("dataset build requires at least one input manifest")
    by_key: dict[tuple[str, str], DatasetInputReference] = {}
    for value in values:
        key = (value.kind, value.id)
        previous = by_key.get(key)
        if previous is not None and previous != value:
            raise ValueError(f"input manifest binding conflict: {key}")
        by_key[key] = value
    return tuple(by_key[key] for key in sorted(by_key))


__all__ = [
    "DATASET_EXCLUSION_POLICY_VERSION",
    "DATASET_TRANSFORM_VERSION",
    "build_dataset_manifest",
    "dataset_input_references",
    "manifest_payload",
    "verify_dataset_inputs",
]
