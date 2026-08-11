# Task 5 Review Findings Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the second Task 5 review findings while keeping `normalized-snapshot-manifest.v1` as the authoritative normalized output and preserving Task 5's offline, non-canonical scope.

**Architecture:** Introduce a nominal verified-source evidence boundary issued only by the raw snapshot verifier. Make the v1 normalized manifest builder and reader bind that evidence, the persisted run manifest, current-use decision evidence, and all three typed Parquet layers. Keep v2 as a separately readable stricter extension, and keep DuckDB-derived behavior out of the authoritative path.

**Tech Stack:** Python 3.12, Pydantic v2, PyArrow Parquet, canonical JSON/SHA-256, pytest, Ruff, mypy, repository architecture and fixture scripts.

---

### Task 1: Establish trusted raw-snapshot and current-use gates

**Files:**
- Create: `src/commander_ai/application/verified_source_snapshot.py`
- Modify: `src/commander_ai/application/normalize_snapshot.py`
- Modify: `src/commander_ai/application/source_policy.py`
- Modify: `src/commander_ai/config/current_use_policy.py`
- Modify: `src/commander_ai/adapters/storage/snapshot_verifier.py`
- Test: `tests/unit/application/test_normalize_snapshot.py`
- Test: `tests/unit/application/test_source_policy.py`

- [x] **Step 1: Write failing gate tests**

  Add tests proving that a coordinator with only `inspect()` is rejected, a `consumable=True` inspection cannot authorize normalization, a fabricated verifier result cannot be passed to the manifest builder, requested source/snapshot identity and manifest path are checked, and an allowed normalize decision must carry a matching deterministic current-use decision reference and digest.

- [x] **Step 2: Run the gate tests and verify the expected red failures**

  Run:

  ```text
  .venv\Scripts\python.exe -m pytest tests/unit/application/test_normalize_snapshot.py tests/unit/application/test_source_policy.py -q
  ```

  Expected: the new fail-closed assertions fail against the existing `inspect()` fallback and decision shape, while the pre-existing tests remain distinguishable from the new failures.

- [x] **Step 3: Implement the nominal evidence and policy binding**

  Add an immutable `VerifiedSourceSnapshot` value with a private verifier-issued token, require `verify_complete_snapshot()` in the coordinator, reject boolean/legacy inspection fallbacks, validate exact requested identity and `raw/{source}/{snapshot}/manifest.json`, and add deterministic current-use decision reference/digest fields to the typed policy result. Have `SnapshotVerifier` issue the nominal evidence only after its existing manifest, path, size, object hash, snapshot-content digest, and detached-digest checks pass.

- [x] **Step 4: Run the gate tests and the raw verifier regression suite**

  Run:

  ```text
  .venv\Scripts\python.exe -m pytest tests/unit/application/test_normalize_snapshot.py tests/unit/application/test_source_policy.py tests/unit/adapters/storage/test_snapshot_verifier.py -q
  ```

  Expected: all selected tests pass and no legacy `inspect()` path can produce `VerifiedNormalizationInput`.

### Task 2: Make v1 the authoritative normalized manifest and verify it from disk

**Files:**
- Create: `src/commander_ai/data_pipeline/provenance/normalized_snapshot_validation.py`
- Modify: `src/commander_ai/data_pipeline/provenance/normalized_snapshot_contracts.py`
- Modify: `src/commander_ai/data_pipeline/provenance/normalized_snapshot_content.py`
- Modify: `src/commander_ai/data_pipeline/provenance/normalized_snapshot_manifests.py`
- Modify: `src/commander_ai/data_pipeline/provenance/normalized_snapshot_verifier.py`
- Modify: `src/commander_ai/adapters/storage/manifest_files.py`
- Modify: `tests/unit/data_pipeline/test_provenance_contracts.py`
- Modify: `tests/unit/data_pipeline/test_normalized_snapshot_verifier.py`
- Modify: `tests/unit/adapters/storage/test_manifest_files.py`

