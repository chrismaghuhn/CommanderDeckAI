"""Normalize combo facts and card/commander relationships."""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal
from uuid import UUID

from commander_ai.data_pipeline.provenance.evidence import SourceEvidence, source_scoped_id
from commander_ai.domain.combos import Combo, ComboCard

ComboRole = Literal["required", "optional", "commander", "enabler", "result"]


@dataclass(frozen=True, slots=True)
class ComboCardInput:
    """One source-neutral card role in a combo fact."""

    oracle_id: str
    role: ComboRole
    quantity: int

    def __post_init__(self) -> None:
        if not isinstance(self.oracle_id, str) or not self.oracle_id.strip():
            raise ValueError("combo card oracle_id must be non-empty")


@dataclass(frozen=True, slots=True)
class ComboRecord:
    """Source-neutral combo values after DTO parsing and card resolution."""

    combo_id: str
    evidence: SourceEvidence
    cards: tuple[ComboCardInput, ...]
    requirements: tuple[str, ...]
    results: tuple[str, ...]
    steps: tuple[str, ...] = ()
    name: str | None = None
    source_status: str | None = None
    commander_compatible: bool | None = None
    commander_oracle_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.combo_id.strip():
            raise ValueError("combo_id must be non-empty")
        if self.name is not None and not self.name.strip():
            raise ValueError("combo name must be non-empty when supplied")
        if self.source_status is not None and not self.source_status.strip():
            raise ValueError("combo source_status must be non-empty when supplied")


@dataclass(frozen=True, slots=True)
class CommanderComboCompatibility:
    """Feature relationship from a commander identity to a combo."""

    schema_version: ClassVar[Literal["combo-commander-compatibility.v1"]] = (
        "combo-commander-compatibility.v1"
    )
    combo_id: str
    commander_oracle_id: str
    compatible: bool
    evidence: SourceEvidence

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "combo_id": self.combo_id,
            "commander_oracle_id": self.commander_oracle_id,
            "compatible": self.compatible,
            "raw_locator": self.evidence.raw_locator.exact_locator,
            "provenance": [item.model_dump(mode="json") for item in self.evidence.provenance],
        }


@dataclass(frozen=True, slots=True)
class ComboNormalization:
    """Curated combo facts or a retained quarantine decision."""

    combo: Combo | None
    cards: tuple[ComboCard, ...]
    commander_compatibility: tuple[CommanderComboCompatibility, ...]
    evidence: SourceEvidence
    source_status: str | None
    finding_codes: tuple[str, ...]
    status: Literal["CURATED", "QUARANTINED"]


def normalize_combo(record: ComboRecord) -> ComboNormalization:
    """Create combo feature facts without making them a legality authority."""

    findings: set[str] = set()
    scoped_combo_id = source_scoped_id("combo", record.evidence.source_id, record.combo_id)
    invalid_card = False
    aggregated: dict[tuple[str, ComboRole], int] = {}
    for card in record.cards:
        try:
            oracle_id = _canonical_uuid(card.oracle_id)
        except ValueError:
            invalid_card = True
            continue
        if type(card.quantity) is not int or card.quantity < 1:
            invalid_card = True
            continue
        key = (oracle_id, card.role)
        aggregated[key] = aggregated.get(key, 0) + card.quantity

    required_ids: list[str] = []
    optional_ids: list[str] = []
    cards: list[ComboCard] = []
    for (oracle_id, role), quantity in sorted(aggregated.items()):
        if role in {"required", "commander", "enabler"}:
            required_ids.append(oracle_id)
        elif role == "optional":
            optional_ids.append(oracle_id)
        try:
            cards.append(
                ComboCard(
                    combo_id=scoped_combo_id,
                    oracle_id=oracle_id,
                    role=role,
                    quantity=quantity,
                    provenance=record.evidence.provenance,
                )
            )
        except ValueError:
            invalid_card = True

    compatibility: list[CommanderComboCompatibility] = []
    if record.commander_compatible is False and record.commander_oracle_ids:
        findings.add("quality.combo_compatibility_conflict")
    elif record.commander_compatible is None and record.commander_oracle_ids:
        findings.add("quality.combo_compatibility_unresolved")
    elif record.commander_compatible is True:
        canonical_commander_ids: set[str] = set()
        for commander_id in record.commander_oracle_ids:
            try:
                canonical_commander_ids.add(_canonical_uuid(commander_id))
            except ValueError:
                findings.add("quality.combo_commander_id_invalid")
        for canonical_commander_id in sorted(canonical_commander_ids):
            compatibility.append(
                CommanderComboCompatibility(
                    combo_id=scoped_combo_id,
                    commander_oracle_id=canonical_commander_id,
                    compatible=True,
                    evidence=record.evidence,
                )
            )
    if record.commander_compatible and not record.commander_oracle_ids:
        findings.add("quality.combo_compatibility_unscoped")

    required = tuple(dict.fromkeys(required_ids))
    optional = tuple(dict.fromkeys(optional_ids))
    if not required:
        findings.add("quality.combo_required_cards_missing")
    if not record.requirements:
        findings.add("quality.combo_requirements_missing")
    if not record.results:
        findings.add("quality.combo_results_missing")
    if invalid_card:
        findings.add("quality.combo_card_invalid")

    blocking = {
        "quality.combo_required_cards_missing",
        "quality.combo_requirements_missing",
        "quality.combo_results_missing",
        "quality.combo_card_invalid",
        "quality.combo_commander_id_invalid",
    }
    if findings.intersection(blocking):
        return ComboNormalization(
            combo=None,
            cards=tuple(cards),
            commander_compatibility=tuple(compatibility),
            evidence=record.evidence,
            source_status=record.source_status,
            finding_codes=tuple(sorted(findings)),
            status="QUARANTINED",
        )

    try:
        combo = Combo(
            combo_id=scoped_combo_id,
            name=record.name,
            required_cards=required,
            optional_cards=optional,
            requirements=tuple(record.requirements),
            results=tuple(record.results),
            steps=tuple(record.steps),
            provenance=record.evidence.provenance,
        )
    except ValueError:
        findings.add("quality.combo_contract_invalid")
        return ComboNormalization(
            combo=None,
            cards=tuple(cards),
            commander_compatibility=tuple(compatibility),
            evidence=record.evidence,
            source_status=record.source_status,
            finding_codes=tuple(sorted(findings)),
            status="QUARANTINED",
        )
    return ComboNormalization(
        combo=combo,
        cards=tuple(cards),
        commander_compatibility=tuple(compatibility),
        evidence=record.evidence,
        source_status=record.source_status,
        finding_codes=tuple(sorted(findings)),
        status="CURATED",
    )


def _canonical_uuid(value: str) -> str:
    try:
        return str(UUID(value))
    except (AttributeError, TypeError, ValueError) as error:
        raise ValueError("combo oracle_id must be a valid UUID") from error


__all__ = [
    "ComboCardInput",
    "ComboNormalization",
    "ComboRecord",
    "CommanderComboCompatibility",
    "normalize_combo",
]
