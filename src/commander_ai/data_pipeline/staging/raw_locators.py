"""Immutable, exact locators into finalized raw source objects."""

from __future__ import annotations

import base64
import binascii
import hashlib
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, field_validator, model_validator

from commander_ai.domain.provenance import DomainModel, validate_portable_relative_path
from commander_ai.domain.serialization import canonical_json_bytes

if TYPE_CHECKING:
    from commander_ai.adapters.storage.archive_safety import ArchiveLimits
    from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot


class JsonPointerLocator(DomainModel):
    """RFC 6901 pointer into a JSON raw object."""

    kind: Literal["json_pointer"] = "json_pointer"
    pointer: str

    @field_validator("pointer")
    @classmethod
    def validate_pointer(cls, value: str) -> str:
        return _validate_json_pointer_text(value)


class JsonObjectEntryLocator(DomainModel):
    """Locator for an ordered JSON object entry with a non-pointer-safe key.

    ``parent_pointer`` identifies the containing object, ``entry_index`` is its
    zero-based source order, and ``value_pointer`` optionally identifies a
    descendant within that entry's value. The key metadata is the base64-
    encoded, canonical JSON-escaped key representation used by the malformed-
    scalar envelope. Validation resolves the parent object from verified
    source bytes and checks the entry, descendant, and key metadata before
    accepting the locator.
    """

    kind: Literal["json_object_entry"] = "json_object_entry"
    parent_pointer: str
    entry_index: int = Field(ge=0)
    value_pointer: str = ""
    key_base64: str = Field(min_length=1)
    key_byte_length: int = Field(gt=0)
    key_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

    @field_validator("parent_pointer", "value_pointer")
    @classmethod
    def validate_pointers(cls, value: str) -> str:
        return _validate_json_pointer_text(value)

    @model_validator(mode="after")
    def validate_key_metadata(self) -> JsonObjectEntryLocator:
        try:
            raw = base64.b64decode(self.key_base64, validate=True)
        except (ValueError, UnicodeEncodeError, binascii.Error):
            raise ValueError("JSON object entry key_base64 must be valid base64") from None
        if base64.b64encode(raw).decode("ascii") != self.key_base64:
            raise ValueError("JSON object entry key_base64 must use canonical padding")
        if len(raw) != self.key_byte_length:
            raise ValueError("JSON object entry key byte length does not match key_base64")
        if hashlib.sha256(raw).hexdigest() != self.key_sha256:
            raise ValueError("JSON object entry key sha256 does not match key_base64")
        return self


class RecordIndexLocator(DomainModel):
    """Zero-based logical-record index for line-oriented or tabular objects."""

    kind: Literal["record_index"] = "record_index"
    index: int = Field(ge=0)


class ByteRangeLocator(DomainModel):
    """Half-open byte range for a record in a binary or text object."""

    kind: Literal["byte_range"] = "byte_range"
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @property
    def length(self) -> int:
        return self.end - self.start

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        if self.end <= self.start:
            raise ValueError("byte range end must be greater than start")


RawLocation = Annotated[
    JsonPointerLocator | JsonObjectEntryLocator | RecordIndexLocator | ByteRangeLocator,
    Field(discriminator="kind"),
]


class RawLocatorValidationError(ValueError):
    """Locator rejection carrying a stable validation or security code."""

    def __init__(self, message: str, *, code: str | None = None) -> None:
        self.code = code
        super().__init__(message)


class RawLocator(DomainModel):
    """Source snapshot/object identity plus one exact logical-record locator."""

    source_id: str = Field(min_length=1)
    source_snapshot_id: str = Field(min_length=1)
    raw_object_id: str = Field(min_length=1)
    raw_object_path: str = Field(min_length=1)
    location: RawLocation
    archive_member: str | None = Field(default=None, min_length=1)

    @field_validator("raw_object_path")
    @classmethod
    def validate_raw_object_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)

    @field_validator("archive_member")
    @classmethod
    def validate_archive_member(cls, value: str | None) -> str | None:
        return None if value is None else validate_portable_relative_path(value)

    @property
    def exact_locator(self) -> str:
        if isinstance(self.location, JsonPointerLocator):
            location: dict[str, object] = {
                "kind": self.location.kind,
                "pointer": self.location.pointer,
            }
        elif isinstance(self.location, JsonObjectEntryLocator):
            location = {
                "kind": self.location.kind,
                "parent_pointer": self.location.parent_pointer,
                "entry_index": self.location.entry_index,
                "value_pointer": self.location.value_pointer,
                "key_base64": self.location.key_base64,
                "key_byte_length": self.location.key_byte_length,
                "key_sha256": self.location.key_sha256,
            }
        elif isinstance(self.location, RecordIndexLocator):
            location = {"kind": self.location.kind, "index": self.location.index}
        else:
            location = {
                "kind": self.location.kind,
                "start": self.location.start,
                "end": self.location.end,
            }
        return canonical_json_bytes(
            {
                "source_id": self.source_id,
                "source_snapshot_id": self.source_snapshot_id,
                "raw_object_id": self.raw_object_id,
                "raw_object_path": self.raw_object_path,
                "archive_member": self.archive_member,
                "location": location,
            }
        ).decode("utf-8")

    @property
    def identity(self) -> str:
        """Canonical identity used to reject duplicate source locators."""

        return self.exact_locator


def validate_raw_locator_against_snapshot(
    locator: RawLocator,
    *,
    verified_snapshot: VerifiedSourceSnapshot,
    source_id: str | None = None,
    raw_sha256: str | None = None,
    archive_limits: ArchiveLimits | None = None,
) -> None:
    """Fail closed unless locator identity agrees with nominal raw evidence."""

    from .locator_validation import validate_raw_locator_against_snapshot as validate

    validate(
        locator,
        verified_snapshot=verified_snapshot,
        source_id=source_id,
        raw_sha256=raw_sha256,
        archive_limits=archive_limits,
    )


RawObjectLocator = RawLocator


def _validate_json_pointer_text(value: str) -> str:
    if value and not value.startswith("/"):
        raise ValueError("JSON pointer must be empty or start with '/'")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        raise ValueError("JSON pointer cannot contain surrogate code points")
    if any(char == "~" and index + 1 == len(value) for index, char in enumerate(value)):
        raise ValueError("JSON pointer has an incomplete escape")
    for index, char in enumerate(value[:-1]):
        if char == "~" and value[index + 1] not in "01":
            raise ValueError("JSON pointer escape must be ~0 or ~1")
    return value

__all__ = [
    "ByteRangeLocator",
    "JsonObjectEntryLocator",
    "JsonPointerLocator",
    "RawLocation",
    "RawLocator",
    "RawLocatorValidationError",
    "RawObjectLocator",
    "RecordIndexLocator",
    "validate_raw_locator_against_snapshot",
]
