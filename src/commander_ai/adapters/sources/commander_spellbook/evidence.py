"""Read only verified Commander Spellbook raw-object evidence."""

from __future__ import annotations

import hashlib
from pathlib import Path

from commander_ai.adapters.http.content_coding import (
    HttpContentCodingError,
    decode_entity_body,
)
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot

from .errors import CommanderSpellbookParseError
from .settings import (
    DOCUMENTED_CONTRACTS,
    SpellbookContract,
    documented_bulk_endpoint,
    documented_endpoint,
    raw_object_identity,
)


def read_verified_object(
    verified_snapshot: VerifiedSourceSnapshot,
    *,
    raw_object_id: str,
    contract: SpellbookContract | str,
    max_decoded_bytes: int,
) -> tuple[SpellbookContract, str, bytes, bytes, bool]:
    """Validate request/object lineage and return raw plus bounded decoded bytes."""

    _require_snapshot(verified_snapshot)
    normalized_contract = _require_contract(contract)
    try:
        object_contract, page = raw_object_identity(raw_object_id)
    except ValueError:
        raise CommanderSpellbookParseError("INTEGRITY_OBJECT_IDENTITY_MISMATCH") from None
    is_bulk = page is None
    if object_contract != normalized_contract:
        raise CommanderSpellbookParseError("INTEGRITY_PRODUCT_MISMATCH")
    reference = verified_snapshot.object_index.get(raw_object_id)
    raw_path = verified_snapshot.object_paths.get(raw_object_id)
    if reference is None or raw_path is None:
        raise CommanderSpellbookParseError("INTEGRITY_OBJECT_MISSING")
    if reference.source_object_id != normalized_contract:
        raise CommanderSpellbookParseError("INTEGRITY_PRODUCT_MISMATCH")
    request = next(
        (
            item
            for item in verified_snapshot.manifest.requests
            if item.request_id == reference.request_id
        ),
        None,
    )
    if request is None:
        raise CommanderSpellbookParseError("INTEGRITY_REQUEST_MISMATCH")
    expected_endpoint = (
        documented_bulk_endpoint() if is_bulk else documented_endpoint(normalized_contract)
    )
    expected_parameters = {} if is_bulk else {"page": page}
    if (
        request.sanitized_method != "GET"
        or request.format != "json"
        or request.sanitized_endpoint != expected_endpoint
        or request.sanitized_parameters != expected_parameters
    ):
        raise CommanderSpellbookParseError("INTEGRITY_REQUEST_MISMATCH")
    raw_bytes = _read_verified_bytes(raw_path, reference.bytes, reference.sha256)
    try:
        decoded_bytes = decode_entity_body(
            raw_bytes,
            reference.content_encoding,
            max_decoded_bytes=max_decoded_bytes,
        )
    except HttpContentCodingError as error:
        raise CommanderSpellbookParseError(error.code) from None
    return normalized_contract, reference.path, raw_bytes, decoded_bytes, is_bulk


def _require_contract(contract: SpellbookContract | str) -> SpellbookContract:
    if not isinstance(contract, str) or contract not in DOCUMENTED_CONTRACTS:
        raise CommanderSpellbookParseError("SPELLBOOK_CONTRACT_UNSUPPORTED")
    return contract


def _require_snapshot(verified_snapshot: VerifiedSourceSnapshot) -> None:
    if not isinstance(verified_snapshot, VerifiedSourceSnapshot):
        raise CommanderSpellbookParseError("INTEGRITY_SNAPSHOT_INVALID")
    try:
        verified_snapshot.assert_consistent()
    except ValueError:
        raise CommanderSpellbookParseError("INTEGRITY_SNAPSHOT_INVALID") from None
    if verified_snapshot.manifest.source_id != "commander_spellbook":
        raise CommanderSpellbookParseError("INTEGRITY_SOURCE_MISMATCH")


def _read_verified_bytes(path: Path, expected_bytes: int, expected_sha256: str) -> bytes:
    try:
        raw_bytes = path.read_bytes()
    except OSError:
        raise CommanderSpellbookParseError("INTEGRITY_OBJECT_MISSING") from None
    if len(raw_bytes) != expected_bytes:
        raise CommanderSpellbookParseError("INTEGRITY_OBJECT_SIZE_MISMATCH")
    if hashlib.sha256(raw_bytes).hexdigest() != expected_sha256:
        raise CommanderSpellbookParseError("INTEGRITY_OBJECT_HASH_MISMATCH")
    return raw_bytes


__all__ = ["read_verified_object"]
