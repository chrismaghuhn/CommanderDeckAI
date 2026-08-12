# Data-foundation implementation guide

This guide describes the reproducible, legally cautious data path for the
Commander data foundation. It covers acquisition, immutable evidence,
staging, canonicalization, quality evaluation, audit/quarantine, reports, and
task-specific datasets. It does not cover model training, optimization, Forge,
serving, or UI work.

## Prerequisites and roots

Use Python `>=3.12,<3.14` and the repository lockfile:

```text
uv sync
```

The default CLI composition uses repository-local `data/` and `artifacts/`.
Applications that need external storage pass
`RuntimeConfig(data_root=..., artifact_root=...)` to the composition root;
persisted manifests contain only portable root-relative paths or the
non-reloadable `<external-root>` marker.
Do not put raw snapshots, Parquet corpora, DuckDB files, credentials, or cache
fragments in Git.

Historical Commander rulesets are separate immutable inputs under
`<data-root>/rulesets/*.json`. Each file must satisfy the existing
`ruleset.v1`/`RulesetSnapshot` contract. The default CLI composition injects a
read-only provider for this directory; it does not download or infer a current
ruleset. The provider records both the ruleset contract hash and the exact file
byte hash in operation provenance.

## Source review and approval

Before a source can be synchronized, its full typed `SourceRegistry` entry must
bind source settings and historical approval metadata. A current-use decision is
required for downstream processing and export when the operation policy requires
one.
The individual files under `configs/sources/` are not a registry substitute.
For the application commands, provide the reviewed registry through the
`COMMANDER_AI_SOURCE_REGISTRY` environment variable or pass the registry path
through the repository's runtime composition. The variable contains a path,
never credentials.
The acquisition gate is an allowlist:

| Operation | Allowed status |
| --- | --- |
| local `source sync` | `APPROVED_LOCAL`, `APPROVED_REDISTRIBUTION` |
| public export/publish | `APPROVED_REDISTRIBUTION` and current-use `ALLOWED` |
| all other approval statuses | blocked |

`PROPOSED`, `REVIEWED`, `REJECTED`, and `PAUSED` remain blocked. A later
takedown or current-use prohibition can block an old snapshot without changing
its immutable acquisition provenance. Credential settings contain environment
variable names only; they never contain key values.

Research-only sources are documented in
`docs/03-data/source-reviews/` and are not mass-scraped.

## Reproduce a source snapshot

The normal command vocabulary is:

```text
uv run cda source list --json
uv run cda source review mtgjson --json
uv run cda source sync mtgjson --config path/to/reviewed-source-registry.yaml --json
```

The sync configuration must be a reviewed `SourceRegistry`, not an individual
source settings file. The command fails closed when the registry is missing,
credentials are unavailable, or the source status is outside the allowlist.
Normalize, validate, report, dataset build, and export additionally fail closed
when the current-use decision is missing or prohibited. TopDeck and Spicerack
remain gated by their repository approval status and credential requirements.

Each response body or downloaded archive is archived byte-for-byte as a raw
object before parsing. Compressed archives remain the authoritative raw object;
extracted files are derived views. Raw objects are written through the shared
snapshot store using same-filesystem temporary files, SHA-256 calculation,
atomic publication, and collision protection. A `COMPLETE` manifest is written
last. Interrupted or failed work remains `INCOMPLETE`/`FAILED` and is not
normalizer input.

## Downstream workflow

Only a fresh integrity verification of a `COMPLETE` snapshot permits parsing:

```text
raw source blob
  -> parse and structural validation
  -> source DTO/staging row + exact raw locator
  -> deterministic card/deck identity resolution
  -> canonical record
  -> semantic quality/legality evaluation
  -> curated record or audit/quarantine record
```

Use the existing command vocabulary for downstream operations:

```text
uv run cda data normalize <snapshot-id>
uv run cda data validate <normalized-snapshot-id>
uv run cda data report all
uv run cda dataset build --config configs/datasets/completion-v1.yaml
uv run cda dataset inspect <dataset-id>
```

Normalization verifies every referenced raw object, byte count, object digest,
snapshot-content digest, detached manifest digest, and current-use policy before
parsing. Staging and audit records retain the source snapshot, raw object, and
JSON-pointer/record-index/byte-range locator. Unresolved and malformed records
are preserved; they are not silently discarded or guessed into canonical cards.

During canonicalization, the provider selects a ruleset only when its explicit
`effective_from`/`effective_until` range covers the observation date. No matching
or ambiguous input leaves legality `unknown`; downstream legal-only dataset
construction therefore remains fail-closed. The canonicalization run binds each
ruleset input by version ID, portable path, and exact file-byte hash. Existing
`ruleset.v1` and `canonical-snapshot-manifest.v1` contracts remain unchanged.

