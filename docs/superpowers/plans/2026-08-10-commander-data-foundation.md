# Commander Data Foundation Implementation Plan

> For agentic workers: execute this plan task-by-task with the repository implementation workflow. Keep every task reviewable, test-first, and limited to the approved data-foundation track.

**Goal:** Build a reproducible, legally cautious, offline-testable acquisition, snapshot, normalization, validation, reporting, and dataset-preparation foundation for MTGJSON, Commander Spellbook, TopDeck, and Spicerack, with assessment-only handling for Archidekt, Moxfield, EDHREC, and cEDH Decklist Database.

**Architecture:** Preserve the existing Clean Architecture dependency direction. Source adapters produce source DTOs and staging records; shared storage owns immutable raw bytes; domain contracts remain source-agnostic; application use cases compose ports; CLI commands remain thin. Raw snapshots and manifests are authoritative ingestion artifacts. Normalized audit data is distinct from curated training-eligible data. SQL/DuckDB tables are derived, local, rebuildable query/index/cache infrastructure; authoritative normalized and curated outputs are Parquet artifacts plus their versioned manifests.

**Tech Stack:** Python >=3.12,<3.14, the repository's existing Pydantic/configuration conventions, JSON Schema contracts, HTTPX for source transport, DuckDB for local transformation/query infrastructure, PyArrow/Parquet for large derived tables, Typer for the existing CLI, and pytest/ruff/mypy as configured by the repository.

## Non-negotiable design anchors

- Preserve all existing v1 contracts. Add versioned contracts for new persisted semantics; do not repurpose generic metadata to avoid versioning.
- Use an allowlist source gate: local sync is allowed only for 'APPROVED_LOCAL' and 'APPROVED_REDISTRIBUTION'; public export is allowed only for 'APPROVED_REDISTRIBUTION'.
- Keep historical snapshot approval metadata separate from the current source-use/takedown policy.
- Preserve exact raw HTTP entity bytes with response.iter_raw() before parsing or decompression. A compressed archive is the authoritative MTGJSON raw object; extracted files are derived views.
- Use one shared RawSnapshotWriter/RawSnapshotStore; adapters must not duplicate storage, hashing, finalization, or manifest persistence.
- The pipeline is raw blob -> parse/structural validation -> staging record -> deterministic resolution -> canonicalization -> semantic quality evaluation -> curated or quarantine.
- Only a COMPLETE snapshot that passes a fresh object-presence, size, hash, and manifest-consistency verification may enter normalization.
- objects[].sha256 hashes exact raw bytes. snapshot_content_sha256 hashes a documented canonical ordered object-hash document. A detached manifest digest hashes canonical manifest JSON with its self-digest field omitted.
- All persisted paths are portable POSIX-style root-relative paths and cannot escape the configured root.
- canonical_deck_id is deterministically derived from the structural fingerprint. The fingerprint uses stable format family 'commander', not a temporal ruleset version, and includes the supported card zones.
- Deck structure, legality evaluation, quality evaluation, event observation, and pod entry are separate contracts.
- RulesetSnapshots selected by explicit effective dates are authoritative for legality. If no applicable ruleset can be resolved, the result is 'unknown'.
- Card resolution is deterministic and auditable, with resolver, normalization-policy, alias-catalog, and card-catalog snapshot provenance.
- Completion split grouping uses forward-only promotion. Tournament splits use temporal cutoffs plus complete event grouping. Near-duplicate algorithms and thresholds are versioned dataset policy, never canonical identity.
- Participant references are source-scoped opaque IDs only when approved and useful; otherwise use event/snapshot-scoped synthetic references. Never create a global unsalted name hash or retain raw names in curated data.
- Every operation and task-specific dataset binds input manifests, transform/policy versions, configuration snapshot/hash, output hashes, exclusions, and status.
- Normal CI is fully offline. Live source smoke tests are opt-in and never required.

## Repository boundary

The existing run-manifest.v1 contract on main is frozen and must not be silently changed. Use that generic contract for source sync, normalize, validate, report, and dataset build runs through its existing run kind, stage, generic inputs, configuration provenance, determinism, environment, and output-artifact fields. Add a new provenance contract only after a concrete semantic gap is demonstrated and reviewed.

## Implementation sequence

1. Add contracts and domain value objects.
2. Add source registry/current-use policy, configuration validation, and source-review gates.
3. Add canonical serialization, portable paths, and deterministic digest primitives.
4. Add shared raw snapshot storage, HTTP transport, integrity verification, and commit-like finalization.
5. Add staging, audit/quarantine, Parquet persistence, and data-operation run manifests.
6. Implement MTGJSON.
7. Implement Commander Spellbook.
8. Implement TopDeck contracts/client while preserving its acquisition gate.
9. Implement Spicerack contracts/client while preserving missing-data semantics.
10. Implement card catalog and deterministic resolution.
11. Implement canonical decks, fingerprints, deduplication, ruleset selection, and evaluations.
12. Implement event observations, pod entries, participants, and combos.
13. Implement task-specific curated dataset builders and leakage-safe splits.
14. Implement quality/audit reports.
15. Wire application use cases and the existing CLI vocabulary.
16. Complete documentation, architecture checks, offline end-to-end fixtures, and final verification.

---

## Task 1: Add versioned contracts and source-agnostic domain models

**Files**

- Add JSON Schemas under schemas/: source-snapshot-manifest.v2.schema.json, normalized-snapshot-manifest.v1.schema.json, canonical-deck.v1.schema.json, deck-legality-evaluation.v1.schema.json, deck-quality-evaluation.v1.schema.json, card-resolution.v1.schema.json, printing.v1.schema.json, card-face.v1.schema.json, event-deck-observation.v1.schema.json, participant-reference.v1.schema.json, combo.v1.schema.json, combo-card.v1.schema.json, and dataset-manifest.v2.schema.json.
- Add minimal valid examples under examples/ for every new contract, including examples/normalized-snapshot-manifest.v1.json.
- Add focused domain models under src/commander_ai/domain/: cards.py, decks.py, evaluations.py, observations.py, combos.py, and provenance.py.
- Update only the domain package export surface needed by the new models.
- Add contract and domain tests under tests/contract/ and tests/unit/domain/.

