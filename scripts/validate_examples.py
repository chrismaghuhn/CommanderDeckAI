from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCRIPT_ROOT = Path(__file__).resolve().parents[1]


def locate_project_root() -> Path:
    for candidate in (SCRIPT_ROOT, SCRIPT_ROOT.parent):
        schemas = list((candidate / "schemas").glob("*.schema.json"))
        examples = list((candidate / "examples").glob("*.json"))
        if schemas and examples:
            return candidate
    return SCRIPT_ROOT


PROJECT_ROOT = locate_project_root()


def main() -> None:
    schemas_dir = PROJECT_ROOT / "schemas"
    examples_dir = PROJECT_ROOT / "examples"
    if not schemas_dir.is_dir() or not examples_dir.is_dir():
        raise SystemExit(
            f"schemas/examples not found beneath {PROJECT_ROOT}; "
            "run from the design package or copied repository scaffold"
        )

    failures: list[str] = []
    schema_paths = sorted(schemas_dir.glob("*.schema.json"))
    example_paths = sorted(examples_dir.glob("*.json"))
    if not example_paths:
        raise SystemExit(f"no JSON examples found in {examples_dir}")

    schema_names = {path.name.removesuffix(".schema.json") for path in schema_paths}
    example_names = {path.stem for path in example_paths}
    for missing_example in sorted(schema_names - example_names):
        failures.append(f"missing example for {missing_example}.schema.json")

    for example_path in example_paths:
        schema_path = schemas_dir / f"{example_path.stem}.schema.json"
        if not schema_path.exists():
            failures.append(f"missing schema for {example_path.name}")
            continue
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        instance = json.loads(example_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path)):
            failures.append(f"{example_path.name} {list(error.path)}: {error.message}")

    if failures:
        raise SystemExit("\n".join(failures))
    print(f"schema examples: ok ({len(example_paths)} files)")


if __name__ == "__main__":
    main()
