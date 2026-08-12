"""Expansion of decoded MTGJSON members into source logical records."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Callable, Mapping

from commander_ai.data_pipeline.staging.raw_locators import (
    JsonObjectEntryLocator,
    RawLocation,
    RawLocator,
)

from .dto import MTGJSONCard, MTGJSONCardFace, MTGJSONDeckProduct, MTGJSONSet
from .models import (
    MTGJSONFinding,
    MTGJSONParsedRecord,
    finding_record,
    record_with_findings,
)
from .scalar_safety import MalformedJSONScalar, find_malformed_scalars, sanitize_json_scalars
from .settings import MTGJSONProduct

RecordLocation = str | JsonObjectEntryLocator


class MTGJSONMemberParser:
    """Parse one already-decoded archive member without changing raw values."""

    def __init__(self, locator_factory: Callable[[str | RawLocation], RawLocator]) -> None:
        self._locator = locator_factory

    def parse(self, payload: object, product: MTGJSONProduct) -> tuple[MTGJSONParsedRecord, ...]:
        payload = sanitize_json_scalars(payload)
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
        for entry_index, (set_code, set_value) in enumerate(data.items()):
            set_location = self._record_location("/data", set_code, entry_index)
            set_locator = self._locator(set_location)
            source_values = _record_source_values(set_code, set_value)
            identity_finding = _malformed_identity_finding(
                set_code,
                set_locator,
                parent_pointer="/data",
                entry_index=entry_index,
            )
            if not isinstance(set_value, Mapping):
                findings = [
                    MTGJSONFinding(
                        code="parse.record_not_object",
                        message="set record is not an object",
                        raw_locator=set_locator,
                    )
                ]
                if identity_finding is not None:
                    findings.append(identity_finding)
                records.append(
                    record_with_findings("set", set_locator, source_values, None, findings)
                )
                continue
            set_findings = _required_findings(set_value, ("code", "name"), set_locator)
            scalar_finding = _malformed_scalar_finding(set_value, set_locator)
            if scalar_finding is not None:
                set_findings.append(scalar_finding)
            if identity_finding is not None:
                set_findings.append(identity_finding)
            if scalar_finding is not None or identity_finding is not None:
                set_dto = None
            else:
                try:
                    set_dto = MTGJSONSet.model_validate(set_value)
                except ValueError:
                    set_dto = None
                    set_findings.append(_shape_finding("set", set_locator))
            records.append(
                record_with_findings("set", set_locator, source_values, set_dto, set_findings)
            )
            cards = set_value.get("cards")
            cards_location = _append_location(set_location, "/cards")
            if not isinstance(cards, list):
                records.append(
                    finding_record(
                        "set_cards",
                        self._locator(cards_location),
                        cards,
                        code="parse.missing_or_invalid_data",
                        message="set cards must be an array",
                    )
                )
                continue
            for index, card_value in enumerate(cards):
                card_location = _append_location(cards_location, f"/{index}")
                records.extend(self._parse_card(card_value, card_location))
        return tuple(records)

    def _parse_card(
        self, value: object, location: RecordLocation
    ) -> tuple[MTGJSONParsedRecord, ...]:
        locator = self._locator(location)
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
        scalar_finding = _malformed_scalar_finding(value, locator)
        if scalar_finding is not None:
            findings.append(scalar_finding)
        if scalar_finding is not None:
            dto = None
        else:
            try:
                dto = MTGJSONCard.model_validate(value)
            except ValueError:
                dto = None
                findings.append(_shape_finding("card", locator))
        records = [record_with_findings("card", locator, value, dto, findings)]
        if "faceName" in value or "side" in value:
            face_location = _append_location(
                location,
                "/faceName" if "faceName" in value else "/side",
            )
            face_locator = self._locator(face_location)
            face_findings = _required_findings(value, ("name",), face_locator)
            face_scalar_finding = _malformed_scalar_finding(value, face_locator)
            if face_scalar_finding is not None:
                face_findings.append(face_scalar_finding)
            if face_scalar_finding is not None:
                face_dto = None
            else:
                try:
                    face_dto = MTGJSONCardFace.model_validate(value)
                except ValueError:
                    face_dto = None
                    face_findings.append(_shape_finding("card face", face_locator))
            records.append(
                record_with_findings("card_face", face_locator, value, face_dto, face_findings)
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
                self._parse_deck_record(
                    value,
                    self._record_location("/data", key, entry_index),
                    identity_key=key,
                    identity_parent_pointer="/data",
                    identity_entry_index=entry_index,
                )
                for entry_index, (key, value) in enumerate(data.items())
            )
        return (self._parse_deck_record(payload, ""),)

    def _parse_deck_record(
        self,
        value: object,
        location: RecordLocation,
        *,
        identity_key: object | None = None,
        identity_parent_pointer: str = "/data",
        identity_entry_index: int = 0,
    ) -> MTGJSONParsedRecord:
        locator = self._locator(location)
        source_values = _record_source_values(identity_key, value)
        identity_finding = _malformed_identity_finding(
            identity_key,
            locator,
            parent_pointer=identity_parent_pointer,
            entry_index=identity_entry_index,
        )
        if not isinstance(value, Mapping):
            findings = [
                MTGJSONFinding(
                    code="parse.record_not_object",
                    message="deck product record is not an object",
                    raw_locator=locator,
                )
            ]
            if identity_finding is not None:
                findings.append(identity_finding)
            return record_with_findings("deck_product", locator, source_values, None, findings)
        findings = _required_findings(
            value,
            ("code", "name", "mainBoard", "sideBoard", "type"),
            locator,
        )
        scalar_finding = _malformed_scalar_finding(value, locator)
        if scalar_finding is not None:
            findings.append(scalar_finding)
        if identity_finding is not None:
            findings.append(identity_finding)
        if scalar_finding is not None or identity_finding is not None:
            dto = None
        else:
            try:
                dto = MTGJSONDeckProduct.model_validate(value)
            except ValueError:
                dto = None
                findings.append(_shape_finding("deck product", locator))
        return record_with_findings("deck_product", locator, source_values, dto, findings)

    def _record_location(
        self, parent_pointer: str, key: object, entry_index: int
    ) -> RecordLocation:
        if not isinstance(key, MalformedJSONScalar):
            return f"{parent_pointer}/{_escape_pointer(str(key))}"
        return JsonObjectEntryLocator(
            parent_pointer=parent_pointer,
            entry_index=entry_index,
            key_base64=base64.b64encode(key.raw_bytes).decode("ascii"),
            key_byte_length=len(key.raw_bytes),
            key_sha256=hashlib.sha256(key.raw_bytes).hexdigest(),
        )


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


def _malformed_scalar_finding(
    value: Mapping[str, object], locator: RawLocator
) -> MTGJSONFinding | None:
    malformed = find_malformed_scalars(value)
    if not malformed:
        return None
    locations = ", ".join(path for path, _scalar in malformed)
    return MTGJSONFinding(
        code="parse.malformed_scalar",
        message=f"source record contains malformed JSON scalar(s) at {locations}",
        raw_locator=locator,
    )


def _malformed_identity_finding(
    key: object | None,
    locator: RawLocator,
    *,
    parent_pointer: str,
    entry_index: int,
) -> MTGJSONFinding | None:
    if not isinstance(key, MalformedJSONScalar):
        return None
    digest = hashlib.sha256(key.raw_bytes).hexdigest()
    return MTGJSONFinding(
        code="parse.malformed_scalar",
        message=(
            "source record contains a malformed JSON object key at "
            f"{parent_pointer}/@entry/{entry_index}/key/{digest}"
        ),
        raw_locator=locator,
    )


def _record_source_values(key: object | None, value: object) -> object:
    if isinstance(key, MalformedJSONScalar):
        return {key: value}
    return value


def _append_location(location: RecordLocation, suffix: str) -> RecordLocation:
    if isinstance(location, str):
        return f"{location}{suffix}"
    return location.model_copy(update={"value_pointer": f"{location.value_pointer}{suffix}"})


def _escape_pointer(value: str) -> str:
    return value.replace("~", "~0").replace("/", "~1")


__all__ = ["MTGJSONMemberParser"]