**Tests first**

1. Load every new example against its matching JSON Schema.
2. Reject unknown fields where the contract is closed.
3. Verify a canonical deck accepts one commander, partner pairs, and Background relationships without a fixed command-zone size.
4. Verify deck identity is independent of source, player, event, observation time, legal status, and ruleset version.
5. Verify event observations can reference one canonical deck many times and pod entries remain round/seat records.
6. Verify v1 schema examples still validate unchanged.
7. Verify the normalized-snapshot-manifest.v1 example binds the normalized snapshot ID, producing run ID, input source snapshot manifest ID/hash, source ID, status, schema/mapper/transform versions, normalized/audit artifact hashes, counts, finding/quarantine references, provenance, timestamps, and integrity/content digest.

**Implementation**

- Make v2 snapshot manifests retain v1 guarantees: COMPLETE/INCOMPLETE/FAILED status, approval status, adapter version, lifecycle timestamps, redacted compatibility summary, raw-object path/hash/byte metadata, pagination state, attribution, redistribution status, and snapshot/content hash.
- Add authoritative requests[] and objects[] records. Keep request_parameters_redacted explicitly derived for compatibility only.
- Define separate snapshot_content_sha256 and detached manifest digest fields; never overload a single digest field.
- Model card identity separately from printing identity and face identity.
- Model zones as explicit quantity-bearing records. Keep command zone variable-length and preserve source-declared command-zone roles without making them a legality authority.
- Model CanonicalDeck, DeckLegalityEvaluation, and DeckQualityEvaluation separately.
- Model EventDeckObservation, PodEntry, and ParticipantReference separately.
- Model normalized-snapshot-manifest.v1 as the authoritative identity/provenance contract for one normalization output; do not use dataset-manifest for this role.
- Define separate normalized-content and manifest-integrity digests using the canonical serialization rules from Task 3; do not overload one digest field.
- Keep combo requirements/results as feature data, not legality facts.
- Use stable machine-readable finding-code namespaces, for example acquisition.*, integrity.*, parse.*, resolution.*, legality.*, and quality.*.

**Verification**

Run the contract test subset and validate all examples. Confirm no v1 schema file changed in this task. Commit as feat(data): add foundation contracts and domain models.

---

## Task 2: Implement configuration ownership, source reviews, and current-use policy

**Files**

- Add focused configuration modules under src/commander_ai/config/: runtime.py, source_settings.py, dataset_settings.py, yaml_loader.py, source_registry.py, and current_use_policy.py.
- Add application ports/policies under src/commander_ai/application/: source_policy.py and configuration.py.
- Update source configuration files under configs/sources/ only where needed to express explicit status, endpoint/host allowlists, environment-variable names, limits, and filters.
- Add dataset configuration examples under configs/datasets/.
- Extend existing source review files under docs/03-data/source-reviews/, preserving their authoritative location.
- Add tests under tests/unit/config/ and tests/unit/application/.

**Tests first**

1. Accept only known fields and reject unknown fields in runtime, source, dataset, and operation configuration.
2. Verify local sync allows exactly APPROVED_LOCAL and APPROVED_REDISTRIBUTION.
3. Verify public export allows exactly APPROVED_REDISTRIBUTION.
4. Verify PROPOSED, REVIEWED, REJECTED, and PAUSED are blocked.
5. Verify a historical snapshot approval cannot override a current-use REJECTED, PAUSED, or takedown decision.
6. Verify source, dataset, experiment, and optimizer configuration cannot silently override one another.
7. Verify secrets are absent from serialized resolved configuration and error text.

**Implementation**

- Use separate typed configuration models. Global/runtime config owns data/artifact roots and safe defaults. Source config owns endpoint policy, credentials by environment-variable name, network limits, and source filters. Dataset config owns filters, split policy, near-duplicate policy, and exclusions. RulesetSnapshots remain separate inputs.
- Implement a source registry lookup that returns historical approval metadata and a separate current-use decision.
- Require a current-use decision for normalize, validate, report, build, and public export operations where source policy applies.
- Normalize all configured roots and enforce root-relative portable paths for persisted artifacts.
- Redact API keys, authorization values, cookies, secret query parameters, and other credentials before config snapshots or errors.
- Update source reviews with documented access, authentication, rate-limit, terms, redistribution, attribution, and recommended-use statements. Do not claim legal guarantees.
- Keep Archidekt, Moxfield, EDHREC, and cEDH Decklist Database assessment-only unless the source registry changes.

**Verification**

Run configuration and policy tests with every source status. Verify source adapters cannot be instantiated without an explicit source configuration and review record. Commit as feat(data): add source policy and typed configuration.

---

## Task 3: Add deterministic serialization, digest, and path primitives

**Files**

- Add src/commander_ai/adapters/storage/canonical_json.py.
- Add src/commander_ai/adapters/storage/digests.py.
- Add src/commander_ai/adapters/storage/path_policy.py.
- Add tests under tests/unit/adapters/storage/.

**Tests first**

1. Assert exact UTF-8 bytes for canonical JSON: lexicographically sorted keys, ensure_ascii=false, separators comma and colon, no trailing newline.
2. Assert objects[].sha256 changes for every raw-byte change.
3. Assert snapshot content digest uses exactly {"objects":[{"bytes":...,"raw_object_id":...,"sha256":"..."}]} with objects sorted by raw_object_id using Unicode code-point order.
4. Assert detached manifest digest hashes canonical manifest JSON after omitting only the detached/self-digest field.
5. Assert a path with an absolute prefix, .., alternate separators, or symlink escape is rejected.
6. Assert paths emitted into manifests are POSIX-style and root-relative.

**Implementation**

