"""Index construction and source-value primitives for card catalogs."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from uuid import UUID

from commander_ai.data_pipeline.staging.records import StagingRecord
from commander_ai.domain.cards import CanonicalCard, CardFace, CardResolutionCandidate, Printing
from commander_ai.domain.provenance import ProvenanceReference
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex

from .canonical_cards import CardMappingError, source_identifiers
from .card_faces import related_face_ids, source_text
from .catalog_models import CardCatalog, sorted_candidates


def build_catalog_indexes(
    *,
    cards: tuple[CanonicalCard, ...],
    faces: tuple[CardFace, ...],
    printings: tuple[Printing, ...],
    source_records: Iterable[tuple[StagingRecord, CanonicalCard]],
) -> CardCatalog:
    cards = tuple(sorted(cards, key=lambda item: item.oracle_id))
    faces = tuple(sorted(faces, key=lambda item: item.face_id))
    printings = tuple(sorted(printings, key=lambda item: item.printing_id))
    identifiers: dict[str, list[CardResolutionCandidate]] = {}
    names: dict[str, list[CardResolutionCandidate]] = {}
    face_names: dict[str, list[CardResolutionCandidate]] = {}
    relationships: dict[str, tuple[str, ...]] = {}
    for card in cards:
        append_index(names, card.normalized_name, CardResolutionCandidate(oracle_id=card.oracle_id))
    for face in faces:
        append_index(
            face_names,
            face.normalized_name,
            CardResolutionCandidate(oracle_id=face.oracle_id, face_id=face.face_id),
        )
    for printing in printings:
        append_index(
            identifiers,
            printing.printing_id,
            CardResolutionCandidate(
                oracle_id=printing.oracle_id,
                printing_id=printing.printing_id,
            ),
        )
    for record, card in source_records:
        values = mapping_values(record)
        printing_id = printing_uuid(values)
        indexed_printing_id = (
            printing_id
            if any(
                printing.printing_id == printing_id and printing.oracle_id == card.oracle_id
                for printing in printings
            )
            else None
        )
        face_id = source_text(values, "uuid", "faceId", "face_id")
        if face_id:
            related = related_face_ids(values)
            if related:
                relationships[face_id] = tuple(sorted(set(related)))
        for identifier_name, identifier in source_identifiers(values):
            is_oracle_identifier = identifier_name in {"scryfallOracleId", "oracleId", "oracle_id"}
            append_index(
                identifiers,
                identifier,
                CardResolutionCandidate(
                    oracle_id=card.oracle_id,
                    printing_id=None if is_oracle_identifier else indexed_printing_id,
                    face_id=face_id if identifier_name == "uuid" else None,
                ),
            )
    for card in cards:
        append_index(identifiers, card.oracle_id, CardResolutionCandidate(oracle_id=card.oracle_id))
    payload = {
        "cards": [item.model_dump(mode="json") for item in cards],
        "faces": [item.model_dump(mode="json") for item in faces],
        "printings": [item.model_dump(mode="json") for item in printings],
        "identifiers": index_payload(identifiers),
        "names": index_payload(names),
        "face_names": index_payload(face_names),
        "related_face_ids": {key: list(value) for key, value in sorted(relationships.items())},
    }
    snapshot_id = f"card-catalog-{sha256_hex(canonical_json_bytes(payload))[:32]}"
    return CardCatalog(
        catalog_snapshot_id=snapshot_id,
        cards=cards,
        faces=faces,
        printings=printings,
        identifier_index={key: sorted_candidates(value) for key, value in identifiers.items()},
        name_index={key: sorted_candidates(value) for key, value in names.items()},
        face_name_index={key: sorted_candidates(value) for key, value in face_names.items()},
        related_face_ids=relationships,
    )


def append_index(
    index: dict[str, list[CardResolutionCandidate]],
    key: str,
    candidate: CardResolutionCandidate,
) -> None:
    index.setdefault(key, [])
    if candidate not in index[key]:
        index[key].append(candidate)


def index_payload(
    index: Mapping[str, Iterable[CardResolutionCandidate]],
) -> dict[str, list[dict[str, object]]]:
    return {
        key: [candidate.model_dump(mode="json") for candidate in sorted_candidates(value)]
        for key, value in sorted(index.items())
    }


def mapping_values(record: StagingRecord) -> Mapping[str, object]:
    values = record.original_source_values
    if not isinstance(values, Mapping):
        raise CardMappingError(
            "quality.source_value_not_object", "card source values are not an object"
        )
    return values


def source_oracle(values: Mapping[str, object]) -> str | None:
    identifiers = values.get("identifiers")
    candidates = [
        values.get("scryfallOracleId"),
        values.get("oracleId"),
        values.get("oracle_id"),
        identifiers.get("scryfallOracleId") if isinstance(identifiers, Mapping) else None,
        identifiers.get("oracleId") if isinstance(identifiers, Mapping) else None,
        identifiers.get("oracle_id") if isinstance(identifiers, Mapping) else None,
    ]
    valid: list[str] = []
    for value in candidates:
        if not isinstance(value, str):
            continue
        try:
            candidate = str(UUID(value))
        except ValueError:
            continue
        if candidate not in valid:
            valid.append(candidate)
    if len(valid) > 1:
        raise CardMappingError(
            "quality.conflicting_canonical_identifiers",
            "source row contains contradictory canonical oracle identifiers",
        )
    return valid[0] if valid else None


def printing_uuid(values: Mapping[str, object]) -> str | None:
    identifiers = values.get("identifiers")
    candidates = [
        values.get("scryfallId"),
        identifiers.get("scryfallId") if isinstance(identifiers, Mapping) else None,
    ]
    candidates.extend([values.get("printingId"), values.get("uuid")])
    for value in candidates:
        if not isinstance(value, str):
            continue
        try:
            return str(UUID(value))
        except ValueError:
            continue
    return None


def optional_bool(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def without_provenance(value: object) -> object:
    if hasattr(value, "model_dump"):
        payload = value.model_dump(mode="python")
        payload.pop("provenance", None)
        return payload
    return value


def merge_provenance(
    first: tuple[ProvenanceReference, ...], second: tuple[ProvenanceReference, ...]
) -> tuple[ProvenanceReference, ...]:
    by_key = {
        (item.source_id, item.source_snapshot_id, item.source_object_id, item.raw_sha256): item
        for item in (*first, *second)
    }
    return tuple(by_key[key] for key in sorted(by_key))


def mapping_code(error: ValueError) -> str:
    return getattr(error, "reason_code", "quality.invalid_card_record")
