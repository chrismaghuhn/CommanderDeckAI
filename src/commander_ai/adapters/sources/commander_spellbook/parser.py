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
    RecordIndexLocator,
)

from .api_models import (
    CommanderSpellbookParsedRecord,
    CommanderSpellbookParseResult,
    MalformedJSONScalar,
    SpellbookCard,
    SpellbookVariant,
    finding_record,
    record_with_findings,
)
from .settings import DOCUMENTED_CONTRACTS, SpellbookContract


class CommanderSpellbookParseError(RuntimeError):
    """Stable parser failure for missing or unverifiable raw evidence."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _DuplicateJSONKey(ValueError):
    pass


class CommanderSpellbookParser:
    """Read raw bytes only after the shared verifier has issued evidence."""

    def parse_object(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        *,
        raw_object_id: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        self._require_snapshot(verified_snapshot)
        normalized_contract = self._require_contract(contract)
        reference = verified_snapshot.object_index.get(raw_object_id)
        raw_path = verified_snapshot.object_paths.get(raw_object_id)
        if reference is None or raw_path is None:
            raise CommanderSpellbookParseError("INTEGRITY_OBJECT_MISSING")
        raw_bytes = self._read_verified_bytes(raw_path, reference.bytes, reference.sha256)
        return self.parse_bytes(
            raw_bytes,
            source_id=verified_snapshot.manifest.source_id,
            source_snapshot_id=verified_snapshot.manifest.source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=reference.path,
            contract=normalized_contract,
        )

    def parse_bytes(
        self,
        raw_bytes: bytes,
        *,
        source_id: str = "commander_spellbook",
        source_snapshot_id: str,
        raw_object_id: str,
        raw_object_path: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        normalized_contract = self._require_contract(contract)
        root_locator = self._locator(
            source_id,
            source_snapshot_id,
            raw_object_id,
            raw_object_path,
            "",
        )
        try:
            payload = json.loads(
                raw_bytes.decode("utf-8"),
                object_pairs_hook=_pairs_without_duplicates,
                parse_constant=lambda token: MalformedJSONScalar(token),
            )
        except _DuplicateJSONKey:
            return CommanderSpellbookParseResult(
                records=(
                    finding_record(
                        normalized_contract,
                        root_locator,
                        raw_bytes,
                        code="parse.duplicate_json_key",
                        message="JSON response contains a duplicate object key",
                    ),
                )
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            return CommanderSpellbookParseResult(
                records=(
                    finding_record(
                        normalized_contract,
                        root_locator,
                        raw_bytes,
                        code="parse.invalid_json",
                        message="JSON response cannot be decoded as valid UTF-8 JSON",
                    ),
                )
            )
        return self.parse_payload(
            payload,
            source_id=source_id,
            source_snapshot_id=source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=raw_object_path,
            contract=normalized_contract,
        )

    def parse_payload(
        self,
        payload: object,
        *,
        source_id: str = "commander_spellbook",
        source_snapshot_id: str,
        raw_object_id: str,
        raw_object_path: str,
        contract: SpellbookContract | str,
    ) -> CommanderSpellbookParseResult:
        normalized_contract = self._require_contract(contract)
        base = (source_id, source_snapshot_id, raw_object_id, raw_object_path)
        if isinstance(payload, list):
            records = tuple(
                self._record(
                    item,
                    locator=self._locator(*base, RecordIndexLocator(index=index)),
                    contract=normalized_contract,
                )
                for index, item in enumerate(payload)
            )
            return CommanderSpellbookParseResult(records=records)
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            locator = self._locator(*base, "")
            return CommanderSpellbookParseResult(
                records=(
                    finding_record(
                        normalized_contract,
                        locator,
                        payload,
                        code="parse.invalid_response_envelope",
                        message="documented response must contain a results array",
                    ),
                )
            )
        records = tuple(
            self._record(
                item,
                locator=self._locator(*base, f"/results/{index}"),
                contract=normalized_contract,
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
        if _contains_malformed_value(value):
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
        if contract not in DOCUMENTED_CONTRACTS:
            raise CommanderSpellbookParseError("SPELLBOOK_CONTRACT_UNSUPPORTED")
        return contract

    @staticmethod
    def _require_snapshot(verified_snapshot: VerifiedSourceSnapshot) -> None:
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise CommanderSpellbookParseError("INTEGRITY_SNAPSHOT_INVALID") from None
        if verified_snapshot.manifest.source_id != "commander_spellbook":
            raise CommanderSpellbookParseError("INTEGRITY_SOURCE_MISMATCH")

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


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJSONKey(key)
        result[key] = value
    return result


def _contains_malformed_value(value: object) -> bool:
    if isinstance(value, MalformedJSONScalar):
        return True
    if isinstance(value, str):
        return any(0xD800 <= ord(character) <= 0xDFFF for character in value)
    if isinstance(value, Mapping):
        return any(
            _contains_malformed_value(key) or _contains_malformed_value(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_malformed_value(item) for item in value)
    return False


__all__ = ["CommanderSpellbookParseError", "CommanderSpellbookParser"]