- Expose small pure functions for canonical bytes, raw-object SHA-256, snapshot-content SHA-256, detached-manifest SHA-256, and portable-root-relative path validation.
- Centralize the exact canonicalization algorithm in documentation and tests so no source adapter invents a digest convention.
- Treat text encoding, key ordering, list ordering, and omission rules as contract semantics.
- Make path validation operate on resolved filesystem paths for writes while persisting only normalized portable relative paths.
- Do not use a general-purpose utils.py, helpers.py, or common.py.

**Verification**

Run the storage tests and compare produced digest bytes to the contract examples. Commit as feat(data): add canonical artifact primitives.

---

## Task 4: Implement the shared immutable raw snapshot store and safe HTTP transport

**Files**

- Add src/commander_ai/adapters/storage/raw_snapshots.py.
- Add src/commander_ai/adapters/storage/snapshot_verifier.py.
- Add src/commander_ai/adapters/storage/archive_safety.py.
- Add src/commander_ai/adapters/http/transport.py.
- Add src/commander_ai/adapters/http/redirect_policy.py.
- Add src/commander_ai/adapters/http/redaction.py.
- Add sql/schema/007_snapshot_objects.sql for snapshot/request/object persistence.
- Add tests under tests/unit/adapters/storage/ and tests/unit/adapters/http/.

**Tests first**

1. Write bytes to a same-filesystem temporary object, finalize atomically, and verify no partially written final object is visible.
2. Verify a second snapshot/object ID collision cannot overwrite the first immutable object.
3. Simulate interruption, process failure before finalization, checksum mismatch, and disk/write failure; verify the resulting snapshot is non-consumable and auditable.
4. Verify COMPLETE verification rejects missing objects, invalid sizes, hash mismatches, duplicate object IDs, malformed manifests, and incorrect snapshot-content digests.
5. Verify HTTP raw capture uses the compressed/entity bytes returned by iter_raw() and parsing happens only after finalization.
6. Verify redirects to a non-allowlisted host are rejected, including redirect chains, and safe metadata never persists authorization, cookies, secret query parameters, or unsanitized redirect URLs.
7. Verify archive extraction rejects absolute paths, .. traversal, symlinks/hardlinks, and compressed/decompressed size-limit violations.
8. Verify an MTGJSON-style upstream checksum mismatch is reported without confusing it with the locally computed raw-object digest.

**Implementation**

- Let RawSnapshotStore own snapshot IDs, immutable layout, temporary paths on the target filesystem, streaming writes, SHA-256, byte counts, atomic finalization, collision protection, raw-object registration, manifest writes, and detached manifest digest.
- Persist one raw object per response body or downloaded archive. Preserve byte-for-byte source responses; never serialize individual logical records as raw.
- Record per-request method, sanitized endpoint, API version, sanitized parameters, retrieved timestamp, and request ID. Record per-object request ID, path, content type, byte count, local hash, optional upstream hash, checksum verification status, and optional logical-record count.
- Finalize objects and integrity metadata first. Finalize COMPLETE state and manifest last. Any failure before completion leaves INCOMPLETE/FAILED or equivalent non-consumable state.
- Implement bounded retries, 429/Retry-After handling, timeouts, connection-failure handling, respectful source-specific rate limits, and an identifiable user agent.
- Use an explicit safe persistence allowlist for HTTP metadata. Re-check host policy for every redirect destination. Do not persist credentials or secrets.
- Provide a verify_complete_snapshot port/use case that must run before any normalization path.
- Treat the snapshot/request/object SQL tables as derived local query/index/cache infrastructure. Raw objects and manifests remain authoritative and must be sufficient to rebuild those tables without reacquiring the source.

**Verification**

Run all storage/HTTP security tests offline with mocked responses and local stubs. Confirm source adapters only call the shared writer. Commit as feat(data): add immutable raw snapshot infrastructure.

---

## Task 5: Add staging, audit/quarantine, Parquet, and operation-run provenance

**Files**

- Add src/commander_ai/data_pipeline/staging/raw_locators.py.
- Add src/commander_ai/data_pipeline/staging/records.py.
- Add src/commander_ai/data_pipeline/provenance/run_manifests.py.
- Add src/commander_ai/data_pipeline/provenance/normalized_snapshot_manifests.py.
- Add src/commander_ai/data_pipeline/provenance/rows.py.
- Add src/commander_ai/data_pipeline/quality/finding_codes.py.
- Add src/commander_ai/data_pipeline/quality/quarantine.py.
- Add src/commander_ai/adapters/storage/parquet_tables.py.
- Add sql/schema/008_staging_audit_runs.sql for staging, provenance, audit, quarantine, and run references.
- Add tests under tests/unit/data_pipeline/.

**Tests first**

1. Verify every staging record retains source_snapshot_id, raw_object_id/path, and a JSON pointer, record index, byte range, or equivalent exact locator.
2. Verify parse failures can be quarantined without being forced into canonical invariants.
3. Verify all resolution attempts, including ambiguous and unresolved attempts, are persisted.
4. Verify audit/provenance/quarantine records are not emitted into curated tables.
5. Verify Parquet output schema and hashes are stable across identical runs.
6. Verify data-operation manifests contain git commit, lock hash, safe config snapshot/hash, input manifest hashes, schema/transform/policy versions, RulesetSnapshot IDs when applicable, seed when applicable, output hashes, timestamps, and status without secrets.
7. Verify a normalized operation rejects INCOMPLETE/FAILED snapshots and rejects COMPLETE snapshots failing integrity verification.
8. Verify normalization produces normalized-snapshot-manifest.v1 with its normalized snapshot ID, producing run ID, input source snapshot manifest ID/hash, source ID, status, version bindings, artifact hashes, row/count summaries, finding/quarantine references, provenance, timestamps, and integrity/content digest.

**Implementation**

