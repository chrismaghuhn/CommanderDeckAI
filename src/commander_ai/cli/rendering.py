"""Stable, concise CLI rendering and error output."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any, cast

import typer

from commander_ai.application.errors import ApplicationError


def render_result(value: object, *, as_json: bool) -> None:
    payload = _payload(value)
    if as_json:
        typer.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
        return
    if isinstance(payload, Mapping):
        for key in _preferred_keys(payload):
            typer.echo(f"{key}={_human_value(payload[key])}")
        return
    if isinstance(payload, Sequence) and not isinstance(payload, (str, bytes, bytearray)):
        for item in payload:
            typer.echo(_human_value(item))
        return
    typer.echo(_human_value(payload))


def render_error(error: ApplicationError, *, as_json: bool) -> None:
    payload = {"error_code": error.code}
    if as_json:
        typer.echo(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    else:
        typer.echo(f"error_code={error.code}", err=True)


def _payload(value: object) -> object:
    as_dict = getattr(value, "as_dict", None)
    if callable(as_dict):
        function = cast(Callable[[], object], as_dict)
        return _payload(function())
    if isinstance(value, Mapping):
        return {str(key): _payload(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_payload(item) for item in value]
    return value


def _preferred_keys(payload: Mapping[str, object]) -> tuple[str, ...]:
    preferred = (
        "source_id",
        "snapshot_id",
        "normalized_snapshot_id",
        "dataset_id",
        "selector",
        "status",
        "manifest_path",
        "manifest_sha256",
        "review_path",
        "review_exists",
        "local_sync_allowed",
        "public_export_allowed",
        "research_only",
        "counts",
        "outputs",
        "artifact_paths",
        "summary",
    )
    return tuple(key for key in preferred if key in payload) + tuple(
        sorted(set(payload) - set(preferred))
    )


def _human_value(value: Any) -> str:
    if isinstance(value, (Mapping, list, tuple)):
        return json.dumps(
            _payload(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    return str(value)


__all__ = ["render_error", "render_result"]
