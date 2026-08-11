# Task 6 MTGJSON Review Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the first Task 6 MTGJSON review findings with one focused, offline-tested commit while preserving the Task-5 staging-only boundary.

**Architecture:** Keep URL/product construction in the MTGJSON adapter. The client owns a shared policy-bound `HttpTransport` built from validated source settings and accepts only a low-level `httpx.Client` for safe local stubs. Bind parsed records to verified snapshot/source/object/member identity and retain only DTOs, structural findings, and Task-5 staging rows.

**Tech Stack:** Python 3.12, Pydantic 2, httpx, pytest, PyYAML, existing raw snapshot store/verifier, Ruff, mypy, and repository architecture/fixture gates.

---

### Task 1: Record the approved design and baseline

**Files:**
- Create: `docs/superpowers/specs/2026-08-11-task-6-mtgjson-review-fix-design.md`
- Create: `docs/superpowers/plans/2026-08-11-task-6-mtgjson-review-fix.md`
- Preserve: `docs/superpowers/plans/2026-08-11-programmer-thinking-skill.md`

- [x] Verify branch `data-foundation`, HEAD `94bdb21bf09f811ce528303649bdc0207d34741d`, no tracked diff, and preserve the existing untracked file.
- [x] Review M3/source boundaries, ADR-0006/0011, source-snapshot schemas, MTGJSON/HTTP/storage/config READMEs, and the current Task 6 adapter.
- [x] Self-review the design and plan for placeholders, scope drift, and coverage of every requested P1/P2 finding.

### Task 2: Add failing settings, metadata, and DTO tests

**Files:**
- Modify: `tests/unit/adapters/sources/mtgjson/test_downloader.py`
- Modify: `tests/unit/application/test_source_policy.py`
- Modify: `tests/unit/config/test_configuration.py`
- Modify: `tests/unit/adapters/sources/mtgjson/test_parser_and_staging.py`

- [x] Add URL assertions for `/AllPrintings.json.zip` and `/AllPrintings.json.zip.sha256`.
- [x] Add tests that unknown MTGJSON filter keys, unsupported products, and conflicting top-level `files` versus `filters.files` fail closed.
- [x] Add tests for the dedicated checksum limit.
- [x] Add registry mismatch tests for review path, attribution, raw local storage, and redistribution before any HTTP handler runs.
- [x] Add a nested unknown DTO-field test proving mappings/sequences are immutable while `model_dump(mode="json")` remains valid.
- [x] Run the focused tests and confirm RED failures caused by the current implementation.

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/adapters/sources/mtgjson/test_downloader.py tests/unit/application/test_source_policy.py tests/unit/config/test_configuration.py tests/unit/adapters/sources/mtgjson/test_parser_and_staging.py -q
```

### Task 3: Add failing HTTP, checksum, locator, and archive-member tests

**Files:**
- Modify: `tests/unit/adapters/sources/mtgjson/test_downloader.py`
- Modify: `tests/unit/adapters/sources/mtgjson/test_parser_and_staging.py`
- Modify: `tests/unit/data_pipeline/test_staging_and_audit.py`
- Modify: `tests/unit/data_pipeline/test_parquet_tables.py`
- Modify: `tests/unit/data_pipeline/test_normalized_snapshot_verifier.py`

- [x] Use local `httpx` stubs to return a response/request whose endpoint is `evil.invalid`; assert the client/shared transport rejects it while the settings-built URL remains unchanged.
- [x] Return an oversized checksum body and assert a failed snapshot with no partial archive object.
- [x] Pass bytes that differ from a verified archive member and assert an integrity error; verify a non-MTGJSON snapshot is rejected.
- [x] Add `source_id` to generic locators and assert staging/provenance/verified-snapshot validation rejects mismatches; assert source identity changes `exact_locator`.
- [x] Run the new tests and confirm RED for the old injection, unbounded checksum, arbitrary member, hardcoded source, and locator behavior.

Run:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/adapters/sources/mtgjson tests/unit/data_pipeline/test_staging_and_audit.py tests/unit/data_pipeline/test_parquet_tables.py tests/unit/data_pipeline/test_normalized_snapshot_verifier.py -q
```

### Task 4: Implement settings, transport boundary, and registry policy

**Files:**
- Modify: `src/commander_ai/adapters/sources/mtgjson/settings.py`
- Modify: `src/commander_ai/adapters/sources/mtgjson/client.py`
- Modify: `src/commander_ai/application/source_policy.py`