- Keep raw response blobs immutable and separate from logical staging records.
- Define staging record status and structural validation finding codes separately from resolution, legality, and quality finding codes.
- Write normalized audit tables for provenance, locators, resolution attempts, quality findings, and quarantine.
- Write curated tables only after semantic quality policy has accepted a canonical record.
- Make Parquet and manifests authoritative derived artifacts; DuckDB is a local transformation/query/cache consumer.
- Use the existing run-manifest.v1 contract for sync, normalize, validate, report, and build runs. Bind portable artifact paths and exact input hashes through its generic fields; do not create a competing data-run schema or persist environment secrets.
- Produce normalized-snapshot-manifest.v1 after normalization and bind every normalized/audit Parquet artifact, hash, count, finding/quarantine summary, input snapshot manifest, mapper/transform version, and producing run ID. This manifest and its Parquet artifacts are authoritative and rebuildable; SQL/DuckDB rows are only derived local infrastructure.
- Ensure no domain/application module imports HTTP, DuckDB, PyArrow, or source-specific DTOs.

**Verification**

Run data-pipeline tests and architecture import checks. Commit as feat(data): add staging audit and derived artifact persistence.

---

## Task 6: Implement MTGJSON acquisition and parsing

**Files**

- Extend src/commander_ai/adapters/sources/mtgjson/settings.py.
- Extend src/commander_ai/adapters/sources/mtgjson/client.py.
- Extend src/commander_ai/adapters/sources/mtgjson/downloader.py.
- Extend src/commander_ai/adapters/sources/mtgjson/dto.py.
- Extend src/commander_ai/adapters/sources/mtgjson/parser.py.
- Extend src/commander_ai/adapters/sources/mtgjson/staging.py.
- Extend src/commander_ai/adapters/sources/mtgjson/__init__.py.
- Add small fixtures under tests/fixtures/mtgjson/ and tests under tests/unit/adapters/sources/mtgjson/.

**Tests first**

1. Parse a minimal AllPrintings-style fixture with one normal card, one double-faced card, one split card, two printings, identifiers, color identity, mana data, types/subtypes, rules text, and keywords.
2. Parse a minimal Commander deck-product fixture and preserve product/deck provenance.
3. Verify the raw compressed archive remains authoritative and extracted JSON is derived.
4. Verify upstream .sha256 is stored separately from local object SHA-256 and checksum verification has an explicit result.
5. Verify malformed records produce parse/structural findings with exact locators and are never silently dropped; generic quarantine behavior is covered by Task 5.
6. Verify card identity, printing identity, and face identity remain distinct.
7. Verify a COMPLETE snapshot with a missing/corrupt archive is rejected by shared integrity verification before parser input.

**Implementation**

- Use the documented MTGJSON bulk files and configured release/file filters. Keep all endpoint and host policy in source configuration.
- Download the compressed archive through the shared raw writer. Verify the published upstream checksum when available; never replace the local computed digest.
- Parse only after raw finalization and COMPLETE integrity verification.
- Preserve the source fields required for later canonical card construction: identifiers, color identity, mana cost/value, types/subtypes, rules text, keywords, faces, and legality-relevant fields.
- Preserve multiple printings, related faces, and official Commander precon/deck-product records.
- Emit source DTOs, staging rows, and parse/structural findings with exact raw locators. Do not create canonical cards or independently perform semantic quarantine; generic audit/quarantine behavior belongs to the data pipeline and canonical card construction belongs to Task 10.

**Verification**

Run MTGJSON fixture, contract, and adapter/application-boundary tests with fixtures, mocked ports, or a local HTTP stub. Do not invoke CLI commands in this task. Keep acquisition status controlled by the source registry. Commit as feat(data): add mtgjson adapter.

---

## Task 7: Implement Commander Spellbook acquisition and combo staging

**Files**

- Extend src/commander_ai/adapters/sources/commander_spellbook/settings.py.
- Extend src/commander_ai/adapters/sources/commander_spellbook/client.py.
- Extend src/commander_ai/adapters/sources/commander_spellbook/downloader.py.
- Extend src/commander_ai/adapters/sources/commander_spellbook/dto.py.
- Extend src/commander_ai/adapters/sources/commander_spellbook/parser.py.
- Extend src/commander_ai/adapters/sources/commander_spellbook/staging.py.
- Extend src/commander_ai/adapters/sources/commander_spellbook/__init__.py.
- Add fixtures under tests/fixtures/commander_spellbook/ and tests under tests/unit/adapters/sources/commander_spellbook/.

**Tests first**

1. Parse a documented combo response with combo ID, involved cards, prerequisites, results/effects, color identity, status, and source metadata.
2. Verify pagination state and raw-object locators survive across pages.
3. Verify missing optional fields remain explicit missing values.
4. Verify source card references, variant links, and commander-compatibility fields are preserved deterministically in staging records.
5. Verify only documented read contracts are consumed; undocumented scraping paths are rejected by configuration.
6. Verify combo data cannot be used by legality evaluation.

**Implementation**

- Use only configured/documented read endpoints and the shared snapshot store.
- Preserve every response body as an immutable raw object and map logical combo records to exact locators.
- Map documented responses into source DTOs and staging combo/variant rows only; retain source status, provenance, and exact raw locators. Do not emit canonical combo or other canonical domain records from this adapter.
- Keep Commander compatibility as source-declared feature data; legality continues to derive from card facts and RulesetSnapshots.
- Apply bounded pagination and fail closed on malformed pagination metadata.

**Verification**

Run Spellbook fixture, malformed-pagination, and adapter/application-boundary tests with fixtures, mocked ports, or a local HTTP stub. Do not invoke CLI commands in this task. Commit as feat(data): add commander spellbook adapter.

---

## Task 8: Implement TopDeck contracts and gated acquisition

**Files**

