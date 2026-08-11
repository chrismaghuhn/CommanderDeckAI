from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from commander_ai.adapters.http.content_coding import DEFAULT_MAX_DECODED_BYTES
from commander_ai.adapters.sources.spicerack.parser import (
    SpicerackParseError,
    SpicerackParser,
)
from commander_ai.adapters.sources.spicerack.settings import SpicerackSettings
from commander_ai.adapters.sources.spicerack.staging import (
    SpicerackStagingError,
    SpicerackStagingMapper,
)
from commander_ai.adapters.storage.parquet_tables import ParquetTableWriter
from commander_ai.adapters.storage.raw_snapshot_store import RawSnapshotStore
from commander_ai.adapters.storage.snapshot_verifier import SnapshotIntegrityError, SnapshotVerifier
from commander_ai.application.source_policy import SourcePolicy
from commander_ai.config.current_use_policy import CurrentUseDecision
from commander_ai.config.source_registry import (
    HistoricalApprovalMetadata,
    SourceRegistry,
    SourceRegistryEntry,
)
from commander_ai.config.source_settings import SourceApprovalStatus, SourceSettings
from commander_ai.data_pipeline.staging.raw_locators import ByteRangeLocator, JsonPointerLocator
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.serialization import canonical_json_bytes

FIXTURE_ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "spicerack"
EFFECTIVE_AT = datetime(2026, 8, 10, tzinfo=UTC)


def _source_settings(formats: tuple[str, ...] = ("COMMANDER2",)) -> SourceSettings:
    return SourceSettings(
        source_id="spicerack",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        review_path="docs/03-data/source-reviews/spicerack.md",
        endpoints=("https://api.spicerack.gg",),
        host_allowlist=("api.spicerack.gg",),
        api_key_env="SPICERACK_API_KEY",
        max_download_bytes=1_000_000,
        attribution_required=True,
        raw_storage="allowed_local",
        redistribution="not_approved",
        filters={"formats": list(formats)},
    )


def _settings(
    response_format: str = "json", formats: tuple[str, ...] = ("COMMANDER2",)
) -> SpicerackSettings:
    return SpicerackSettings.from_source_settings(
        _source_settings(formats),
        credential_header="X-API-Key",
        response_format=response_format,
    )


def _registry(current_status: str = "ALLOWED") -> SourceRegistry:
    settings = _source_settings()
    historical = HistoricalApprovalMetadata(
        source_id="spicerack",
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        review_path="docs/03-data/source-reviews/spicerack.md",
        reviewed_at=EFFECTIVE_AT,
        effective_at=EFFECTIVE_AT,
        reason="fixture source review",
        official_docs=("https://docs.spicerack.gg/api-reference/public-decklist-database",),
        terms_reference="https://terms.fixture.invalid/spicerack",
        attribution_required=True,
        raw_local_storage="allowed_local",
        redistribution_raw="not_approved",
        redistribution_derived="not_approved",
    )
    current = CurrentUseDecision(
        source_id="spicerack",
        status=current_status,
        approval_status=SourceApprovalStatus.APPROVED_LOCAL,
        reason="fixture current-use decision",
        effective_at=EFFECTIVE_AT,
    )
    return SourceRegistry(
        entries=(
            SourceRegistryEntry(
                source_id="spicerack",
                settings=settings,
                historical_approval=historical,
                current_use=current,
            ),
        )
    )


def _allowed_policy() -> SourcePolicy:
    return SourcePolicy(_registry())


def _verified_snapshot(
    tmp_path: Path,
    raw: bytes,
    *,
    response_format: str = "json",
    snapshot_id: str = "spicerack-parser-fixture",
    formats: tuple[str, ...] = ("COMMANDER2",),
    request_format: str | None = None,
):
    settings = _settings(response_format, formats)
    store = RawSnapshotStore(tmp_path)
    writer = store.start_snapshot(
        source_id="spicerack",
        snapshot_id=snapshot_id,
        approval_status="APPROVED_LOCAL",
        adapter_version="spicerack-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
    )
    selected_format = request_format or settings.formats[0]
    request_id = f"spicerack-{selected_format.lower()}"
    parameters = settings.request_parameters(selected_format=selected_format)
    writer.add_request(
        {
            "request_id": request_id,
            "sanitized_method": "GET",
            "sanitized_endpoint": settings.endpoint,
            "api_version": "public-decklist-api",
            "format": response_format,
            "sanitized_parameters": parameters,
        }
    )
    raw_object_id = f"{request_id}.{response_format}"
    writer.write_object(
        raw_object_id=raw_object_id,
        request_id=request_id,
        chunks=[raw],
        content_type="application/x-ndjson" if response_format == "ndjson" else "application/json",
        source_object_id="spicerack-public-decklists",
        logical_record_count=(len(raw.splitlines()) if response_format == "ndjson" else None),
    )
    writer.finalize()
    return SnapshotVerifier(tmp_path).verify_complete_snapshot("spicerack", snapshot_id)


