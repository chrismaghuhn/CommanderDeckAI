# Commander Data Foundation Design

**Status:** Approved for implementation (amendments applied 2026-08-10)
**Date:** 2026-08-10
**Scope:** Combined M1-M3 data-foundation track only

## Goal

Build a reproducible, legally cautious, maintainable data foundation for Commander card, deck, combo, tournament, pod, result, provenance, validation, and reporting data. The foundation must preserve source evidence and support later task-specific datasets without implementing ML, optimization, Forge, gameplay, serving, or UI behavior.

## Scope and non-goals

This design covers:

- MTGJSON and Commander Spellbook acquisition and normalization;
- gated TopDeck.gg and Spicerack clients/contracts;
- immutable raw snapshots and provenance;
- raw-DTO, staging, resolution, canonical, audit, quarantine, and curated layers;
- card identity and printing identity;
- variable-size Commander command zones;
- structural deck fingerprints and derived duplicate reports;
- historical legality evaluation hooks;
- event observations and multiplayer pod entries;
- combo/card relationships;
- task-specific curated datasets and leakage-safe split preparation;
- configuration, CLI operations, reports, tests, and documentation.

This design explicitly does not implement model training, DeepSets, Set Transformers, reinforcement learning, optimizer behavior, Forge integration, gameplay agents, serving, or UI functionality.

## Existing decisions preserved

The implementation follows the repository's accepted decisions:

- Parquet and manifests are authoritative; DuckDB is a local transformation/query/cache layer.
- `oracle_id` is the canonical game identity; printings remain separate.
- raw, normalized, curated, and run snapshots are immutable.
- command zones are variable-length collections, not a single commander field.
- historical, temporal, grouped splits prevent leakage.
- source approval is a technical risk gate, not a legal guarantee.
- no LLM, external embedding service, or network access in domain/application/data-derived logic.

The repository currently labels M0 as the general project milestone. The user explicitly approved this data-foundation track as a bounded M1-M3 exception. No unrelated milestone work is authorized.

## Architecture

The dependency direction remains:

```text
domain
  ↑
application
  ↑
adapters / data_pipeline / evaluation
  ↑
cli
```

The domain contains source-agnostic structural types and stable finding/error codes. Application ports describe snapshot, source, repository, resolution, validation, report, and dataset operations. Concrete HTTP, filesystem, Parquet, DuckDB, YAML, and source-client behavior lives in adapters or data-pipeline implementations. Typer commands only compose and invoke application use cases.

Each source package owns settings, request construction, source-specific client behavior, DTO parsing, staging mapping, and logical-record locator creation. It does not own raw snapshot storage semantics and does not import another source adapter.

## Data flow and storage layers

The required sequence is:

```text
raw source blob
  → parse / structural validation
  → staging record
  → deterministic identity resolution
  → canonicalization
  → semantic quality evaluation
  → curated or quarantine
```

### Raw source blobs

Raw HTTP entity bodies, downloaded files, and compressed archives are stored byte-for-byte under:

```text
data/raw/{source}/{snapshot_id}/objects/
```

Persisted `path` values and locator paths are portable POSIX-style paths relative to the configured data/artifact root. They never contain a drive letter, leading root marker, `..` component, or machine-specific absolute prefix. Resolution must remain beneath the configured root without following symlinks or equivalent filesystem escapes.

The raw blob is finalized before decompression, decoding, or parsing. HTTP acquisition must use the transport's raw streaming interface so the stored bytes represent the response entity body before HTTP content decoding/decompression. Parsing and decompression happen only after finalization.

For an archive, the compressed archive is the authoritative raw object. Extracted members are derived views and retain an archive-member locator back to the original archive object.

### Snapshot verification gate

`COMPLETE` is necessary but not sufficient for downstream use. Before parsing or normalization, the consumer verifies:

