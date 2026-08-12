from pathlib import Path

import pytest

from commander_ai.adapters.snapshot_locator import find_source_for_snapshot


@pytest.mark.parametrize("snapshot_id", ("", "../../escape", ".hidden-snapshot"))
def test_snapshot_locator_rejects_invalid_ids_before_path_probing(
    tmp_path: Path, snapshot_id: str
) -> None:
    with pytest.raises(ValueError, match="single portable path components"):
        find_source_for_snapshot(tmp_path, snapshot_id)


def test_snapshot_locator_finds_unique_source_for_valid_id(tmp_path: Path) -> None:
    manifest = tmp_path / "raw/fixture/snapshot-1/manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text("{}", encoding="utf-8")

    assert find_source_for_snapshot(tmp_path, "snapshot-1") == "fixture"