def _fixture(name: str = "valid_export.json") -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()


def test_json_fixture_preserves_source_records_and_exact_json_pointers(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture())
    records = SpicerackParser(_settings()).parse_object(verified)

    event = next(item for item in records if item.record_type == "event")
    decklist = next(item for item in records if item.record_type == "decklist")
    player = next(item for item in records if item.record_type == "player")
    standing = next(item for item in records if item.record_type == "standing")
    result = next(item for item in records if item.record_type == "result")

    assert event.raw_locator.location == JsonPointerLocator(pointer="/0")
    assert event.dto.event_id == "fixture-tournament-1"
    assert event.dto.name == "Spicerack Fixture Open"
    assert decklist.raw_locator.location == JsonPointerLocator(pointer="/0/standings/0")
    assert decklist.source_values["decklist"].endswith("/deck/1")
    assert player.raw_locator.location == JsonPointerLocator(pointer="/0/standings/0")
    assert player.dto.player_id is None
    assert standing.raw_locator.location == JsonPointerLocator(pointer="/0/standings/0")
    assert standing.source_values["winsSwiss"] == 3
    assert result.raw_locator.location == JsonPointerLocator(pointer="/0/standings/0")
    assert result.source_values["winsSwiss"] == 3
    assert set(decklist.source_values) == {"decklist", "decklist_text"}
    assert set(result.source_values) == {
        "winsSwiss",
        "lossesSwiss",
        "draws",
        "winsBracket",
        "lossesBracket",
    }
    assert "name" not in player.source_values
    assert "Fixture Player Name" not in json.dumps(player.source_values)
    assert "Fixture Player Name" not in json.dumps(event.source_values)
    assert all("canonical_deck_id" not in item.model_dump(mode="json") for item in records)
    assert all(item.record_type != "pod" for item in records)


def test_ndjson_fixture_uses_replayable_zero_based_line_locators(tmp_path: Path) -> None:
    verified = _verified_snapshot(
        tmp_path,
        _fixture("valid_export.ndjson"),
        response_format="ndjson",
        snapshot_id="ndjson",
        formats=("DUEL",),
        request_format="DUEL",
    )
    records = SpicerackParser(_settings("ndjson", ("DUEL",))).parse_object(
        verified, raw_object_id="spicerack-duel.ndjson"
    )

    assert [item.record_type for item in records] == [
        "event",
        "standing",
        "player",
        "decklist",
        "result",
        "standing",
        "player",
        "decklist",
        "result",
    ]
    assert all(isinstance(item.raw_locator.location, ByteRangeLocator) for item in records)
    assert records[0].raw_locator.location.start == 0
    assert records[0].raw_locator.location.end > records[0].raw_locator.location.start
    assert records[1].raw_locator.exact_locator != records[5].raw_locator.exact_locator
    assert len({item.raw_locator.exact_locator for item in records}) == 3
    assert len(records[0].source_values["standings"]) == 2
    assert "NDJSON Player Name" not in json.dumps(records[0].source_values)
    rows = SpicerackStagingMapper(
        _settings("ndjson", ("DUEL",)), policy=_allowed_policy()
    ).map_records(records, verified_snapshot=verified)
    assert len(rows) == len(records)
    artifact = ParquetTableWriter(tmp_path / "artifacts").write_table(
        "spicerack-ndjson-staging",
        rows,
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
        max_decoded_bytes=_settings("ndjson", ("DUEL",)).max_response_bytes,
    )
    assert artifact.rows == len(rows)


