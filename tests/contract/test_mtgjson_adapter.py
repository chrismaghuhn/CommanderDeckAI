from __future__ import annotations

import ast
from pathlib import Path

from commander_ai.adapters.sources.mtgjson.settings import MTGJSONProduct

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_ROOT = PROJECT_ROOT / "src" / "commander_ai" / "adapters" / "sources" / "mtgjson"


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_adapter_scaffold_uses_only_the_approved_mtgjson_products() -> None:
    assert {item.value for item in MTGJSONProduct} == {"AllPrintings", "AllDeckFiles"}


def test_adapter_does_not_import_canonical_card_or_resolution_layers() -> None:
    forbidden_fragments = ("domain.cards", "card_resolution", "resolution", "canonical")
    for path in ADAPTER_ROOT.glob("*.py"):
        modules = _imported_modules(path)
        assert not any(
            fragment in module.casefold() for module in modules for fragment in forbidden_fragments
        ), path


def test_source_adapter_remains_above_task5_staging_and_below_no_cli_boundary() -> None:
    for path in ADAPTER_ROOT.glob("*.py"):
        text = path.read_text(encoding="utf-8").casefold()
        assert "commander_ai.cli" not in text
        assert "commander_ai.domain.cards" not in text
        assert "commander_ai.card_resolution" not in text
