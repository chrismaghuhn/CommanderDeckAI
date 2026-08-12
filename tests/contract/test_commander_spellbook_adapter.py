from __future__ import annotations

import ast
from pathlib import Path

from commander_ai.adapters.sources.commander_spellbook.settings import (
    CommanderSpellbookSettings,
)
from commander_ai.config.source_settings import SourceSettings
from commander_ai.config.yaml_loader import load_source_settings

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ADAPTER_ROOT = (
    PROJECT_ROOT / "src" / "commander_ai" / "adapters" / "sources" / "commander_spellbook"
)


def _imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.add(node.module)
    return modules


def test_spellbook_adapter_has_one_source_owned_package_and_no_later_layer_imports() -> None:
    assert ADAPTER_ROOT.is_dir()
    assert not (PROJECT_ROOT / "src" / "commander_ai" / "spellbook").exists()
    forbidden = (
        "domain.cards",
        "domain.combos",
        "canonical",
        "graph",
        "ml",
        "optimization",
        "forge",
        "commander_ai.cli",
    )
    for path in ADAPTER_ROOT.glob("*.py"):
        modules = _imported_modules(path)
        assert not any(
            fragment in module.casefold() for module in modules for fragment in forbidden
        ), path
        text = path.read_text(encoding="utf-8").casefold()
        assert "commander_ai.domain.cards" not in text
        assert "commander_ai.cli" not in text


def test_settings_contract_is_strict_and_source_specific() -> None:
    source = SourceSettings(
        source_id="commander_spellbook",
        approval_status="APPROVED_LOCAL",
        access_method="bulk_json_with_sparse_rest",
        endpoints=(
            "https://backend.commanderspellbook.com",
            "https://json.commanderspellbook.com",
        ),
        host_allowlist=("backend.commanderspellbook.com", "json.commanderspellbook.com"),
        max_pages=3,
        files=("variants.json",),
        bulk_type="json",
        review_path="docs/03-data/source-reviews/commander-spellbook.md",
        filters={
            "documented_read_contracts": ["cards", "variants"],
            "bulk_file": "variants.json",
            "sparse_rest_page_limit": 3,
        },
        features={"combos": True, "variants": True},
        attribution_required=True,
        raw_storage="allowed_local",
        redistribution="license_and_content_review",
    )
    settings = CommanderSpellbookSettings.from_source_settings(source)
    assert settings.source.source_id == "commander_spellbook"
    assert settings.contracts == ("cards", "variants")
    assert settings.model_config["extra"] == "forbid"


def test_checked_in_config_selects_bulk_sync_and_sparse_rest_policy() -> None:
    source = load_source_settings(PROJECT_ROOT / "configs" / "sources" / "commander_spellbook.yaml")

    assert source.access_method == "bulk_json_with_sparse_rest"
    assert source.endpoints == (
        "https://backend.commanderspellbook.com",
        "https://json.commanderspellbook.com",
    )
    assert source.host_allowlist == (
        "backend.commanderspellbook.com",
        "json.commanderspellbook.com",
    )
    assert source.rate_limit_per_minute == 30
    assert source.max_pages == 3
    assert source.bulk_type == "json"
    assert source.files == ("variants.json",)
    assert source.filters["bulk_file"] == "variants.json"
    assert source.filters["sparse_rest_page_limit"] == 3
