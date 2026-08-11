"""Verified MTGJSON archive extraction and exact member/JSON-pointer parsing."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit

from commander_ai.adapters.storage.archive_safety import (
    ArchiveLimits,
    ArchiveSafetyError,
    extract_archive,
    read_archive_member,
)
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.staging.raw_locators import (
    JsonPointerLocator,
    RawLocation,
    RawLocator,
)

from .models import (
    MTGJSONFinding,
    MTGJSONParsedRecord,
    MTGJSONParseResult,
    finding_record,
)
from .record_parser import MTGJSONMemberParser
from .scalar_safety import malformed_json_constant
from .settings import MTGJSONProduct


class MTGJSONParseError(RuntimeError):
    """Stable parser failure for missing verification or unsafe archive input."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class _DuplicateJsonKey(ValueError):
    pass


class MTGJSONParser:
    """Parse only complete, verifier-issued snapshot evidence."""

    def __init__(self, *, archive_limits: ArchiveLimits | None = None) -> None:
        self._archive_limits = archive_limits

    def parse_archive(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        *,
        raw_object_id: str,
        destination: Path | str,
        product: MTGJSONProduct,
    ) -> MTGJSONParseResult:
        self._require_mtgjson_snapshot(verified_snapshot)
        normalized_product = self._require_product_identity(
            verified_snapshot, raw_object_id, product
        )
        raw_path = verified_snapshot.object_paths.get(raw_object_id)
        if raw_path is None or raw_object_id not in verified_snapshot.object_index:
            raise MTGJSONParseError("INTEGRITY_OBJECT_MISSING")
        try:
            extracted = extract_archive(
                raw_path,
                destination,
                destination_root=Path(destination).expanduser().parent,
                limits=self._archive_limits,
            )
        except ArchiveSafetyError as error:
            raise MTGJSONParseError(error.code) from None

        records: list[MTGJSONParsedRecord] = []
        for member_path in sorted(extracted.files, key=lambda path: path.as_posix()):
            member_name = member_path.relative_to(extracted.root).as_posix()
            records.extend(
                self.parse_member(
                    verified_snapshot=verified_snapshot,
                    raw_object_id=raw_object_id,
                    archive_member=member_name,
                    member_bytes=member_path.read_bytes(),
                    product=normalized_product,
                )
            )
        return MTGJSONParseResult(tuple(records), extracted.root)

    def parse_member(
        self,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        archive_member: str,
        member_bytes: bytes | None = None,
        product: MTGJSONProduct,
    ) -> tuple[MTGJSONParsedRecord, ...]:
        self._require_mtgjson_snapshot(verified_snapshot)
        normalized_product = self._require_product_identity(
            verified_snapshot, raw_object_id, product
        )
        verified_member_bytes = self._read_verified_member(
            verified_snapshot, raw_object_id, archive_member
        )
        if member_bytes is not None and member_bytes != verified_member_bytes:
            raise MTGJSONParseError("INTEGRITY_ARCHIVE_MEMBER_MISMATCH")
        member_bytes = verified_member_bytes
        locator = self._locator(verified_snapshot, raw_object_id, archive_member, "")
        try:
            payload = json.loads(
                member_bytes.decode("utf-8"),
                object_pairs_hook=_pairs_without_duplicates,
                parse_constant=malformed_json_constant,
            )
        except _DuplicateJsonKey:
            return (
                finding_record(
                    "archive_member",
                    locator,
                    member_bytes,
                    code="parse.duplicate_json_key",
                    message="JSON member contains a duplicate object key",
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError):
            return (
                finding_record(
                    "archive_member",
                    locator,
                    member_bytes,
                    code="parse.invalid_json",
                    message="JSON member cannot be decoded as valid UTF-8 JSON",
                ),
            )
        member_parser = MTGJSONMemberParser(
            lambda pointer: self._locator(verified_snapshot, raw_object_id, archive_member, pointer)
        )
        return member_parser.parse(payload, normalized_product)

    @staticmethod
    def _locator(
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        archive_member: str,
        location: str | RawLocation,
    ) -> RawLocator:
        reference = verified_snapshot.object_index.get(raw_object_id)
        if reference is None:
            raise MTGJSONParseError("INTEGRITY_OBJECT_MISSING")
        return RawLocator(
            source_id=verified_snapshot.manifest.source_id,
            source_snapshot_id=verified_snapshot.manifest.source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=reference.path,
            archive_member=archive_member,
            location=(
                JsonPointerLocator(pointer=location)
                if isinstance(location, str)
                else location
            ),
        )

    @staticmethod
    def _require_mtgjson_snapshot(verified_snapshot: VerifiedSourceSnapshot) -> None:
        try:
            verified_snapshot.assert_consistent()
        except ValueError:
            raise MTGJSONParseError("INTEGRITY_SNAPSHOT_INVALID") from None
        if verified_snapshot.manifest.source_id != "mtgjson":
            raise MTGJSONParseError("INTEGRITY_SOURCE_MISMATCH")

    @staticmethod
    def _require_product_identity(
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        product: MTGJSONProduct,
    ) -> MTGJSONProduct:
        try:
            normalized_product = MTGJSONProduct(product)
        except (TypeError, ValueError):
            raise MTGJSONParseError("INTEGRITY_PRODUCT_MISMATCH") from None
        reference = verified_snapshot.object_index.get(raw_object_id)
        if reference is None:
            raise MTGJSONParseError("INTEGRITY_OBJECT_MISSING")
        expected_object_id = f"{normalized_product.value}.json.zip"
        if (
            raw_object_id != expected_object_id
            or reference.source_object_id != normalized_product.value
        ):
            raise MTGJSONParseError("INTEGRITY_PRODUCT_MISMATCH")
        request = next(
            (
                item
                for item in verified_snapshot.manifest.requests
                if item.request_id == reference.request_id
            ),
            None,
        )
        if request is None:
            raise MTGJSONParseError("INTEGRITY_PRODUCT_MISMATCH")
        endpoint_name = urlsplit(request.sanitized_endpoint).path.rstrip("/").rsplit("/", 1)[-1]
        if endpoint_name != expected_object_id:
            raise MTGJSONParseError("INTEGRITY_PRODUCT_MISMATCH")
        return normalized_product

    def _read_verified_member(
        self,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        archive_member: str,
    ) -> bytes:
        self._require_mtgjson_snapshot(verified_snapshot)
        raw_path = verified_snapshot.object_paths.get(raw_object_id)
        if raw_path is None or raw_object_id not in verified_snapshot.object_index:
            raise MTGJSONParseError("INTEGRITY_OBJECT_MISSING")
        reference = verified_snapshot.object_index[raw_object_id]
        try:
            digest = hashlib.sha256()
            actual_bytes = 0
            with raw_path.open("rb") as raw_stream:
                while chunk := raw_stream.read(1024 * 1024):
                    actual_bytes += len(chunk)
                    digest.update(chunk)
            if actual_bytes != reference.bytes or digest.hexdigest() != reference.sha256:
                raise MTGJSONParseError("INTEGRITY_OBJECT_HASH_MISMATCH")
            return read_archive_member(
                raw_path,
                archive_member,
                limits=self._archive_limits,
            )
        except MTGJSONParseError:
            raise
        except ArchiveSafetyError as error:
            code = (
                "INTEGRITY_ARCHIVE_MEMBER_MISSING"
                if error.code == "SECURITY_ARCHIVE_MEMBER_MISSING"
                else error.code
            )
            raise MTGJSONParseError(code) from None
        except (OSError, KeyError, ValueError):
            raise MTGJSONParseError("INTEGRITY_ARCHIVE_MEMBER_MISSING") from None


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateJsonKey(key)
        result[key] = value
    return result


__all__ = [
    "MTGJSONFinding",
    "MTGJSONParseError",
    "MTGJSONParseResult",
    "MTGJSONParsedRecord",
    "MTGJSONParser",
]
