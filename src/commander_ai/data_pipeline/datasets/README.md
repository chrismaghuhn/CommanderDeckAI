# Dataset projections

The dataset pipeline projects curated canonical records into task-specific,
immutable Parquet artifacts. The `dataset-manifest.v2` artifact binds the exact
input manifests, configuration and policy versions, exclusions, counts, and
output hashes. `dataset_inspection` verifies those bindings without rebuilding
or acquiring source data.

Completion, tournament, co-occurrence, and combo projections have separate
record policies. DuckDB or other local indexes may be rebuilt from these
artifacts; they are never the authority for dataset contents.
