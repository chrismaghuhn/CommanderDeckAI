"""Build deterministic curated dataset projections and their manifests."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import JsonArtifact, ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import CuratedRow, ParquetTableWriter
from commander_ai.config.current_use_policy import CurrentUseDecision
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.deduplication.near_duplicates import NearDuplicatePolicy
from commander_ai.data_pipeline.provenance.run_manifests import RunManifest
from commander_ai.data_pipeline.splitting.deck_completion_policy import (
    CompletionExclusion,
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
from commander_ai.domain.serialization import canonical_json_bytes

from .dataset_builder_types import DatasetProjectionRecord
from .dataset_filters import (
    filter_completion_records,
    validate_current_use_decisions,
    validate_selector_configuration,
)
from .dataset_manifest import (
    DATASET_EXCLUSION_POLICY_VERSION,
    DATASET_TRANSFORM_VERSION,
    build_dataset_manifest,
    manifest_payload,
    verify_dataset_inputs,
)
from .dataset_provenance import require_completion_provenance, require_observation_provenance
from .dataset_rows import completion_rows, cooccurrence_rows, projection_rows, tournament_rows


@dataclass(frozen=True, slots=True)
class DatasetBuildRequest:
    settings: DatasetSettings
    input_manifests: tuple[DatasetInputReference, ...]
    output_root: Path | str
    code_commit: str
    dependency_lock_hash: str
    source_snapshot_ids: tuple[str, ...] = ()
    source_snapshot_bindings: tuple[tuple[str, str], ...] = ()
    historical_approval_statuses: tuple[tuple[str, SourceApprovalStatus], ...] = ()
    ruleset_versions: tuple[str, ...] = ()
    card_snapshot_ids: tuple[str, ...] = ()
    schema_versions: tuple[str, ...] = ()
    transform_versions: tuple[str, ...] = ()
    policy_versions: tuple[str, ...] = ()
    current_use_decisions: tuple[CurrentUseDecision, ...] = ()
    configuration_path: str | None = None
    configuration_snapshot: object | None = None
    input_root: Path | str | None = None
    raw_input_root: Path | str | None = None
    producing_run: RunManifest | None = None
    producing_run_path: str | None = None
    builder_version: str = "dataset-builder-v1"
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class DatasetBuildResult:
    manifest: DatasetManifest
    output_artifacts: tuple[DatasetOutputReference, ...]
    manifest_artifact: JsonArtifact
    split_result: DeckCompletionSplitResult | TournamentSplitResult | tuple[SplitAssignment, ...]


class DatasetBuildError(ValueError):
    """Stable data-pipeline failure that can be promoted to an application code."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_dataset(
    request: DatasetBuildRequest,
    records: Sequence[DeckCompletionRecord | TournamentRecord | DatasetProjectionRecord],
) -> DatasetBuildResult:
    """Build one task-specific dataset according to dataset-owned settings."""

    if request.producing_run is None:
        raise ValueError("dataset build requires a producing run")
    _validate_ruleset_binding(request)
    kind = request.settings.dataset_kind
    historical_statuses = dict(request.historical_approval_statuses)
    current_use_decisions = validate_current_use_decisions(
        request.current_use_decisions,
        request.source_snapshot_ids,
        required_source_ids=request.settings.inputs.source_ids,
        require_decision=bool(request.input_manifests),
        historical_statuses=historical_statuses,
    )
    verify_dataset_inputs(request)
    split_result: DeckCompletionSplitResult | TournamentSplitResult | tuple[SplitAssignment, ...]
    if kind in {"deck_completion", "card_cooccurrence"}:
        if not all(isinstance(record, DeckCompletionRecord) for record in records):
            raise TypeError(f"{kind} datasets require DeckCompletionRecord inputs")
        validate_selector_configuration(request.settings, kind)
        completion_records = tuple(
            record for record in records if isinstance(record, DeckCompletionRecord)
        )
        require_completion_provenance(
            completion_records,
            current_use_decisions,
            request.source_snapshot_bindings,
        )
        filtered_records, filter_exclusions = filter_completion_records(
            request.settings, completion_records, current_use_decisions
        )
        if any(item.code == "policy.current_use_required" for item in filter_exclusions):
            raise ValueError("POLICY_CURRENT_USE_REQUIRED: dataset build needs source decisions")
        split_result = _build_completion(request.settings, filtered_records)
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
        exclusions = _completion_exclusions(split_result, filter_exclusions)
        counts = _split_counts(split_result.assignments, _exclusion_count(exclusions))
    elif kind == "tournament_outcomes":
        if not all(isinstance(record, TournamentRecord) for record in records):
            raise TypeError("tournament_outcomes datasets require TournamentRecord inputs")
        validate_selector_configuration(request.settings, kind)
        tournament_records = tuple(
            record for record in records if isinstance(record, TournamentRecord)
        )
        require_observation_provenance(
            tournament_records,
            current_use_decisions,
            request.source_snapshot_bindings,
        )
        split_result = _build_tournament(request.settings, tournament_records)
        rows = tournament_rows(request.settings.dataset_id, split_result)
        table_name = "tournament_corpus"
        row_schema = "tournament-corpus.v1"
        exclusions = _tournament_exclusions(split_result)
        counts = _split_counts(split_result.assignments, _exclusion_count(exclusions))
        counts["familiar_records"] = sum(
            strata == "familiar" for _, strata in split_result.familiar_strata
        )
        counts["unseen_records"] = sum(
            strata == "unseen" for _, strata in split_result.familiar_strata
        )
    elif kind == "combo":
        if not all(isinstance(record, DatasetProjectionRecord) for record in records):
            raise TypeError("combo datasets require DatasetProjectionRecord inputs")
        validate_selector_configuration(request.settings, kind)
        projection_records = tuple(
            record for record in records if isinstance(record, DatasetProjectionRecord)
        )
        require_observation_provenance(
            projection_records,
            current_use_decisions,
            request.source_snapshot_bindings,
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

    counts["input_records"] = len(records)
    counts["output_rows"] = len(rows)
    output_root = Path(request.output_root).expanduser().absolute()
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
    try:
        output_reference = DatasetOutputReference(
            name=table_name,
            path=parquet_artifact.path,
            sha256=parquet_artifact.sha256,
            rows=parquet_artifact.rows,
            bytes=parquet_artifact.bytes,
        )
        manifest = build_dataset_manifest(
            request=request,
            row_schema=row_schema,
            table_name=table_name,
            rows=rows,
            output=output_reference,
            exclusions=exclusions,
            counts=counts,
            near_duplicate_policy=(
                _near_duplicate_policy(request.settings)
                if kind in {"deck_completion", "card_cooccurrence"}
                else None
            ),
        )
        manifest_path = f"datasets/{request.settings.dataset_id}/manifest.json"
        manifest_artifact = ManifestFileWriter(output_root).write_json(
            manifest_path,
            canonical_json_bytes(manifest_payload(manifest)),
        )
    except Exception:
        _remove_unpublished_output(output_root, parquet_artifact.path)
        raise
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
            require_complete_decklists=settings.inputs.require_complete_decklists,
        ),
    )


