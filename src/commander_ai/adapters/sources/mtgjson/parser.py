"""Verified MTGJSON archive extraction and exact member/JSON-pointer parsing."""

from __future__ import annotations

import json
from pathlib import Path

from commander_ai.adapters.storage.archive_safety import (
    ArchiveLimits,
    ArchiveSafetyError,
    extract_archive,
)
from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot
from commander_ai.data_pipeline.staging.raw_locators import JsonPointerLocator, RawLocator

from .models import (
    MTGJSONFinding,
    MTGJSONParsedRecord,
    MTGJSONParseResult,
    finding_record,
)
from .record_parser import MTGJSONMemberParser
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
        verified_snapshot.assert_consistent()
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
                    product=product,
                )
            )
        return MTGJSONParseResult(tuple(records), extracted.root)

    def parse_member(
        self,
        *,
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        archive_member: str,
        member_bytes: bytes,
        product: MTGJSONProduct,
    ) -> tuple[MTGJSONParsedRecord, ...]:
        locator = self._locator(verified_snapshot, raw_object_id, archive_member, "")
        try:
            payload = json.loads(
                member_bytes.decode("utf-8"),
                object_pairs_hook=_pairs_without_duplicates,
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
        return member_parser.parse(payload, product)

    @staticmethod
    def _locator(
        verified_snapshot: VerifiedSourceSnapshot,
        raw_object_id: str,
        archive_member: str,
        pointer: str,
    ) -> RawLocator:
        reference = verified_snapshot.object_index.get(raw_object_id)
        if reference is None:
            raise MTGJSONParseError("INTEGRITY_OBJECT_MISSING")
        return RawLocator(
            source_snapshot_id=verified_snapshot.manifest.source_snapshot_id,
            raw_object_id=raw_object_id,
            raw_object_path=reference.path,
            archive_member=archive_member,
            location=JsonPointerLocator(pointer=pointer),
        )


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
