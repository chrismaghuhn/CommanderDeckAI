"""Map Spellbook parse observations into Task 5 staging and audit rows."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping
from typing import cast

from pydantic import ValidationError

from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.provenance.rows import AuditRecord
from commander_ai.data_pipeline.quality.finding_codes import FindingCode
from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    validate_raw_locator_against_snapshot,
)
from commander_ai.data_pipeline.staging.records import (
    SourceRecordDTO,
    StagingRecord,
    StagingStatus,
)
from commander_ai.domain.serialization import canonical_json_bytes

from .api_models import (
    CommanderSpellbookParsedRecord,
    SpellbookCard,
    SpellbookVariant,
    json_safe_source_value,
)
from .errors import CommanderSpellbookStagingError
from .json_support import DuplicateJSONKey, contains_malformed_value, decode_json
from .settings import documented_endpoint, raw_object_identity


class CommanderSpellbookStagingMapper:
    """Keep source observations permissive and never assign semantic identity."""

    def map_records(
        self,
        records: Iterable[CommanderSpellbookParsedRecord],
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[StagingRecord, ...]:
        validated = self._validate_records(records, verified_snapshot)
        return tuple(self._map_record(record) for record in validated)

    def map_audit_records(
        self,
        records: Iterable[CommanderSpellbookParsedRecord],
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[AuditRecord, ...]:
        audits: list[AuditRecord] = []
        for record in self._validate_records(records, verified_snapshot):
            staging_id = self._staging_record_id(record)
            for finding in record.findings:
                digest = hashlib.sha256(
                    f"{record.raw_locator.exact_locator}|{finding.code}".encode()
                ).hexdigest()[:32]
                audits.append(
                    AuditRecord(
                        audit_id=f"commander-spellbook-audit-{digest}",
                        entity_id=staging_id,
                        stage=FindingCode.parse(finding.code).namespace,
                        finding_code=finding.code,
                        raw_locator=finding.raw_locator,
                        details={
                            "record_type": record.record_type,
                            "message": finding.message,
                            "source_values": record.source_values,
                        },
                    )
                )
        return tuple(audits)

    @staticmethod
    def _validate_records(
        records: Iterable[CommanderSpellbookParsedRecord],
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> tuple[CommanderSpellbookParsedRecord, ...]:
        if not isinstance(verified_snapshot, VerifiedSourceSnapshot):
            raise CommanderSpellbookStagingError("INTEGRITY_VERIFIED_SNAPSHOT_REQUIRED")
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise ValueError(
                "Commander Spellbook staging requires consistent snapshot evidence"
            ) from None
        if verified_snapshot.manifest.source_id != "commander_spellbook":
            raise ValueError("Commander Spellbook staging requires the Commander Spellbook source")

        validated: list[CommanderSpellbookParsedRecord] = []
        for record in records:
            if not isinstance(record, CommanderSpellbookParsedRecord):
                raise TypeError("Commander Spellbook staging requires parsed source records")
            expected_codes = tuple(sorted({finding.code for finding in record.findings}))
            if len(expected_codes) != len(record.findings):
                raise ValueError("Commander Spellbook findings must use unique codes")
            if record.finding_codes != expected_codes:
                raise ValueError("Commander Spellbook finding codes must match findings")
            try:
                contract, page = raw_object_identity(record.raw_locator.raw_object_id)
            except ValueError:
                raise ValueError("Commander Spellbook record product identity is invalid") from None
            expected_record_types = {contract, contract[:-1]}
            if record.record_type not in expected_record_types:
                raise ValueError(
                    "Commander Spellbook record type does not match its source product"
                )
            reference = verified_snapshot.object_index.get(record.raw_locator.raw_object_id)
            request = (
                None
                if reference is None
                else next(
                    (
                        item
                        for item in verified_snapshot.manifest.requests
                        if item.request_id == reference.request_id
                    ),
                    None,
                )
            )
            parameters = {} if request is None else request.sanitized_parameters
            if (
                reference is None
                or reference.source_object_id != contract
                or request is None
                or request.sanitized_method != "GET"
                or request.format != "json"
                or request.sanitized_endpoint != documented_endpoint(contract)
                or set(parameters) != {"page"}
                or not isinstance(parameters.get("page"), int)
                or isinstance(parameters.get("page"), bool)
                or parameters.get("page") != page
            ):
                raise ValueError("Commander Spellbook record request/product evidence disagrees")
            validate_raw_locator_against_snapshot(
                record.raw_locator,
                verified_snapshot=verified_snapshot,
                source_id="commander_spellbook",
            )
            CommanderSpellbookStagingMapper._validate_record_source(record, verified_snapshot)
            for finding in record.findings:
                if finding.raw_locator.exact_locator != record.raw_locator.exact_locator:
                    raise ValueError("Commander Spellbook finding locator disagrees with record")
                validate_raw_locator_against_snapshot(
                    finding.raw_locator,
                    verified_snapshot=verified_snapshot,
                    source_id="commander_spellbook",
                )
            validated.append(record)
        return tuple(validated)

    @staticmethod
    def _validate_record_source(
        record: CommanderSpellbookParsedRecord,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> None:
        location = record.raw_locator.location
        if not isinstance(location, JsonPointerLocator):
            raise ValueError("Commander Spellbook records require JSON pointer locators")
        raw_path = verified_snapshot.object_paths[record.raw_locator.raw_object_id]
        try:
            raw_bytes = raw_path.read_bytes()
        except OSError:
            raise ValueError("Commander Spellbook record source cannot be read") from None
        if not location.pointer:
            expected_codes, expected_values = _root_record_expectation(raw_bytes)
            _assert_record_semantics(record, expected_codes, expected_values)
            return
        parts = location.pointer.split("/")
        if len(parts) != 3 or parts[1] != "results" or not parts[2].isdigit():
            raise ValueError("Commander Spellbook record locator must identify a result")
        index_text = parts[2]
        if index_text != "0" and index_text.startswith("0"):
            raise ValueError("Commander Spellbook record locator index is not canonical")
        index = int(index_text)
        try:
            payload = decode_json(raw_path.read_bytes())
        except (DuplicateJSONKey, UnicodeDecodeError, ValueError):
            raise ValueError("Commander Spellbook record source cannot be decoded") from None
        if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
            raise ValueError("Commander Spellbook record source has no results array")
        results = cast(list[object], payload["results"])
        if index >= len(results):
            raise ValueError("Commander Spellbook record locator is outside results")
        target = results[index]
        expected_code = _expected_record_finding(target, record.record_type)
        expected_codes = () if expected_code is None else (expected_code,)
        _assert_record_semantics(record, expected_codes, json_safe_source_value(target))

    def staging_record_id(
        self,
        record: CommanderSpellbookParsedRecord,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
    ) -> str:
        self._validate_records((record,), verified_snapshot)
        return self._staging_record_id(record)

    @staticmethod
    def _staging_record_id(record: CommanderSpellbookParsedRecord) -> str:
        digest = hashlib.sha256(record.raw_locator.exact_locator.encode("utf-8")).hexdigest()
        return f"commander-spellbook-staging-{digest[:32]}"

    def _map_record(self, record: CommanderSpellbookParsedRecord) -> StagingRecord:
        source_dto = SourceRecordDTO(
            source_id=record.raw_locator.source_id,
            record_type=record.record_type,
            raw_locator=record.raw_locator,
            original_source_values=record.source_values,
        )
        return StagingRecord.from_dto(
            source_dto,
            staging_record_id=self._staging_record_id(record),
            status=self._status(record.finding_codes),
            finding_codes=record.finding_codes,
        )

    @staticmethod
    def _status(codes: tuple[str, ...]) -> StagingStatus:
        if not codes:
            return "OBSERVED"
        if any(code.startswith("integrity.") for code in codes):
            return "INCOMPLETE"
        if any(
            code
            in {
                "parse.invalid_json",
                "parse.duplicate_json_key",
                "parse.record_not_object",
            }
            for code in codes
        ):
            return "PARSE_FAILED"
        return "STRUCTURAL_INVALID"


def _root_record_expectation(raw_bytes: bytes) -> tuple[tuple[str, ...], object]:
    try:
        payload = decode_json(raw_bytes)
    except DuplicateJSONKey:
        return ("parse.duplicate_json_key",), json_safe_source_value(raw_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
        return ("parse.invalid_json",), json_safe_source_value(raw_bytes)
    if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
        return ("parse.invalid_response_envelope",), json_safe_source_value(payload)
    raise ValueError("Commander Spellbook record locator must identify a result")


def _assert_record_semantics(
    record: CommanderSpellbookParsedRecord,
    expected_codes: tuple[str, ...],
    expected_values: object,
) -> None:
    if record.finding_codes != expected_codes:
        raise ValueError("Commander Spellbook finding codes disagree with raw bytes")
    if canonical_json_bytes(record.source_values) != canonical_json_bytes(expected_values):
        raise ValueError("Commander Spellbook source values disagree with raw bytes")


def _expected_record_finding(value: object, record_type: str) -> str | None:
    if not isinstance(value, Mapping):
        return "parse.record_not_object"
    contract = "cards" if record_type in {"card", "cards"} else "variants"
    if contains_malformed_value(value):
        return "parse.malformed_scalar"
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
    if any(field not in value for field in required):
        return "parse.missing_required_field"
    try:
        if contract == "cards":
            SpellbookCard.model_validate(value)
        else:
            SpellbookVariant.model_validate(value)
    except ValidationError:
        return "parse.invalid_record_shape"
    return None


CommanderSpellbookMapper = CommanderSpellbookStagingMapper


__all__ = ["CommanderSpellbookMapper", "CommanderSpellbookStagingMapper"]