- Extend src/commander_ai/adapters/sources/topdeck/settings.py.
- Extend src/commander_ai/adapters/sources/topdeck/client.py.
- Extend src/commander_ai/adapters/sources/topdeck/downloader.py.
- Extend src/commander_ai/adapters/sources/topdeck/dto.py.
- Extend src/commander_ai/adapters/sources/topdeck/parser.py.
- Extend src/commander_ai/adapters/sources/topdeck/staging.py.
- Extend src/commander_ai/adapters/sources/topdeck/__init__.py.
- Add fixtures under tests/fixtures/topdeck/ and tests under tests/unit/adapters/sources/topdeck/.

**Tests first**

1. Verify missing API credentials fail with a stable redacted configuration error.
2. Verify configured PROPOSED or REVIEWED status blocks sync before any request.
3. Verify the client sends credentials only in the approved request location and never writes them to manifests/logs/errors.
4. Parse event, format, date, player reference, commander, decklist, standing, wins/losses/draws, round, and result fixtures.
5. Preserve round tables as source table records first.
6. Preserve source table records, format/structure semantics, and ambiguity findings in staging; defer EventDeckObservation and PodEntry canonicalization to Task 12.
7. Verify all participants, decks, round, pod identity, seat/result semantics, and winner/result are retained without creating independent 1v1 matches.
8. Verify source staff/attendee records are not treated as players unless the source contract explicitly identifies them as participants.

**Implementation**

- Implement documented TopDeck v2 request/response contracts and authentication through the configured environment-variable name.
- Preserve raw response bodies and per-request provenance through the shared writer.
- Add source-specific parsers for events, decklists, standings, rounds, tables, and result semantics.
- Preserve event, standing, decklist, round, and table source records as staging rows with exact locators. Task 12 decides whether the source semantics justify EventDeckObservation or PodEntry canonicalization.
- Leave acquisition blocked under the repository’s current status until approval changes; implementing contracts/client behavior does not authorize local sync.
- Treat ambiguous semantics as preserved source fields plus a stable finding code, not guessed canonical semantics.

**Verification**

Run mocked response, source-gate, and adapter/application-boundary tests without credentials. Ensure no live request or CLI workflow is required in normal CI. Commit as feat(data): add topdeck adapter contracts.

---

## Task 9: Implement Spicerack contracts and missing-data preservation

**Files**

- Extend src/commander_ai/adapters/sources/spicerack/settings.py.
- Extend src/commander_ai/adapters/sources/spicerack/client.py.
- Extend src/commander_ai/adapters/sources/spicerack/downloader.py.
- Extend src/commander_ai/adapters/sources/spicerack/dto.py.
- Extend src/commander_ai/adapters/sources/spicerack/parser.py.
- Extend src/commander_ai/adapters/sources/spicerack/staging.py.
- Extend src/commander_ai/adapters/sources/spicerack/__init__.py.
- Add fixtures under tests/fixtures/spicerack/ and tests under tests/unit/adapters/sources/spicerack/.

**Tests first**

1. Verify authentication and missing-credential redaction.
2. Parse event, decklist, player reference, standings, and result fixtures using Spicerack’s own schema.
3. Verify JSON and NDJSON/page response handling preserves exact response locators.
4. Verify missing pod information remains missing and is never synthesized from standings.
5. Verify source-specific status/result fields survive staging.
6. Verify current-use policy can block a previously acquired snapshot without rewriting it.

**Implementation**

- Use only the documented Spicerack API/access contract and source settings.
- Store raw response bodies through the shared writer and parse after finalization.
- Preserve events, decks, players, standings, and results as source DTOs and staging records only, without assuming TopDeck field names or emitting canonical observations.
- Preserve pod fields only when Spicerack explicitly supplies them; otherwise retain missingness and a quality finding. Task 12 performs any justified EventDeckObservation or PodEntry mapping.
- Keep the adapter acquisition gate independent from the parser and normalizer.

**Verification**

Run offline Spicerack fixtures, blocked/gated source tests, and adapter/application-boundary tests with mocked ports or a local HTTP stub. Do not invoke CLI commands in this task. Commit as feat(data): add spicerack adapter contracts.

---

## Task 10: Build the card catalog and deterministic resolution stage

**Files**

- Add src/commander_ai/data_pipeline/resolution/card_catalog.py.
- Add src/commander_ai/data_pipeline/resolution/card_resolution.py.
- Add src/commander_ai/data_pipeline/resolution/canonical_cards.py.
- Add src/commander_ai/data_pipeline/resolution/card_faces.py.
- Add src/commander_ai/data_pipeline/quality/resolution_reports.py.
- Add tests under tests/unit/data_pipeline/resolution/.

**Tests first**

1. Resolve by canonical source identifier and preserve the original source value.
2. Resolve by printing identifier, Scryfall identifier, or MTGJSON identifier where the catalog supports it.
3. Resolve exact Unicode-normalized names with explicit normalization policy.
4. Resolve only documented aliases from a versioned alias catalog.
5. Reject ambiguous and unresolved names without fuzzy guessing.
6. Verify split-card, double-faced, related-face, and alternate representation handling.
7. Verify every attempt records method, resolver version, normalization policy version, alias catalog version/hash, and card-catalog snapshot ID.
8. Verify resolution reports count total entries, exact matches, alias matches, ambiguous values, unresolved values, and failures.
9. Verify failed resolution rows move to quarantine/audit and are not deleted.

**Implementation**

- Build a canonical card catalog from MTGJSON cards/printings plus source identifiers.
- Define deterministic resolution priority: stable identifier, printing identifier, exact normalized name, documented alias; stop on ambiguity.
- Keep card concept, printing, and face identity separate.
- Preserve unresolved source strings, source snapshot/object locator, requested quantity, and all attempted candidates.
- Version resolver code and each normalization/alias/catalog input. Persist these versions in resolution results and dataset manifests.
- Make the resolution stage an explicit boundary between staging and canonical records.

**Verification**

Run resolver fixtures across all source formats and compare stable output hashes across repeated runs. Commit as feat(data): add deterministic card resolution.

---

## Task 11: Implement canonical decks, ruleset evaluation, fingerprints, and deduplication