- [x] **Step 1: Write failing v1 production/read tests**

  Change the authoritative builder assertions to require `schema_version == "normalized-snapshot-manifest.v1"`. Add tests for deterministic v1 ID/content digest, canonical bytes and detached digest, exact source manifest ID/hash, policy decision/run bindings, sorted quarantine references, rejection of omitted/mismatched quarantine output, v1 read verification of real Parquet existence/portable paths/sha256/bytes/rows, and rejection of tampered manifest, run, raw snapshot, or Parquet content.

- [x] **Step 2: Run the v1 tests and verify the expected red failures**

  Run:

  ```text
  .venv\Scripts\python.exe -m pytest tests/unit/data_pipeline/test_provenance_contracts.py tests/unit/data_pipeline/test_normalized_snapshot_verifier.py tests/unit/adapters/storage/test_manifest_files.py -q
  ```

  Expected: the tests fail because the current builder emits v2 and the reader rejects v1.

- [x] **Step 3: Implement v1 build/content semantics without changing frozen schemas**

  Make the normal builder return `NormalizedSnapshotManifest` v1, retain the v2 model as a separate extension, sort all digest-relevant collections, require one normalized/audit/quarantine artifact and matching successful run output references, require a bound current-use decision input, bind source object IDs and raw hashes from trusted evidence, and derive the v1 ID/content digest from the complete internal artifact and policy binding payload without adding v1 fields.

- [x] **Step 4: Implement the v1 filesystem read/verify path**

  Let the reader parse v1 or v2, verify canonical bytes and detached sidecar, load and fully verify the referenced run-manifest.v1, derive actual artifact metadata from the run's three output files, verify Parquet layer metadata, row counts, byte counts, SHA-256 values, raw snapshot evidence, source manifest identity/hash, one-to-one source provenance, and all quarantine references before returning a verified result. Preserve v2 verification as an explicit branch.

- [x] **Step 5: Run the focused v1 suite green**

  Run the command from Step 2 and confirm all tests pass, including the tamper cases.

### Task 3: Close row-layer, staging, locator, provenance, and run-manifest gaps

**Files:**
- Modify: `src/commander_ai/adapters/storage/parquet_tables.py`
- Modify: `src/commander_ai/data_pipeline/staging/raw_locators.py`
- Modify: `src/commander_ai/data_pipeline/staging/records.py`
- Modify: `src/commander_ai/data_pipeline/provenance/rows.py`
- Create: `src/commander_ai/domain/normalized_snapshot_validation.py`
- Modify: `src/commander_ai/data_pipeline/provenance/run_manifests.py`
- Modify: `src/commander_ai/data_pipeline/provenance/run_manifest_redaction.py`
- Modify: `src/commander_ai/data_pipeline/provenance/run_manifest_verifier.py`
- Test: `tests/unit/data_pipeline/test_parquet_tables.py`
- Test: `tests/unit/data_pipeline/test_staging_and_audit.py`
- Test: `tests/unit/data_pipeline/test_provenance_contracts.py`
- Test: `tests/contract/test_foundation_contracts.py`

- [x] **Step 1: Write failing typed-layer, locator, status, and run tests**

  Add tests showing mutable mappings and missing row contracts are rejected, curated requires an explicit curated row type, audit/quarantine rows cannot cross layers, source-backed rows require a verified raw-object index, forged raw object hash/path/locator combinations fail, parse/integrity findings require locators, invalid staging status/finding combinations fail, archive-member locators are portable and unique, timestamps and counts are strict, pathless file/object inputs fail, secret-bearing input IDs/kinds are redacted, duplicate JSON keys and schema-invalid run structures fail, and output artifacts are verified from disk.

- [x] **Step 2: Run the new layer/run tests and verify red failures**

  Run:

  ```text
  .venv\Scripts\python.exe -m pytest tests/unit/data_pipeline/test_parquet_tables.py tests/unit/data_pipeline/test_staging_and_audit.py tests/unit/data_pipeline/test_provenance_contracts.py tests/contract/test_foundation_contracts.py -q
  ```

  Expected: the new assertions fail against mapping-based row persistence, optional path/index checks, incomplete staging semantics, and permissive run JSON parsing.

