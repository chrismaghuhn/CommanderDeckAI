"""Source-aware staging and normalized-snapshot publication."""

from __future__ import annotations

import hashlib
import tempfile
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from commander_ai.adapters.sources.commander_spellbook import (
    CommanderSpellbookParser,
    CommanderSpellbookSettings,
    CommanderSpellbookStagingMapper,
)
from commander_ai.adapters.sources.mtgjson import (
    MTGJSONParser,
    MTGJSONSettings,
    MTGJSONStagingMapper,
)
from commander_ai.adapters.sources.spicerack import (
    SpicerackParser,
    SpicerackSettings,
    SpicerackStagingMapper,
)
from commander_ai.adapters.sources.topdeck import (
    TopDeckParser,
    TopDeckSettings,
    TopDeckStagingMapper,
)
from commander_ai.adapters.storage.manifest_files import ManifestFileWriter
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.adapters.storage.snapshot_verifier import SnapshotVerifier
from commander_ai.application.errors import ApplicationError
from commander_ai.application.normalize_snapshot import NormalizationCoordinator
from commander_ai.application.ports.data_pipeline import NormalizeResult
from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config.source_registry import SourceRegistry
from commander_ai.config.yaml_loader import serialize_config
from commander_ai.data_pipeline.provenance.normalized_snapshot_contracts import (
    NormalizedTableArtifact,
)
from commander_ai.data_pipeline.provenance.normalized_snapshot_manifests import (
    build_normalized_snapshot_manifest,
)
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.provenance.run_manifests import (
    RunArtifactReference,
    RunInputReference,
    build_run_manifest,
)
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord, quarantine_record
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.provenance import QuarantineReference

from .operation_provenance import operation_context
from .snapshot_locator import find_source_for_snapshot


