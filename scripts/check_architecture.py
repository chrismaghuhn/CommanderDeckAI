from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "commander_ai"

FORBIDDEN = {
    "domain": (
        "commander_ai.application",
        "commander_ai.adapters",
        "commander_ai.models",
        "commander_ai.optimization",
        "commander_ai.evaluation",
        "commander_ai.forge",
        "duckdb",
        "httpx",
        "torch",
        "ortools",
        "typer",
    ),
    "application": (
        "commander_ai.adapters",
        "duckdb",
        "httpx",
        "torch",
        "ortools",
        "typer",
    ),
    "models": ("commander_ai.adapters.sources", "httpx"),
    "optimization": (
        "commander_ai.models.deepsets",
        "commander_ai.models.matrix_factorization",
    ),
}
FORBIDDEN_FILENAMES = {"utils.py", "helpers.py", "common.py"}


def imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.append(node.module)
    return found


def main() -> None:
    failures: list[str] = []
    for path in sorted(PACKAGE.rglob("*.py")):
        if path.name in FORBIDDEN_FILENAMES:
            failures.append(f"forbidden generic module: {path.relative_to(ROOT)}")
        relative = path.relative_to(PACKAGE)
        top = relative.parts[0] if len(relative.parts) > 1 else None
        if top not in FORBIDDEN:
            continue
        for imported in imports(path):
            if imported.startswith(FORBIDDEN[top]):
                failures.append(f"{path.relative_to(ROOT)} imports forbidden {imported}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("architecture: ok")


if __name__ == "__main__":
    main()