The authoritative staging output is the versioned
`normalized-snapshot-manifest.v1` plus its staging, audit, and quarantine
Parquet artifacts. After a verified normalized snapshot, the source-neutral
canonical output is the versioned `canonical-snapshot-manifest.v1` plus its
canonical, resolution, provenance, audit, and quarantine Parquet artifacts.
The authoritative task-specific output is its own `dataset-manifest` plus
task-specific Parquet and a bound `run-manifest.v1`.
`run-manifest.v1` is reused for source sync, normalize, validate, report, and
dataset build; no competing data-run contract is used.

Task-specific Parquet rows use their own versioned contracts and JSON Schemas;
the generic `CuratedRow` envelope is not the semantic authority for these
outputs. The current projections are `deck-corpus.v1`,
`card-cooccurrence.v1`, `tournament-corpus.v1`, and `combo-corpus.v1` under
`schemas/`, with small matching examples under `examples/`. The dataset builder
validates each emitted row through its matching domain contract before writing
Parquet, and the dataset manifest binds the resulting row schema and artifact
hash.

`cda data report <source>` publishes the existing source-quality report. For
`cda data report all`, the same measured `SourceMetricsInput` values also feed
an additional `dataset-audit-report.v1` JSON/Markdown artifact; both report
artifacts and their hashes are bound in the report's `run-manifest.v1` and
returned in the stable result summary. Sources without an acquired snapshot
appear only as explicit assessment-only/status rows with zero measured data.
They are never fetched as part of reporting, and their status does not create
a synthetic `SourceMetricsInput`.

Source adapters publish source DTOs and staging records only. The normalize
pipeline then performs deterministic identity resolution and source-neutral
canonicalization into the separately verified canonical snapshot. A staging
row is never relabeled as a combo or outcome record. `dataset build` consumes
only the verified canonical manifest and binds that exact input before a
training-ready dataset is published.

## Provenance and integrity

The three digest domains are separate:

- `objects[].sha256`: SHA-256 of exact raw bytes;
- `snapshot_content_sha256`: SHA-256 of the canonical ordered object-hash
  payload documented in `docs/03-data/storage-layout.md`;
- detached `manifest.sha256`: SHA-256 of the canonical manifest with only its
  documented self-hash field omitted.

Operation manifests bind Git state, dependency-lock hash, redacted config
snapshot/hash, input manifest/object hashes, schema and transform versions,
RulesetSnapshot IDs where applicable, seeds, output hashes, and timestamps.
DuckDB/SQL tables are derived local query/index/cache infrastructure. They can
be deleted and rebuilt from raw evidence and versioned Parquet artifacts without
reacquiring sources.

## Data quality and split policy

Reports must expose record counts, complete/incomplete decklists, unresolved
cards, duplicate/overlap counts, commander coverage, date ranges, missing pod
information, and quarantine findings. Bad results are reported rather than
hidden.

Deck-completion splits use temporal cutoffs plus exact fingerprint, revision,
and versioned near-duplicate groups. Groups use the conservative forward-only
promotion rule: provisional time splits are assigned first, then a group is
promoted to the latest split represented by any member; no later observation is
moved backward into training. Tournament/outcome splits group complete events
independently. Every dataset manifest records the split-policy version and
near-duplicate algorithm/threshold.

## Offline verification

Normal CI uses no live source or private credential. The small fixture workflows
in `tests/e2e/test_cli_data_foundation_workflow.py` and
`tests/e2e/test_data_foundation_workflow.py` prove the CLI/Application
source-sync-to-inspect path plus raw-to-normalized, report, dataset-build,
integrity, and rebuild behavior using local bytes only.
Opt-in live smoke tests, if added later, must remain separate from normal PR
verification.

Useful gates are:

```text
uv run pytest
uv run ruff check .
uv run mypy src
uv run python scripts/check_architecture.py
uv run python scripts/check_file_sizes.py
uv run python scripts/validate_examples.py
uv run python scripts/validate_fixture_consistency.py
git diff --check
```

`uv run ruff format --check .` must also be run; any pre-existing baseline
violations must be identified separately from new changes.

## Source status at this checkpoint

| Source | Status | Project use |
| --- | --- | --- |
| MTGJSON | READY for approved local sync | cards, printings, products, provenance |
| Commander Spellbook | READY for approved local sync | documented bulk variants JSON for periodic sync; REST only for sparse reads |
| TopDeck.gg | PARTIAL / BLOCKED | client and staging contracts; approval/key gate remains |
| Spicerack | PARTIAL / BLOCKED | client and staging contracts; approval/key gate remains |
| Archidekt | RESEARCH ONLY | no automatic acquisition |
| Moxfield | RESEARCH ONLY | no automatic acquisition |
| EDHREC | RESEARCH ONLY | aggregate reference only; no default scraper |
| cEDH Decklist Database | RESEARCH ONLY | manually reviewed/user-provided paths only |

No live source snapshot is part of the repository. Snapshot counts in reports
must therefore be measured from the configured external data root, not guessed
from fixtures or source documentation.
