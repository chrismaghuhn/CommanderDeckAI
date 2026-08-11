"""Typed dataset-owned filters, split, and duplicate policies."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator

from .source_settings import normalize_source_id


class StrictDatasetModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class DatasetInputSettings(StrictDatasetModel):
    source_ids: tuple[str, ...] = Field(
        default_factory=tuple,
        validation_alias=AliasChoices("source_ids", "sources"),
    )
    require_approved_sources: bool = False
    require_complete_decklists: bool = False
    require_complete_pod_result: bool = False
    legal_decks_only: bool = False
    modes: tuple[str, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def normalize_values(self) -> DatasetInputSettings:
        object.__setattr__(
            self,
            "source_ids",
            tuple(dict.fromkeys(normalize_source_id(item) for item in self.source_ids)),
        )
        object.__setattr__(
            self,
            "modes",
            tuple(dict.fromkeys(item.strip().casefold() for item in self.modes if item.strip())),
        )
        return self

    @property
    def sources(self) -> tuple[str, ...]:
        return self.source_ids


class DatasetFilterSettings(StrictDatasetModel):
    source_ids: tuple[str, ...] = Field(default_factory=tuple)
    modes: tuple[str, ...] = Field(default_factory=tuple)
    legal_statuses: tuple[str, ...] = Field(default_factory=tuple)
    quality_statuses: tuple[str, ...] = Field(default_factory=tuple)
    observed_from: str | None = None
    observed_until: str | None = None

    @model_validator(mode="after")
    def normalize_values(self) -> DatasetFilterSettings:
        object.__setattr__(
            self,
            "source_ids",
            tuple(dict.fromkeys(normalize_source_id(item) for item in self.source_ids)),
        )
        for field_name in ("modes", "legal_statuses", "quality_statuses"):
            values = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                tuple(dict.fromkeys(item.strip().casefold() for item in values if item.strip())),
            )
        return self


class DatasetSplitSettings(StrictDatasetModel):
    strategy: str = Field(default="temporal_grouped", min_length=1)
    version: str = Field(default="split-policy-v1", min_length=1)
    group_keys: tuple[str, ...] = Field(default_factory=tuple)
    extra_segments: tuple[str, ...] = Field(default_factory=tuple)
    train_until: datetime | None = None
    validation_until: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_single_group_key(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = {str(key): item for key, item in value.items()}
        if "group_key" in data:
            group_key = data.pop("group_key")
            if "group_keys" in data and tuple(data["group_keys"]) != (group_key,):
                raise ValueError("group_key conflicts with group_keys")
            data["group_keys"] = (group_key,)
        return data

    @model_validator(mode="after")
    def normalize_values(self) -> DatasetSplitSettings:
        object.__setattr__(
            self,
            "strategy",
            self.strategy.strip().casefold().replace("-", "_"),
        )
        object.__setattr__(
            self,
            "group_keys",
            tuple(dict.fromkeys(item.strip() for item in self.group_keys if item.strip())),
        )
        object.__setattr__(
            self,
            "extra_segments",
            tuple(dict.fromkeys(item.strip() for item in self.extra_segments if item.strip())),
        )
        if (self.train_until is None) != (self.validation_until is None):
            raise ValueError("train_until and validation_until must be supplied together")
        if (
            self.train_until is not None
            and self.validation_until is not None
            and self.validation_until <= self.train_until
        ):
            raise ValueError("validation_until must follow train_until")
        for field_name in ("train_until", "validation_until"):
            value = getattr(self, field_name)
            if value is not None and (value.tzinfo is None or value.utcoffset() is None):
                raise ValueError(f"{field_name} must include a timezone")
        return self


class NearDuplicateSettings(StrictDatasetModel):
    algorithm: str = Field(default="jaccard", min_length=1)
    version: str = Field(default="near-duplicate-v1", min_length=1)
    threshold: float = Field(default=0.92, ge=0, le=1)

    @model_validator(mode="after")
    def normalize_algorithm(self) -> NearDuplicateSettings:
        object.__setattr__(
            self,
            "algorithm",
            self.algorithm.strip().casefold().replace("-", "_"),
        )
        return self


class DatasetDeduplicationSettings(StrictDatasetModel):
    exact_fingerprint: bool = True
    group_revisions: bool = True
    near_duplicate: NearDuplicateSettings = Field(default_factory=NearDuplicateSettings)

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_threshold(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = {str(key): item for key, item in value.items()}
        threshold = data.pop("near_duplicate_jaccard_threshold", None)
        if threshold is not None:
            nested = data.get("near_duplicate")
            if nested is None:
                data["near_duplicate"] = {"threshold": threshold}
            elif isinstance(nested, Mapping):
                nested_data = dict(nested)
                if "threshold" in nested_data and nested_data["threshold"] != threshold:
                    raise ValueError("near_duplicate_jaccard_threshold conflicts with threshold")
                nested_data["threshold"] = threshold
                data["near_duplicate"] = nested_data
            else:
                raise ValueError("near_duplicate must be a mapping")
        return data

    @property
    def near_duplicate_algorithm(self) -> str:
        return self.near_duplicate.algorithm

    @property
    def near_duplicate_version(self) -> str:
        return self.near_duplicate.version

    @property
    def near_duplicate_threshold(self) -> float:
        return self.near_duplicate.threshold


class DatasetQualitySettings(StrictDatasetModel):
    fail_on_blocking_findings: bool = False
    emit_leakage_report: bool = False
    report_seat_distribution: bool = False
    report_missingness: bool = False


class DatasetPrivacySettings(StrictDatasetModel):
    player_identifiers: str | None = None
    use_player_as_model_feature: bool = False


class DatasetMaskingSettings(StrictDatasetModel):
    strategies: tuple[str, ...] = Field(default_factory=tuple)
    masks_per_deck: int = Field(default=0, ge=0, le=10_000)


class DatasetSettings(StrictDatasetModel):
    """Dataset policy that never absorbs runtime, source, experiment, or optimizer fields."""

    dataset_id: str = Field(min_length=1)
    schema_version: str = Field(default="dataset-config.v1", min_length=1)
    dataset_kind: Literal[
        "deck_completion",
        "tournament_outcomes",
        "card_cooccurrence",
        "combo",
    ] = "deck_completion"
    inputs: DatasetInputSettings = Field(default_factory=DatasetInputSettings)
    filters: DatasetFilterSettings = Field(default_factory=DatasetFilterSettings)
    split_policy: DatasetSplitSettings = Field(
        default_factory=DatasetSplitSettings,
        validation_alias=AliasChoices("split_policy", "splits"),
    )
    deduplication: DatasetDeduplicationSettings = Field(
        default_factory=DatasetDeduplicationSettings
    )
    inclusions: tuple[str, ...] = Field(default_factory=tuple)
    exclusions: tuple[str, ...] = Field(default_factory=tuple)
    masking: DatasetMaskingSettings = Field(default_factory=DatasetMaskingSettings)
    quality: DatasetQualitySettings = Field(default_factory=DatasetQualitySettings)
    privacy: DatasetPrivacySettings = Field(default_factory=DatasetPrivacySettings)
    seed: int | None = Field(default=None, ge=0)

    @model_validator(mode="before")
    @classmethod
    def accept_near_duplicate_policy_name(cls, value: object) -> object:
        if not isinstance(value, Mapping):
            return value
        data = {str(key): item for key, item in value.items()}
        if "near_duplicate_policy" in data:
            if "deduplication" in data:
                raise ValueError("near_duplicate_policy conflicts with deduplication")
            data["deduplication"] = {"near_duplicate": data.pop("near_duplicate_policy")}
        return data

    @model_validator(mode="after")
    def reject_conflicting_ownership(self) -> DatasetSettings:
        if (
            self.inputs.source_ids
            and self.filters.source_ids
            and self.inputs.source_ids != self.filters.source_ids
        ):
            raise ValueError("inputs.sources conflicts with filters.source_ids")
        if self.inputs.modes and self.filters.modes and self.inputs.modes != self.filters.modes:
            raise ValueError("inputs.modes conflicts with filters.modes")
        return self

    @property
    def source_ids(self) -> tuple[str, ...]:
        return self.filters.source_ids or self.inputs.source_ids

    @property
    def near_duplicate_policy(self) -> NearDuplicateSettings:
        return self.deduplication.near_duplicate


DatasetConfig = DatasetSettings
