from __future__ import annotations

from datetime import UTC, datetime

import pytest

from commander_ai.data_pipeline.normalization.canonical_records import (
    CanonicalRecord,
    canonical_record_from_domain,
)
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator
from commander_ai.domain.cards import CanonicalCard
from commander_ai.domain.provenance import ProvenanceReference


def _evidence() -> tuple[RawLocator, tuple[ProvenanceReference, ...]]:
    locator = RawLocator(
        source_id="mtgjson",
        source_snapshot_id="snapshot-1",
        raw_object_id="AllPrintings.json.zip",
        raw_object_path="objects/AllPrintings.json.zip",
        location=JsonPointerLocator(pointer="/data/TST/cards/0"),
    )
    provenance = (
        ProvenanceReference(
            source_id="mtgjson",
            source_snapshot_id="snapshot-1",
            source_object_id="AllPrintings.json.zip",
            raw_sha256="a" * 64,
            retrieved_at=datetime(2026, 8, 10, tzinfo=UTC),
            adapter_version="mtgjson-v1",
            mapper_version="mtgjson-card-mapper-v1",
            approval_status="APPROVED_LOCAL",
        ),
    )
    return locator, provenance


def _card() -> CanonicalCard:
    locator, provenance = _evidence()
    del locator
    return CanonicalCard(
        card_snapshot_id="mtgjson-snapshot-1",
        oracle_id="00000000-0000-0000-0000-000000000001",
        name="Fixture Card",
        normalized_name="fixture card",
        layout="normal",
        mana_value=1,
        colors=("U",),
        color_identity=("U",),
        types=("Creature",),
        legalities={"commander": "legal"},
        provenance=provenance,
    )


def test_canonical_record_validates_and_round_trips_domain_payload() -> None:
    locator, provenance = _evidence()
    record = canonical_record_from_domain(
        _card(),
        source_record_id="mtgjson-staging-card-1",
        raw_locator=locator,
        provenance=provenance,
        observed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    assert record.record_type == "card"
    assert record.payload["oracle_id"] == "00000000-0000-0000-0000-000000000001"
    assert record.layer == "normalized"
    assert CanonicalRecord.model_validate(record.model_dump(mode="json")) == record


def test_canonical_record_rejects_payload_that_does_not_match_record_type() -> None:
    locator, provenance = _evidence()
    with pytest.raises(ValueError, match="payload does not satisfy"):
        CanonicalRecord(
            record_id="canonical-card-invalid",
            record_type="card",
            source_record_id="source-card-1",
            source_id="mtgjson",
            source_snapshot_id="snapshot-1",
            raw_locator=locator,
            observed_at=datetime(2026, 8, 10, tzinfo=UTC),
            payload={"not": "a card"},
            provenance=provenance,
        )


def test_canonical_record_id_is_deterministic() -> None:
    locator, provenance = _evidence()
    first = canonical_record_from_domain(
        _card(),
        source_record_id="source-card-1",
        raw_locator=locator,
        provenance=provenance,
        observed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    second = canonical_record_from_domain(
        _card(),
        source_record_id="source-card-1",
        raw_locator=locator,
        provenance=provenance,
        observed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert first.record_id == second.record_id
