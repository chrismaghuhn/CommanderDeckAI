# Speicherlayout

```text
data/
├── rulesets/{ruleset_version}.json
├── raw/{source}/{snapshot_id}/
│   ├── objects/
│   └── manifest.json
├── normalized/{source}/{snapshot_id}/
│   ├── *.parquet
│   └── manifest.json
├── canonical/{source}/{snapshot_id}/
│   ├── *.parquet
│   └── manifest.json
├── curated/{dataset_id}/
│   ├── train/
│   ├── validation/
│   ├── test/
│   ├── reports/
│   └── manifest.json
├── indexes/
├── reports/
├── runs/
└── cache/
```

`artifacts/` may contain the same run, report, and dataset outputs when an
external artifact root is configured. All persisted paths are portable and
root-relative; absolute machine paths are never part of a manifest.

`data/rulesets/` is the authoritative local input directory for existing
`ruleset.v1` JSON snapshots. The file provider reads only these versioned input
files; an absent directory or absent applicable effective-date snapshot produces
an unknown legality evaluation and never falls back to a current ruleset. The
embedded `RulesetSnapshot.sha256` remains the semantic hash in the frozen
contract, while run inputs bind the SHA-256 of the exact ruleset file bytes.

## Raw snapshot boundary (Task 4)

Raw object files preserve the exact HTTP entity or source archive bytes. The snapshot
writer streams bytes into a same-filesystem temporary file, verifies the byte count and
SHA-256, and publishes the object atomically. A manifest and its detached digest are
published only after every referenced object is final; the `COMPLETE` state is written
last. `INCOMPLETE` and `FAILED` snapshots are never normalizer input.

The verifier checks manifest structure, request/object lineage, object paths, sizes,
hashes, snapshot-content digest, and detached manifest digest before any parsing. The
raw files and manifests are authoritative evidence. SQL tables created by migration
`007_snapshot_objects.sql` are derived query/cache projections and may be deleted and
rebuilt from those files without reacquisition.

Persisted paths are portable root-relative POSIX paths. Absolute paths, traversal,
alternate-data-stream colons, trailing dot/space segments, Windows device names, and
symlink escapes are rejected before publication. File contents are fsynced; directory
fsync is required where available, with an atomic publication fallback only for known
unsupported directory operations. Other durability errors leave the snapshot
non-consumable.

## Regeln

- Raw und Curated sind immutable;
- `cache/` ist jederzeit löschbar;
- DuckDB-Dateien sind lokale Query-Caches, nicht die alleinige Wahrheit;
- Parquet-Dateien werden nach Source/Snapshot oder Split partitioniert;
- keine einzelne JSON-Datei mit Millionen Decks;
- große Listen werden gestreamt und nicht vollständig als Python-Objekte geladen.

## Kanonische Artefaktbytes und Digest-Domänen

Persistierte JSON-Manifeste verwenden genau dieselbe kanonische Serialisierung: UTF-8,
lexikografisch nach Unicode-Codepoints sortierte Objekt-Schlüssel, `ensure_ascii=false`,
die Trenner `,` und `:`, keine zusätzlichen Leerzeichen und keinen abschließenden
Zeilenumbruch. Array-/Listenreihenfolgen bleiben erhalten. Nicht-JSON-Werte werden
abgewiesen; sie werden nicht per String-Konvertierung in ein Manifest übernommen.

Die drei SHA-256-Domänen sind getrennt und dürfen nicht gegeneinander ausgetauscht werden:

- `objects[].sha256` ist der Hash der exakten, unveränderten Raw-Objektbytes. Jede Änderung
  an diesen Bytes erzeugt eine andere Eingabe für diese Digest-Domäne.
- `snapshot_content_sha256` ist der Hash der kanonischen Bytes von genau
  `{"objects":[{"bytes":123,"raw_object_id":"object-a","sha256":"..."}]}`.
  Die Einträge werden ausschließlich nach `raw_object_id` in Unicode-Codepoint-Reihenfolge
  sortiert; Request-Metadaten und ein Manifest-Digest gehören nicht in diesen Payload.
- Der detached `manifest.sha256`-Sidecar ist der Hash der kanonischen Manifestbytes nach
  Entfernung ausschließlich des dokumentierten Feldes `manifest_sha256`. Andere Felder,
  insbesondere verschachtelte Hashfelder oder ein `sha256`-Wert, bleiben Bestandteil der
  Eingabe. Der Sidecar ist kein Raw-Objekt- und kein Snapshot-Content-Digest.

`<external-root>` und `<repository-root>` sind ausschließlich nicht reloadbare Marker in
aufgelösten Konfigurations-Snapshots. Sie sind keine gültigen gespeicherten Artefaktpfade.
Alle tatsächlichen Artefaktpfade bleiben nichtleer, POSIX-artig, root-relativ und dürfen
keinen Symlink- oder Traversal-Escape aus dem konfigurierten Root ermöglichen.
Task-5 normalized outputs additionally contain separate rebuildable Parquet tables for
staging observations, audit findings/resolution attempts, and quarantine rows. Each
table is root-relative and carries an explicit layer in its Parquet metadata. The
frozen `normalized-snapshot-manifest.v1` is the authoritative Task-5 output and remains
unchanged. Its content digest and the producing run bind normalized, audit, and
quarantine artifacts; the verifier derives and checks portable paths, byte counts,
hashes, row counts, quarantine references, the run, the raw snapshot, and every Parquet
artifact before use. The versioned `normalized-snapshot-manifest.v2` is a separate
optional stricter extension, not a replacement for v1. The SQL
migration `008_staging_audit_runs.sql` is only a local index and can be dropped and
rebuilt from Raw manifests, Parquet, and the versioned normalized manifest.

Canonicalization publishes a separate `canonical-snapshot-manifest.v1`. Its canonical
Parquet table contains source-neutral card, deck, observation, participant, pod, and
combo envelopes; separate resolution, provenance, audit, and quarantine tables retain
all identity attempts and failures. The canonical manifest binds the normalized
manifest hash, producing run, table hashes, row counts, and raw-source verification.
It is the authoritative input for curated dataset projections; DuckDB remains only a
rebuildable local index.

All DuckDB/SQL tables introduced by the data-foundation migrations are derived
query, index, or cache infrastructure. They are never the only copy of an
observation, finding, provenance binding, or result. Deleting DuckDB must not
require reacquiring a source: raw manifests/raw objects plus normalized, canonical,
and curated Parquet and their manifests are sufficient to rebuild it.

The `DuckDBDerivedStore` adapter provides the executable rebuild boundary for local
cache checks. It consumes explicit Parquet artifact references, rechecks portable
paths, byte counts, and SHA-256 values, then materializes only derived row/index
tables. Its database file is disposable and is not included in any authoritative
manifest.