- the manifest has valid structure and a valid detached manifest digest;
- every referenced object exists beneath the configured root-relative snapshot path;
- every object has valid byte-count metadata;
- locally computed object SHA-256 values match the manifest;
- the ordered object-hash manifest recomputes to the declared snapshot-content digest;
- object/request references and pagination state are internally consistent.

Any failure produces an `INTEGRITY_*` error and rejects the snapshot before parsing. A corrupt or incomplete object can never contribute to normalized, curated, or training-ready data merely because the historical manifest says `COMPLETE`.

### Logical source records and staging

Logical records are not raw blobs. A staging record retains its exact source evidence through:

```text
source_snapshot_id
raw_object_id
raw_object_path
json_pointer or record_index or equivalent
archive_member when applicable
```

Staging may preserve source names, identifiers, malformed quantities, missing commanders, source result semantics, and incomplete fields. It does not require canonical UUIDs or strict Commander legality invariants.

Parse and structural-validation failures are written to normalized/audit outputs with raw locators and stable codes. They are not coerced into canonical objects.

### Canonical, audit, quarantine, and curated layers

Normalized/audit outputs retain all resolution attempts, provenance, quality findings, parse failures, quarantine records, and source observations. `curated` is reserved for records eligible under a declared quality policy.

Curated datasets are task-specific projections from canonical and evaluation outputs. Each projection has its own dataset manifest, exclusion counts, table hashes, and split policy.

The normalized tables are:

```text
cards
printings
card_faces
decks
deck_cards
card_resolutions
deck_legality_evaluations
deck_quality_evaluations
events
event_deck_observations
pods
pod_entries
combos
combo_cards
quality_findings
provenance
quarantine
```

## Versioned contracts

Existing v1 contracts remain immutable. New persisted semantics use explicit versioned contracts rather than generic metadata fields.

### Source snapshot manifest v2

`source-snapshot-manifest.v2` is a semantic extension of v1. It retains:

- `COMPLETE`, `INCOMPLETE`, and `FAILED` status;
- approval status;
- adapter version;
- start and completion timestamps;
- redacted request parameters;
- raw object path, hash, byte count, and content type;
- pagination state;
- attribution requirement;
- redistribution status;
- explicit snapshot-content digest semantics, superseding the ambiguous v1 top-level `sha256` meaning.

It adds explicit request/object structures:

```text
snapshot:
  source_id
  source_snapshot_id
  adapter_version
  status
  started_at
  completed_at
  approval_status
  usage_status
  attribution_required
  redistribution_status
  snapshot_content_sha256
  request_parameters_redacted

requests:
  request_id
  sanitized_method
  sanitized_endpoint
  api_version
  format
  sanitized_parameters

objects:
  raw_object_id
  request_id
  retrieved_at
  path
  bytes
  content_type
  sha256
  upstream_sha256
  checksum_verification_status
  logical_record_count
```

`upstream_sha256` is always the separately supplied source checksum, while the local object digest and snapshot-content digest use the distinct meanings defined below. Record counts are object-level `logical_record_count` values; reports may aggregate them but no field is reused for a different scope. Safe metadata is persisted through an explicit allowlist. Authorization headers, cookies, API keys, secret query parameters, and unsanitized redirect URLs are never persisted.

Hash meanings in v2 are distinct:

- `objects[].sha256` is the lowercase hexadecimal SHA-256 of the exact immutable raw-object bytes;
- `snapshot_content_sha256` is the lowercase hexadecimal SHA-256 of the canonical UTF-8 bytes of an ordered object-hash document;
- the detached `manifest.sha256` sidecar is the lowercase hexadecimal SHA-256 of the canonical manifest JSON with no self-digest field.

The snapshot-content document is exactly:

```json
{"objects":[
  {"bytes":123,"raw_object_id":"object-a","sha256":"..."},
  {"bytes":456,"raw_object_id":"object-b","sha256":"..."}
]}
```

