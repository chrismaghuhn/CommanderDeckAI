import json
from datetime import UTC, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.config.dataset_settings import DatasetSettings
from commander_ai.data_pipeline.datasets.dataset_builder import (
    DatasetBuildRequest,
    build_dataset,
)
from commander_ai.data_pipeline.datasets.dataset_inspection import inspect_dataset
from commander_ai.data_pipeline.decks.canonical_decks import (
    DeckOccurrence,
    DeckSourceReference,
    DeckStructureInput,
    canonical_deck_from_input,
)
from commander_ai.domain.dataset_contracts import DatasetInputReference
from commander_ai.domain.decks import CardQuantity, CardZone, CommandZoneEntry
from commander_ai.domain.provenance import ProvenanceReference, detached_manifest_sha256

PROJECT_ROOT = Path(__file__).resolve().parents[4]
ORACLE_A = "11111111-1111-4111-8111-111111111111"
ORACLE_B = "22222222-2222-4222-8222-222222222222"
ORACLE_C = "33333333-3333-4333-8333-333333333333"


def _occurrence() -> DeckOccurrence:
    observed_at = datetime(2024, 1, 1, tzinfo=UTC)
    source = DeckSourceReference(
        source_id="fixture",
        source_deck_id="deck-1",
        source_snapshot_id="snapshot-1",
        raw_object_id="response.json",
        raw_sha256="0" * 64,
        observed_at=observed_at,
    )
    provenance = (
        ProvenanceReference(
            source_id="fixture",
            source_snapshot_id="snapshot-1",
            source_object_id="response.json",
            raw_sha256="0" * 64,
            retrieved_at=observed_at,
            adapter_version="fixture-adapter-v1",
            mapper_version="fixture-deck-mapper-v1",
            approval_status="APPROVED_LOCAL",
        ),
    )
    result = canonical_deck_from_input(
        DeckStructureInput(
            source=source,
            command_zone=(CommandZoneEntry(oracle_id=ORACLE_A, quantity=1),),
            card_zones=(
                CardZone(
                    zone="mainboard",
                    cards=(
                        CardQuantity(oracle_id=ORACLE_B, quantity=1),
                        CardQuantity(oracle_id=ORACLE_C, quantity=1),
                    ),
                ),
            ),
            provenance=provenance,
        )
    )
    return DeckOccurrence(deck=result.deck, source=source)


def _settings(
    *, dataset_id: str = "fixture-dataset", dataset_kind: str = "deck_completion"
) -> DatasetSettings:
    return DatasetSettings.model_validate(
        {
            "dataset_id": dataset_id,
            "dataset_kind": dataset_kind,
            "inputs": {
                "require_complete_decklists": True,
                "legal_decks_only": True,
            },
            "split_policy": {
                "strategy": "temporal_grouped",
                "version": "temporal-grouped-test-v1",
                "train_until": "2025-01-01T00:00:00Z",
                "validation_until": "2026-01-01T00:00:00Z",
            },
            "deduplication": {
                "exact_fingerprint": True,
                "group_revisions": False,
                "near_duplicate": {
                    "algorithm": "jaccard",
                    "version": "near-duplicate-test-v1",
                    "threshold": 0.92,
                },
            },
            "quality": {"fail_on_blocking_findings": True},
        }
    )


def _request(settings: DatasetSettings, root: Path) -> DatasetBuildRequest:
    return DatasetBuildRequest(
        settings=settings,
        input_manifests=(
            DatasetInputReference(
                kind="normalized_snapshot_manifest",
                id="normalized-fixture",
                path="normalized/fixture/manifest.json",
                sha256="a" * 64,
            ),
        ),
        output_root=root,
        code_commit="abcdef1234567890abcdef1234567890abcdef12",
        dependency_lock_hash="b" * 64,
        source_snapshot_ids=("snapshot-1",),
        card_snapshot_ids=("cards-fixture-v1",),
        schema_versions=("canonical-deck.v1",),
        created_at=datetime(2026, 8, 11, 12, 0, tzinfo=UTC),
    )


def _build(root: Path):
    from commander_ai.data_pipeline.splitting.deck_completion_policy import DeckCompletionRecord

    return build_dataset(
        _request(_settings(), root),
        [
            DeckCompletionRecord(
                record_id="record-1",
                occurrence=_occurrence(),
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                payload={"player_name": "Alice", "nested": {"email": "alice@example.test"}},
                complete_decklist=True,
                resolution_complete=True,
                legal_status="legal",
                quality_status="accepted",
            )
        ],
    )


