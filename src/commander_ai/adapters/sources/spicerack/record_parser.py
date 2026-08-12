"""Spicerack source-value projection and PII minimization."""

from __future__ import annotations

from collections.abc import Mapping

from .json_support import json_safe_source_value


def sanitize_source_values(record_type: str, value: Mapping[object, object]) -> dict[str, object]:
    """Keep source fields needed for staging while excluding direct contact data."""

    def clean(item: object, *, remove_player_names: bool = False) -> object:
        if isinstance(item, Mapping):
            result: dict[str, object] = {}
            for raw_key, raw_value in item.items():
                name = str(raw_key)
                normalized = name.casefold().replace("-", "_")
                if normalized in {"email", "discord", "contact", "account", "handle"}:
                    continue
                if (
                    remove_player_names
                    or record_type in {"player", "standing", "decklist", "result"}
                ) and normalized in {
                    "name",
                    "display_name",
                    "player_name",
                }:
                    continue
                result[name] = clean(
                    raw_value,
                    remove_player_names=remove_player_names
                    or (record_type == "event" and normalized == "standings"),
                )
            return result
        if isinstance(item, (list, tuple)):
            return [clean(child, remove_player_names=remove_player_names) for child in item]
        return item

    sanitized = json_safe_source_value(clean(value))
    if not isinstance(sanitized, dict):
        raise TypeError("Spicerack source values must remain an object")
    return sanitized


__all__ = ["sanitize_source_values"]
