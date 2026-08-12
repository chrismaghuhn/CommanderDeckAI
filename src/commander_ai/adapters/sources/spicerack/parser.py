"""Parse verified Spicerack export responses into source staging records."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping

from commander_ai.adapters.http.content_coding import HttpContentCodingError, decode_entity_body
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.staging.raw_locators import (
    ByteRangeLocator,
    JsonPointerLocator,
    RawLocator,
    RawLocatorValidationError,
    validate_raw_locator_against_snapshot,
)
from commander_ai.domain.provenance import RawObjectReference
from commander_ai.domain.serialization import canonical_json_bytes

from .dto import SpicerackParsedRecord
from .errors import SpicerackParseError
from .json_support import DuplicateJSONKey, decode_json
from .logical_records import event_records, finding
from .ndjson_locators import standing_object_ranges
from .settings import SPICERACK_SOURCE_ID, SpicerackSettings

_OBJECT_ID = re.compile(r"^spicerack-([a-z0-9_]+)\.(json|ndjson)$")


class SpicerackParser:
    """Validate snapshot evidence, then preserve documented export records."""

    def __init__(
        self, settings: SpicerackSettings, *, max_decoded_bytes: int | None = None
    ) -> None:
        self.settings = settings
        selected = settings.max_response_bytes if max_decoded_bytes is None else max_decoded_bytes
        if type(selected) is not int or selected < 1:
            raise ValueError("max_decoded_bytes must be a positive integer")
        self.max_decoded_bytes = selected

    def parse_object(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        *,
        raw_object_id: str = "spicerack-commander2.json",
    ) -> tuple[SpicerackParsedRecord, ...]:
        _raw_bytes, decoded_bytes, reference = self._read_verified_object(
            verified_snapshot, raw_object_id
        )
        match = _OBJECT_ID.fullmatch(raw_object_id)
        if match is None or match.group(2) != self.settings.response_format:
            raise SpicerackParseError("INTEGRITY_RESPONSE_FORMAT_MISMATCH")
        if self.settings.response_format == "ndjson":
            return self._parse_ndjson(
                decoded_bytes, verified_snapshot, raw_object_id, reference.path
            )
        return self._parse_json(decoded_bytes, verified_snapshot, raw_object_id, reference.path)

    def parse_bytes(
        self,
        raw_bytes: bytes,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str = "spicerack-commander2.json",
    ) -> tuple[SpicerackParsedRecord, ...]:
        evidence, _, _ = self._read_verified_object(verified_snapshot, raw_object_id)
        if not isinstance(raw_bytes, bytes) or raw_bytes != evidence:
            raise SpicerackParseError("INTEGRITY_OBJECT_BYTES_MISMATCH")
        return self.parse_object(verified_snapshot, raw_object_id=raw_object_id)

    def _read_verified_object(
        self, verified_snapshot: VerifiedSourceSnapshot, raw_object_id: str
    ) -> tuple[bytes, bytes, RawObjectReference]:
        if not isinstance(verified_snapshot, VerifiedSourceSnapshot):
            raise SpicerackParseError("INTEGRITY_VERIFIED_SNAPSHOT_REQUIRED")
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise SpicerackParseError("INTEGRITY_VERIFIED_SNAPSHOT_INVALID") from None
        manifest = verified_snapshot.manifest
        if manifest.source_id != SPICERACK_SOURCE_ID:
            raise SpicerackParseError("INTEGRITY_SOURCE_MISMATCH")
        reference = verified_snapshot.object_index.get(raw_object_id)
        if reference is None or reference.source_object_id != "spicerack-public-decklists":
            raise SpicerackParseError("INTEGRITY_OBJECT_MISMATCH")
        match = _OBJECT_ID.fullmatch(raw_object_id)
        if match is None:
            raise SpicerackParseError("INTEGRITY_OBJECT_MISMATCH")
        selected_format = match.group(1).upper()
        if selected_format not in self.settings.formats:
            raise SpicerackParseError("INTEGRITY_REQUEST_MISMATCH")
        request = next(
            (item for item in manifest.requests if item.request_id == reference.request_id), None
        )
        expected = self.settings.request_parameters(selected_format=selected_format)
        request_matches = request is not None and canonical_json_bytes(
            request.sanitized_parameters
        ) == canonical_json_bytes(expected)
        if (
            request is None
            or request.sanitized_method != "GET"
            or request.sanitized_endpoint != self.settings.endpoint
            or request.format != self.settings.response_format
            or not request_matches
        ):
            raise SpicerackParseError("INTEGRITY_REQUEST_MISMATCH")
        path = verified_snapshot.object_paths[raw_object_id]
        try:
            raw = path.read_bytes()
        except OSError:
            raise SpicerackParseError("INTEGRITY_OBJECT_UNREADABLE") from None
        locator = RawLocator(
            source_id=SPICERACK_SOURCE_ID,
            source_snapshot_id=manifest.source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=reference.path,
            location=JsonPointerLocator(pointer=""),
        )
        try:
            validate_raw_locator_against_snapshot(
                locator,
                verified_snapshot=verified_snapshot,
                source_id=SPICERACK_SOURCE_ID,
                max_decoded_bytes=self.max_decoded_bytes,
            )
        except RawLocatorValidationError as error:
            raise SpicerackParseError(error.code or "INTEGRITY_OBJECT_MISMATCH") from None
        except ValueError as error:
            if "bytes do not match its manifest digest" in str(error):
                raise SpicerackParseError("INTEGRITY_OBJECT_HASH_MISMATCH") from None
            raise SpicerackParseError("INTEGRITY_OBJECT_MISMATCH") from None
        except TypeError:
            raise SpicerackParseError("INTEGRITY_OBJECT_MISMATCH") from None
        try:
            decoded = decode_entity_body(
                raw, reference.content_encoding, max_decoded_bytes=self.max_decoded_bytes
            )
        except HttpContentCodingError as error:
            raise SpicerackParseError(error.code) from None
        return raw, decoded, reference

    def _parse_json(
        self, raw: bytes, verified: VerifiedSourceSnapshot, object_id: str, path: str
    ) -> tuple[SpicerackParsedRecord, ...]:
        try:
            payload = decode_json(raw)
        except DuplicateJSONKey:
            return (
                finding(
                    "response",
                    verified,
                    object_id,
                    path,
                    "",
                    "parse.spicerack_duplicate_json_key",
                    "response contains a duplicate JSON key",
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError):
            return (
                finding(
                    "response",
                    verified,
                    object_id,
                    path,
                    "",
                    "parse.spicerack_invalid_json",
                    "response is not valid UTF-8 JSON",
                ),
            )
        if not isinstance(payload, list):
            return (
                finding(
                    "response",
                    verified,
                    object_id,
                    path,
                    "",
                    "parse.spicerack_invalid_response",
                    "export response must be an array",
                ),
            )
        records: list[SpicerackParsedRecord] = []
        for index, item in enumerate(payload):
            records.extend(event_records(item, verified, object_id, path, f"/{index}"))
        return tuple(records)

    def _parse_ndjson(
        self, raw: bytes, verified: VerifiedSourceSnapshot, object_id: str, path: str
    ) -> tuple[SpicerackParsedRecord, ...]:
        records: list[SpicerackParsedRecord] = []
        offset = 0
        for line in raw.splitlines(keepends=True):
            start = offset
            offset += len(line)
            location = ByteRangeLocator(start=start, end=offset)
            content = line.rstrip(b"\r\n")
            if not content.strip():
                continue
            try:
                payload = decode_json(content)
            except (DuplicateJSONKey, UnicodeDecodeError, json.JSONDecodeError, ValueError):
                records.append(
                    finding(
                        "response",
                        verified,
                        object_id,
                        path,
                        location,
                        "parse.spicerack_invalid_ndjson",
                        "NDJSON line is invalid",
                    )
                )
                continue
            nested_locations = (
                standing_object_ranges(content, line_offset=start)
                if isinstance(payload, Mapping)
                else ()
            )
            standings = payload.get("standings") if isinstance(payload, Mapping) else None
            if (
                isinstance(standings, list)
                and standings
                and (nested_locations is None or len(nested_locations) != len(standings))
            ):
                records.extend(
                    event_records(
                        payload,
                        verified,
                        object_id,
                        path,
                        location,
                        expand_nested=False,
                    )
                )
                records.append(
                    finding(
                        "response",
                        verified,
                        object_id,
                        path,
                        ByteRangeLocator(start=location.start, end=location.start + 1),
                        "parse.spicerack_nested_locator_unavailable",
                        "nested NDJSON standings could not be located safely",
                    )
                )
            else:
                records.extend(
                    event_records(
                        payload,
                        verified,
                        object_id,
                        path,
                        location,
                        nested_locations=nested_locations or (),
                    )
                )
        return tuple(records)


__all__ = ["SpicerackParseError", "SpicerackParser"]