def test_missing_pod_is_preserved_and_emits_quality_audit_finding(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture())
    records = SpicerackParser(_settings()).parse_object(verified)
    result = next(item for item in records if item.record_type == "result")

    assert result.dto.pod is None
    assert "pod" not in result.source_values
    assert result.finding_codes == ("quality.spicerack_missing_pod",)
    assert not any(item.record_type == "pod" for item in records)
    audits = SpicerackStagingMapper(_settings(), policy=_allowed_policy()).map_audit_records(
        records, verified_snapshot=verified
    )
    pod_audit = next(
        item for item in audits if item.finding_code == "quality.spicerack_missing_pod"
    )
    assert pod_audit.stage == "quality"
    assert pod_audit.raw_locator == result.raw_locator


def test_source_specific_status_and_result_fields_survive_staging(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture())
    records = SpicerackParser(_settings()).parse_object(verified)
    rows = SpicerackStagingMapper(_settings(), policy=_allowed_policy()).map_records(
        records, verified_snapshot=verified
    )

    result_row = next(item for item in rows if item.record_type == "result")
    standing_row = next(item for item in rows if item.record_type == "standing")
    assert result_row.original_source_values["winsSwiss"] == 3
    assert result_row.original_source_values["lossesSwiss"] == 0
    assert standing_row.original_source_values["winsSwiss"] == 3
    assert standing_row.original_source_values["decklist"].endswith("/deck/1")
    assert all(row.has_canonical_identity is False for row in rows)
    artifact = ParquetTableWriter(tmp_path / "artifacts").write_table(
        "spicerack-json-staging",
        rows,
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
        max_decoded_bytes=_settings().max_response_bytes,
    )
    assert artifact.rows == len(rows)


def test_invalid_json_is_retained_as_parse_record(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, b'{"broken":', snapshot_id="invalid-json")
    records = SpicerackParser(_settings()).parse_object(verified)

    assert len(records) == 1
    assert records[0].record_type == "response"
    assert records[0].finding_codes == ("parse.spicerack_invalid_json",)
    row = SpicerackStagingMapper(_settings(), policy=_allowed_policy()).map_records(
        records, verified_snapshot=verified
    )[0]
    assert row.status == "PARSE_FAILED"


def test_malformed_json_scalar_is_audited_and_quarantinable(tmp_path: Path) -> None:
    raw = b'[{"TID":"fixture-scalar","standings":[{"winsSwiss":NaN}]}]'
    verified = _verified_snapshot(tmp_path, raw, snapshot_id="malformed-scalar")
    settings = _settings()
    records = SpicerackParser(settings).parse_object(verified)

    assert any("parse.spicerack_malformed_json_scalar" in item.finding_codes for item in records)
    rows = SpicerackStagingMapper(settings, policy=_allowed_policy()).map_records(
        records, verified_snapshot=verified
    )
    assert rows
    assert all(row.status == "PARSE_FAILED" for row in rows)
    audits = SpicerackStagingMapper(settings, policy=_allowed_policy()).map_audit_records(
        records, verified_snapshot=verified
    )
    assert any(item.finding_code == "parse.spicerack_malformed_json_scalar" for item in audits)


def test_malformed_ndjson_is_retained_with_exact_line_locator(tmp_path: Path) -> None:
    raw = _fixture("malformed_export.ndjson")
    verified = _verified_snapshot(
        tmp_path,
        raw,
        response_format="ndjson",
        snapshot_id="invalid-ndjson",
        formats=("DUEL",),
        request_format="DUEL",
    )
    records = SpicerackParser(_settings("ndjson", ("DUEL",))).parse_object(
        verified, raw_object_id="spicerack-duel.ndjson"
    )

    malformed = next(item for item in records if item.record_type == "response")
    assert isinstance(malformed.raw_locator.location, ByteRangeLocator)
    assert malformed.raw_locator.location.start > 0
    assert malformed.raw_locator.location.length == len(b'{"broken":\n')
    assert malformed.finding_codes == ("parse.spicerack_invalid_ndjson",)


def test_parser_applies_configured_decode_limit_during_locator_validation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import commander_ai.data_pipeline.staging.locator_validation as locator_validation

    observed_limits: list[int | None] = []
    decode = locator_validation.decode_entity_body

    def observe_limit(
        raw_bytes: bytes,
        content_encoding: str | None,
        *,
        max_decoded_bytes: int = DEFAULT_MAX_DECODED_BYTES,
    ) -> bytes:
        observed_limits.append(max_decoded_bytes)
        return decode(
            raw_bytes,
            content_encoding,
            max_decoded_bytes=max_decoded_bytes,
        )

    monkeypatch.setattr(locator_validation, "decode_entity_body", observe_limit)
    settings = _settings()
    verified = _verified_snapshot(tmp_path, _fixture(), snapshot_id="bounded-locator")

    SpicerackParser(settings).parse_object(verified)

    assert observed_limits == [settings.max_response_bytes]


