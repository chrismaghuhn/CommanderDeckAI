"""Build deterministic curated dataset projections and their manifests."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import JsonArtifact, ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import CuratedRow, ParquetTableWriter
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.data_pipeline.deduplication.near_duplicates import NearDuplicatePolicy
from commander_ai.data_pipeline.provenance.run_manifests import RunManifest
from commander_ai.data_pipeline.splitting.deck_completion_policy import (
    DeckCompletionPolicy,
    DeckCompletionRecord,
    DeckCompletionSplitResult,
    build_deck_completion_splits,
)
from commander_ai.data_pipeline.splitting.group_promotion import SplitAssignment, TemporalCutoffs
from commander_ai.data_pipeline.splitting.tournament_policy import (
    TournamentRecord,
    TournamentSplitPolicy,
    TournamentSplitResult,
    build_tournament_splits,
)
from commander_ai.domain.dataset_contracts import (
    DatasetExclusion,
    DatasetInputReference,
    DatasetManifest,
    DatasetOutputReference,
)
from commander_ai.domain.provenance import (
    detached_manifest_sha256,
)
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .dataset_rows import completion_rows, cooccurrence_rows, projection_rows, tournament_rows

DATASET_TRANSFORM_VERSION = "dataset-transform-v1"
DATASET_EXCLUSION_POLICY_VERSION = "dataset-exclusions-v1"


@dataclass(frozen=True, slots=True)
class DatasetProjectionRecord:
    """Generic time-indexed record for combo projections."""

    record_id: str
    observed_at: datetime
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.record_id.strip():
            raise ValueError("record_id must be non-empty")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must include a timezone")
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be a mapping")


@dataclass(frozen=True, slots=True)
class DatasetBuildRequest:
    settings: DatasetSettings
    input_manifests: tuple[DatasetInputReference, ...]
    output_root: Path | str
    code_commit: str
    dependency_lock_hash: str
    source_snapshot_ids: tuple[str, ...] = ()
    ruleset_versions: tuple[str, ...] = ()
    card_snapshot_ids: tuple[str, ...] = ()
    schema_versions: tuple[str, ...] = ()
    transform_versions: tuple[str, ...] = ()
    policy_versions: tuple[str, ...] = ()
    producing_run: RunManifest | None = None
    builder_version: str = "dataset-builder-v1"
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DatasetBuildResult:
    manifest: DatasetManifest
    output_artifacts: tuple[DatasetOutputReference, ...]
    manifest_artifact: JsonArtifact
    split_result: DeckCompletionSplitResult | TournamentSplitResult | tuple[SplitAssignment, ...]


def build_dataset(
    request: DatasetBuildRequest,
    records: Sequence[DeckCompletionRecord | TournamentRecord | DatasetProjectionRecord],
) -> DatasetBuildResult:
    """Build one task-specific dataset according to dataset-owned settings."""

    kind = request.settings.dataset_kind
    split_result: DeckCompletionSplitResult | TournamentSplitResult | tuple[SplitAssignment, ...]
    if kind in {"deck_completion", "card_cooccurrence"}:
        if not all(isinstance(record, DeckCompletionRecord) for record in records):
            raise TypeError(f"{kind} datasets require DeckCompletionRecord inputs")
        completion_records = tuple(
            record for record in records if isinstance(record, DeckCompletionRecord)
        )
        split_result = _build_completion(request.settings, completion_records)
        if kind == "deck_completion":
            rows = completion_rows(
                request.settings.dataset_id,
                split_result,
                row_schema="deck-corpus.v1",
            )
            table_name = "deck_corpus"
            row_schema = "deck-corpus.v1"
        else:
            rows = cooccurrence_rows(request.settings.dataset_id, split_result)
            table_name = "card_cooccurrence"
            row_schema = "card-cooccurrence.v1"
        exclusions = _completion_exclusions(split_result)
        counts = _split_counts(split_result.assignments, len(split_result.exclusions))
    elif kind == "tournament_outcomes":
        if not all(isinstance(record, TournamentRecord) for record in records):
            raise TypeError("tournament_outcomes datasets require TournamentRecord inputs")
        tournament_records = tuple(
            record for record in records if isinstance(record, TournamentRecord)
        )
        split_result = _build_tournament(request.settings, tournament_records)
        rows = tournament_rows(request.settings.dataset_id, split_result)
        table_name = "tournament_corpus"
        row_schema = "tournament-corpus.v1"
        exclusions = _tournament_exclusions(split_result)
        counts = _split_counts(split_result.assignments, len(split_result.exclusions))
        counts["familiar_records"] = sum(
            strata == "familiar" for _, strata in split_result.familiar_strata
        )
        counts["unseen_records"] = sum(
            strata == "unseen" for _, strata in split_result.familiar_strata
        )
    elif kind == "combo":
        if not all(isinstance(record, DatasetProjectionRecord) for record in records):
            raise TypeError("combo datasets require DatasetProjectionRecord inputs")
        projection_records = tuple(
            record for record in records if isinstance(record, DatasetProjectionRecord)
        )
        rows, split_result = projection_rows(
            request.settings, projection_records, "combo-corpus.v1"
        )
        table_name = "combo_corpus"
        row_schema = "combo-corpus.v1"
        exclusions = ()
        counts = _split_counts(split_result, 0)
    else:  # pragma: no cover - DatasetSettings closes the kind union
        raise ValueError(f"unsupported dataset kind: {kind}")

    counts["output_rows"] = len(rows)
    output_root = Path(request.output_root).expanduser().resolve()
    table_writer = ParquetTableWriter(output_root)
    relative_path = f"datasets/{request.settings.dataset_id}/{table_name}.parquet"
    parquet_artifact = table_writer.write_table(
        table_name,
        rows,
        relative_path=relative_path,
        schema_version=row_schema,
        layer="curated",
        row_contract=CuratedRow,
    )
    output_reference = DatasetOutputReference(
        name=table_name,
        path=parquet_artifact.path,
        sha256=parquet_artifact.sha256,
        rows=parquet_artifact.rows,
        bytes=parquet_artifact.bytes,
    )
    manifest = _build_manifest(
        request=request,
        row_schema=row_schema,
        table_name=table_name,
        rows=rows,
        output=output_reference,
        exclusions=exclusions,
        counts=counts,
    )
    manifest_path = f"datasets/{request.settings.dataset_id}/manifest.json"
    manifest_artifact = ManifestFileWriter(output_root).write_json(
        manifest_path,
        canonical_json_bytes(_manifest_payload(manifest)),
    )
    return DatasetBuildResult(
        manifest=manifest,
        output_artifacts=(output_reference,),
        manifest_artifact=manifest_artifact,
        split_result=split_result,
    )


def _build_completion(
    settings: DatasetSettings, records: tuple[DeckCompletionRecord, ...]
) -> DeckCompletionSplitResult:
    return build_deck_completion_splits(
        records,
        DeckCompletionPolicy(
            cutoffs=_settings_cutoffs(settings),
            exact_fingerprint=settings.deduplication.exact_fingerprint,
            group_revisions=settings.deduplication.group_revisions,
            group_near_duplicates=bool(settings.deduplication.near_duplicate),
            near_duplicate_policy=_near_duplicate_policy(settings),
            require_complete_decklists=settings.inputs.require_complete_decklists,
            require_resolution=True,
            legal_decks_only=settings.inputs.legal_decks_only,
            accepted_quality_statuses=(
                ("accepted",)
                if settings.quality.fail_on_blocking_findings
                else ("accepted", "review")
            ),
        ),
    )


def _build_tournament(
    settings: DatasetSettings, records: tuple[TournamentRecord, ...]
) -> TournamentSplitResult:
    return build_tournament_splits(
        records,
        TournamentSplitPolicy(
            cutoffs=_settings_cutoffs(settings),
            require_complete_event=settings.inputs.require_complete_pod_result,
        ),
    )


def _build_manifest(
    *,
    request: DatasetBuildRequest,
    row_schema: str,
    table_name: str,
    rows: tuple[CuratedRow, ...],
    output: DatasetOutputReference,
    exclusions: tuple[DatasetExclusion, ...],
    counts: dict[str, int],
) -> DatasetManifest:
    input_manifests = list(request.input_manifests)
    producing_run_id = None
    if request.producing_run is not None:
        if request.producing_run.status != "succeeded":
            raise ValueError("dataset manifest requires a succeeded producing run")
        producing_run_id = request.producing_run.run_id
        input_manifests.append(
            DatasetInputReference(
                kind="run_manifest",
                id=request.producing_run.run_id,
                sha256=request.producing_run.sha256,
            )
        )
    input_refs = _unique_input_manifests(input_manifests)
    near_policy = _near_duplicate_policy(request.settings)
    policy_versions = set(request.policy_versions)
    policy_versions.update(
        {
            request.settings.split_policy.version,
            DATASET_EXCLUSION_POLICY_VERSION,
        }
    )
    if request.settings.dataset_kind in {"deck_completion", "card_cooccurrence"}:
        policy_versions.add(near_policy.version)
    schema_versions = tuple(sorted(set((*request.schema_versions, row_schema))))
    transform_versions = tuple(
        sorted(set((*request.transform_versions, DATASET_TRANSFORM_VERSION)))
    )
    content_payload = {
        "dataset_id": request.settings.dataset_id,
        "dataset_kind": request.settings.dataset_kind,
        "table_name": table_name,
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    content_digest = sha256_hex(canonical_json_bytes(content_payload))
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
            "quality": request.settings.quality.model_dump(mode="json"),
            "privacy": request.settings.privacy.model_dump(mode="json"),
        },
        split_policy=request.settings.split_policy.model_dump(mode="json"),
        split_policy_version=request.settings.split_policy.version,
        near_duplicate_algorithm=near_policy.algorithm,
        near_duplicate_version=near_policy.version,
        near_duplicate_threshold=near_policy.threshold,
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
        update={"manifest_sha256": detached_manifest_sha256(_manifest_payload(manifest))}
    )


def _manifest_payload(manifest: DatasetManifest) -> dict[str, object]:
    """Return the exact schema-valid payload published for a dataset manifest."""

    payload = manifest.model_dump(mode="json", exclude_none=True)
    if not isinstance(payload, dict):
        raise TypeError("dataset manifest payload must be a mapping")
    return payload


def _completion_exclusions(result: DeckCompletionSplitResult) -> tuple[DatasetExclusion, ...]:
    return _exclusions((item.record_id, item.code) for item in result.exclusions)


def _tournament_exclusions(result: TournamentSplitResult) -> tuple[DatasetExclusion, ...]:
    return _exclusions((item.record_id, item.code) for item in result.exclusions)


def _exclusions(items: Iterable[tuple[str, str]]) -> tuple[DatasetExclusion, ...]:
    grouped: dict[str, list[str]] = {}
    for record_id, code in items:
        grouped.setdefault(code, []).append(record_id)
    return tuple(
        DatasetExclusion(code=code, count=len(references), references=tuple(sorted(references)))
        for code, references in sorted(grouped.items())
    )


def _split_counts(assignments: Sequence[SplitAssignment], excluded: int) -> dict[str, int]:
    counts = Counter(item.split for item in assignments)
    return {
        "train": counts.get("train", 0),
        "validation": counts.get("validation", 0),
        "test": counts.get("test", 0),
        "eligible_records": len(assignments),
        "excluded_records": excluded,
    }


def _settings_cutoffs(settings: DatasetSettings) -> TemporalCutoffs:
    train_until = settings.split_policy.train_until
    validation_until = settings.split_policy.validation_until
    if train_until is None or validation_until is None:
        raise ValueError("dataset split policy requires explicit train_until and validation_until")
    return TemporalCutoffs(train_until=train_until, validation_until=validation_until)


def _near_duplicate_policy(settings: DatasetSettings) -> NearDuplicatePolicy:
    configured = settings.near_duplicate_policy
    algorithm = (
        "quantity_weighted_jaccard"
        if configured.algorithm in {"jaccard", "quantity_weighted_jaccard"}
        else configured.algorithm
    )
    return NearDuplicatePolicy(
        threshold=configured.threshold,
        algorithm=algorithm,
        version=configured.version,
    )


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
    "DatasetBuildRequest",
    "DatasetBuildResult",
    "DatasetProjectionRecord",
    "build_dataset",
]
