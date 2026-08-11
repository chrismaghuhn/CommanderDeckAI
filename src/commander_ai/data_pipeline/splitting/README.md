# Splitting

Temporal/grouped split assignment and leakage-safe segment builders.

Completion datasets first receive provisional `train`, `validation`, and `test`
assignments from explicit timezone-aware cutoffs. Exact canonical fingerprints,
source revision groups, and versioned near-duplicate clusters are then formed
independently of the tournament policy. Each connected completion group is
promoted to the latest provisional segment represented by one of its members;
promotion is forward-only, so `train + train + test` becomes `test + test + test`.

Tournament datasets use complete event groups as their leakage boundary. A
canonical deck may therefore be familiar in a later event without forcing all
events containing that deck into one split. The resulting familiar/unseen
stratum is derived from training event observations.

Cold fingerprint, cold command-zone, cold commander, and low-data commander
benchmarks are separate derived policies. Their grouping metadata never changes
canonical deck identity. Every near-duplicate algorithm, version, threshold,
split policy, and exclusion policy is bound into the task-specific dataset
manifest.