- [x] **Step 3: Implement typed row contracts and verified locator validation**

  Require explicit table-layer and allowed immutable row contracts in `ParquetTableWriter`, add an explicit curated row contract, require a trusted verified source snapshot for source-backed rows, validate locator source snapshot/object/path/hash/range identity against the verified object index, and keep audit/quarantine rows retained but unavailable to curated output.

- [x] **Step 4: Implement staging and run-manifest semantic validation**

  Enforce status/finding namespace combinations, locator requirements, deterministic archive-member identity, timezone-aware lifecycle values and sensible counts, secret-free input kind/id serialization, path requirements for file/object hashes, duplicate-key rejection, schema-compatible lifecycle/dirty-worktree/unique-structure rules, and persisted-file verification for every applicable run input/output.

- [x] **Step 5: Run the focused data-contract suite green**

  Run the command from Step 2 and confirm all selected tests pass.

### Task 4: Update Task-5 documentation and perform repository gates

**Files:**
- Modify: `src/commander_ai/data_pipeline/README.md`
- Modify: `docs/03-data/storage-layout.md`
- Modify: `docs/03-data/provenance.md`
- Modify: `tests/unit/data_pipeline/test_provenance_contracts.py`
- Modify: `tests/unit/data_pipeline/test_normalized_snapshot_verifier.py`

- [x] **Step 1: Update documentation to state the v1 authority boundary**

  Document v1 as the produced/verified Task-5 normalized snapshot manifest, describe v2 only as a separate stricter extension, and preserve DuckDB as derived local infrastructure. Do not modify either frozen normalized-manifest schema or the frozen run-manifest schema.

- [x] **Step 2: Run focused tests, formatting, and static repository checks**

  Run:

  ```text
  .venv\Scripts\python.exe -m pytest tests/unit/application/test_normalize_snapshot.py tests/unit/application/test_source_policy.py tests/unit/data_pipeline/test_provenance_contracts.py tests/unit/data_pipeline/test_normalized_snapshot_verifier.py tests/unit/data_pipeline/test_parquet_tables.py tests/unit/data_pipeline/test_staging_and_audit.py tests/unit/adapters/storage/test_snapshot_verifier.py tests/unit/adapters/storage/test_manifest_files.py tests/contract/test_foundation_contracts.py -q
  .venv\Scripts\python.exe -m ruff format --check src tests scripts
  .venv\Scripts\python.exe -m ruff check src tests scripts
  .venv\Scripts\python.exe scripts/check_file_sizes.py
  .venv\Scripts\python.exe scripts/check_architecture.py
  .venv\Scripts\python.exe scripts/validate_examples.py
  .venv\Scripts\python.exe scripts/validate_fixture_consistency.py
  git diff --check
  ```

  Expected: every command exits zero; no production file exceeds the repository's hard limit; no frozen schema is modified.

- [x] **Step 3: Run the full offline repository test gate**

  Run:

  ```text
  .venv\Scripts\python.exe -m pytest -q
  ```

  Expected: the full repository suite exits zero without live source access, API keys, CLI execution, ML, optimizer, canonical-entity, or Forge work.

- [x] **Step 4: Audit scope, status, diff, and commit exactly once**

  Confirm `git status --short`, `git diff --stat`, `git diff --check`, frozen schema hashes, and the final file list. Create one commit containing the focused Task-5 production changes, regression tests, documentation, and this implementation plan:

  ```text
  git add docs/superpowers/plans/2026-08-11-task-5-review-fix.md docs/03-data/provenance.md docs/03-data/storage-layout.md src/commander_ai/data_pipeline/README.md src tests scripts
  git commit -m "fix(data): close second Task 5 review findings"
  ```

  Verify the commit contains no Task 6+ files and record its SHA only after all gates pass.