def test_parser_rejects_tampered_complete_object_before_decoding(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture(), snapshot_id="tampered")
    object_path = tmp_path / "raw/spicerack/tampered/objects/spicerack-commander2.json"
    object_path.write_bytes(b"tampered")

    with pytest.raises(SpicerackParseError) as error:
        SpicerackParser(_settings()).parse_object(verified)
    assert error.value.code == "INTEGRITY_OBJECT_HASH_MISMATCH"


def test_multi_format_snapshot_uses_the_object_format_for_request_integrity(
    tmp_path: Path,
) -> None:
    verified = _verified_snapshot(
        tmp_path,
        _fixture(),
        snapshot_id="multi-format",
        formats=("COMMANDER2", "DUEL"),
        request_format="DUEL",
    )

    records = SpicerackParser(_settings(formats=("COMMANDER2", "DUEL"))).parse_object(
        verified,
        raw_object_id="spicerack-duel.json",
    )

    assert records
    assert all(item.raw_locator.raw_object_id == "spicerack-duel.json" for item in records)


def test_staging_requires_a_current_use_policy(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture(), snapshot_id="policy-required")
    records = SpicerackParser(_settings()).parse_object(verified)

    with pytest.raises(SpicerackStagingError) as error:
        SpicerackStagingMapper(_settings())
    assert error.value.code == "POLICY_CURRENT_USE_REQUIRED"

    rows = SpicerackStagingMapper(_settings(), policy=_allowed_policy()).map_records(
        records, verified_snapshot=verified
    )
    assert rows


def test_current_use_prohibition_blocks_verified_snapshot_without_manifest_rewrite(
    tmp_path: Path,
) -> None:
    verified = _verified_snapshot(tmp_path, _fixture(), snapshot_id="blocked-current-use")
    manifest_path = tmp_path / "raw/spicerack/blocked-current-use/manifest.json"
    before = manifest_path.read_bytes()
    records = SpicerackParser(_settings()).parse_object(verified)
    blocked_policy = SourcePolicy(_registry(current_status="PROHIBITED"))

    with pytest.raises(SpicerackStagingError) as error:
        SpicerackStagingMapper(_settings(), policy=blocked_policy).map_records(
            records, verified_snapshot=verified
        )
    assert error.value.code == "POLICY_CURRENT_USE_BLOCKED"
    assert manifest_path.read_bytes() == before


def test_audit_mapping_remains_available_after_current_use_block(tmp_path: Path) -> None:
    settings = _settings()
    verified = _verified_snapshot(tmp_path, _fixture(), snapshot_id="audit-after-takedown")
    records = SpicerackParser(settings).parse_object(verified)
    policy = SourcePolicy(_registry(current_status="TAKEDOWN"))
    mapper = SpicerackStagingMapper(settings, policy=policy)

    audits = mapper.map_audit_records(records, verified_snapshot=verified)

    assert audits
    with pytest.raises(SpicerackStagingError) as error:
        mapper.map_records(records, verified_snapshot=verified)
    assert error.value.code == "POLICY_CURRENT_USE_BLOCKED"


def test_snapshot_verifier_rejects_integrity_failure_before_parser_input(tmp_path: Path) -> None:
    store = RawSnapshotStore(tmp_path)
    writer = store.start_snapshot(
        source_id="spicerack",
        snapshot_id="incomplete",
        approval_status="APPROVED_LOCAL",
        adapter_version="spicerack-v1",
        usage_status="POLICY_LOCAL_SYNC_ALLOWED",
    )
    writer.add_request(
        {
            "request_id": "request",
            "sanitized_method": "GET",
            "sanitized_endpoint": _settings().endpoint,
            "api_version": "public-decklist-api",
            "format": "json",
            "sanitized_parameters": _settings().request_parameters(),
        }
    )
    writer.write_object(
        raw_object_id="spicerack-commander2.json",
        request_id="request",
        chunks=[_fixture()],
        source_object_id="spicerack-public-decklists",
    )
    with pytest.raises(SnapshotIntegrityError) as error:
        SnapshotVerifier(tmp_path).verify_complete_snapshot("spicerack", "incomplete")
    assert error.value.code == "INTEGRITY_SNAPSHOT_NOT_COMPLETE"