def test_dataset_build_is_reproducible_and_manifest_binds_inputs_and_policy(tmp_path: Path) -> None:
    first = _build(tmp_path / "first")
    second = _build(tmp_path / "second")

    assert first.manifest.dataset_id == second.manifest.dataset_id
    assert first.manifest.dataset_content_sha256 == second.manifest.dataset_content_sha256
    assert first.manifest.manifest_sha256 == second.manifest.manifest_sha256
    assert first.manifest.input_manifests[0].id == "normalized-fixture"
    assert first.manifest.split_policy_version == "temporal-grouped-test-v1"
    assert first.manifest.near_duplicate_version == "near-duplicate-test-v1"
    assert first.manifest.counts["eligible_records"] == 1

    first_table = tmp_path / "first" / first.output_artifacts[0].path
    second_table = tmp_path / "second" / second.output_artifacts[0].path
    assert first_table.read_bytes() == second_table.read_bytes()
    first_manifest = tmp_path / "first" / first.manifest_artifact.path
    second_manifest = tmp_path / "second" / second.manifest_artifact.path
    assert first_manifest.read_bytes() == second_manifest.read_bytes()

    schema = json.loads((PROJECT_ROOT / "schemas" / "dataset-manifest.v2.schema.json").read_text())
    errors = list(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(
            first.manifest.model_dump(mode="json", exclude_none=True)
        )
    )
    assert errors == []
    assert first.manifest.manifest_sha256 == detached_manifest_sha256(
        first.manifest.model_dump(mode="json", exclude_none=True)
    )


def test_dataset_inspection_verifies_artifact_hashes_and_excludes_private_payload_keys(
    tmp_path: Path,
) -> None:
    result = _build(tmp_path)

    inspection = inspect_dataset(tmp_path, result.manifest.dataset_id)

    assert inspection.manifest.dataset_id == "fixture-dataset"
    rows = ParquetTableWriter(tmp_path).read_table(result.output_artifacts[0].path)
    row = rows[0]["values"]
    assert row["payload"] == {
        "player_name": "[EXCLUDED]",
        "nested": {"email": "[EXCLUDED]"},
    }


def test_card_cooccurrence_projection_emits_commander_and_card_relations(tmp_path: Path) -> None:
    from commander_ai.data_pipeline.splitting.deck_completion_policy import DeckCompletionRecord

    settings = _settings(dataset_id="fixture-cooccurrence", dataset_kind="card_cooccurrence")
    request = _request(settings, tmp_path)
    result = build_dataset(
        request,
        [
            DeckCompletionRecord(
                record_id="deck-1",
                occurrence=_occurrence(),
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                payload={},
            )
        ],
    )

    rows = ParquetTableWriter(tmp_path).read_table(result.output_artifacts[0].path)
    relations = {row["values"]["relation_type"] for row in rows}
    assert relations == {"commander_card", "card_card"}
    assert len(rows) == 3
    assert result.manifest.counts["output_rows"] == 3


def test_tournament_and_combo_builders_publish_separate_task_artifacts(tmp_path: Path) -> None:
    from commander_ai.data_pipeline.datasets.dataset_builder import DatasetProjectionRecord
    from commander_ai.data_pipeline.splitting.tournament_policy import TournamentRecord

    tournament_settings = _settings(
        dataset_id="fixture-tournament",
        dataset_kind="tournament_outcomes",
    )
    tournament = build_dataset(
        _request(tournament_settings, tmp_path),
        [
            TournamentRecord(
                record_id="entry-1",
                event_id="event-1",
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                canonical_deck_id="deck-a",
                payload={"standing": 1},
            )
        ],
    )
    assert tournament.output_artifacts[0].name == "tournament_corpus"

    combo_settings = _settings(dataset_id="fixture-combo", dataset_kind="combo")
    combo = build_dataset(
        _request(combo_settings, tmp_path),
        [
            DatasetProjectionRecord(
                record_id="combo-1",
                observed_at=datetime(2024, 1, 1, tzinfo=UTC),
                payload={"cards": [ORACLE_A, ORACLE_B], "result": "infinite"},
            )
        ],
    )
    assert combo.output_artifacts[0].name == "combo_corpus"