Objects are sorted by `raw_object_id` using Unicode code-point order. The JSON is emitted as UTF-8 with lexicographically sorted object keys, no insignificant whitespace, and only strings, non-negative integers, booleans, arrays, and nulls. The implementation uses the repository's locked canonical JSON serializer and tests the exact byte sequence. The manifest file is emitted using the same canonical serialization with the detached digest omitted; the sidecar is written only after the manifest bytes are finalized.

The v1 top-level `sha256` is treated by the compatibility reader as a legacy snapshot-content value only. It is never interpreted as a detached manifest self-digest. A v1-to-v2 migration preserves that legacy value in migration provenance while requiring the new explicit fields for v2 processing.

`request_parameters_redacted` is a derived v1-compatibility summary generated from `requests[]`. `requests[]` is the sole authoritative request-provenance representation; the summary is never independently edited or used to reconstruct request lineage. No field overloads raw-object, snapshot-content, and manifest-file digests, or object and snapshot record counts.

### Structural deck and evaluations

The new structural contract represents only deck structure:

```text
CanonicalDeck
  canonical_deck_id
  structural_fingerprint
  command_zone
  card_zones
  provenance
```

Structural identity is independent of legality and quality. The existing `deck.v1` contract is not mutated solely to perform this cleanup.

Legality is a separate contract:

```text
DeckLegalityEvaluation
  canonical_deck_id
  ruleset_version
  evaluated_at
  legal_status
  finding_codes
```

Quality and quarantine evaluations are also derived records. The same structural deck may be legal under one historical RulesetSnapshot and illegal under another without changing its structural identity.

### Observations and pods

Event-level final standings use a dedicated `EventDeckObservation` contract:

```text
event_id
canonical_deck_id
observed_at
participant_reference
participant_reference_scope
final_placement
aggregate_wins
aggregate_losses
aggregate_draws
source_result_semantics
provenance
```

Round/pod records use the existing `pod.v1` semantics or a compatible versioned successor:

```text
pod_id
event_id
round
seat
canonical_deck_id
result
points
placement
provenance
```

These are not combined into one broad observation contract. Pod records are never flattened into synthetic independent 1v1 matches.

Participant minimization is explicit:

- an approved source-provided opaque participant ID may be retained only in a source-scoped reference, never as a global project identity;
- when only a public name is available, the normalized layer creates an event-scoped synthetic reference, assigned deterministically within that event and not reused across events;
- when event linkage is not reliable, the record receives a snapshot/object-scoped reference or no participant reference and cannot be used for cross-event participant analysis;
- curated outputs never retain raw names, account handles, emails, or authorization data unless a separately approved requirement exists.

The source-to-reference mapping remains in restricted audit/provenance data. A simple unsalted hash of a plaintext name is never used as a global pseudonym.

### Other contracts

Additional versioned contracts will cover card-resolution attempts, printings/card faces where required, combos, dataset-specific split policies, data run manifests, and dataset manifests with exact input hashes, transform/policy versions, exclusions, counts, and outputs. Existing v1 schema examples continue to validate unchanged.

## Shared raw snapshot infrastructure

`RawSnapshotWriter`/`RawSnapshotStore` is shared infrastructure. It owns:

- temporary same-filesystem writes;
- streaming and incremental SHA-256 calculation;
- size and content checks;
- atomic finalization;
- collision protection;
- immutable directory layout;
- raw-object registration;
- request/object manifest persistence;
- crash-safe completion state.

Source adapters never duplicate these semantics. Objects are written and integrity-checked first. The COMPLETE manifest/state is finalized last. A crash, checksum failure, missing object, or validation failure leaves an INCOMPLETE/FAILED or otherwise non-consumable snapshot. Only a COMPLETE snapshot that passes the full snapshot verification gate may enter normalization; normalization must not use a status-only shortcut.

An existing completed snapshot is never overwritten, even if its content hash matches a new acquisition. Snapshot IDs and paths are collision-checked before finalization.

## Source approval and acquisition

Local synchronization is allowlist-based:

- `APPROVED_LOCAL`: allowed;
- `APPROVED_REDISTRIBUTION`: allowed;
- `PROPOSED`, `REVIEWED`, `REJECTED`, and `PAUSED`: blocked.

