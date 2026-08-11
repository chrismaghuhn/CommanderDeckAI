"""Commander Spellbook settings derived from the reviewed source registry."""

from __future__ import annotations

import re
from typing import Literal, cast
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from commander_ai.config.source_settings import SourceSettings

SpellbookContract = Literal["cards", "variants"]
DOCUMENTED_CONTRACTS: tuple[SpellbookContract, ...] = ("cards", "variants")
DOCUMENTED_SOURCE_ID = "commander_spellbook"
DOCUMENTED_BASE_ENDPOINT = "https://backend.commanderspellbook.com"
DOCUMENTED_HOST = "backend.commanderspellbook.com"
DOCUMENTED_API_PATH: Literal["/api"] = "/api"
_RAW_OBJECT_ID = re.compile(r"^(cards|variants)-page-([1-9][0-9]*)\.json$")


def documented_endpoint(contract: SpellbookContract | str) -> str:
    if contract not in DOCUMENTED_CONTRACTS:
        raise ValueError("Commander Spellbook contract is not documented")
    return f"{DOCUMENTED_BASE_ENDPOINT}{DOCUMENTED_API_PATH}/{contract}/"


def raw_object_identity(raw_object_id: str) -> tuple[SpellbookContract, int]:
    if not isinstance(raw_object_id, str):
        raise ValueError("Commander Spellbook raw object ID must be a string")
    match = _RAW_OBJECT_ID.fullmatch(raw_object_id)
    if match is None:
        raise ValueError("Commander Spellbook raw object ID is not a documented page object")
    contract = match.group(1)
    if contract not in DOCUMENTED_CONTRACTS:
        raise ValueError("Commander Spellbook raw object ID has an unsupported product")
    return contract, int(match.group(2))


class CommanderSpellbookSettings(BaseModel):
    """Source-owned API contract and limits for the approved read adapter."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    source: SourceSettings
    contracts: tuple[SpellbookContract, ...] = Field(min_length=1)
    api_path: Literal["/api"] = DOCUMENTED_API_PATH
    adapter_version: str = Field(default="commander-spellbook-v1", min_length=1)

    @field_validator("contracts", mode="before")
    @classmethod
    def normalize_contracts(cls, value: object) -> object:
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list, set, frozenset)):
            raise ValueError("Commander Spellbook contracts must be a sequence")
        if any(not isinstance(item, str) for item in value):
            raise ValueError("Commander Spellbook contracts must contain strings")
        contracts = tuple(item.strip() for item in value)
        if not contracts or len(contracts) != len(set(contracts)):
            raise ValueError("Commander Spellbook contracts must be non-empty and unique")
        if any(item not in DOCUMENTED_CONTRACTS for item in contracts):
            raise ValueError("Commander Spellbook contracts must use documented read contracts")
        return contracts

    @model_validator(mode="after")
    def validate_source_ownership(self) -> CommanderSpellbookSettings:
        if self.source.source_id != DOCUMENTED_SOURCE_ID:
            raise ValueError("Commander Spellbook settings require source_id commander_spellbook")
        if self.source.endpoints != (DOCUMENTED_BASE_ENDPOINT,):
            raise ValueError("Commander Spellbook settings require the documented base endpoint")
        if self.source.host_allowlist != (DOCUMENTED_HOST,):
            raise ValueError("Commander Spellbook settings require the documented host allowlist")
        if self.source.files or self.source.bulk_type is not None:
            raise ValueError("Commander Spellbook uses documented API contracts, not bulk files")
        if self.source.api_key_env is not None or self.source.credential_env_vars:
            raise ValueError("Commander Spellbook does not document API credentials")
        unknown_features = set(self.source.features) - {"combos", "variants"}
        if unknown_features:
            raise ValueError("unknown Commander Spellbook feature fields")
        unknown_filters = set(self.source.filters) - {"documented_read_contracts"}
        if unknown_filters:
            raise ValueError("unknown Commander Spellbook filter fields")
        configured_contracts = self.source.filters.get("documented_read_contracts")
        if configured_contracts is not None:
            expected = self._normalize_contracts(configured_contracts)
            if set(expected) != set(self.contracts):
                raise ValueError("conflicting Commander Spellbook contract settings")
        return self

    @staticmethod
    def _normalize_contracts(value: object) -> tuple[SpellbookContract, ...]:
        if isinstance(value, str):
            value = (value,)
        if not isinstance(value, (tuple, list, set, frozenset)):
            raise ValueError("Commander Spellbook contracts must be a sequence")
        if any(not isinstance(item, str) for item in value):
            raise ValueError("Commander Spellbook contracts must contain strings")
        contracts = tuple(item.strip() for item in value)
        if not contracts or len(contracts) != len(set(contracts)):
            raise ValueError("Commander Spellbook contracts must be non-empty and unique")
        if any(item not in DOCUMENTED_CONTRACTS for item in contracts):
            raise ValueError("Commander Spellbook contracts must use documented read contracts")
        return tuple(cast(SpellbookContract, item) for item in contracts)

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
            api_path=DOCUMENTED_API_PATH,
            adapter_version=adapter_version,
        )

    def endpoint(self, contract: SpellbookContract | str) -> str:
        """Return a configured, allowlisted URL for one documented contract."""

        if contract not in self.contracts:
            raise ValueError("Commander Spellbook contract is not enabled")
        if contract not in DOCUMENTED_CONTRACTS:
            raise ValueError("Commander Spellbook contract is not documented")
        return documented_endpoint(contract)

    def validate_pagination_link(self, contract: SpellbookContract, link: object) -> int:
        if not isinstance(link, str) or not link:
            raise ValueError("Commander Spellbook pagination link must be an absolute URL")
        parsed = urlsplit(link)
        expected = urlsplit(self.endpoint(contract))
        if (
            parsed.scheme != expected.scheme
            or parsed.netloc != expected.netloc
            or parsed.path != expected.path
            or parsed.username is not None
            or parsed.password is not None
            or parsed.fragment
        ):
            raise ValueError(
                "Commander Spellbook pagination link is outside the documented endpoint"
            )
        parameters = parse_qs(parsed.query, keep_blank_values=True)
        if set(parameters) != {"page"} or len(parameters["page"]) != 1:
            raise ValueError("Commander Spellbook pagination link must contain one page parameter")
        page_value = parameters["page"][0]
        if not page_value.isdecimal() or int(page_value) < 1:
            raise ValueError("Commander Spellbook pagination page is invalid")
        return int(page_value)

    @property
    def max_pages(self) -> int:
        return self.source.max_pages

    @property
    def max_response_bytes(self) -> int:
        return self.source.max_download_bytes


__all__ = [
    "DOCUMENTED_API_PATH",
    "DOCUMENTED_BASE_ENDPOINT",
    "DOCUMENTED_CONTRACTS",
    "DOCUMENTED_HOST",
    "DOCUMENTED_SOURCE_ID",
    "CommanderSpellbookSettings",
    "SpellbookContract",
    "documented_endpoint",
    "raw_object_identity",
]
