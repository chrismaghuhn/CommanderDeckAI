# Commander Deck-Completion Research Prototype

**Recommendation: YELLOW** — Commander-plus-context and hybrid signals are robust, but pure context-only B4 fails and target coverage is only 55.0%.

This is a throwaway completion/recovery experiment. It does not evaluate deck construction quality, legality beyond the approximate candidate filter, gameplay strength, M4 release-gate readiness, or production architecture.

## 1. Dataset

- Source: MTGJSON `AllDeckFiles.zip` ([official download documentation](https://mtgjson.com/downloads/all-files/)).
- Download URL: `https://mtgjson.com/api/v5/AllDeckFiles.zip`.
- Retrieved: `2026-08-11T12:08:30.944164+00:00`; SHA-256: `41b5c64a0a5797518cfb0d0584c5b2cba320ec955f775c40b4bbecfd66a298b1`.
- Usable Commander decks: **192**; unique command zones: **168**.
- Release-date coverage: `2009-08-26` to `2026-06-26`.
- Accepted types: `Commander Deck, MTGO Commander Deck`.
- Oracle-ID resolution: 100.0% resolved; 0 unresolved entries counted.

## 2. Splits

- Release-ordered grouped split: train **129**, validation **29**, test **34**.
- Exact deck fingerprints: 168 for 192 decks; 24 duplicate copies were kept in the same group.
- Near-duplicate grouping: same command zone and Jaccard >= 0.98; grouped deck clusters: 168.
- The split is temporal by MTGJSON product `releaseDate`, not the future frozen M4 benchmark.

## 3. Masking and candidate pool

- Each eligible deck receives deterministic `late_build` (5), `mid_build` (~20%), and `early_build` (~50%) masks; repeated card copies are collapsed to one oracle identity for ranking.
- Candidate pool: training-observed oracle IDs, excluding visible/command-zone cards and filtering by approximate color identity; pool size mean **2542.5**, range **964–4550**.
- Test target-in-pool coverage: **55.0%**; out-of-vocabulary targets are counted as misses, not dropped.
- Secondary in-vocabulary sensitivity: 101 of 102 examples contain at least one in-pool target; 1235 target labels are available for that sensitivity view.

## 4. B0–B5 test results

| Model | Recall@10 | Recall@25 | Recall@50 | NDCG@10 | NDCG@25 | NDCG@50 | MRR | n |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B0 | 0.002 | 0.005 | 0.013 | 0.006 | 0.006 | 0.009 | 0.034 | 102|
| B1 | 0.103 | 0.137 | 0.186 | 0.335 | 0.245 | 0.230 | 0.700 | 102|
| B2 | 0.103 | 0.137 | 0.186 | 0.335 | 0.245 | 0.230 | 0.700 | 102|
| B3 | 0.103 | 0.137 | 0.186 | 0.335 | 0.245 | 0.230 | 0.700 | 102|
| B4 | 0.007 | 0.020 | 0.027 | 0.015 | 0.019 | 0.020 | 0.049 | 102|
| B5 | 0.127 | 0.182 | 0.223 | 0.370 | 0.292 | 0.268 | 0.742 | 102|

The additional `B4_commander_context` diagnostic is present in `metrics.json` but is not substituted for the clean context-only B4 comparison.
Commander-plus-context diagnostic: NDCG@25=0.283; relative uplift vs B2=15.4%; paired bootstrap 95% CI=0.029 to 0.046.
In-vocabulary target sensitivity is reported in `metrics.json`; the primary table keeps out-of-vocabulary targets as misses.

## 5. Mask-regime results

| Regime | B2 NDCG@25 | B3 NDCG@25 | B4 NDCG@25 | B5 NDCG@25 | Samples |
|---|---:|---:|---:|---:|---:|
| late_build | 0.137 | 0.137 | 0.009 | 0.175 | 34 |
| mid_build | 0.211 | 0.211 | 0.021 | 0.254 | 34 |
| early_build | 0.388 | 0.388 | 0.027 | 0.447 | 34 |

## 6. Hypothesis checks

- H0, B1 > B0: 0.239 NDCG@25 difference.
- H1, commander signal: not estimable because every test command zone is unseen; B2/B3 fall back to B1.
- H2, visible context: clean B4 vs B2 is -0.227 absolute / -92.3% relative NDCG@25; CI -0.255 to -0.196.
- Commander-plus-context B4 is 0.038 absolute / 15.4% relative; CI 0.029 to 0.046.
- B5 vs B2 is 0.047 absolute / 19.0% relative NDCG@25; bootstrap 95% CI 0.033 to 0.059.

## 7. Anti-collapse diagnostics

| Model | Top-25 catalog coverage | Unique recommended cards | Mean train prevalence | Long-tail Recall@25 |
|---|---:|---:|---:|---:|
| B0 | 41.9% | 1912 | 2.1 | 0.8% |
| B1 | 1.6% | 72 | 33.0 | 0.0% |
| B2 | 1.6% | 72 | 33.0 | 0.0% |
| B3 | 1.6% | 72 | 33.0 | 0.0% |
| B4 | 18.5% | 843 | 1.0 | 15.8% |
| B5 | 9.4% | 427 | 25.6 | 2.6% |

## 8. Segment analysis

Segments are reported only with their sample counts. `high_data_commander` means at least two training decks, `low_data_commander` means one, and `unseen_cold_commander` means zero.

- `high_data_commander`: n=0; B2 NDCG@25=n/a; B4 NDCG@25=n/a.
- `low_data_commander`: n=0; B2 NDCG@25=n/a; B4 NDCG@25=n/a.
- `unseen_cold_commander`: n=102; B2 NDCG@25=0.245; B4 NDCG@25=0.019.

## 9. Interpretation and validity threats

- Completion/recovery quality is not construction quality and is not gameplay strength.
- The source is official/product Commander data, not a broad corpus of user-built casual decks; repeated precon and collector-edition patterns remain a major external-validity threat.
- Only exact and cheap same-commander near-duplicate grouping was attempted; revisions outside that rule may still cross splits.
- Candidate legality is approximate color-identity filtering, not a versioned Commander ruleset; no full legality claim is made.
- The temporal field is product release date, not the date a deck was authored or revised.
- Small test and commander-support counts make confidence intervals wide, especially for cold commanders.

## 10. Research conclusions

1. Dataset: MTGJSON AllDeckFiles, accepted Commander product types.
2. Usable decks: 192; unique command zones: 168.
3. Splits: release-ordered, exact/near-duplicate-grouped train/validation/test.
4. Masking: deterministic late/mid/early masks with collapsed oracle identities.
5. Candidate pool: train-observed cards with approximate color-identity filtering.
6. B0–B5: see the table above; B5 weights selected on validation only: `[0.5, 1.0, 0.5, 2.0]`.
7. Commander-specific signal: Commander-specific signal is not estimable here: every test command zone is unseen, so B2/B3 correctly fall back to B1.
8. Visible-deck context: Clean context-only B4 is weak, but commander-plus-context B4 and B5 both show robust held-out uplift.
9. Staple collapse: strong recommendation concentration is visible in the Top-25 catalog coverage diagnostic.
10. Segment conclusion: all test examples are unseen cold commanders; high-data and low-data commander segments are not estimable.
11. Biggest threats: source narrowness, small held-out support, approximate legality, and residual near-duplicate/revision leakage.
12. Matrix Factorization: a follow-up is plausible after broader deck coverage, but this pilot does not justify adding B6 now.
13. DeepSets: not justified by this throwaway pilot; no neural model was built.
14. Production change: make no production change; use this only to prioritize a broader, frozen M4-style completion benchmark.
15. Qualitative examples are in `example_recommendations.md`.

Final prototype-only recommendation: **YELLOW**.
