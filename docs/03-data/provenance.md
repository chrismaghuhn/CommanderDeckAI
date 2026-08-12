# Provenienz

Jede normalisierte Zeile muss auf mindestens ein Source-Objekt zurückführbar sein.

## Erforderliche Felder

- `source_id`;
- `source_snapshot_id`;
- `source_object_id`;
- `retrieved_at`;
- `raw_sha256`;
- `adapter_version`;
- `mapper_version`;
- `approval_status`;
- `terms_reference`;
- `attribution_required`;
- `redistribution_status`.

## Transformationslinie

Datasetmanifeste listen alle Input-Snapshots und SQL-/Codeversionen. Modellmanifeste referenzieren genau ein Datasetmanifest. Optimizer-Ergebnisse referenzieren einen Score-Snapshot und ein Ruleset.

Ohne vollständige Linie gilt ein Artefakt als nicht releasefähig.

## Exakte Raw-Locators

Ein Staging-/Audit-Locator bindet immer `source_id`,
`source_snapshot_id`, `raw_object_id`, den verifizierten Raw-Pfad, optional den
Archivmember sowie JSON-Pointer, Record-Index oder Bytebereich. Der MTGJSON-
Parser liest den benannten Member erneut aus dem verifizierten komprimierten
Raw-Objekt und vergleicht optional angelieferte Bytes bytegenau; fremde Bytes
werden verworfen. Ein Locator aus einem anderen Source-Snapshot oder mit einer
anderen `source_id` ist ungültig. Extrahierte Dateien sind nur eine abgeleitete
Ansicht und keine neue Raw-Identität.

Vor der Persistenz wird ein Locator gegen das verifizierte Archiv und das
abgeleitete Dokument aufgelöst: der Archivmember muss existieren, ein
JSON-Pointer muss vorhanden sein und ein Record-Index muss im verifizierten
Dokument liegen. Der deklarierte Produktname des Raw-Objekts und der
Archivdateiname werden ebenfalls gegen den Parser-Produktkontext gebunden.
Normale Karten und Kartenfaces behalten unterschiedliche exakte Pointer und
Staging-Identitäten, damit Double-Faced- und Split-Fälle keine Locator-
Kollision erzeugen. Nicht decodierbare Quellbytes bleiben als Audit-/Staging-
Fehler erhalten und werden mit expliziter Base64-Kodierung, Byte-Länge und
Digest JSON-sicher dargestellt.

## Operation runs and normalized snapshots

Dataset inspection is fail-closed: the requested dataset ID, dataset-local output
paths, declared byte counts, output hashes, row counts, and the logical content digest
must all verify before an artifact is treated as inspectable. A failed dataset-manifest
publication removes only the newly written, still-unreferenced Parquet output; no
previous immutable artifact is overwritten.

`run-manifest.v1` is reused for `source_sync`, `normalize`, `validate`, `report`, and
dataset operations. A constructed run binds the full Git commit and dirty-worktree
state where applicable, dependency-lock hash, a portable configuration path and hash
of its redacted snapshot, input manifest/object hashes, schema/mapper/transform/policy
versions, RulesetSnapshot IDs, explicit seeds, output hashes, lifecycle timestamps,
status, and a detached canonical digest. Credential-shaped configuration values are
replaced before the snapshot is serialized.

`normalized-snapshot-manifest.v1` is a semantic normalization contract, not a dataset
manifest. Its deterministic ID/content digest binds the producing run, verified source
manifest ID/hash, source and transform versions, normalized/audit/quarantine table
hashes and row counts, findings, quarantine references, source provenance, and
timestamps. The frozen v1 JSON shape stays unchanged; detailed byte/row descriptors
are verified from the typed Parquet artifacts and persisted run bindings. Parquet and
this manifest are authoritative; the SQL tables are derived and rebuildable.

`canonical-snapshot-manifest.v1` is a separate semantic extension for the
source-neutral canonicalization stage. It binds exactly one verified normalized
manifest file hash, the canonical producing run, canonical/audit/resolution/
resolution-attempt/provenance/quarantine artifacts, deterministic counts, findings,
quarantine references, and source provenance. Canonical Parquet plus this manifest
remain authoritative; a missing or deleted DuckDB database must not require a new
source acquisition.

Dataset builds fail closed before writing Curated Parquet unless they have a completed
`run-manifest.v1`, a portable configuration snapshot/path, current-use decisions for
their source inputs, and hash-verified file-backed input manifests. Current-use
decisions are persisted as redacted policy bindings, while credentials and raw player
identifiers are not copied into Curated payloads. The producing run must be a
successful data-stage `dataset_build` run whose configuration hash and required input
references match the dataset request; a historical source status outside the local
approval allowlist blocks the build even when the current-use decision says ALLOWED.

## Rebuildable local indexes

DuckDB and SQL projections are convenience infrastructure for local queries and
indexes. They may be deleted and rebuilt from the immutable raw snapshot
manifests/raw objects and the versioned normalized/curated Parquet manifests.
They are not provenance authorities and must not be needed to reconstruct a
normalized or task-specific dataset.