def _completion_exclusions(
    result: DeckCompletionSplitResult,
    additional: Sequence[CompletionExclusion] = (),
) -> tuple[DatasetExclusion, ...]:
    return _exclusions((item.record_id, item.code) for item in (*result.exclusions, *additional))


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


def _exclusion_count(exclusions: Sequence[DatasetExclusion]) -> int:
    return sum(item.count for item in exclusions)


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


def _remove_unpublished_output(output_root: Path, relative_path: str) -> None:
    path = output_root.joinpath(*relative_path.split("/"))
    if path.is_file() and not path.is_symlink():
        path.unlink()


def _validate_ruleset_binding(request: DatasetBuildRequest) -> None:
    versions = tuple(request.ruleset_versions)
    if any(not version.strip() or version.strip().casefold() == "unknown" for version in versions):
        raise DatasetBuildError("LEGAL_RULESET_BINDING_INVALID")
    if request.settings.inputs.legal_decks_only and not versions:
        raise DatasetBuildError("LEGAL_RULESET_BINDING_REQUIRED")


__all__ = [
    "DATASET_EXCLUSION_POLICY_VERSION",
    "DATASET_TRANSFORM_VERSION",
    "DatasetBuildError",
    "DatasetBuildRequest",
    "DatasetBuildResult",
    "DatasetProjectionRecord",
    "build_dataset",
]
