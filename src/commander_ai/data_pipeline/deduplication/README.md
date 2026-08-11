# Deduplication

Exact fingerprints, revision grouping and near-duplicate clustering.

The modules in this package produce rebuildable derived metadata only. Exact groups
use the deterministic canonical deck fingerprint, revision groups are source-scoped,
and near-duplicate clusters use the versioned quantity-weighted Jaccard policy
(`near-duplicate-v1`, default threshold `0.92`). None of these groups changes
canonical deck identity or deletes raw/source observations.
