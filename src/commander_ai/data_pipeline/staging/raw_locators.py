"""Immutable, exact locators into finalized raw source objects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field, field_validator

from commander_ai.domain.provenance import DomainModel, validate_portable_relative_path
from commander_ai.domain.serialization import canonical_json_bytes

if TYPE_CHECKING:
    from commander_ai.application.verified_source_snapshot import VerifiedSourceSnapshot


class JsonPointerLocator(DomainModel):
    """RFC 6901 pointer into a JSON raw object."""

    kind: Literal["json_pointer"] = "json_pointer"
    pointer: str

    @field_validator("pointer")
    @classmethod
    def validate_pointer(cls, value: str) -> str:
        if value and not value.startswith("/"):
            raise ValueError("JSON pointer must be empty or start with '/'")
        if any(char == "~" and index + 1 == len(value) for index, char in enumerate(value)):
            raise ValueError("JSON pointer has an incomplete escape")
        for index, char in enumerate(value[:-1]):
            if char == "~" and value[index + 1] not in "01":
                raise ValueError("JSON pointer escape must be ~0 or ~1")
        return value


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
    JsonPointerLocator | RecordIndexLocator | ByteRangeLocator,
    Field(discriminator="kind"),
]


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
) -> None:
    """Fail closed unless locator identity agrees with nominal raw evidence."""

    from .locator_validation import validate_raw_locator_against_snapshot as validate

    validate(
        locator,
        verified_snapshot=verified_snapshot,
        source_id=source_id,
        raw_sha256=raw_sha256,
    )


RawObjectLocator = RawLocator

__all__ = [
    "ByteRangeLocator",
    "JsonPointerLocator",
    "RawLocation",
    "RawLocator",
    "RawObjectLocator",
    "RecordIndexLocator",
    "validate_raw_locator_against_snapshot",
]