**Files**

- Add src/commander_ai/data_pipeline/decks/canonical_decks.py.
- Add src/commander_ai/data_pipeline/decks/fingerprints.py.
- Add src/commander_ai/data_pipeline/decks/ruleset_selection.py.
- Add src/commander_ai/data_pipeline/decks/ruleset_evaluation.py.
- Add src/commander_ai/data_pipeline/decks/quality.py.
- Add src/commander_ai/data_pipeline/deduplication/exact.py.
- Add src/commander_ai/data_pipeline/deduplication/revisions.py.
- Add src/commander_ai/data_pipeline/deduplication/near_duplicates.py.
- Add src/commander_ai/data_pipeline/quality/dedup_reports.py.
- Add sql/schema/009_canonical_decks_evaluations.sql for canonical deck structure, legality/quality evaluations, and deduplication metadata.
- Add tests under tests/unit/data_pipeline/decks/ and tests/unit/data_pipeline/deduplication/.

**Tests first**

1. Verify structural fingerprint canonicalization is independent of input ordering and source-specific deck IDs.
2. Verify identical structural decks get identical deterministic canonical_deck_id values across independent runs.
3. Verify the fingerprint includes stable format family commander, command zone, main deck, sideboard if present, companion/other supported zones, card identities, and integer quantities.
4. Verify changing a card quantity or command-zone card changes the fingerprint.
5. Verify ruleset version/date never changes structural identity.
6. Verify partner and Background command zones are preserved while legality is delegated to RulesetSnapshot evaluation.
7. Verify a historical date chooses an applicable effective-dated RulesetSnapshot; no match yields unknown, never current-ruleset substitution.
8. Verify exact duplicates and cross-source duplicates are reported but raw records remain intact.
9. Verify revision and near-duplicate groups are derived metadata with explicit algorithm/threshold versions and never modify canonical identity.
10. Verify legality and quality evaluations are separate records and can differ for one canonical deck under different rulesets.

**Implementation**

- Use canonical JSON with sorted zones/cards and normalized quantities to compute the structural fingerprint.
- Set canonical_deck_id equal to the lowercase structural fingerprint unless an existing repository identity convention requires a documented deterministic UUIDv5 wrapper.
- Keep event/player/source observation fields outside the canonical deck.
- Implement singleton, 100-card, basic-land exception, color identity, Commander legality, command-zone legality, and banned-card hooks against versioned card facts and RulesetSnapshots.
- Store legality finding codes and evaluation context in DeckLegalityEvaluation; store completeness/resolution/missing-field findings separately in quality evaluation.
- Implement exact fingerprint counts, source overlap, revision grouping, and a versioned near-duplicate algorithm suitable for auditable reports. Do not introduce ML similarity.
- Treat the canonical-deck/evaluation/deduplication SQL migration as derived local infrastructure; canonical Parquet artifacts and their manifests remain authoritative and must rebuild it.

**Verification**

Run structural, legality, historical-date, and duplicate tests. Validate the schema migration without modifying existing v1 tables in place. Commit as feat(data): add canonical decks and evaluations.

---

## Task 12: Normalize event observations, pod entries, participants, and combos

**Files**

- Add src/commander_ai/data_pipeline/events/event_records.py.
- Add src/commander_ai/data_pipeline/events/event_observations.py.
- Add src/commander_ai/data_pipeline/events/pod_entries.py.
- Add src/commander_ai/data_pipeline/events/participants.py.
- Add src/commander_ai/data_pipeline/combos/normalized.py.
- Add sql/schema/010_event_observations_pods_combos.sql for event, observation, pod, participant, and combo persistence.
- Add tests under tests/unit/data_pipeline/events/ and tests/unit/data_pipeline/combos/.

**Tests first**

1. Verify one canonical deck can have many event observations without changing deck identity.
2. Verify final event placement/aggregate record stays in EventDeckObservation.
3. Verify pod round, seat, result, points, and placement stay in PodEntry.
4. Verify a four-player pod is not flattened to independent 1v1 matches.
5. Verify source-provided opaque participant IDs are source-scoped and names/handles are not copied into curated records.
6. Verify name-only participants receive event/snapshot-scoped synthetic references with no cross-event linkage.
7. Verify incomplete participant linkage is preserved as missing or a finding.
8. Verify combo cards, prerequisites, results/effects, status, and commander compatibility normalize without becoming legality facts.
9. Verify all event/pod/combo rows retain source provenance and exact raw locators.

**Implementation**

- Reuse or version existing pod.v1 semantics rather than introducing a competing pod representation.
- Use separate normalized tables/contracts for events, event-deck observations, pod entries, participants, and combos.
- Minimize participant data at the staging-to-curated boundary. Preserve source opaque IDs only when policy allows; otherwise store scoped synthetic references.
- Preserve source result semantics when ambiguous and add finding codes instead of guessing.
- Write combo-to-card and commander-compatible relationship projections as normalized feature data.
- Treat event/pod/combo SQL rows as derived local infrastructure; event, observation, pod, participant, and combo Parquet artifacts plus manifests remain authoritative and rebuildable.

**Verification**

Run event/pod privacy and multiplayer semantics tests plus fixture normalization. Commit as feat(data): add event pod and combo normalization.

---

## Task 13: Implement curated dataset builders and leakage-safe split policies

**Files**

- Add src/commander_ai/data_pipeline/splitting/group_promotion.py.
- Add src/commander_ai/data_pipeline/splitting/deck_completion_policy.py.
- Add src/commander_ai/data_pipeline/splitting/tournament_policy.py.
- Add src/commander_ai/data_pipeline/datasets/dataset_builder.py.
- Add src/commander_ai/data_pipeline/datasets/dataset_inspection.py.
- Add dataset configs under configs/datasets/: deck-completion.example.yaml and tournament-outcomes.example.yaml.
- Extend schemas/dataset-manifest.v2.schema.json and its example as needed without changing the existing v1 contract.
- Add sql/schema/011_datasets.sql only if the dataset-manifest contract requires persistent SQL state after a concrete gap review; artifact manifests remain the default.
- Add tests under tests/unit/data_pipeline/splitting/ and tests/unit/data_pipeline/datasets/.