def test_locator_and_source_values_are_bound_to_verified_evidence(tmp_path: Path) -> None:
    verified = _verified_snapshot(tmp_path, _fixture(), snapshot_id="bound")
    records = SpicerackParser(_settings()).parse_object(verified)
    forged = records[0].model_copy(update={"source_values": {"id": "forged"}})

    with pytest.raises(ValueError, match="does not match verified source"):
        SpicerackStagingMapper(_settings(), policy=_allowed_policy()).map_records(
            (forged,), verified_snapshot=verified
        )


def test_staging_rejects_silently_omitted_verified_records(tmp_path: Path) -> None:
    settings = _settings()
    verified = _verified_snapshot(tmp_path, _fixture(), snapshot_id="omitted-record")
    records = SpicerackParser(settings).parse_object(verified)

    with pytest.raises(ValueError, match="omit verified source records"):
        SpicerackStagingMapper(settings, policy=_allowed_policy()).map_records(
            records[:1], verified_snapshot=verified
        )


def test_staging_rejects_empty_input_for_non_empty_verified_snapshot(tmp_path: Path) -> None:
    settings = _settings()
    verified = _verified_snapshot(tmp_path, _fixture(), snapshot_id="empty-input")

    with pytest.raises(ValueError, match="omit verified source records"):
        SpicerackStagingMapper(settings, policy=_allowed_policy()).map_records(
            (), verified_snapshot=verified
        )


def test_ndjson_pagination_line_is_not_emitted_as_a_source_record(tmp_path: Path) -> None:
    verified = _verified_snapshot(
        tmp_path,
        _fixture("valid_export.ndjson"),
        response_format="ndjson",
        snapshot_id="page-line",
        formats=("DUEL",),
        request_format="DUEL",
    )
    records = SpicerackParser(_settings("ndjson", ("DUEL",))).parse_object(
        verified, raw_object_id="spicerack-duel.ndjson"
    )
    assert not any(item.record_type == "pagination" for item in records)


def test_ndjson_locator_failure_is_retained_with_distinct_quarantine_evidence(
    tmp_path: Path,
) -> None:
    raw = b'{"TID":"fixture-fallback","standings":[1]}\n'
    verified = _verified_snapshot(
        tmp_path,
        raw,
        response_format="ndjson",
        snapshot_id="locator-fallback",
        formats=("DUEL",),
        request_format="DUEL",
    )
    records = SpicerackParser(_settings("ndjson", ("DUEL",))).parse_object(
        verified, raw_object_id="spicerack-duel.ndjson"
    )

    assert [item.record_type for item in records] == ["event", "response"]
    assert len({item.raw_locator.exact_locator for item in records}) == 2
    rows = SpicerackStagingMapper(
        _settings("ndjson", ("DUEL",)), policy=_allowed_policy()
    ).map_records(records, verified_snapshot=verified)
    artifact = ParquetTableWriter(tmp_path / "artifacts").write_table(
        "spicerack-fallback-staging",
        rows,
        layer="normalized",
        row_contract=StagingRecord,
        verified_snapshot=verified,
        max_decoded_bytes=_settings("ndjson", ("DUEL",)).max_response_bytes,
    )
    assert artifact.rows == 2


def test_json_invalid_standings_finding_has_a_field_locator(tmp_path: Path) -> None:
    verified = _verified_snapshot(
        tmp_path,
        b'[{"TID":"fixture-invalid-standings","standings":{"bad":true}}]',
        snapshot_id="invalid-standings",
    )
    records = SpicerackParser(_settings()).parse_object(verified)

    assert [item.record_type for item in records] == ["event", "standing"]
    assert records[1].raw_locator.location == JsonPointerLocator(pointer="/0/standings")
    rows = SpicerackStagingMapper(_settings(), policy=_allowed_policy()).map_records(
        records, verified_snapshot=verified
    )
    assert len(rows) == 2


def test_request_contract_digest_is_deterministic() -> None:
    settings = _settings()
    expected = {
        "num_days": 14,
        "event_format": "COMMANDER2",
        "decklist_as_text": True,
    }
    assert settings.request_parameters() == expected
    assert canonical_json_bytes(settings.request_parameters()) == canonical_json_bytes(
        {"decklist_as_text": True, "event_format": "COMMANDER2", "num_days": 14}
    )
    assert hashlib.sha256(canonical_json_bytes(settings.request_parameters())).hexdigest()
