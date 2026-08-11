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

## Operation runs and normalized snapshots

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