class SourceNormalizationPipeline:
    """Normalize a verified raw snapshot into staging, audit, and quarantine tables."""

    def __init__(self, data_root: Path, artifact_root: Path, registry: SourceRegistry) -> None:
        self._data_root = data_root
        self._artifact_root = artifact_root
        self._registry = registry
        self._policy = SourcePolicy(registry)

    def normalize_snapshot(self, snapshot_id: str) -> NormalizeResult:
        source_id = find_source_for_snapshot(self._data_root, snapshot_id)
        try:
            prepared = NormalizationCoordinator(
                self._policy,
                SnapshotVerifier(self._data_root),
            ).prepare(source_id, snapshot_id)
            entry = self._registry.lookup(source_id)
            staging, audits, quarantine, mapper_version = self._stage(
                entry.settings, prepared.verified_snapshot
            )
            return self._publish(
                prepared,
                entry,
                staging=staging,
                audits=audits,
                quarantine=quarantine,
                mapper_version=mapper_version,
            )
        except ApplicationError:
            raise
        except Exception as error:
            code = getattr(error, "code", None)
            if isinstance(code, str) and code.isupper():
                raise ApplicationError(code) from None
            raise ApplicationError("INTEGRITY_NORMALIZATION_REJECTED") from None

    def _stage(
        self, settings: Any, verified: Any
    ) -> tuple[
        tuple[StagingRecord, ...],
        tuple[AuditRecord, ...],
        tuple[QuarantineRecord, ...],
        str,
    ]:
        records, mapper_version = self._parse(settings, verified)
        staging = self._map_staging(settings, records, verified)
        audits = _audit_records(records, staging)
        quarantine = tuple(
            quarantine_record(record, reason_code=record.finding_codes[0])
            for record in staging
            if record.status != "OBSERVED"
        )
        return staging, audits, quarantine, mapper_version

    def _parse(self, settings: Any, verified: Any) -> tuple[tuple[Any, ...], str]:
        source_id = settings.source_id
        if source_id == "mtgjson":
            mtgjson_settings = MTGJSONSettings.from_source_settings(settings)
            mtgjson_parser = MTGJSONParser()
            parsed_records: list[Any] = []
            with tempfile.TemporaryDirectory(dir=self._temporary_root()) as directory:
                for product in mtgjson_settings.products:
                    object_id = mtgjson_settings.archive_filename(product)
                    if object_id in verified.object_index:
                        parsed_records.extend(
                            mtgjson_parser.parse_archive(
                                verified,
                                raw_object_id=object_id,
                                destination=Path(directory) / product.value,
                                product=product,
                            ).records
                        )
            if not parsed_records:
                raise ValueError("MTGJSON snapshot contains no configured product objects")
            return tuple(parsed_records), f"{mtgjson_settings.adapter_version}-staging-v1"
        if source_id == "commander_spellbook":
            spellbook_settings = CommanderSpellbookSettings.from_source_settings(settings)
            spellbook_parser = CommanderSpellbookParser(
                max_decoded_bytes=spellbook_settings.max_response_bytes
            )
            parsed_records = []
            for reference in verified.manifest.objects:
                raw_id = reference.raw_object_id
                if raw_id.split("-", maxsplit=1)[0] in spellbook_settings.contracts:
                    contract = raw_id.split("-", maxsplit=1)[0]
                    parsed_records.extend(
                        spellbook_parser.parse_object(
                            verified,
                            raw_object_id=raw_id,
                            contract=contract,
                        ).records
                    )
            return tuple(parsed_records), f"{spellbook_settings.adapter_version}-staging-v1"
        if source_id == "topdeck":
            topdeck_settings = TopDeckSettings.from_source_settings(settings)
            topdeck_parser = TopDeckParser(topdeck_settings)
            parsed_records = []
            for reference in verified.manifest.objects:
                if reference.source_object_id == "tournaments-v2":
                    parsed_records.extend(
                        topdeck_parser.parse_object(verified, raw_object_id=reference.raw_object_id)
                    )
            return tuple(parsed_records), f"{topdeck_settings.adapter_version}-staging-v1"
        if source_id == "spicerack":
            spicerack_settings = SpicerackSettings.from_source_settings(settings)
            spicerack_parser = SpicerackParser(spicerack_settings)
            parsed_records = []
            for reference in verified.manifest.objects:
                if reference.source_object_id == "spicerack-public-decklists":
                    parsed_records.extend(
                        spicerack_parser.parse_object(
                            verified, raw_object_id=reference.raw_object_id
                        )
                    )
            return tuple(parsed_records), f"{spicerack_settings.adapter_version}-staging-v1"
        raise ValueError("source adapter is not implemented")

    def _map_staging(
        self, settings: Any, records: Iterable[Any], verified: Any
    ) -> tuple[StagingRecord, ...]:
        source_id = settings.source_id
        if source_id == "mtgjson":
            return MTGJSONStagingMapper().map_records(records)
        if source_id == "commander_spellbook":
            return CommanderSpellbookStagingMapper().map_records(
                records, verified_snapshot=verified
            )
        if source_id == "topdeck":
            return TopDeckStagingMapper(TopDeckSettings.from_source_settings(settings)).map_records(
                records, verified_snapshot=verified
            )
        if source_id == "spicerack":
            mapper = SpicerackStagingMapper(
                SpicerackSettings.from_source_settings(settings), policy=self._policy
            )
            return mapper.map_records(records, verified_snapshot=verified)
        raise ValueError("source adapter is not implemented")

    def _publish(
        self,
        prepared: Any,
        entry: Any,
        *,
        staging: tuple[StagingRecord, ...],
        audits: tuple[AuditRecord, ...],
        quarantine: tuple[QuarantineRecord, ...],
        mapper_version: str,
    ) -> NormalizeResult:
        source_id = prepared.source_id
        snapshot_id = prepared.source_snapshot_id
        prefix = f"normalized/{source_id}/{snapshot_id}"
        writer = ParquetTableWriter(self._artifact_root)
        artifacts = (
            writer.write_table(
                "staging",
                staging,
                relative_path=f"{prefix}/staging.parquet",
                schema_version="staging.v1",
                layer="normalized",
                row_contract=StagingRecord,
                verified_snapshot=prepared.verified_snapshot,
            ),
            writer.write_table(
                "audit",
                audits,
                relative_path=f"{prefix}/audit.parquet",
                schema_version="audit.v1",
                layer="audit",
                row_contract=AuditRecord,
                verified_snapshot=prepared.verified_snapshot,
            ),
            writer.write_table(
                "quarantine",
                quarantine,
                relative_path=f"{prefix}/quarantine.parquet",
                schema_version="quarantine.v1",
                layer="quarantine",
                row_contract=QuarantineRecord,
                verified_snapshot=prepared.verified_snapshot,
            ),
        )
        table_artifacts = tuple(_table_artifact(item) for item in artifacts)
        run_id = f"normalize-{source_id}-{snapshot_id}"
        config_snapshot = {
            "source": serialize_config(entry.settings),
            "historical_approval": serialize_config(entry.historical_approval),
            "current_use": (
                None if entry.current_use is None else serialize_config(entry.current_use)
            ),
        }
        operation = operation_context(self._artifact_root, run_id)
        current = prepared.policy_decision
        if current.decision_reference is None or current.decision_sha256 is None:
            raise ValueError("normalization policy decision is not bound")
        run_inputs = (
            RunInputReference(
                kind="source_snapshot_manifest",
                id=snapshot_id,
                path=f"raw/{source_id}/{snapshot_id}/manifest.json",
                sha256=prepared.source_manifest_sha256,
            ),
            RunInputReference(
                kind="current_use_decision",
                id=current.decision_reference,
                sha256=current.decision_sha256,
            ),
        )
        run = build_run_manifest(
            run_id=run_id,
            run_kind="normalize",
            stage="data",
            status="succeeded",
            git_commit=operation.git_commit,
            git_dirty=operation.git_dirty,
            git_worktree_sha256=operation.git_worktree_sha256,
            dependency_lock_hash=operation.dependency_lock_hash,
            configuration_path=f"configs/normalize/{source_id}/{snapshot_id}.json",
            configuration_snapshot=config_snapshot,
            inputs=run_inputs,
            schema_versions=("staging.v1",),
            mapper_versions=(mapper_version,),
            transform_versions=("normalize-v1",),
            policy_versions=("current-use-v1",),
            artifacts=(
                *operation.artifacts,
                *(
                    RunArtifactReference(path=item.path, sha256=item.sha256, kind=item.layer)
                    for item in table_artifacts
                ),
            ),
            determinism=operation.determinism,
            created_at=prepared.manifest.started_at,
            started_at=prepared.manifest.started_at,
            finished_at=prepared.manifest.completed_at or datetime.now(UTC),
        )
        manifest_writer = ManifestFileWriter(self._artifact_root)
        manifest_writer.write_run_manifest(
            run,
            manifest_path=f"runs/{run_id}/manifest.json",
            configuration_snapshot=config_snapshot,
        )
        normalized = build_normalized_snapshot_manifest(
            producing_run=run,
            verified_snapshot=prepared.verified_snapshot,
            table_artifacts=table_artifacts,
            normalized_schema_version="staging.v1",
            mapper_version=mapper_version,
            transform_version="normalize-v1",
            policy_version="current-use-v1",
            counts={
                "input_records": len(staging),
                "normalized_records": len(staging),
                "audit_records": len(audits),
                "quarantine_records": len(quarantine),
            },
            finding_codes=tuple(code for item in staging for code in item.finding_codes),
            quarantine_references=tuple(
                QuarantineReference(
                    quarantine_id=item.quarantine_id,
                    reason_code=item.reason_code,
                    path=table_artifacts[2].path,
                    record_locator=item.raw_locator.exact_locator,
                )
                for item in quarantine
            ),
            started_at=prepared.manifest.started_at,
            created_at=prepared.manifest.started_at,
            completed_at=prepared.manifest.completed_at or datetime.now(UTC),
        )
        manifest_artifact, _ = manifest_writer.write_normalized_manifest(
            normalized,
            manifest_path=f"{prefix}/manifest.json",
        )
        return NormalizeResult(
            source_id=source_id,
            source_snapshot_id=snapshot_id,
            normalized_snapshot_id=normalized.manifest.normalized_snapshot_id,
            status=normalized.manifest.status,
            manifest_path=manifest_artifact.path,
            manifest_sha256=manifest_artifact.sha256,
        )

    def _temporary_root(self) -> str:
        root = self._data_root / "tmp"
        root.mkdir(parents=True, exist_ok=True)
        return str(root)


