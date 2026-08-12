from __future__ import annotations

import ast
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOMAIN_PATH_POLICY = PROJECT_ROOT / "src" / "commander_ai" / "domain" / "path_policy.py"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_domain_path_policy_is_pure_string_validation() -> None:
    imports = _imported_modules(DOMAIN_PATH_POLICY)

    assert "os" not in imports
    assert "pathlib" not in imports
    assert "shutil" not in imports
    assert "tempfile" not in imports

    tree = ast.parse(DOMAIN_PATH_POLICY.read_text(encoding="utf-8"))
    defined_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }
    assert defined_names <= {"validate_portable_relative_path", "normalize_portable_relative_path"}
