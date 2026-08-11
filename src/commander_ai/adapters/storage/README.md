# Storage

DuckDB, Parquet, local artifact and manifest repository implementations.

Raw snapshots are authoritative byte evidence. `RawSnapshotStore` writes immutable
objects and manifests atomically, and `SnapshotVerifier` must approve a `COMPLETE`
manifest before normalization. SQL snapshot/object tables are derived rebuildable
caches, never the only source of truth.
