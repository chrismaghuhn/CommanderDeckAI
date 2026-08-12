"""Deterministic catalog construction from observed staging records."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from datetime import date

from commander_ai.data_pipeline.provenance.rows import ProvenanceRow
from commander_ai.data_pipeline.quality.quarantine import QuarantineRecord, quarantine_record
from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CanonicalCard, CardFace, Printing
from commander_ai.domain.provenance import ProvenanceReference

from .canonical_cards import (
    CARD_MAPPING_VERSION,
    CardMappingError,
    canonical_card_from_staging,
    card_face_from_staging,
)
from .card_faces import explicit_face, source_sequence, source_text, split_face_id
from .catalog_indexes import (
    build_catalog_indexes,
    mapping_code,
    mapping_values,
    merge_provenance,
    optional_bool,
    printing_uuid,
    source_oracle,
    without_provenance,
)
from .catalog_models import AliasCatalog, CardCatalog, CatalogBuildResult

ProvenanceForRecord = Callable[[StagingRecord], tuple[ProvenanceReference, ...]]


class CardCatalogBuilder:
    """Build cards without discarding malformed or semantically incomplete rows."""

    def __init__(
        self,
        *,
        card_snapshot_id: str,
        provenance_for: ProvenanceForRecord,
        release_dates: Mapping[str, date] | None = None,
        mapper_version: str = CARD_MAPPING_VERSION,
    ) -> None:
        self._card_snapshot_id = card_snapshot_id
        self._provenance_for = provenance_for
        self._release_dates = dict(release_dates or {})
        self._mapper_version = mapper_version

    def build(self, records: Iterable[StagingRecord]) -> CatalogBuildResult:
        ordered = tuple(sorted(records, key=lambda record: record.staging_record_id))
        cards: dict[str, CanonicalCard] = {}
        card_records: list[tuple[StagingRecord, CanonicalCard]] = []
        faces: dict[str, CardFace] = {}
        printings: dict[str, Printing] = {}
        quarantines: list[QuarantineRecord] = []
        finding_codes: list[str] = []
        provenance_rows: list[ProvenanceRow] = []

        for record in ordered:
            if record.record_type not in {"card", "card_face"}:
                continue
            if record.status != "OBSERVED":
                code = (
                    record.finding_codes[0]
                    if record.finding_codes
                    else "integrity.non_observed_card"
                )
                quarantines.append(quarantine_record(record, reason_code=code))
                finding_codes.append(code)
                continue
            if record.record_type != "card":
                continue
            try:
                card = canonical_card_from_staging(
                    record,
                    card_snapshot_id=self._card_snapshot_id,
                    provenance=self._validated_provenance(record),
                )
            except (CardMappingError, ValueError) as error:
                code = mapping_code(error)
                quarantines.append(quarantine_record(record, reason_code=code))
                finding_codes.append(code)
                continue
            existing = cards.get(card.oracle_id)
            if existing is None:
                cards[card.oracle_id] = card
            elif explicit_face(mapping_values(record)):
                card = existing
            elif without_provenance(existing) == without_provenance(card):
                cards[card.oracle_id] = existing.model_copy(
                    update={"provenance": merge_provenance(existing.provenance, card.provenance)}
                )
            else:
                code = "quality.conflicting_card_facts"
                quarantines.append(quarantine_record(record, reason_code=code))
                finding_codes.append(code)
                continue
            provenance_rows.extend(self._provenance_rows(record, f"card:{card.oracle_id}"))
            card_records.append((record, card))
            self._try_add_face(record, card, faces, quarantines, finding_codes, provenance_rows)

        self._add_explicit_faces(ordered, cards, faces, quarantines, finding_codes, provenance_rows)
        self._add_printings(
            card_records, faces, printings, quarantines, finding_codes, provenance_rows
        )
        catalog = build_catalog_indexes(
            cards=tuple(cards.values()),
            faces=tuple(faces.values()),
            printings=tuple(printings.values()),
            source_records=card_records,
        )
        return CatalogBuildResult(
            catalog=catalog,
            quarantines=tuple(quarantines),
            finding_codes=tuple(sorted(set(finding_codes))),
            provenance_rows=tuple(provenance_rows),
        )

    def _try_add_face(
        self,
        record: StagingRecord,
        card: CanonicalCard,
        faces: dict[str, CardFace],
        quarantines: list[QuarantineRecord],
        finding_codes: list[str],
        provenance_rows: list[ProvenanceRow],
    ) -> None:
        try:
            values = mapping_values(record)
            parts = source_sequence(values, "cardParts")
            base_face_id = source_text(values, "uuid", "faceId", "face_id")
            if len(parts) > 1 and not explicit_face(values) and base_face_id is not None:
                for index, part in enumerate(parts):
                    self._merge_face(
                        card_face_from_staging(
                            record,
                            oracle_id=card.oracle_id,
                            layout=card.layout,
                            provenance=self._validated_provenance(record),
                            face_id_override=split_face_id(base_face_id, index),
                            face_name_override=part,
                            face_index_override=index,
                        ),
                        faces,
                    )
                    provenance_rows.extend(
                        self._provenance_rows(record, f"face:{split_face_id(base_face_id, index)}")
                    )
            else:
                self._merge_face(
                    card_face_from_staging(
                        record,
                        oracle_id=card.oracle_id,
                        layout=card.layout,
                        provenance=self._validated_provenance(record),
                    ),
                    faces,
                )
                face_id = source_text(values, "uuid", "faceId", "face_id")
                if face_id is not None:
                    provenance_rows.extend(self._provenance_rows(record, f"face:{face_id}"))
        except (CardMappingError, ValueError) as error:
            code = mapping_code(error)
            quarantines.append(quarantine_record(record, reason_code=code))
            finding_codes.append(code)

    def _add_explicit_faces(
        self,
        records: tuple[StagingRecord, ...],
        cards: Mapping[str, CanonicalCard],
        faces: dict[str, CardFace],
        quarantines: list[QuarantineRecord],
        finding_codes: list[str],
        provenance_rows: list[ProvenanceRow],
    ) -> None:
        for record in records:
            if record.record_type != "card_face" or record.status != "OBSERVED":
                continue
            try:
                values = mapping_values(record)
                oracle_id = source_oracle(values)
                if oracle_id is None or oracle_id not in cards:
                    raise CardMappingError(
                        "quality.missing_canonical_identifier",
                        "face row does not link to a canonical card",
                    )
                face = card_face_from_staging(
                    record,
                    oracle_id=oracle_id,
                    layout=cards[oracle_id].layout,
                    provenance=self._validated_provenance(record),
                )
                self._merge_face(face, faces)
                provenance_rows.extend(self._provenance_rows(record, f"face:{face.face_id}"))
            except (CardMappingError, ValueError) as error:
                code = mapping_code(error)
                quarantines.append(quarantine_record(record, reason_code=code))
                finding_codes.append(code)

    def _add_printings(
        self,
        card_records: Iterable[tuple[StagingRecord, CanonicalCard]],
        faces: Mapping[str, CardFace],
        printings: dict[str, Printing],
        quarantines: list[QuarantineRecord],
        finding_codes: list[str],
        provenance_rows: list[ProvenanceRow],
    ) -> None:
        for record, card in card_records:
            try:
                printing = self._printing_from_record(record, card, faces)
                if printing is not None:
                    self._merge_printing(printing, printings)
                    provenance_rows.extend(
                        self._provenance_rows(record, f"printing:{printing.printing_id}")
                    )
            except (CardMappingError, ValueError) as error:
                code = mapping_code(error)
                finding_codes.append(code)
                quarantines.append(
                    quarantine_record(
                        record,
                        reason_code=code,
                        quarantine_id=(
                            f"quarantine-{record.staging_record_id}-printing-"
                            f"{code.replace('.', '-')}"
                        ),
                    )
                )

    def _printing_from_record(
        self,
        record: StagingRecord,
        card: CanonicalCard,
        faces: Mapping[str, CardFace],
    ) -> Printing | None:
        values = mapping_values(record)
        printing_id = printing_uuid(values)
        if printing_id is None:
            return None
        set_code = source_text(values, "setCode", "set_code")
        collector_number = source_text(values, "number", "collectorNumber", "collector_number")
        release_date = card.released_at or self._release_dates.get(set_code or "")
        face_id = source_text(values, "uuid", "faceId", "face_id")
        if not set_code or not collector_number or release_date is None or face_id is None:
            raise CardMappingError("quality.incomplete_printing", "printing facts are incomplete")
        parts = source_sequence(values, "cardParts")
        face_ids = (
            tuple(split_face_id(face_id, index) for index in range(len(parts)))
            if len(parts) > 1 and not explicit_face(values)
            else (face_id,)
        )
        if any(face_identifier not in faces for face_identifier in face_ids):
            raise CardMappingError(
                "quality.missing_face_projection", "printing face is not projected"
            )
        return Printing(
            printing_id=printing_id,
            oracle_id=card.oracle_id,
            card_snapshot_id=self._card_snapshot_id,
            set_code=set_code,
            collector_number=collector_number,
            released_at=release_date,
            language=source_text(values, "language"),
            rarity=source_text(values, "rarity"),
            is_foil=optional_bool(values.get("isFoil")),
            is_promo=optional_bool(values.get("isPromo")),
            face_ids=face_ids,
            provenance=self._validated_provenance(record),
        )

    @staticmethod
    def _merge_face(face: CardFace, faces: dict[str, CardFace]) -> None:
        existing = faces.get(face.face_id)
        if existing is None:
            faces[face.face_id] = face
        elif without_provenance(existing) == without_provenance(face):
            faces[face.face_id] = existing.model_copy(
                update={"provenance": merge_provenance(existing.provenance, face.provenance)}
            )
        else:
            raise CardMappingError("quality.conflicting_face_facts", "face facts disagree")

    @staticmethod
    def _merge_printing(printing: Printing, printings: dict[str, Printing]) -> None:
        existing = printings.get(printing.printing_id)
        if existing is None:
            printings[printing.printing_id] = printing
        elif without_provenance(existing) == without_provenance(printing):
            printings[printing.printing_id] = existing.model_copy(
                update={"provenance": merge_provenance(existing.provenance, printing.provenance)}
            )
        else:
            existing_facts = without_provenance(existing)
            printing_facts = without_provenance(printing)
            if isinstance(existing_facts, dict) and isinstance(printing_facts, dict):
                existing_facts.pop("face_ids", None)
                printing_facts.pop("face_ids", None)
            if existing_facts == printing_facts:
                printings[printing.printing_id] = existing.model_copy(
                    update={
                        "face_ids": tuple(sorted(set(existing.face_ids).union(printing.face_ids))),
                        "provenance": merge_provenance(existing.provenance, printing.provenance),
                    }
                )
            else:
                raise CardMappingError(
                    "quality.conflicting_printing_facts", "printing facts disagree"
                )

    def _validated_provenance(self, record: StagingRecord) -> tuple[ProvenanceReference, ...]:
        references = self._provenance_for(record)
        if not references:
            raise CardMappingError("quality.missing_provenance", "card row has no provenance")
        for reference in references:
            if (
                reference.source_id != record.source_id
                or reference.source_snapshot_id != record.raw_locator.source_snapshot_id
                or reference.source_object_id != record.raw_locator.raw_object_id
            ):
                raise CardMappingError(
                    "quality.provenance_mismatch", "provenance does not match the raw locator"
                )
            if (
                reference.retrieved_at is None
                or reference.adapter_version is None
                or reference.mapper_version != self._mapper_version
                or reference.approval_status is None
            ):
                raise CardMappingError(
                    "quality.incomplete_provenance", "card provenance is incomplete or unbound"
                )
        return references

    def _provenance_rows(self, record: StagingRecord, entity_id: str) -> tuple[ProvenanceRow, ...]:
        references = self._validated_provenance(record)
        return tuple(
            ProvenanceRow(
                provenance_id=f"{entity_id}:provenance-{index}",
                entity_id=entity_id,
                source_id=record.source_id,
                source_snapshot_id=record.raw_locator.source_snapshot_id,
                raw_object_id=record.raw_locator.raw_object_id,
                raw_object_path=record.raw_locator.raw_object_path,
                raw_sha256=reference.raw_sha256,
                raw_locator=record.raw_locator,
                adapter_version=reference.adapter_version or self._mapper_version,
                mapper_version=reference.mapper_version,
                layer="normalized",
            )
            for index, reference in enumerate(references)
        )


def build_card_catalog(
    records: Iterable[StagingRecord],
    *,
    card_snapshot_id: str,
    provenance_for: ProvenanceForRecord,
    release_dates: Mapping[str, date] | None = None,
    mapper_version: str = CARD_MAPPING_VERSION,
) -> CatalogBuildResult:
    """Functional entry point for the staging-to-catalog boundary."""

    return CardCatalogBuilder(
        card_snapshot_id=card_snapshot_id,
        provenance_for=provenance_for,
        release_dates=release_dates,
        mapper_version=mapper_version,
    ).build(records)


__all__ = [
    "AliasCatalog",
    "CardCatalog",
    "CardCatalogBuilder",
    "CatalogBuildResult",
    "build_card_catalog",
]
