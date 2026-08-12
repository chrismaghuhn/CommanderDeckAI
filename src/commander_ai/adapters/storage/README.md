# Storage

DuckDB, Parquet, local artifact and manifest repository implementations.

Raw snapshots are authoritative byte evidence. `RawSnapshotStore` writes immutable
objects and manifests atomically; `COMPLETE` is a commit-like state that is only
published after all object writers close and object-directory metadata is flushed.
Every file is fsynced before publication. Directory fsync is required where the
platform supports it; Windows and explicitly unsupported directory operations use
the documented safe fallback of fsynced files plus the atomic link/replace boundary.
Unexpected durability errors are fatal and cannot publish a consumable `COMPLETE`.
`SnapshotVerifier` binds manifest identity to the requested source/snapshot path and
must approve a `COMPLETE` manifest before normalization. SQL snapshot/object tables are
derived rebuildable caches, never the only source of truth.

`DuckDBDerivedStore` is the executable local-cache boundary for rebuild checks. It
accepts explicit `ParquetArtifact` references, verifies each portable path, byte count,
and SHA-256, and rebuilds its derived tables from those Parquet bytes. The database can
be deleted and recreated without source access; Parquet artifacts and their versioned
manifests remain authoritative.