**Tests first**

1. Verify completion records receive provisional time splits by explicit timestamp and cutoff.
2. Verify exact fingerprint, revision, and near-duplicate groups are formed from versioned policies.
3. Verify forward-only group promotion: the entire group receives the latest provisional split represented by any member, so TRAIN + TRAIN + TEST becomes TEST + TEST + TEST.
4. Verify no record is moved backward into an older split.
5. Verify tournament/outcome splits group by complete event and respect temporal cutoff.
6. Verify repeated canonical decks may appear in later tournament events and reports distinguish familiar versus unseen deck strata.
7. Verify optional cold fingerprint, cold command-zone, and cold/low-data commander benchmarks are separate policies.
8. Verify incomplete, unresolved, illegal, unknown, and quality-failed records are excluded according to task-specific policy and counted.
9. Verify every dataset manifest binds exact input snapshot IDs/manifests, transform/schema/policy versions, split policy/version, near-duplicate algorithm/threshold, exclusions, row counts, and output hashes.
10. Verify identical inputs/configs produce identical dataset IDs and Parquet bytes.

**Implementation**

- Keep curated as quality-policy-eligible canonical records. Build task-specific datasets as projections from curated data plus explicit exclusions.
- Make dataset configuration own filters, split strategy, exclusions, grouping policy, algorithm/version, thresholds, and seed.
- Keep deck-completion grouping separate from tournament event grouping; do not create one universal connected-component assignment.
- Add deterministic seed handling for any randomized operation, though the default split policy should be deterministic without randomness.
- Produce deck corpus, card co-occurrence corpus, tournament corpus, and combo corpus as separate task-ready artifacts with separate manifests.
- If the optional dataset SQL migration is required, keep it derived and rebuildable from task-specific Parquet artifacts and dataset manifests; it must never become the sole authority.

**Verification**

Build each dataset against small fixtures, inspect the manifest, and assert no cross-split leakage. Commit as feat(data): add curated dataset builders and split policies.

---

## Task 14: Implement source and dataset quality/audit reports

**Files**

- Add src/commander_ai/data_pipeline/reports/source_metrics.py.
- Add src/commander_ai/data_pipeline/reports/dataset_audit.py.
- Add src/commander_ai/data_pipeline/reports/report_writer.py.
- Add tests under tests/unit/data_pipeline/reports/.

**Tests first**

1. Verify report output has stable JSON keys and deterministic ordering.
2. Verify Markdown is a derived artifact from the same report data.
3. Verify per-source reports include snapshot date, raw size, record counts, Commander deck counts, unique commanders/cards, complete/incomplete decklists, date range, duplicates, resolution success, missing commanders, legality/unknown counts, and overlaps where available.
4. Verify the audit reports complete Commander decks, casual/competitive classification availability, usable outcomes, full pod availability, commander long tail/dominance, source duplication, unresolved cards, covered dates, historical legality unknowns, missing information, and training suitability.
5. Verify blocked/research-only sources are reported without attempting acquisition.
6. Verify report artifacts bind input manifest hashes and current-use policy decisions.

**Implementation**

- Implement concise human-readable default summaries and stable machine-readable JSON.
- Write long reports as portable-root-relative artifacts under the configured report root.
- Distinguish observed facts, missingness, unknown legality, quarantine, and exclusions; do not hide poor source quality.
- Classify sources for deck-completion training, performance modeling, audit-only, or research-only based on measured fields and documented policy.

**Verification**

Run report fixtures and compare exact JSON snapshots. Commit as feat(data): add dataset quality reports.

---

## Task 15: Wire application use cases and the existing CLI vocabulary

**Files**

- Add application ports under src/commander_ai/application/ports/: source_adapter.py, snapshot_store.py, data_pipeline.py, dataset_store.py, and reporting.py.
- Add use cases under src/commander_ai/application/use_cases/: source_commands.py, normalize_data.py, validate_data.py, report_data.py, build_dataset.py, and inspect_dataset.py.
- Add thin CLI groups under src/commander_ai/cli/: source_commands.py, data_commands.py, and dataset_commands.py.
- Modify only the CLI composition root needed to register the groups.
- Add tests under tests/unit/application/ and tests/unit/cli/.

**Tests first**

1. Verify cda source list shows status, local-sync eligibility, public-export eligibility, and research-only state.
2. Verify cda source review <source> emits concise human output and stable --json output.
3. Verify cda source sync <source> --config <path> uses the source gate and shared snapshot store.
4. Verify cda data normalize <snapshot-id> rejects incomplete/failed/unverified snapshots before parsing.
5. Verify cda data validate <normalized-snapshot-id> resolves normalized-snapshot-manifest.v1, verifies its referenced artifacts and hashes, and produces validation artifacts with stable error codes.
6. Verify cda data report <source|all> supports concise output, stable --json, and report artifact paths.
7. Verify cda dataset build --config <dataset-config> emits/binds a dataset manifest.
8. Verify cda dataset inspect <dataset-id> summarizes manifest counts/exclusions/hashes.
9. Verify exit codes and error codes are stable and secrets are redacted.
10. Verify CLI modules contain composition and argument handling only; business logic remains in application/data-pipeline modules.

**Implementation**

- Preserve the exact existing command vocabulary. Do not add data fetch or data prepare aliases.
- Make application use cases depend on protocols/ports, not HTTPX, DuckDB, PyArrow, or source DTO modules.
- Emit operation/run provenance for sync, normalize, validate, report, and build. Bind current-use decisions and input/output hashes. Normalize produces normalized-snapshot-manifest.v1; validate resolves and verifies that manifest before validating its artifacts.
- Keep source adapter instantiation source-specific and explicit; no global adapter registry that leaks source tables into domain semantics.
- Use the repository’s existing CLI output/error conventions.

