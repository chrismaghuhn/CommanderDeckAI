"""Provenance-carrying RulesetSnapshot inputs for historical evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from commander_ai.domain.path_policy import validate_portable_relative_path
from commander_ai.domain.rulesets import RulesetSnapshot


@dataclass(frozen=True, slots=True)
class RulesetSnapshotInput:
    """One authoritative ruleset file and its exact file-byte digest.

    ``snapshot.sha256`` is the semantic hash carried by the frozen ``ruleset.v1``
    contract. ``input_sha256`` is the digest of the exact persisted input bytes
    and is the value used for run-manifest file binding.
    """

    snapshot: RulesetSnapshot
    path: str
    input_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", validate_portable_relative_path(self.path))
        if len(self.input_sha256) != 64 or any(
            character not in "0123456789abcdef" for character in self.input_sha256
        ):
            raise ValueError("ruleset input sha256 must be a lowercase SHA-256 digest")

    @property
    def snapshot_id(self) -> str:
        """Return the frozen contract's stable snapshot identifier."""

        return self.snapshot.ruleset_version


class RulesetSnapshotProvider(Protocol):
    """Port for loading authoritative, provenance-carrying ruleset inputs."""

    def load(self) -> tuple[RulesetSnapshotInput, ...]:
        """Return all available inputs; an empty result means no applicable input."""


__all__ = ["RulesetSnapshotInput", "RulesetSnapshotProvider"]
