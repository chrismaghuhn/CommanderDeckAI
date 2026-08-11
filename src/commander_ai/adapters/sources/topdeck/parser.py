"""Verify complete TopDeck raw objects before source-shaped parsing."""

from __future__ import annotations

import hashlib
import json

from commander_ai.adapters.http.content_coding import (
    HttpContentCodingError,
    decode_entity_body,
)
from commander_ai.adapters.http.redaction import redact_request_parameters, sanitize_endpoint
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    RawLocator,
    validate_raw_locator_against_snapshot,
)
from commander_ai.domain.serialization import canonical_json_bytes

from .dto import TopDeckParsedRecord
from .errors import TopDeckParseError
from .json_support import DuplicateJSONKey, decode_json
from .record_parser import TopDeckRecordFactory, TopDeckRecordParser
from .settings import TOPDECK_SOURCE_ID, TopDeckSettings


class TopDeckParser:
    """Read only complete, hash-verified TopDeck raw response evidence."""

    def __init__(
        self,
        settings: TopDeckSettings,
        *,
        max_decoded_bytes: int | None = None,
    ) -> None:
        self.settings = settings
        selected_limit = (
            self.settings.max_response_bytes if max_decoded_bytes is None else max_decoded_bytes
        )
        if not isinstance(selected_limit, int) or isinstance(selected_limit, bool):
            raise ValueError("max_decoded_bytes must be a positive integer")
        if selected_limit < 1:
            raise ValueError("max_decoded_bytes must be a positive integer")
        self.max_decoded_bytes = selected_limit

    def parse_object(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        *,
        raw_object_id: str = "tournaments-v2.json",
    ) -> tuple[TopDeckParsedRecord, ...]:
        _, decoded_bytes = self._read_verified_object(
            verified_snapshot, raw_object_id=raw_object_id
        )
        return self._parse_decoded(decoded_bytes, verified_snapshot, raw_object_id)

    def parse_bytes(
        self,
        raw_bytes: bytes,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str = "tournaments-v2.json",
    ) -> tuple[TopDeckParsedRecord, ...]:
        verified_bytes, decoded_bytes = self._read_verified_object(
            verified_snapshot, raw_object_id=raw_object_id
        )
        if not isinstance(raw_bytes, bytes) or raw_bytes != verified_bytes:
            raise TopDeckParseError("INTEGRITY_OBJECT_BYTES_MISMATCH")
        return self._parse_decoded(decoded_bytes, verified_snapshot, raw_object_id)

    def _read_verified_object(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        *,
        raw_object_id: str,
    ) -> tuple[bytes, bytes]:
        if not isinstance(verified_snapshot, VerifiedSourceSnapshot):
            raise TopDeckParseError("INTEGRITY_VERIFIED_SNAPSHOT_REQUIRED")
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise TopDeckParseError("INTEGRITY_VERIFIED_SNAPSHOT_INVALID") from None
        manifest = verified_snapshot.manifest
        if manifest.source_id != TOPDECK_SOURCE_ID:
            raise TopDeckParseError("INTEGRITY_SOURCE_MISMATCH")
        reference = verified_snapshot.object_index.get(raw_object_id)
        if reference is None or reference.source_object_id != "tournaments-v2":
            raise TopDeckParseError("INTEGRITY_OBJECT_MISMATCH")
        request = next(
            (item for item in manifest.requests if item.request_id == reference.request_id), None
        )
        expected_requests = tuple(
            (
                redact_request_parameters(parameters),
                hashlib.sha256(canonical_json_bytes(parameters)).hexdigest(),
            )
            for parameters in self.settings.request_parameter_sets()
        )
        request_matches = request is not None and any(
            canonical_json_bytes(request.sanitized_parameters) == canonical_json_bytes(parameters)
            and request.request_body_sha256 == body_sha256
            for parameters, body_sha256 in expected_requests
        )
        if (
            request is None
            or request.sanitized_method != "POST"
            or request.sanitized_endpoint != sanitize_endpoint(self.settings.endpoint)
            or request.api_version != self.settings.api_version
            or request.format != "json"
            or not request_matches
        ):
            raise TopDeckParseError("INTEGRITY_REQUEST_MISMATCH")
        path = verified_snapshot.object_paths[raw_object_id]
        try:
            raw_bytes = path.read_bytes()
        except OSError:
            raise TopDeckParseError("INTEGRITY_OBJECT_UNREADABLE") from None
        locator = RawLocator(
            source_id=TOPDECK_SOURCE_ID,
            source_snapshot_id=manifest.source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=reference.path,
            location=JsonPointerLocator(pointer=""),
        )
        try:
            validate_raw_locator_against_snapshot(
                locator, verified_snapshot=verified_snapshot, source_id=TOPDECK_SOURCE_ID
            )
        except (ValueError, TypeError) as error:
            code = str(error)
            if code.startswith("HTTP_"):
                raise TopDeckParseError(code) from None
            raise TopDeckParseError("INTEGRITY_OBJECT_MISMATCH") from None
        try:
            decoded_bytes = decode_entity_body(
                raw_bytes,
                reference.content_encoding,
                max_decoded_bytes=self.max_decoded_bytes,
            )
        except HttpContentCodingError as error:
            raise TopDeckParseError(error.code) from None
        return raw_bytes, decoded_bytes

    def _parse_decoded(
        self,
        decoded_bytes: bytes,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
    ) -> tuple[TopDeckParsedRecord, ...]:
        factory = TopDeckRecordFactory(
            lambda pointer: self._locator(verified_snapshot, raw_object_id, pointer)
        )
        try:
            payload = decode_json(decoded_bytes)
        except DuplicateJSONKey:
            return (
                factory.finding_record(
                    "response",
                    factory.locator(""),
                    decoded_bytes,
                    "parse.topdeck_duplicate_json_key",
                    "response contains a duplicate JSON key",
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return (
                factory.finding_record(
                    "response",
                    factory.locator(""),
                    decoded_bytes,
                    "parse.topdeck_invalid_json",
                    "response is not valid UTF-8 JSON",
                ),
            )
        return TopDeckRecordParser(factory).parse(payload)

    @staticmethod
    def _locator(verified: VerifiedSourceSnapshot, raw_object_id: str, pointer: str) -> RawLocator:
        reference = verified.object_index[raw_object_id]
        return RawLocator(
            source_id=TOPDECK_SOURCE_ID,
            source_snapshot_id=verified.manifest.source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=reference.path,
            location=JsonPointerLocator(pointer=pointer),
        )


__all__ = ["TopDeckParser"]
