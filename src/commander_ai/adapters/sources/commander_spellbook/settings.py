"""Commander Spellbook settings derived from the reviewed source registry."""

from __future__ import annotations

from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.config.source_settings import SourceSettings

SpellbookContract = Literal["cards", "variants"]
DOCUMENTED_CONTRACTS: tuple[SpellbookContract, ...] = ("cards", "variants")


class CommanderSpellbookSettings(BaseModel):
    """Source-owned API contract and limits for the approved read adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SourceSettings
    contracts: tuple[SpellbookContract, ...] = Field(min_length=1)
    api_path: str = Field(default="/api", min_length=1)
    adapter_version: str = Field(default="commander-spellbook-v1", min_length=1)

    @field_validator("contracts", mode="before")
    @classmethod
    def normalize_contracts(cls, value: object) -> object:
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list, set, frozenset)):
            raise ValueError("Commander Spellbook contracts must be a sequence")
        contracts = tuple(str(item) for item in value)
        if not contracts or len(contracts) != len(set(contracts)):
            raise ValueError("Commander Spellbook contracts must be non-empty and unique")
        if any(item not in DOCUMENTED_CONTRACTS for item in contracts):
            raise ValueError("Commander Spellbook contracts must use documented read contracts")
        return contracts

    @field_validator("api_path")
    @classmethod
    def normalize_api_path(cls, value: str) -> str:
        normalized = "/" + value.strip("/")
        if normalized == "/" or "?" in normalized or "#" in normalized:
            raise ValueError("Commander Spellbook API path is invalid")
        return normalized

    @model_validator(mode="after")
    def validate_source_ownership(self) -> CommanderSpellbookSettings:
        if self.source.source_id != "commander_spellbook":
            raise ValueError("Commander Spellbook settings require source_id commander_spellbook")
        if not self.source.endpoints:
            raise ValueError("Commander Spellbook settings require a configured endpoint")
        return self

    @classmethod
    def from_source_settings(
        cls,
        source: SourceSettings,
        *,
        adapter_version: str = "commander-spellbook-v1",
    ) -> CommanderSpellbookSettings:
        """Create the adapter view without copying secrets into adapter state."""

        filters = dict(source.filters)
        unknown_filters = set(filters) - {"documented_read_contracts"}
        if unknown_filters:
            raise ValueError("unknown Commander Spellbook filter fields")
        if source.files or source.bulk_type is not None:
            raise ValueError("Commander Spellbook uses documented API contracts, not bulk files")
        if source.api_key_env is not None or source.credential_env_vars:
            raise ValueError("Commander Spellbook does not document API credentials")
        configured = filters.get("documented_read_contracts", DOCUMENTED_CONTRACTS)
        return cls(
            source=source,
            contracts=configured,
            api_path="/api",
            adapter_version=adapter_version,
        )

    def endpoint(self, contract: SpellbookContract | str) -> str:
        """Return a configured, allowlisted URL for one documented contract."""

        if contract not in self.contracts:
            raise ValueError("Commander Spellbook contract is not enabled")
        if contract not in DOCUMENTED_CONTRACTS:
            raise ValueError("Commander Spellbook contract is not documented")
        base = self.source.endpoints[0]
        parsed = urlsplit(base)
        path = parsed.path.rstrip("/")
        api_path = self.api_path.rstrip("/")
        if path.endswith(api_path):
            combined_path = f"{path}/{contract}/"
        else:
            combined_path = f"{path}{api_path}/{contract}/"
        return urlunsplit((parsed.scheme, parsed.netloc, combined_path, "", ""))

    @property
    def max_pages(self) -> int:
        return self.source.max_pages

    @property
    def max_response_bytes(self) -> int:
        return self.source.max_download_bytes


__all__ = ["DOCUMENTED_CONTRACTS", "CommanderSpellbookSettings", "SpellbookContract"]
