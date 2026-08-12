"""Application adapter for building task-specific datasets from verified tables."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.application.errors import ApplicationError
from commander_ai.application.ports.dataset_store import DatasetBuildResult
from commander_ai.application.source_policy import SourcePolicy, SourcePolicyError
from commander_ai.config import RuntimeConfig, load_dataset_settings, serialize_config
from commander_ai.config.current_use_policy import (
    PolicyOperation,
    current_use_decision_binding,
)
from commander_ai.config.source_settings import SourceApprovalStatus
from commander_ai.data_pipeline.datasets.dataset_builder import (
    DatasetBuildRequest,
    DatasetProjectionRecord,
    build_dataset,
)
from commander_ai.data_pipeline.decks.canonical_decks import DeckOccurrence, DeckSourceReference
from commander_ai.data_pipeline.events.pod_entries import index_complete_pods
from commander_ai.data_pipeline.normalization.canonical_records import CanonicalRecord
from commander_ai.data_pipeline.normalization.evaluation_records import (
    index_deck_evaluations,
)
from commander_ai.data_pipeline.provenance.canonical_snapshot_verifier import (
    read_canonical_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
)
from commander_ai.data_pipeline.splitting.deck_completion_policy import DeckCompletionRecord
from commander_ai.data_pipeline.splitting.tournament_policy import TournamentRecord
from commander_ai.domain.dataset_contracts import DatasetInputReference
from commander_ai.domain.decks import CanonicalDeck
from commander_ai.domain.evaluations import DeckLegalityEvaluation
from commander_ai.domain.observations import EventDeckObservation
from commander_ai.domain.provenance import ProvenanceReference
from commander_ai.domain.serialization import canonical_json_bytes

from .operation_provenance import operation_context
from .registry_context import SourceRegistryProvider
from .report_provenance import sha256_path as _sha256


class ConfiguredDatasetBuild:
    """Build task datasets only from explicitly canonicalized input records."""

    def __init__(self, runtime: RuntimeConfig, registry_provider: SourceRegistryProvider) -> None:
        self._runtime = runtime
        self._registry_provider = registry_provider

    def build_dataset(self, config_path: str) -> DatasetBuildResult:
        registry, _ = self._registry_provider.load()
        try:
            settings = load_dataset_settings(config_path)
        except ValueError:
            raise ApplicationError("CONFIG_DATASET_CONFIG_INVALID") from None
        policy = SourcePolicy(registry)
        input_manifests: list[DatasetInputReference] = []
        records: list[DeckCompletionRecord | TournamentRecord | DatasetProjectionRecord] = []
        decisions = []
        source_snapshot_ids: list[str] = []
        source_snapshot_bindings: set[tuple[str, str]] = set()
        historical_statuses: dict[str, SourceApprovalStatus] = {}
        input_created_at: list[datetime] = []
        ruleset_versions: set[str] = set()
        selected_sources = settings.source_ids
        manifest_paths = _select_canonical_manifests(self._runtime.artifact_root, "all")
        for manifest_path in manifest_paths:
            verified = read_canonical_snapshot_manifest(
                self._runtime.artifact_root,
                manifest_path,
                raw_root=self._runtime.data_root,
                run_root=self._runtime.artifact_root,
            )
            source_id = verified.manifest.source_id
            if selected_sources and source_id not in selected_sources:
                continue
            try:
                policy.require_operation(source_id, PolicyOperation.DATASET_BUILD)
            except SourcePolicyError as error:
                raise ApplicationError(error.code) from None
            entry = registry.lookup(source_id)
            if entry.current_use is None:
                raise ApplicationError("POLICY_CURRENT_USE_REQUIRED")
            decision = entry.current_use
            if decision not in decisions:
                decisions.append(decision)
            source_snapshot_id = (
                verified.normalized_snapshot.manifest.input_source_snapshot_manifest_id
            )
            source_snapshot_ids.append(source_snapshot_id)
            source_snapshot_bindings.add((source_id, source_snapshot_id))
            historical_statuses[source_id] = entry.historical_approval.approval_status
            input_created_at.append(verified.manifest.created_at)
            normalized_hash = _sha256(self._runtime.artifact_root / manifest_path)
            input_manifests.append(
                DatasetInputReference(
                    kind="canonical_snapshot_manifest",
                    id=verified.manifest.canonical_snapshot_id,
                    path=manifest_path,
                    sha256=normalized_hash,
                )
            )
            canonical_artifact = next(
                item for item in verified.manifest.artifacts if item.artifact_kind == "canonical"
            )
            rows = ParquetTableWriter(self._runtime.artifact_root).read_table(
                canonical_artifact.path
            )
            ruleset_versions.update(_ruleset_versions(rows))
            records.extend(
                _dataset_records(
                    settings.dataset_kind,
                    rows,
                    source_id=source_id,
                    source_snapshot_id=source_snapshot_id,
                )
            )
        if not input_manifests:
            raise ApplicationError("INTEGRITY_NORMALIZED_SNAPSHOT_NOT_FOUND")
        if settings.inputs.legal_decks_only and not ruleset_versions:
            raise ApplicationError("LEGAL_RULESET_BINDING_REQUIRED")

        configuration_snapshot = serialize_config(settings)
        configuration_path = f"configs/datasets/{settings.dataset_id}.json"
        ManifestFileWriter(self._runtime.artifact_root).write_json(
            configuration_path,
            canonical_json_bytes(configuration_snapshot),
        )
        run_id = f"dataset-build-{settings.dataset_id}"
        operation = operation_context(self._runtime.artifact_root, run_id)
        run_inputs = [
            RunInputReference(
                kind=item.kind,
                id=item.id,
                path=item.path,
                sha256=item.sha256,
            )
            for item in input_manifests
        ]
        for decision in decisions:
            entry = registry.lookup(decision.source_id)
            reference, digest = current_use_decision_binding(
                source_id=decision.source_id,
                historical_status=entry.historical_approval.approval_status,
                current_use=decision,
                operation=PolicyOperation.DATASET_BUILD,
            )
            run_inputs.append(
                RunInputReference(kind="current_use_decision", id=reference, sha256=digest)
            )
        created_at = max(
            input_created_at,
            default=datetime(1970, 1, 1, tzinfo=UTC),
        )
        dataset_schema_version = _dataset_schema_version(settings.dataset_kind)
        run = build_run_manifest(
            run_id=run_id,
            run_kind="dataset_build",
            stage="data",
            status="succeeded",
            git_commit=operation.git_commit,
            git_dirty=operation.git_dirty,
            git_worktree_sha256=operation.git_worktree_sha256,
            dependency_lock_hash=operation.dependency_lock_hash,
            configuration_path=configuration_path,
            configuration_snapshot=configuration_snapshot,
            inputs=tuple(run_inputs),
            schema_versions=(dataset_schema_version,),
            transform_versions=("dataset-transform-v1",),
            policy_versions=("current-use-v1", settings.split_policy.version),
            ruleset_snapshot_ids=tuple(sorted(ruleset_versions)),
            artifacts=operation.artifacts,
            determinism=operation.determinism,
            created_at=created_at,
            started_at=created_at,
            finished_at=created_at,
        )
        request = DatasetBuildRequest(
            settings=settings,
            input_manifests=tuple(input_manifests),
            output_root=self._runtime.artifact_root,
            input_root=self._runtime.artifact_root,
            raw_input_root=self._runtime.data_root,
            code_commit=operation.git_commit,
            dependency_lock_hash=operation.dependency_lock_hash,
            source_snapshot_ids=tuple(sorted(set(source_snapshot_ids))),
            source_snapshot_bindings=tuple(sorted(source_snapshot_bindings)),
            historical_approval_statuses=tuple(sorted(historical_statuses.items())),
            ruleset_versions=tuple(sorted(ruleset_versions)),
            schema_versions=(dataset_schema_version,),
            transform_versions=("dataset-transform-v1",),
            policy_versions=("current-use-v1",),
            current_use_decisions=tuple(decisions),
            configuration_path=configuration_path,
            configuration_snapshot=configuration_snapshot,
            producing_run=run,
            producing_run_path=None,
            created_at=created_at,
        )
        try:
            result = build_dataset(request, records)
        except ApplicationError:
            raise
        except (OSError, TypeError, ValueError) as error:
            code = getattr(error, "code", None)
            if isinstance(code, str) and code.isupper():
                raise ApplicationError(code) from None
            raise ApplicationError("QUALITY_DATASET_BUILD_REJECTED") from None
        final_run = build_run_manifest(
            run_id=run_id,
            run_kind="dataset_build",
            stage="data",
            status="succeeded",
            git_commit=operation.git_commit,
            git_dirty=operation.git_dirty,
            git_worktree_sha256=operation.git_worktree_sha256,
            dependency_lock_hash=operation.dependency_lock_hash,
            configuration_path=configuration_path,
            configuration_snapshot=configuration_snapshot,
            inputs=tuple(run_inputs),
            schema_versions=(settings.schema_version, dataset_schema_version),
            transform_versions=("dataset-transform-v1",),
            policy_versions=("current-use-v1", settings.split_policy.version),
            ruleset_snapshot_ids=tuple(sorted(ruleset_versions)),
            artifacts=(
                *operation.artifacts,
                *(
                    RunArtifactReference(
                        path=item.path,
                        sha256=item.sha256,
                        kind="curated",
                    )
                    for item in result.output_artifacts
                ),
                *(
                    RunArtifactReference(
                        path=item.path,
                        sha256=item.sha256,
                        kind=item.name,
                    )
                    for item in result.report_artifacts
                ),
                RunArtifactReference(
                    path=result.manifest_artifact.path,
                    sha256=result.manifest_artifact.sha256,
                    kind="dataset_manifest",
                ),
            ),
            determinism=operation.determinism,
            created_at=created_at,
            started_at=created_at,
            finished_at=created_at,
        )
        ManifestFileWriter(self._runtime.artifact_root).write_run_manifest(
            final_run,
            manifest_path=f"runs/{run_id}/manifest.json",
            configuration_snapshot=configuration_snapshot,
            write_configuration=False,
        )
        return DatasetBuildResult(
            dataset_id=result.manifest.dataset_id,
            dataset_kind=result.manifest.dataset_kind,
            status="COMPLETE",
            manifest_path=result.manifest_artifact.path,
            manifest_sha256=result.manifest_artifact.sha256,
            output_paths=tuple(
                item.path for item in (*result.output_artifacts, *result.report_artifacts)
            ),
        )


def _select_canonical_manifests(root: Path, selector: str) -> tuple[str, ...]:
    canonical_root = root / "canonical"
    paths: list[str] = []
    if not canonical_root.is_dir() or canonical_root.is_symlink():
        return ()
    for path in canonical_root.rglob("manifest.json"):
        if not path.is_file() or path.is_symlink():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if selector == "all" or payload.get("source_id") == selector:
            paths.append(path.relative_to(root).as_posix())
    return tuple(sorted(paths))


def _dataset_records(
    dataset_kind: str,
    rows: list[dict[str, object]],
    *,
    source_id: str,
    source_snapshot_id: str,
) -> tuple[DeckCompletionRecord | TournamentRecord | DatasetProjectionRecord, ...]:
    canonical_rows = tuple(CanonicalRecord.model_validate(row) for row in rows)
    evaluations = index_deck_evaluations(canonical_rows)
    complete_pod_keys = index_complete_pods(canonical_rows).complete_event_deck_keys
    canonical_deck_ids = {
        CanonicalDeck.model_validate(item.payload).canonical_deck_id
        for item in canonical_rows
        if item.record_type == "canonical_deck"
    }
    records: list[DeckCompletionRecord | TournamentRecord | DatasetProjectionRecord] = []
    for canonical in canonical_rows:
        if dataset_kind in {"deck_completion", "card_cooccurrence"}:
            if canonical.record_type != "canonical_deck":
                continue
            deck = CanonicalDeck.model_validate(canonical.payload)
            evaluation_key = (canonical.source_record_id, deck.canonical_deck_id)
            legality = evaluations.legality.get(evaluation_key)
            quality = evaluations.quality.get(evaluation_key)
            ids = evaluations.legality_record_ids, evaluations.quality_record_ids
            raw_reference = _raw_reference(canonical)
            source = DeckSourceReference(
                source_id=source_id,
                source_deck_id=canonical.source_record_id,
                source_snapshot_id=source_snapshot_id,
                raw_object_id=canonical.raw_locator.raw_object_id,
                raw_sha256=raw_reference.raw_sha256,
                observed_at=canonical.observed_at,
            )
            records.append(
                DeckCompletionRecord(
                    record_id=canonical.record_id,
                    occurrence=DeckOccurrence(deck=deck, source=source),
                    observed_at=canonical.observed_at,
                    payload=canonical.payload,
                    complete_decklist=True,
                    resolution_complete=quality is not None
                    and "quality.card_resolution_incomplete" not in quality.finding_codes,
                    legal_status="unknown" if legality is None else legality.legal_status,
                    quality_status="unknown" if quality is None else quality.quality_status,
                    legality_evaluation_record_id=ids[0].get(evaluation_key),
                    quality_evaluation_record_id=ids[1].get(evaluation_key),
                )
            )
        elif dataset_kind == "tournament_outcomes":
            if canonical.record_type != "event_deck_observation":
                continue
            observation = EventDeckObservation.model_validate(canonical.payload)
            records.append(
                TournamentRecord(
                    record_id=canonical.record_id,
                    event_id=observation.event_id,
                    observed_at=observation.observed_at,
                    canonical_deck_id=observation.canonical_deck_id,
                    payload=canonical.payload,
                    complete_event=(observation.event_id, observation.canonical_deck_id)
                    in complete_pod_keys,
                    complete_decklist=observation.canonical_deck_id in canonical_deck_ids,
                    source_id=source_id,
                    source_snapshot_id=source_snapshot_id,
                )
            )
        elif dataset_kind == "combo":
            if canonical.record_type not in {"combo", "combo_card"}:
                continue
            records.append(
                DatasetProjectionRecord(
                    record_id=canonical.record_id,
                    observed_at=canonical.observed_at,
                    payload=canonical.payload,
                    source_id=source_id,
                    source_snapshot_id=source_snapshot_id,
                )
            )
        else:
            raise ApplicationError("CONFIG_DATASET_KIND_INVALID")
    return tuple(records)


def _ruleset_versions(rows: list[dict[str, object]]) -> frozenset[str]:
    versions: set[str] = set()
    for row in rows:
        if row.get("record_type") != "deck_legality_evaluation":
            continue
        evaluation = DeckLegalityEvaluation.model_validate(row.get("payload"))
        if evaluation.ruleset_version.casefold() != "unknown":
            versions.add(evaluation.ruleset_version)
    return frozenset(versions)


def _raw_reference(canonical: CanonicalRecord) -> ProvenanceReference:
    for reference in canonical.provenance:
        if reference.source_object_id == canonical.raw_locator.raw_object_id:
            return reference
    raise ValueError("canonical record has no matching raw provenance")


def _dataset_schema_version(dataset_kind: str) -> str:
    try:
        return {
            "deck_completion": "deck-corpus.v1",
            "card_cooccurrence": "card-cooccurrence.v1",
            "tournament_outcomes": "tournament-corpus.v1",
            "combo": "combo-corpus.v1",
        }[dataset_kind]
    except KeyError as error:
        raise ApplicationError("CONFIG_DATASET_KIND_INVALID") from error
