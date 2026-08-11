"""MTGJSON-owned bulk-file settings built on the shared source policy contract."""

from __future__ import annotations

import re
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.config.source_settings import SourceSettings


class MTGJSONProduct(StrEnum):
    """Documented MTGJSON bulk products admitted by Task 6."""

    ALL_PRINTINGS = "AllPrintings"
    ALL_DECK_FILES = "AllDeckFiles"


_SUFFIX = re.compile(r"^\.[A-Za-z0-9]+(?:\.[A-Za-z0-9]+)*$")


class MTGJSONSettings(BaseModel):
    """Source-specific URL, product, archive, and attribution configuration."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SourceSettings
    products: tuple[MTGJSONProduct, ...]
    archive_extension: str = Field(default=".json.zip", min_length=2)
    checksum_suffix: str | None = Field(default=".sha256", min_length=2)
    checksum_max_bytes: int = Field(default=4096, ge=1, le=1_000_000)
    adapter_version: str = Field(default="mtgjson-v1", min_length=1)

    @field_validator("products", mode="before")
    @classmethod
    def normalize_products(cls, value: object) -> object:
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list, set, frozenset)):
            raise ValueError("MTGJSON products must be a sequence")
        normalized = tuple(MTGJSONProduct(item) for item in value)
        if not normalized:
            raise ValueError("at least one MTGJSON product is required")
        if len(normalized) != len(set(normalized)):
            raise ValueError("MTGJSON products must be unique")
        return normalized

    @field_validator("archive_extension", "checksum_suffix")
    @classmethod
    def validate_suffix(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _SUFFIX.fullmatch(value) is None:
            raise ValueError("MTGJSON file suffix must be a portable dotted suffix")
        return value

    @model_validator(mode="after")
    def validate_source_ownership(self) -> MTGJSONSettings:
        if self.source.source_id != "mtgjson":
            raise ValueError("MTGJSON settings require source_id mtgjson")
        if not self.source.endpoints:
            raise ValueError("MTGJSON settings require a configured bulk endpoint")
        if self.checksum_max_bytes > self.source.max_download_bytes:
            raise ValueError("MTGJSON checksum limit cannot exceed the general download limit")
        return self

    @classmethod
    def from_source_settings(
        cls,
        source: SourceSettings,
        *,
        adapter_version: str = "mtgjson-v1",
    ) -> MTGJSONSettings:
        """Build the adapter view without moving settings into module globals."""

        filters = dict(source.filters)
        allowed_filters = {
            "archive_extension",
            "checksum_suffix",
            "checksum_max_bytes",
            "files",
        }
        unknown_filters = set(filters) - allowed_filters
        if unknown_filters:
            raise ValueError("unknown MTGJSON filter fields")
        if source.bulk_type is not None:
            raise ValueError("MTGJSON bulk_type must be represented by the files filter")
        configured_products = _configured_products(filters.get("files"))
        source_products = _configured_products(source.files) if source.files else None
        if (
            source_products is not None
            and configured_products is not None
            and set(source_products) != set(configured_products)
        ):
            raise ValueError("conflicting MTGJSON product filters")
        products = source_products or configured_products or tuple(MTGJSONProduct)
        return cls(
            source=source,
            products=products,
            archive_extension=filters.get("archive_extension", ".json.zip"),
            checksum_suffix=filters.get("checksum_suffix", ".sha256"),
            checksum_max_bytes=filters.get("checksum_max_bytes", 4096),
            adapter_version=adapter_version,
        )

    def archive_filename(self, product: MTGJSONProduct | str) -> str:
        normalized = self._require_product(product)
        return f"{normalized.value}{self.archive_extension}"

    def archive_url(self, product: MTGJSONProduct | str) -> str:
        return f"{self.source.endpoints[0].rstrip('/')}/{self.archive_filename(product)}"

    def checksum_url(self, product: MTGJSONProduct | str) -> str | None:
        if self.checksum_suffix is None:
            return None
        return f"{self.archive_url(product)}{self.checksum_suffix}"

    def _require_product(self, product: MTGJSONProduct | str) -> MTGJSONProduct:
        try:
            normalized = MTGJSONProduct(product)
        except ValueError:
            raise ValueError("unsupported MTGJSON product") from None
        if normalized not in self.products:
            raise ValueError("MTGJSON product is not enabled by source configuration")
        return normalized


def _configured_products(value: object) -> tuple[MTGJSONProduct, ...] | None:
    if value is None:
        return None
    if isinstance(value, str):
        value = (value,)
    if not isinstance(value, (tuple, list, set, frozenset)):
        raise ValueError("MTGJSON product filters must be a sequence")
    products = tuple(MTGJSONProduct(str(item)) for item in value)
    if not products:
        raise ValueError("at least one MTGJSON product is required")
    if len(products) != len(set(products)):
        raise ValueError("MTGJSON products must be unique")
    return products


__all__ = ["MTGJSONProduct", "MTGJSONSettings"]