Public export/publish is separately allowlisted and requires exactly `APPROVED_REDISTRIBUTION`.

Snapshot approval is historical provenance: it records what was permitted when the immutable snapshot was acquired. Current use is evaluated separately from the current source registry and policy records. A current `REJECTED`, `PAUSED`, takedown, object exclusion, or explicit processing prohibition can block later normalization, dataset builds, or exports without rewriting the historical snapshot manifest. The current-policy version/hash is bound to every affected run.

Downstream processing therefore requires both:

1. a historically valid immutable snapshot and successful integrity verification;
2. a current-use policy decision allowing the requested operation.

Local processing uses the current local-use allowlist. Public export additionally requires both historical and current `APPROVED_REDISTRIBUTION` permission. Audit-only inspection may report a blocked snapshot, but it must not emit newly processed or redistributable records.

### MTGJSON

The adapter supports the explicitly configured `AllPrintings` and `AllDeckFiles` bulk inputs, including compressed archives and published checksum sidecars. Card metadata, identifiers, printings, faces, Commander-relevant fields, and official deck-product provenance are preserved. The downloadable files are documented by the [MTGJSON all-files page](https://www.mtgjson.com/downloads/all-files/); SHA-256 sidecar behavior is sourced from the [MTGJSON FAQ](https://www.mtgjson.com/faq/).

### Commander Spellbook

The adapter consumes only documented read contracts from the configured REST endpoint or approved export. The documented API exposes public read endpoints such as cards and variants. Undocumented scraping and inferred private endpoints are out of scope.

### TopDeck.gg

The adapter implements the documented Tournaments v2 request and response contracts, API-key environment lookup, EDH format filters, standings/decklist fields, and source table records. Round tables are canonicalized as multiplayer pods only when format and structure justify that interpretation. Acquisition remains blocked while the repository source config is not approved.

### Spicerack

The adapter implements the documented public decklist export contract, API-key environment lookup, Commander format filtering, JSON/NDJSON parsing, event and standings/decklist staging, and missing-pod reporting. No pods are synthesized when the source does not supply pod structure.

### Research-only sources

Archidekt, Moxfield, EDHREC, and cEDH Decklist Database receive source-review records only. No mass scraping, anti-bot bypass, undocumented API use, or automatic acquisition is implemented without an approved access and storage path.

## HTTP and archive security

Shared HTTP behavior includes:

- explicit host allowlists;
- bounded retries and `Retry-After` handling;
- timeouts;
- safe user-agent identification;
- response-size and compressed/decompressed-size limits;
- content-type checks;
- raw entity-body streaming;
- redacted errors and metadata;
- redirect validation against the same host policy for every destination.

Archive extraction rejects absolute paths, `..` traversal, links, and equivalent filesystem escapes. Interrupted downloads, process failure before finalization, checksum mismatch, malformed pagination, missing credentials, unknown configuration fields, secret leakage, and corrupt COMPLETE manifests are explicit tested failure paths.

## Card resolution and canonical identity

Resolution order is deterministic:

1. source-supported canonical identifiers;
2. exact known cross-source identifiers;
3. Unicode-normalized exact names and documented aliases;
4. explicit split/face representations;
5. ambiguous or unresolved result.

No fuzzy guessing is used. Every attempt records the original source value, raw locator, method, status, candidates, canonical identity when available, and failure code. It also binds:

```text
resolver_version
normalization_policy_version
alias_catalog_version/hash
card_catalog_snapshot_id
```

Canonical card identity and printing identity remain separate. A change to normalization or aliases creates a new resolver/policy version and cannot silently reinterpret an existing resolution record.

## Deck identity, legality, and deduplication

The structural fingerprint is versioned and hashes a canonical representation of:

```text
format family = commander
sorted command-zone oracle IDs and quantities
sorted (zone, oracle_id, quantity) for non-command zones: mainboard,
sideboard, companion, and any other supported structural card zone
```

The command zone is included exactly once by the dedicated command-zone component; non-command zones are included exactly once by the `(zone, oracle_id, quantity)` component. The canonical representation uses the repository's canonical JSON serialization: UTF-8, lexicographically sorted object keys, no insignificant whitespace, stable array ordering, and integer quantities. `canonical_deck_id` is exactly the lowercase hexadecimal structural fingerprint, so identical structures produce the same ID across independent runs. The fingerprint algorithm/version is recorded separately and is not a RulesetSnapshot ID.

The stable `commander` format-family identifier is used in the fingerprint. A temporal ruleset or banlist version such as `commander-2026-02-09` is never included. Source ID, title, player, event, standing, provenance, and evaluation status do not affect structural identity.

Command-zone legality is decided only by canonical card facts plus the applicable RulesetSnapshot. Explicit source-declared partner/background roles may be preserved as evidence, but they do not become an independent legality authority.

Historical legality selects a RulesetSnapshot by explicit effective dates. If no authoritative applicable snapshot can be resolved, the evaluation is `unknown`; the current ruleset is never substituted.

Deduplication reports source-object duplicates, exact structural fingerprints, source deck revision groups, cross-source overlap, and versioned near-duplicate clusters. Near-duplicate membership is derived metadata and never changes canonical deck identity.

## Dataset-specific splits

Deck-completion datasets use a forward-only promotion policy:

1. assign each record a provisional split from its observation/deck timestamp and the dataset temporal cutoffs;
2. form the dataset's exact-fingerprint, source-revision, and versioned near-duplicate groups;
3. assign every member of a group to the latest provisional split represented by any member;
4. never move a later observation backward into an earlier split.

For example, a group with provisional `TRAIN`, `TRAIN`, and `TEST` membership becomes `TEST`, `TEST`, `TEST`. This may reduce training volume, but it prevents a later near-duplicate from promoting future information into training.

Tournament/outcome datasets use:

- temporal cutoff;
- complete-event grouping.

Repeated canonical decks may occur in later events. Outcome reports include familiar-versus-unseen deck strata rather than globally binding every event containing the same deck. Optional strict benchmarks include cold fingerprint, cold command zone, and cold/low-data commander variants. Near-duplicate algorithm, threshold, group version, and forward-promotion rule are bound in the dataset/split manifest and covered by leakage tests.

Every dataset manifest binds the exact input snapshot/manifest IDs, code and dependency-lock information, schema/transform/policy versions, split policy and near-duplicate threshold, exclusions, counts, output hashes, RulesetSnapshots, and explicit seeds where randomness is used.

## CLI and configuration

The existing CLI vocabulary is preserved:

```text
cda source list
cda source review <source>
cda source sync <source> --config ...

cda data normalize <snapshot-id>
cda data validate <normalized-snapshot-id>
cda data report <source|all>

cda dataset build --config <dataset-config>
cda dataset inspect <dataset-id>
```

Commands remain thin composition-root adapters. Human output is concise by default, `--json` is stable where supported, and long reports are written as artifacts with stable error and exit codes.

Configuration ownership remains separate:

- global/runtime config: data/artifact roots and safe runtime defaults;
- source config: endpoints, host allowlists, secret environment names, timeouts, retries, rates, page/download limits, source filters;
- dataset config: filters, task inclusion/exclusion, split policy, near-duplicate algorithm/version/threshold;
- RulesetSnapshots: separate versioned inputs;
- experiment and optimizer config: outside this milestone and not consumed by data-source code.

Unknown fields fail validation. No configuration class silently overrides another. Resolved config snapshots and artifact references use the same portable, root-relative, non-escaping path policy as raw manifests.

## Reproducible operation runs

`source sync`, `data normalize`, `data validate`, `data report`, and `dataset build` emit or bind operation/run provenance. Derived operations bind, where applicable:

- git commit;
- dependency-lock hash;
- resolved non-secret config snapshot/hash;
- input snapshot and manifest hashes;
- schema, transform, and policy versions;
- RulesetSnapshot IDs;
- current source-registry/use-policy hash and decision;
- explicit seeds;
- output hashes;
- status and timestamps.

Resolved API keys, authorization values, cookies, and other secrets are never included. External acquisition is `EXTERNAL` reproducibility: the immutable raw snapshot is the reproducible boundary for all downstream work.

## Stable failure namespaces

Finding and error codes use explicit namespaces/stages to prevent collisions:

```text
ACQ_*       acquisition and approval
POLICY_*    current-use, takedown, and export policy
INTEGRITY_* raw object/snapshot integrity
PARSE_*     structural parsing
RESOLVE_*   identity resolution
LEGAL_*     Ruleset-based legality evaluation
QUALITY_*   semantic quality evaluation
SPLIT_*     dataset split/leakage checks
CONFIG_*    configuration
SECURITY_*  secret/path/host policy
```

Failure details identify source, snapshot, object, record locator, and entity IDs without including secrets or full raw responses.

## Testing strategy

Normal CI remains fully offline. Unit, contract, integration, property, golden, and tiny E2E tests use small fixtures, mocked responses, or local HTTP stubs. Live source smoke tests are explicitly opt-in and never required for contributors without private credentials.

Required tests include:

- raw undecoded HTTP byte preservation;
- shared writer atomicity, collision protection, and incomplete-state behavior;
- SHA-256 and upstream checksum verification;
- exact snapshot-content and detached-manifest hash canonicalization bytes;
- redirects to disallowed hosts;
- archive traversal/link rejection;
- compressed/decompressed size limits;
- interrupted downloads and process failure before finalization;
- malformed pagination and missing credentials;
- unknown configuration fields and secret/error redaction;
- COMPLETE manifests referencing missing/corrupt objects;
- current source-policy/takedown changes blocking later processing without rewriting snapshots;
- source DTO parsing and raw locators;
- staging, resolver provenance, deck fingerprints, command zones, and observations;
- deterministic deck IDs remaining stable across RulesetSnapshot changes;
- Ruleset-based historical legality and unknown-ruleset behavior;
- duplicate and versioned near-duplicate reports;
- separate deck and tournament split policies;
- forward-only temporal group promotion and leakage boundaries;
- participant-reference minimization and absence of global name-derived identities;
- portable path and root-escape rejection;
- combo relationships;
- Parquet/DuckDB round trips;
- CLI gate, report, and dataset-build behavior;
- architecture boundaries, file sizes, schema examples, and `git diff --check`.

## Documentation deliverables

Use the repository's authoritative source-review path:

```text
docs/03-data/source-reviews/
```

Add:

```text
docs/03-data/implementation-guide.md
```

Update the existing acquisition, source-approval, source catalog/review, configuration, storage, reproducibility, and CLI-catalog documentation. Documentation must distinguish local acquisition approval, credential requirements, approval-gated sources, local storage permission, redistribution permission, raw/staging/normalized/audit/curated artifacts, and reproducibility boundaries.

## Completion criteria

The implementation is complete only when:

- approved MTGJSON and Commander Spellbook acquisition paths exist;
- TopDeck and Spicerack clients/contracts exist and remain approval/credential gated;
- raw blobs are immutable and locatable;
- only COMPLETE snapshots normalize;
- provenance/manifests and run metadata are complete and secret-safe;
- deterministic card resolution and audit reports exist;
- structural deck identity is separate from legality/quality evaluations;
- variable command zones and additional zones are supported;
- deck fingerprints and exact/near duplicate reports exist;
- event observations and multiplayer pods remain separate;
- combo data is normalized without becoming legality authority;
- historical RulesetSnapshot selection is explicit;
- task-specific curated datasets and split policies exist;
- source reviews cover all requested research-only sources;
- tests, lint, type checking, architecture checks, schema validation, and `git diff --check` pass;
- no ML, optimizer, Forge, gameplay, serving, or UI work is introduced.
