"""Immutable, exact locators into finalized raw source objects."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, field_validator

from commander_ai.domain.provenance import DomainModel, validate_portable_relative_path


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

    source_snapshot_id: str = Field(min_length=1)
    raw_object_id: str = Field(min_length=1)
    raw_object_path: str = Field(min_length=1)
    location: RawLocation
    archive_member: str | None = Field(default=None, min_length=1)

    @field_validator("raw_object_path")
    @classmethod
    def validate_raw_object_path(cls, value: str) -> str:
        return validate_portable_relative_path(value)

    @property
    def exact_locator(self) -> str:
        if isinstance(self.location, JsonPointerLocator):
            return f"json-pointer:{self.location.pointer}"
        if isinstance(self.location, RecordIndexLocator):
            return f"record-index:{self.location.index}"
        return f"byte-range:{self.location.start}-{self.location.end}"


RawObjectLocator = RawLocator

__all__ = [
    "ByteRangeLocator",
    "JsonPointerLocator",
    "RawLocation",
    "RawLocator",
    "RawObjectLocator",
    "RecordIndexLocator",
]