**Verification**

Run CLI tests using local fixtures and mocked ports. Exercise the exact source sync, data normalize, data validate, data report, dataset build, and dataset inspect command paths against local stubs/fixtures; inspect help output and JSON output for stable fields. Commit as feat(data): add data foundation application commands.

---

## Task 16: Update schema storage, documentation, fixtures, and complete offline verification

**Files**

- Verify and test the migrations created in Tasks 4, 5, 11, and 12; verify any Task 13 dataset migration only if its concrete contract-gap review approved one. Do not create a second aggregate migration here.
- Add docs/03-data/implementation-guide.md.
- Extend existing acquisition, source-approval, configuration, storage, reproducibility, and CLI-catalog documentation.
- Extend docs/03-data/source-reviews/ for MTGJSON, Commander Spellbook, TopDeck, Spicerack, Archidekt, Moxfield, EDHREC, and cEDH Decklist Database.
- Add small deterministic end-to-end fixtures under tests/fixtures/data_foundation/.
- Add an offline workflow test under tests/e2e/test_data_foundation_workflow.py.
- Update .gitignore for configurable raw data, normalized/curated Parquet, DuckDB files, caches, secrets, temporary downloads, and generated reports while keeping small fixtures tracked.

**Tests first**

1. Run the complete offline workflow: source sync against local stubs -> COMPLETE snapshot -> integrity verification -> normalize -> validate -> report -> dataset build -> dataset inspect.
2. Run the same workflow twice and compare manifest/config/Parquet/report hashes.
3. Verify a corrupt COMPLETE snapshot is rejected before normalization and produces no curated/training output.
4. Verify interrupted and incomplete snapshots remain inspectable but cannot contribute downstream.
5. Verify source review and current-use gates block assessment-only or paused sources without network access.
6. Verify raw, staging/audit, curated, and task-specific datasets are visibly distinct in layout and documentation.
7. Verify deleting DuckDB leaves all authoritative raw/normalized/curated artifacts and manifests intact, and rebuilding local tables from them does not reacquire a source.
8. Verify no API key, auth header, cookie, secret query parameter, raw participant name, or absolute local path appears in persisted artifacts.
9. Verify no source adapter imports training, models, optimization, Forge, serving, or UI packages.
10. Verify all hand-written production files stay below the repository hard limit and split by responsibility where needed.
11. Verify git diff --check passes.

**Implementation**

- Document exact acquisition prerequisites, environment variables by name only, source approval/current-use gates, storage roots, raw/normalized/curated/audit outputs, snapshot immutability, integrity verification, report inspection, and reproducibility boundaries.
- Cite MTGJSON’s bulk-file documentation for downloadable datasets and the MTGJSON FAQ for checksum behavior.
- State explicitly that public redistribution requires APPROVED_REDISTRIBUTION; local storage permission and redistribution permission are separate.
- Document assessment-only sources without mass scraping or undocumented access. Use conservative wording such as “documented access appears to permit”.
- Document hash algorithms and canonical bytes exactly, including raw-object hashes, snapshot-content digest, and detached manifest digest.
- Document that SQL/DuckDB is derived local query/index/cache infrastructure only; raw snapshot manifests/raw objects and Parquet artifacts with versioned manifests are authoritative, and all local tables are rebuildable without reacquisition.
- Document the forward-only split rule and event-grouped tournament rule with examples.
- Document participant minimization and historical legality unknown behavior.
- Preserve existing v1 contracts and describe every new versioned contract/migration.

**Verification commands**

Run the repository-standard commands, adapting only to the actual configured tool names:

    uv run pytest
    uv run ruff format --check .
    uv run ruff check .
    uv run mypy src
    uv run python scripts/check_architecture.py
    uv run python scripts/check_file_sizes.py
    uv run python scripts/validate_examples.py
    uv run python scripts/validate_fixture_consistency.py
    git diff --check

Also run JSON Schema/example validation, focused security tests, the offline end-to-end workflow, and a hand-written scope review confirming no ML, optimizer, Forge, UI, serving, or unrelated milestone changes.

Do not run live source tests unless explicitly opted in. Do not commit raw downloads, Parquet corpora, DuckDB databases, caches, credentials, or temporary files.

Commit documentation/schema/verification changes as docs(data): document reproducible foundation workflow.

---

## Final self-review checklist

Before declaring the implementation complete, verify:

- All four primary source adapters have focused files, explicit config, source-review evidence, tests, and no duplicated snapshot-storage logic.
- MTGJSON compressed archives remain authoritative raw objects and upstream checksum metadata is separate from local digest metadata.
- Spellbook consumes documented read contracts only.
- TopDeck contracts/client exist but the current source gate still controls acquisition.
- Spicerack preserves missing pod information instead of synthesizing it.
- Raw blobs, staging records, canonical records, audit/quarantine, curated entities, and task-specific projections are distinct.
- Every staging and normalized observation can locate its producing raw bytes.
- COMPLETE snapshots are re-verified before normalization.
- Historical approval and current-use policy are separate.
- Canonical deck identity is deterministic and independent of ruleset date, source, player, and event.
- Command-zone legality remains RulesetSnapshot-authoritative.
- Event observations and pod entries are separate, and pods are never flattened into 1v1 outcomes.
- Resolution failures are retained and reported.
- Exact, cross-source, revision, and near-duplicate reports preserve raw data and do not alter canonical identity.
- Completion and tournament split policies are independent and leakage tests pass.
- Every dataset manifest binds exact inputs, policy versions, exclusions, counts, and hashes.
- CLI names match the repository vocabulary and output/error behavior is stable.
- Source assessments are extended in docs/03-data/source-reviews/; no new competing source-assessment directory exists.
- No secrets, large datasets, databases, or temporary files are tracked.
- The final engineering report includes actual measured statistics or clearly reports unavailable data because acquisition was gated/unavailable.
