"""Parse verified Commander Spellbook JSON into source-shaped records."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from pydantic import ValidationError

from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    RawLocation,
    RawLocator,
)

from .api_models import (
    CommanderSpellbookParsedRecord,
    CommanderSpellbookParseResult,
    SpellbookCard,
    SpellbookVariant,
    finding_record,
    record_with_findings,
)
from .json_support import DuplicateJSONKey, contains_malformed_value, decode_json
from .settings import (
    DOCUMENTED_CONTRACTS,
    SpellbookContract,
    documented_endpoint,
    raw_object_identity,
)


class CommanderSpellbookParseError(RuntimeError):
    """Stable parser failure for missing or unverifiable raw evidence."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class CommanderSpellbookParser:
    """Read raw bytes only after the shared verifier has issued evidence."""

    def parse_object(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        *,
        raw_object_id: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        normalized_contract, raw_object_path, raw_bytes = self._read_verified_object(
            verified_snapshot,
            raw_object_id=raw_object_id,
            contract=contract,
        )
        return self._parse_verified_bytes(
            raw_bytes,
            verified_snapshot=verified_snapshot,
            raw_object_id=raw_object_id,
            raw_object_path=raw_object_path,
            contract=normalized_contract,
        )

    def parse_bytes(
        self,
        raw_bytes: bytes,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        normalized_contract, raw_object_path, verified_bytes = self._read_verified_object(
            verified_snapshot,
            raw_object_id=raw_object_id,
            contract=contract,
        )
        if not isinstance(raw_bytes, bytes) or raw_bytes != verified_bytes:
            raise CommanderSpellbookParseError("INTEGRITY_OBJECT_BYTES_MISMATCH")
        return self._parse_verified_bytes(
            verified_bytes,
            verified_snapshot=verified_snapshot,
            raw_object_id=raw_object_id,
            raw_object_path=raw_object_path,
            contract=normalized_contract,
        )

    def parse_payload(
        self,
        payload: object,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        normalized_contract, raw_object_path, verified_bytes = self._read_verified_object(
            verified_snapshot,
            raw_object_id=raw_object_id,
            contract=contract,
        )
        try:
            verified_payload = decode_json(verified_bytes)
        except DuplicateJSONKey:
            raise CommanderSpellbookParseError("INTEGRITY_PAYLOAD_UNAVAILABLE") from None
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            raise CommanderSpellbookParseError("INTEGRITY_PAYLOAD_UNAVAILABLE") from None
        if payload != verified_payload:
            raise CommanderSpellbookParseError("INTEGRITY_PAYLOAD_MISMATCH")
        return self._parse_payload(
            verified_payload,
            source_id=verified_snapshot.manifest.source_id,
            source_snapshot_id=verified_snapshot.manifest.source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=raw_object_path,
            contract=normalized_contract,
        )

    def _parse_verified_bytes(
        self,
        raw_bytes: bytes,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        raw_object_path: str,
        contract: SpellbookContract,
    ) -> CommanderSpellbookParseResult:
        root_locator = self._locator(
            verified_snapshot.manifest.source_id,
            verified_snapshot.manifest.source_snapshot_id,
            raw_object_id,
            raw_object_path,
            "",
        )
        try:
            payload = decode_json(raw_bytes)
        except DuplicateJSONKey:
            return CommanderSpellbookParseResult(
                records=(
                    finding_record(
                        contract,
                        root_locator,
                        raw_bytes,
                        code="parse.duplicate_json_key",
                        message="JSON response contains a duplicate object key",
                    ),
                )
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return CommanderSpellbookParseResult(
                records=(
                    finding_record(
                        contract,
                        root_locator,
                        raw_bytes,
                        code="parse.invalid_json",
                        message="JSON response cannot be decoded as valid UTF-8 JSON",
                    ),
                )
            )
        return self._parse_payload(
            payload,
            source_id=verified_snapshot.manifest.source_id,
            source_snapshot_id=verified_snapshot.manifest.source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=raw_object_path,
            contract=contract,
        )

    @staticmethod
    def _parse_payload(
        payload: object,
        *,
        source_id: str,
        source_snapshot_id: str,
        raw_object_id: str,
        raw_object_path: str,
        contract: SpellbookContract,
    ) -> CommanderSpellbookParseResult:
        base = (source_id, source_snapshot_id, raw_object_id, raw_object_path)
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            locator = CommanderSpellbookParser._locator(*base, "")
            return CommanderSpellbookParseResult(
                records=(
                    finding_record(
                        contract,
                        locator,
                        payload,
                        code="parse.invalid_response_envelope",
                        message="documented response must contain a results array",
                    ),
                )
            )
        records = tuple(
            CommanderSpellbookParser._record(
                item,
                locator=CommanderSpellbookParser._locator(*base, f"/results/{index}"),
                contract=contract,
            )
            for index, item in enumerate(cast(list[object], payload["results"]))
        )
        return CommanderSpellbookParseResult(records=records)

    @staticmethod
    def _record(
        value: object,
        *,
        locator: RawLocator,
        contract: SpellbookContract,
    ) -> CommanderSpellbookParsedRecord:
        if not isinstance(value, Mapping):
            return finding_record(
                contract,
                locator,
                value,
                code="parse.record_not_object",
                message="response record must be a JSON object",
            )
        if contains_malformed_value(value):
            return finding_record(
                contract,
                locator,
                value,
                code="parse.malformed_scalar",
                message="response record contains a malformed JSON scalar",
            )
        required = (
            ("id", "name")
            if contract == "cards"
            else (
                "id",
                "uses",
                "requires",
                "produces",
                "status",
            )
        )
        missing = [field for field in required if field not in value]
        if missing:
            return finding_record(
                contract[:-1] if contract.endswith("s") else contract,
                locator,
                value,
                code="parse.missing_required_field",
                message=f"response record is missing required field(s): {', '.join(missing)}",
            )
        try:
            dto = (
                SpellbookCard.model_validate(value)
                if contract == "cards"
                else SpellbookVariant.model_validate(value)
            )
        except ValidationError:
            return finding_record(
                contract[:-1] if contract.endswith("s") else contract,
                locator,
                value,
                code="parse.invalid_record_shape",
                message="response record does not match the documented DTO shape",
            )
        return record_with_findings(
            contract[:-1] if contract.endswith("s") else contract,
            locator,
            value,
            dto,
            [],
        )

    @staticmethod
    def _locator(
        source_id: str,
        source_snapshot_id: str,
        raw_object_id: str,
        raw_object_path: str,
        location: str | RawLocation,
    ) -> RawLocator:
        return RawLocator(
            source_id=source_id,
            source_snapshot_id=source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=raw_object_path,
            location=(
                JsonPointerLocator(pointer=location) if isinstance(location, str) else location
            ),
        )

    @staticmethod
    def _require_contract(contract: SpellbookContract | str) -> SpellbookContract:
        if not isinstance(contract, str) or contract not in DOCUMENTED_CONTRACTS:
            raise CommanderSpellbookParseError("SPELLBOOK_CONTRACT_UNSUPPORTED")
        return contract

    @staticmethod
    def _require_snapshot(verified_snapshot: VerifiedSourceSnapshot) -> None:
        if not isinstance(verified_snapshot, VerifiedSourceSnapshot):
            raise CommanderSpellbookParseError("INTEGRITY_SNAPSHOT_INVALID")
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise CommanderSpellbookParseError("INTEGRITY_SNAPSHOT_INVALID") from None
        if verified_snapshot.manifest.source_id != "commander_spellbook":
            raise CommanderSpellbookParseError("INTEGRITY_SOURCE_MISMATCH")

    def _read_verified_object(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        *,
        raw_object_id: str,
        contract: SpellbookContract | str,
    ) -> tuple[SpellbookContract, str, bytes]:
        self._require_snapshot(verified_snapshot)
        normalized_contract = self._require_contract(contract)
        try:
            object_contract, page = raw_object_identity(raw_object_id)
        except ValueError:
            raise CommanderSpellbookParseError("INTEGRITY_OBJECT_IDENTITY_MISMATCH") from None
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
        parameters = request.sanitized_parameters
        if (
            request.sanitized_method != "GET"
            or request.format != "json"
            or request.sanitized_endpoint != documented_endpoint(normalized_contract)
            or set(parameters) != {"page"}
            or not isinstance(parameters.get("page"), int)
            or isinstance(parameters.get("page"), bool)
            or parameters.get("page") != page
        ):
            raise CommanderSpellbookParseError("INTEGRITY_REQUEST_MISMATCH")
        raw_bytes = self._read_verified_bytes(raw_path, reference.bytes, reference.sha256)
        return normalized_contract, reference.path, raw_bytes

    @staticmethod
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


__all__ = ["CommanderSpellbookParseError", "CommanderSpellbookParser"]
