from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCRIPT_ROOT = Path(__file__).resolve().parents[1]


def locate_project_root() -> Path:
    for candidate in (SCRIPT_ROOT, SCRIPT_ROOT.parent):
        if (candidate / "examples" / "ruleset.v1.json").is_file():
            return candidate
    return SCRIPT_ROOT


PROJECT_ROOT = locate_project_root()
EXAMPLES = PROJECT_ROOT / "examples"


def load(name: str) -> dict[str, Any]:
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def require_equal(label: str, *values: object) -> None:
    if len(set(values)) != 1:
        raise SystemExit(f"fixture mismatch for {label}: {values}")


def validate_deck_total(label: str, deck: dict[str, Any], ruleset: dict[str, Any]) -> None:
    command_zone = deck["command_zone"]
    mainboard = deck["mainboard"]
    total = sum(item.get("quantity", 1) for item in command_zone)
    total += sum(item["quantity"] for item in mainboard)
    if total != ruleset["required_total_cards"]:
        raise SystemExit(f"{label} has {total} cards; expected {ruleset['required_total_cards']}")

    unlimited = set(ruleset.get("unlimited_copy_oracle_ids", []))
    overrides = ruleset.get("copy_limit_overrides", {})
    default_limit = ruleset["default_copy_limit"]
    for item in mainboard:
        oracle_id = item["oracle_id"]
        quantity = item["quantity"]
        if oracle_id in unlimited:
            continue
        limit = overrides.get(oracle_id, default_limit)
        if quantity > limit:
            raise SystemExit(f"{label} exceeds copy limit for {oracle_id}: {quantity} > {limit}")


def main() -> None:
    ruleset = load("ruleset.v1.json")
    deck = load("deck.v1.json")
    completion = load("completion-example.v1.json")
    dataset = load("dataset-manifest.v1.json")
    model = load("model-manifest.v1.json")
    rank_request = load("rank-request.v1.json")
    rank_response = load("rank-response.v1.json")
    scores = load("score-snapshot.v1.json")
    optimization_request = load("optimization-request.v1.json")
    optimization_result = load("optimization-result.v1.json")
    forge_request = load("forge-evaluation-request.v1.json")
    forge_result = load("forge-evaluation-result.v1.json")
    run_manifest = load("run-manifest.v1.json")

    require_equal(
        "ruleset_version",
        ruleset["ruleset_version"],
        deck["ruleset_version"],
        completion["ruleset_version"],
        rank_request["ruleset_version"],
        rank_response["ruleset_version"],
        scores["ruleset_version"],
        optimization_request["ruleset_version"],
        optimization_result["ruleset_version"],
        forge_request["ruleset_version"],
    )
    require_equal(
        "card_snapshot_id",
        deck["card_snapshot_id"],
        completion["card_snapshot_id"],
        rank_request["card_snapshot_id"],
        scores["card_snapshot_id"],
        forge_request["card_snapshot_id"],
    )
    require_equal(
        "dataset_id",
        dataset["dataset_id"],
        model["dataset_id"],
        completion["dataset_id"],
        rank_response["dataset_id"],
        scores["dataset_id"],
    )
    require_equal(
        "model_id",
        model["model_id"],
        rank_request["model_id"],
        rank_response["model_id"],
        scores["model_id"],
    )
    require_equal(
        "rank request_id",
        rank_request["request_id"],
        rank_response["request_id"],
        scores["request_id"],
    )
    require_equal(
        "score_snapshot_id",
        rank_response["score_snapshot_id"],
        scores["score_snapshot_id"],
        optimization_request["score_snapshot_id"],
    )
    require_equal(
        "optimization_id",
        optimization_request["optimization_id"],
        optimization_result["optimization_id"],
    )
    require_equal(
        "forge request_id",
        forge_request["request_id"],
        forge_result["request_id"],
    )
    require_equal("deck_id", deck["deck_id"], completion["deck_id"])

    input_refs = {(item["kind"], item["id"]) for item in run_manifest["inputs"]}
    if ("dataset_manifest", dataset["dataset_id"]) not in input_refs:
        raise SystemExit("run manifest does not reference the dataset fixture")
    if ("ruleset_snapshot", ruleset["ruleset_version"]) not in input_refs:
        raise SystemExit("run manifest does not reference the ruleset fixture")

    artifact_paths = {item["path"] for item in run_manifest["artifacts"]}
    for model_artifact in model["artifacts"]:
        if model_artifact["path"] not in artifact_paths:
            raise SystemExit("run manifest does not reference every model artifact")

    validate_deck_total("deck fixture", deck, ruleset)
    validate_deck_total("optimization result", optimization_result, ruleset)
    for forge_deck in forge_request["decks"]:
        validate_deck_total(f"Forge seat {forge_deck['seat_key']}", forge_deck, ruleset)

    print("fixture consistency: ok")


if __name__ == "__main__":
    main()
