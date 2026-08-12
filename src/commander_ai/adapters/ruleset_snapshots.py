"""Read-only authoritative RulesetSnapshot inputs from the configured data root."""

from __future__ import annotations

import json
from pathlib import Path

from commander_ai.adapters.storage.path_policy import resolve_under_root, to_portable_relative_path
from commander_ai.data_pipeline.decks.ruleset_inputs import RulesetSnapshotInput
from commander_ai.domain.rulesets import RulesetSnapshot
from commander_ai.domain.serialization import sha256_hex


class RulesetSnapshotInputError(ValueError):
    """Stable failure for an invalid or ambiguous authoritative input set."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


class FileRulesetSnapshotProvider:
    """Load immutable ``ruleset.v1`` JSON inputs without a current-rule fallback."""

    def __init__(self, data_root: Path | str, relative_directory: str = "rulesets") -> None:
        self._data_root = Path(data_root).expanduser().resolve()
        self._relative_directory = relative_directory

    def load(self) -> tuple[RulesetSnapshotInput, ...]:
        directory = resolve_under_root(self._data_root, self._relative_directory)
        if not directory.exists():
            return ()
        if not directory.is_dir() or directory.is_symlink():
            raise RulesetSnapshotInputError(
                "INTEGRITY_RULESET_INPUT_DIRECTORY", "ruleset input directory is not safe"
            )

        inputs: list[RulesetSnapshotInput] = []
        versions: set[str] = set()
        for path in sorted(directory.glob("*.json"), key=lambda item: item.name):
            if path.is_symlink() or not path.is_file():
                raise RulesetSnapshotInputError(
                    "INTEGRITY_RULESET_INPUT_FILE",
                    f"ruleset input is not a regular file: {path.name}",
                )
            relative_path = to_portable_relative_path(path, self._data_root)
            try:
                payload = path.read_bytes()
                snapshot = RulesetSnapshot.model_validate(
                    json.loads(payload.decode("utf-8"), object_pairs_hook=_pairs_without_duplicates)
                )
            except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as error:
                raise RulesetSnapshotInputError(
                    "INTEGRITY_RULESET_INPUT_INVALID",
                    f"ruleset snapshot is invalid: {relative_path}",
                ) from error
            if snapshot.ruleset_version in versions:
                raise RulesetSnapshotInputError(
                    "INTEGRITY_RULESET_INPUT_DUPLICATE",
                    f"duplicate ruleset_version: {snapshot.ruleset_version}",
                )
            versions.add(snapshot.ruleset_version)
            inputs.append(
                RulesetSnapshotInput(
                    snapshot=snapshot,
                    path=relative_path,
                    input_sha256=sha256_hex(payload),
                )
            )
        return tuple(
            sorted(
                inputs,
                key=lambda item: (
                    item.snapshot.effective_from,
                    item.snapshot.ruleset_version,
                    item.path,
                ),
            )
        )


def _pairs_without_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ruleset input contains duplicate JSON members")
        result[key] = value
    return result


__all__ = ["FileRulesetSnapshotProvider", "RulesetSnapshotInputError"]
