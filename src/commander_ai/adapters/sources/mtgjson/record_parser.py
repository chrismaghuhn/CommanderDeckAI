"""Expansion of decoded MTGJSON members into source logical records."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from commander_ai.data_pipeline.staging.raw_locators import RawLocator

from .dto import MTGJSONCard, MTGJSONCardFace, MTGJSONDeckProduct, MTGJSONSet
from .models import (
    MTGJSONFinding,
    MTGJSONParsedRecord,
    finding_record,
    record_with_findings,
)
from .settings import MTGJSONProduct


class MTGJSONMemberParser:
    """Parse one already-decoded archive member without changing raw values."""

    def __init__(self, locator_factory: Callable[[str], RawLocator]) -> None:
        self._locator = locator_factory

    def parse(self, payload: object, product: MTGJSONProduct) -> tuple[MTGJSONParsedRecord, ...]:
        if product is MTGJSONProduct.ALL_PRINTINGS:
            return self._parse_printings(payload)
        return self._parse_decks(payload)

    def _parse_printings(self, payload: object) -> tuple[MTGJSONParsedRecord, ...]:
        if not isinstance(payload, Mapping):
            return (
                finding_record(
                    "file",
                    self._locator(""),
                    payload,
                    code="parse.record_not_object",
                    message="file root is not an object",
                ),
            )
        data = payload.get("data")
        if not isinstance(data, Mapping):
            return (
                finding_record(
                    "file",
                    self._locator("/data"),
                    data,
                    code="parse.missing_or_invalid_data",
                    message="AllPrintings data must be an object",
                ),
            )
        records: list[MTGJSONParsedRecord] = []
        for set_code, set_value in data.items():
            set_pointer = f"/data/{_escape_pointer(str(set_code))}"
            set_locator = self._locator(set_pointer)
            if not isinstance(set_value, Mapping):
                records.append(
                    finding_record(
                        "set",
                        set_locator,
                        set_value,
                        code="parse.record_not_object",
                        message="set record is not an object",
                    )
                )
                continue
            set_findings = _required_findings(set_value, ("code", "name"), set_locator)
            try:
                set_dto = MTGJSONSet.model_validate(set_value)
            except ValueError:
                set_dto = None
                set_findings.append(_shape_finding("set", set_locator))
            records.append(
                record_with_findings("set", set_locator, set_value, set_dto, set_findings)
            )
            cards = set_value.get("cards")
            if not isinstance(cards, list):
                records.append(
                    finding_record(
                        "set_cards",
                        self._locator(f"{set_pointer}/cards"),
                        cards,
                        code="parse.missing_or_invalid_data",
                        message="set cards must be an array",
                    )
                )
                continue
            for index, card_value in enumerate(cards):
                pointer = f"{set_pointer}/cards/{index}"
                records.extend(self._parse_card(card_value, pointer))
        return tuple(records)

    def _parse_card(self, value: object, pointer: str) -> tuple[MTGJSONParsedRecord, ...]:
        locator = self._locator(pointer)
        if not isinstance(value, Mapping):
            return (
                finding_record(
                    "card",
                    locator,
                    value,
                    code="parse.record_not_object",
                    message="card record is not an object",
                ),
            )
        findings = _required_findings(value, ("uuid", "name"), locator)
        try:
            dto = MTGJSONCard.model_validate(value)
        except ValueError:
            dto = None
            findings.append(_shape_finding("card", locator))
        records = [record_with_findings("card", locator, value, dto, findings)]
        if "faceName" in value or "side" in value:
            face_findings = _required_findings(value, ("name",), locator)
            try:
                face_dto = MTGJSONCardFace.model_validate(value)
            except ValueError:
                face_dto = None
                face_findings.append(_shape_finding("card face", locator))
            records.append(
                record_with_findings("card_face", locator, value, face_dto, face_findings)
            )
        return tuple(records)

    def _parse_decks(self, payload: object) -> tuple[MTGJSONParsedRecord, ...]:
        if isinstance(payload, list):
            return tuple(
                self._parse_deck_record(value, f"/{index}") for index, value in enumerate(payload)
            )
        if not isinstance(payload, Mapping):
            return (
                finding_record(
                    "deck_product",
                    self._locator(""),
                    payload,
                    code="parse.record_not_object",
                    message="deck member root is not an object",
                ),
            )
        data = payload.get("data")
        if isinstance(data, Mapping) and "meta" in payload:
            return tuple(
                self._parse_deck_record(value, f"/data/{_escape_pointer(str(key))}")
                for key, value in data.items()
            )
        return (self._parse_deck_record(payload, ""),)

    def _parse_deck_record(self, value: object, pointer: str) -> MTGJSONParsedRecord:
        locator = self._locator(pointer)
        if not isinstance(value, Mapping):
            return finding_record(
                "deck_product",
                locator,
                value,
                code="parse.record_not_object",
                message="deck product record is not an object",
            )
        findings = _required_findings(
            value,
            ("code", "name", "mainBoard", "sideBoard", "type"),
            locator,
        )
        try:
            dto = MTGJSONDeckProduct.model_validate(value)
        except ValueError:
            dto = None
            findings.append(_shape_finding("deck product", locator))
        return record_with_findings("deck_product", locator, value, dto, findings)


def _required_findings(
    value: Mapping[str, object], fields: tuple[str, ...], locator: RawLocator
) -> list[MTGJSONFinding]:
    return [
        MTGJSONFinding(
            code="parse.missing_required_field",
            message=f"source record is missing {field}",
            raw_locator=locator,
        )
        for field in fields
        if field not in value or value[field] is None
    ]


def _shape_finding(record_name: str, locator: RawLocator) -> MTGJSONFinding:
    return MTGJSONFinding(
        code="parse.invalid_record_shape",
        message=f"{record_name} fields do not match the source DTO shape",
        raw_locator=locator,
    )


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


__all__ = ["MTGJSONMemberParser"]
