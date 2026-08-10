from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARD_LIMIT = 400
EXEMPT_PARTS = {"generated", "migrations"}


def main() -> None:
    failures: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        if any(part in EXEMPT_PARTS for part in path.parts):
            continue
        line_count = len(path.read_text(encoding="utf-8").splitlines())
        if line_count > HARD_LIMIT:
            failures.append(f"{path.relative_to(ROOT)}: {line_count} > {HARD_LIMIT}")
    if failures:
        raise SystemExit("\n".join(failures))
    print("file sizes: ok")


if __name__ == "__main__":
    main()