- [x] Default to `.json.zip`; add a small bounded `checksum_max_bytes`; reject unknown MTGJSON filters, unsupported `bulk_type`, unknown products, and conflicting product locations.
- [x] Change the test seam to `http_client: httpx.Client | None`; have the client construct `HttpTransport` from source settings, validate every generated URL/metadata endpoint, and validate returned endpoints against the same allowlist before exposing responses.
- [x] Keep approval/review gates and add fail-closed source-registry comparisons for review path, approval, attribution, raw storage, and redistribution with stable redacted policy codes.
- [x] Run the Task 2 and Task 3 commands and confirm GREEN for the implemented behavior.

### Task 5: Implement bounded checksum acquisition and authoritative manifest metadata

**Files:**
- Modify: `src/commander_ai/adapters/sources/mtgjson/downloader.py`
- Modify: `tests/unit/adapters/sources/mtgjson/test_downloader.py`

- [x] Replace `b"".join(response.iter_raw())` with a bounded `bytearray` reader under `checksum_max_bytes`, closing responses in `finally` and preserving failed-snapshot behavior.
- [x] Keep checksum sidecar bytes as a separate raw object; keep upstream SHA-256, local archive SHA-256, and verification status distinct.
- [x] Build manifest approval, attribution, terms, and redistribution values from authoritative historical registry metadata, never adapter-only overrides.
- [x] Run `.venv\Scripts\python.exe -m pytest tests/unit/adapters/sources/mtgjson/test_downloader.py -q`.

### Task 6: Implement source-bound locators, member identity, staging, and DTO freezing

**Files:**
- Modify: `src/commander_ai/data_pipeline/staging/raw_locators.py`
- Modify: `src/commander_ai/data_pipeline/staging/records.py`
- Modify: `src/commander_ai/data_pipeline/provenance/rows.py`
- Modify: `src/commander_ai/adapters/sources/mtgjson/parser.py`
- Modify: `src/commander_ai/adapters/sources/mtgjson/staging.py`
- Modify: `src/commander_ai/adapters/sources/mtgjson/dto.py`
- Modify: generic locator fixtures from Task 3

- [x] Add required `RawLocator.source_id`, include it in the exact identity, and validate it against the verified manifest and row-level source IDs.
- [x] Reject non-MTGJSON verified snapshots; read the named member from the verified raw archive and compare optional caller bytes before DTO parsing.
- [x] Remove the staging mapper's `mtgjson` literal and derive the row source from the source-bound locator.
- [x] Recursively freeze unknown DTO mappings/sequences while keeping `extra="allow"`.
- [x] Run `.venv\Scripts\python.exe -m pytest tests/unit/adapters/sources/mtgjson tests/unit/data_pipeline tests/unit/domain/test_foundation_models.py -q`.

### Task 7: Update source config and documentation

**Files:**
- Modify: `configs/sources/mtgjson.yaml`
- Modify: `src/commander_ai/adapters/sources/mtgjson/README.md`
- Modify: `docs/03-data/source-reviews/mtgjson.md`
- Modify: `docs/03-data/provenance.md`

- [x] Document the official `.json.zip` and `.json.zip.sha256` names, bounded sidecars, authoritative compressed bytes, and no undocumented endpoint inference.
- [x] Document source-bound reconstructable locators, registry-owned reviewed metadata, and the DTO/staging-only boundary.
- [x] Run `.venv\Scripts\python.exe -m pytest tests/contract/test_mtgjson_adapter.py tests/unit/config/test_configuration.py -q`.

### Task 8: Run all offline gates and make one focused commit

**Files:**
- Stage only files changed by Tasks 1-7.
- Do not stage `docs/superpowers/plans/2026-08-11-programmer-thinking-skill.md`.

- [x] Run each gate independently:

```powershell
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check src tests scripts
.venv\Scripts\python.exe -m mypy src
.venv\Scripts\python.exe scripts/validate_examples.py
.venv\Scripts\python.exe scripts/validate_fixture_consistency.py
.venv\Scripts\python.exe scripts/check_file_sizes.py
.venv\Scripts\python.exe scripts/check_architecture.py
git diff --check
```

- [x] Audit `git status --short`, `git diff --stat`, and `git diff --name-only` for Task 6-only scope and no live/network or later-milestone work.
- [ ] Stage only the audited focused files; do not stage `docs/superpowers/plans/2026-08-11-programmer-thinking-skill.md`.
- [ ] Create exactly one commit with message `fix(data): close Task 6 MTGJSON review findings`.
- [ ] Verify the commit SHA/parent, changed-file list, clean tracked worktree, preserved pre-existing untracked file, and a final `git diff --check`.