def _table_artifact(item: Any) -> NormalizedTableArtifact:
    return NormalizedTableArtifact(
        table_name=item.table_name,
        layer=item.layer,
        path=item.path,
        sha256=item.sha256,
        rows=item.rows,
        bytes=item.bytes,
    )


def _audit_records(
    records: Sequence[Any], staging: Sequence[StagingRecord]
) -> tuple[AuditRecord, ...]:
    by_locator = {item.raw_locator.exact_locator: item for item in staging}
    audits: list[AuditRecord] = []
    for record in records:
        staged = by_locator.get(record.raw_locator.exact_locator)
        if staged is None:
            continue
        for finding in record.findings:
            digest = hashlib.sha256(
                f"{staged.staging_record_id}|{finding.code}|{finding.raw_locator.exact_locator}".encode()
            ).hexdigest()[:32]
            audits.append(
                AuditRecord(
                    audit_id=f"audit-{digest}",
                    entity_id=staged.staging_record_id,
                    stage=FindingCode.parse(finding.code).namespace,
                    finding_code=finding.code,
                    raw_locator=finding.raw_locator,
                    details={"record_type": record.record_type, "message": finding.message},
                )
            )
    return tuple(sorted(audits, key=lambda item: item.audit_id))


__all__ = ["SourceNormalizationPipeline"]
