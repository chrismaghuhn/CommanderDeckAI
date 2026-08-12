"""Integrity helpers for report run input bindings."""

from __future__ import annotations

import hashlib
from pathlib import Path

from commander_ai.application.errors import ApplicationError
from commander_ai.data_pipeline.provenance.run_manifests import RunInputReference
from commander_ai.domain.serialization import canonical_json_bytes, sha256_hex


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def report_digest(values: tuple[str, ...]) -> str:
    return sha256_hex(canonical_json_bytes(list(values)))


def unique_run_inputs(values: list[RunInputReference]) -> tuple[RunInputReference, ...]:
    """Reject conflicting references while returning deterministic input order."""

    unique: dict[tuple[str, str], RunInputReference] = {}
    for value in values:
        key = (value.kind, value.id)
        previous = unique.get(key)
        if previous is not None and previous != value:
            raise ApplicationError("INTEGRITY_REPORT_INPUT_BINDING")
        unique[key] = value
    return tuple(unique[key] for key in sorted(unique))


__all__ = ["report_digest", "sha256_path", "unique_run_inputs"]
