"""Parse verified Commander Spellbook JSON into source-shaped records."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from pydantic import ValidationError

from commander_ai.adapters.http.content_coding import DEFAULT_MAX_DECODED_BYTES
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
from .errors import CommanderSpellbookParseError
from .evidence import read_verified_object
from .json_support import (
    DuplicateJSONKey,
    contains_malformed_value,
    decode_json,
    valid_bulk_envelope,
    valid_pagination_envelope,
)
from .settings import SpellbookContract


class CommanderSpellbookParser:
    """Read raw bytes only after the shared verifier has issued evidence."""

    def __init__(self, *, max_decoded_bytes: int = DEFAULT_MAX_DECODED_BYTES) -> None:
        if (
            not isinstance(max_decoded_bytes, int)
            or isinstance(max_decoded_bytes, bool)
            or max_decoded_bytes < 1
        ):
            raise ValueError("max_decoded_bytes must be a positive integer")
        self.max_decoded_bytes = max_decoded_bytes

    def parse_object(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        *,
        raw_object_id: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        normalized_contract, raw_object_path, _, decoded_bytes, is_bulk = read_verified_object(
            verified_snapshot,
            raw_object_id=raw_object_id,
            contract=contract,
            max_decoded_bytes=self.max_decoded_bytes,
        )
        return self._parse_verified_bytes(
            decoded_bytes,
            verified_snapshot=verified_snapshot,
            raw_object_id=raw_object_id,
            raw_object_path=raw_object_path,
            contract=normalized_contract,
            is_bulk=is_bulk,
        )

    def parse_bytes(
        self,
        raw_bytes: bytes,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        normalized_contract, raw_object_path, verified_bytes, decoded_bytes, is_bulk = (
            read_verified_object(
                verified_snapshot,
                raw_object_id=raw_object_id,
                contract=contract,
                max_decoded_bytes=self.max_decoded_bytes,
            )
        )
        if not isinstance(raw_bytes, bytes) or raw_bytes != verified_bytes:
            raise CommanderSpellbookParseError("INTEGRITY_OBJECT_BYTES_MISMATCH")
        return self._parse_verified_bytes(
            decoded_bytes,
            verified_snapshot=verified_snapshot,
            raw_object_id=raw_object_id,
            raw_object_path=raw_object_path,
            contract=normalized_contract,
            is_bulk=is_bulk,
        )

    def parse_payload(
        self,
        payload: object,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        normalized_contract, raw_object_path, _, decoded_bytes, is_bulk = read_verified_object(
            verified_snapshot,
            raw_object_id=raw_object_id,
            contract=contract,
            max_decoded_bytes=self.max_decoded_bytes,
        )
        try:
            verified_payload = decode_json(decoded_bytes)
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
            is_bulk=is_bulk,
        )

    def _parse_verified_bytes(
        self,
        raw_bytes: bytes,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        raw_object_path: str,
        contract: SpellbookContract,
        is_bulk: bool,
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
            is_bulk=is_bulk,
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
        is_bulk: bool,
    ) -> CommanderSpellbookParseResult:
        base = (source_id, source_snapshot_id, raw_object_id, raw_object_path)
        if is_bulk:
            valid = valid_bulk_envelope(payload)
            collection = "variants"
            invalid_code = "parse.invalid_bulk_envelope"
            invalid_message = "bulk document must contain timestamp, version, and variants"
        else:
            valid = valid_pagination_envelope(payload)
            collection = "results"
            invalid_code = "parse.invalid_response_envelope"
            invalid_message = "documented response must contain a results array"
        if not valid:
            locator = CommanderSpellbookParser._locator(*base, "")
            return CommanderSpellbookParseResult(
                records=(
                    finding_record(
                        contract,
                        locator,
                        payload,
                        code=invalid_code,
                        message=invalid_message,
                    ),
                )
            )
        payload_mapping = cast(Mapping[str, object], payload)
        records = tuple(
            CommanderSpellbookParser._record(
                item,
                locator=CommanderSpellbookParser._locator(*base, f"/{collection}/{index}"),
                contract=contract,
            )
            for index, item in enumerate(
                cast(list[object], payload_mapping["variants" if is_bulk else "results"])
            )
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


__all__ = ["CommanderSpellbookParseError", "CommanderSpellbookParser"]
