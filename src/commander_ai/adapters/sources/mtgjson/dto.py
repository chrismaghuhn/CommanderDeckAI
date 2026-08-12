"""Permissive source DTOs for documented MTGJSON card and product fields."""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import ConfigDict, Field

from commander_ai.domain.provenance import DomainModel, FrozenDict


class MTGJSONModel(DomainModel):
    """Immutable DTO projection that retains unknown source fields."""

    model_config = ConfigDict(extra="allow", frozen=True, populate_by_name=True)

    def model_post_init(self, __context: object) -> None:
        super().model_post_init(__context)
        if self.model_extra:
            object.__setattr__(
                self,
                "__pydantic_extra__",
                FrozenDict(
                    {str(key): _freeze_extra(value) for key, value in self.model_extra.items()}
                ),
            )


def _freeze_extra(value: object) -> object:
    if isinstance(value, Mapping):
        return FrozenDict({str(key): _freeze_extra(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_extra(item) for item in value)
    if isinstance(value, (set, frozenset)):
        return frozenset(_freeze_extra(item) for item in value)
    return value


class MTGJSONCardFace(MTGJSONModel):
    uuid: str | None = None
    name: str | None = None
    face_name: str | None = Field(default=None, alias="faceName")
    side: str | None = None
    mana_cost: str | None = Field(default=None, alias="manaCost")
    mana_value: int | float | None = Field(default=None, alias="manaValue")
    face_mana_value: int | float | None = Field(default=None, alias="faceManaValue")
    color_identity: tuple[str, ...] | None = Field(default=None, alias="colorIdentity")
    colors: tuple[str, ...] | None = None
    type_line: str | None = Field(default=None, alias="type")
    rules_text: str | None = Field(default=None, alias="text")
    types: tuple[str, ...] | None = None
    subtypes: tuple[str, ...] | None = None
    oracle_text: str | None = Field(default=None, alias="oracleText")
    keywords: tuple[str, ...] | None = None
    identifiers: Mapping[str, object] | None = None
    card_parts: tuple[str, ...] | None = Field(default=None, alias="cardParts")
    other_face_ids: tuple[str, ...] | None = Field(default=None, alias="otherFaceIds")
    power: str | None = None
    toughness: str | None = None
    loyalty: str | None = None


class MTGJSONCard(MTGJSONModel):
    uuid: str | None = None
    name: str | None = None
    set_code: str | None = Field(default=None, alias="setCode")
    set_name: str | None = Field(default=None, alias="setName")
    number: str | None = None
    layout: str | None = None
    mana_cost: str | None = Field(default=None, alias="manaCost")
    mana_value: int | float | None = Field(default=None, alias="manaValue")
    face_mana_value: int | float | None = Field(default=None, alias="faceManaValue")
    color_identity: tuple[str, ...] | None = Field(default=None, alias="colorIdentity")
    colors: tuple[str, ...] | None = None
    type_line: str | None = Field(default=None, alias="type")
    rules_text: str | None = Field(default=None, alias="text")
    types: tuple[str, ...] | None = None
    subtypes: tuple[str, ...] | None = None
    supertypes: tuple[str, ...] | None = None
    oracle_text: str | None = Field(default=None, alias="oracleText")
    keywords: tuple[str, ...] | None = None
    legalities: Mapping[str, object] | None = None
    identifiers: Mapping[str, object] | None = None
    card_parts: tuple[str, ...] | None = Field(default=None, alias="cardParts")
    face_name: str | None = Field(default=None, alias="faceName")
    side: str | None = None
    other_face_ids: tuple[str, ...] | None = Field(default=None, alias="otherFaceIds")
    related_cards: object | None = Field(default=None, alias="relatedCards")
    printings: tuple[str, ...] | None = None
    variations: tuple[str, ...] | None = None
    leadership_skills: Mapping[str, object] | None = Field(default=None, alias="leadershipSkills")
    source_products: object | None = Field(default=None, alias="sourceProducts")


class MTGJSONSet(MTGJSONModel):
    code: str | None = None
    name: str | None = None
    type: str | None = None
    release_date: str | None = Field(default=None, alias="releaseDate")
    identifiers: Mapping[str, object] | None = None
    cards: object | None = None
    tokens: object | None = None
    sealed_product: object | None = Field(default=None, alias="sealedProduct")
    source_products: object | None = Field(default=None, alias="sourceProducts")
    decks: object | None = None


class MTGJSONDeckProduct(MTGJSONModel):
    name: str | None = None
    file_name: str | None = Field(default=None, alias="fileName")
    code: str | None = None
    release_date: str | None = Field(default=None, alias="releaseDate")
    type: str | None = None
    identifiers: Mapping[str, object] | None = None
    commander: object | None = None
    partner: object | None = None
    background: object | None = None
    main_board: object | None = Field(default=None, alias="mainBoard")
    side_board: object | None = Field(default=None, alias="sideBoard")
    sealed_product_uuids: tuple[str, ...] | None = Field(default=None, alias="sealedProductUuids")
    tokens: object | None = None
    deck: object | None = None
    cards: object | None = None
    source_products: object | None = Field(default=None, alias="sourceProducts")
    sealed_product_contents: object | None = Field(default=None, alias="sealedProductContents")


class MTGJSONFile(MTGJSONModel):
    meta: Mapping[str, object] | None = None
    data: object | None = None


__all__ = [
    "MTGJSONCard",
    "MTGJSONCardFace",
    "MTGJSONDeckProduct",
    "MTGJSONFile",
    "MTGJSONModel",
    "MTGJSONSet",
]
