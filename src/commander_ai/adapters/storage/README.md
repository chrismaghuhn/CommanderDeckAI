# Storage

DuckDB, Parquet, local artifact and manifest repository implementations.

Raw snapshots are authoritative byte evidence. `RawSnapshotStore` writes immutable
objects and manifests atomically; `COMPLETE` is a commit-like state that is only
published after all object writers close and object-directory metadata is flushed.
`SnapshotVerifier` binds manifest identity to the requested source/snapshot path and
must approve a `COMPLETE` manifest before normalization. SQL snapshot/object tables are
derived rebuildable caches, never the only source of truth.
