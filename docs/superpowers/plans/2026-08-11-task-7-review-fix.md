# Task 7 Commander Spellbook Review Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Task-7 Commander Spellbook P1 review findings and bounded P2 findings in one focused offline-tested commit.

**Architecture:** Keep raw acquisition, verifier-issued snapshot evidence, source-shaped DTO parsing, and Task-5 staging as separate boundaries. Add source-owned contract validation in settings, page validation in the downloader, identity validation in the parser, and evidence validation in the mapper without introducing canonical or later-milestone behavior.

**Tech Stack:** Python 3.12, Pydantic 2 strict scalars, httpx, pytest, existing raw snapshot store/verifier, Ruff, mypy, and repository offline validation scripts.

---

### Task 1: Record the approved design and baseline

**Files:**
- Create: `docs/superpowers/specs/2026-08-11-task-7-review-fix-design.md`
- Create: `docs/superpowers/plans/2026-08-11-task-7-review-fix.md`

- [x] Confirm `data-foundation`, HEAD `befd71f8eafaf47b6a6b2f4ba62e20b2378c6372`, clean tracked diff, active M3 milestone, and Task-7-only source/test surface.
- [x] Review ADR-0005/0006/0011, source approval/provenance contracts, Spellbook settings/client/downloader/parser/mapper, and the existing focused tests.
- [x] Record the explicit user review-fix request as the approved design; no Task-8 or Task-1 work is permitted.
- [x] Establish the baseline with:

```powershell
uv run pytest tests/unit/adapters/sources/commander_spellbook tests/contract/test_commander_spellbook_adapter.py -q
```

Expected baseline: `20 passed`.

### Task 2: Add fixture files and failing regression tests

**Files:**
- Create: `tests/fixtures/commander_spellbook/valid_page.json`
- Create: `tests/fixtures/commander_spellbook/malformed_pagination.json`
- Create: `tests/fixtures/commander_spellbook/strict_scalar_failure.json`
- Create: `tests/fixtures/commander_spellbook/source_identity_settings_binding.json`
- Modify: `tests/unit/adapters/sources/commander_spellbook/test_client_and_acquisition.py`
- Modify: `tests/unit/adapters/sources/commander_spellbook/test_parser_and_staging.py`
- Modify: `tests/contract/test_commander_spellbook_adapter.py`

- [x] Add a valid small page fixture and use it in a successful verified parse/acquisition test.
- [x] Add malformed-page tests for invalid JSON, non-object/missing-results pages, wrong `next` scalar, invalid next host/path/query, and a persisted-object read failure; assert `CommanderSpellbookDownloadError`, no `COMPLETE` manifest, and `FAILED` state.
- [x] Add tests that `fetch` and `request_metadata` reject page zero and pages above `settings.max_pages` without invoking the HTTP handler.
- [x] Add parser tests that direct bytes/payload calls without verified evidence, with foreign source/object/request/product evidence, or with mismatched caller bytes/payloads fail closed.
- [x] Add mapper tests requiring verified evidence and rejecting a foreign snapshot/object/path or a fabricated record type/product.
- [x] Add strict scalar fixture tests for string numeric values, wrong numeric types, and booleans; assert parse findings and preserved original source values.
- [x] Add settings/client injection tests for arbitrary `api_path`, non-reviewed endpoint path/host, unsupported contract, and a mismatched injected downloader client.
- [x] Run the focused tests and confirm RED failures caused by the current behavior, not test setup errors.

Run:

```powershell
uv run pytest tests/unit/adapters/sources/commander_spellbook tests/contract/test_commander_spellbook_adapter.py -q
```

### Task 3: Implement fail-closed pagination and direct page limits

**Files:**
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/downloader.py`
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/client.py`
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/settings.py`

- [x] Validate each persisted page as a documented JSON envelope before deciding whether it has another page; raise stable pagination errors for read, decoding, shape, and link failures.
- [x] Validate next links against the exact configured contract endpoint and a single positive page query without following the link.
- [x] Preserve the existing `_fail_if_open` path so every pagination error writes `FAILED`/non-consumable state and prevents finalization.
- [x] Enforce `settings.max_pages` in both public client methods before transport calls.
- [x] Run the pagination and client regression tests green before moving on.

### Task 4: Implement evidence-bound parser and staging entry points

**Files:**
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/parser.py`
- Create: `src/commander_ai/adapters/sources/commander_spellbook/json_support.py`
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/mapper.py`
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/errors.py` only if a stable parser code needs a named error

- [x] Require verifier-issued `VerifiedSourceSnapshot` evidence and derive source snapshot/object path from the manifest.
- [x] Validate raw object ID/product, `source_object_id`, request lineage, exact GET/JSON endpoint, page parameter, source identity, and record contract before parsing.
- [x] Make optional bytes/payload compatibility entry points compare against the verified object and reject mismatches; never accept caller-supplied provenance fields.
- [x] Require verified snapshot evidence in both staging and audit mapping and validate every exact locator against object bytes before creating rows.
- [x] Preserve malformed JSON/source values and exact locators as auditable rows.
- [x] Run parser/staging focused tests green.

### Task 5: Implement strict DTO scalars and source-owned settings/client binding

**Files:**
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/api_models.py`
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/settings.py`
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/downloader.py`
- Modify: `src/commander_ai/adapters/sources/commander_spellbook/README.md`
- Modify: `docs/03-data/provenance.md` only for the public evidence-boundary wording if needed

- [x] Replace coercive DTO scalar annotations with strict integer/float/bool/string types while retaining documented string-or-integer IDs.
- [x] Reject arbitrary API paths, endpoint paths, hosts, and unsupported source products/contracts while retaining the source policy approval/current-use checks.
- [x] Require an injected downloader client to be a settings-matching `CommanderSpellbookClient` and keep the low-level HTTP test seam bounded by settings.
- [x] Document the evidence, pagination, and source-owned endpoint restrictions without adding new schema versions.
- [x] Run all focused tests and contract tests green.

### Task 6: Run offline gates, audit scope, and create one commit

**Files:**
- Stage only Task-7 adapter, tests, fixtures, and the two Task-7 process/contract documentation files created above.

- [x] Run each available repository gate independently (the repo-wide Ruff format check still reports six unchanged baseline files; the changed Task-7 files pass the same check):

```powershell
uv run pytest -q
uv run ruff format --check src tests scripts
uv run ruff check src tests scripts
uv run mypy src
uv run python scripts/check_architecture.py
uv run python scripts/check_file_sizes.py
uv run python scripts/validate_examples.py
uv run python scripts/validate_fixture_consistency.py
git diff --check
```

- [x] Review `git status --short`, `git diff --stat`, `git diff --name-only`, and the full diff for Task-7-only scope, no secrets, no live data, and no later-milestone work.
- [ ] Create exactly one commit with message `fix(data): close Task 7 Commander Spellbook review findings`.
- [ ] Verify the commit SHA/parent, changed-file list, focused/full test evidence, and final `git diff --check` before reporting completion.
