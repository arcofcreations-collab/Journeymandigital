# Specification v2: method update (before any TEST run)

Written **2026-09-29, ~10:20 UTC**. At this point the TEST split had **not** been run by any version of the method. Everything in `SPEC_v1_FROZEN.md` still applies: users, hypothesis, baselines, DEV/TEST split, case generation, metrics, and pass thresholds T1–T4. **Only the mechanism changed**, for the reasons below. All the evidence behind these changes comes from the DEV split, the unit tests, and a clearly labelled **synthetic** null stress test (uniformly random dates with days ≤ 12, sorted and unsorted, n = 6…1000). That stress test is design data and is not reported as benefit evidence.

## Why v1 was changed

| # | Problem found | Where | Change |
|---|---|---|---|
| 1 | Weekday evidence counted repeated rows, which inflated chance evidence in event data | DEV (birdstrikes windows) | Weekday code runs over **distinct dates** |
| 2 | When rows are not in date order, the file-order code is noise and can outvote the real evidence (82 bits the wrong way on shuffled business days) | unit test | **Two-part code** per reading: min(file-order deltas, sorted grid + arrangement cost). The arrangement cost, log2 of the multiset permutations plus multiplicities, is identical for both readings |
| 3 | On structureless unsorted columns the margin in bits grows with the column's length, so a fixed threshold made confident coin-flip decisions (~50% of decisions wrong) | synthetic null | **Significance test.** Sequence evidence counts as self-evidently significant when its paired z-score is ≥ 3 (items paired by row, or by raw value for the grid). Otherwise it must pass a **randomisation test**: the better reading must be more compressible than the better reading of each of 39 surrogate columns in which a random half of the distinct values have day and month swapped (p < 1/40). Surrogate coins depend only on the unordered (day, month) pair, so the model stays symmetric |
| 4 | Sequence and weekday evidence can point in opposite directions | design | **Abstain on conflict**: opposite signs, each at least τ |
| 5 | A date-sorted file read the wrong way can be as compressible as the right reading, because a constant backward jump each month costs nothing extra | synthetic null (sorted, n = 1000: 5/150 wrong) | Step **direction** coded separately (adaptive binary code). Forward and backward are treated symmetrically, so there is no prior for either |
| 6 | Worst-case runtime 2.15 s for 100k rows on the surrogate path | T4 check | Surrogate test runs on a fixed random subsample of **2,000** rows (was 5,000) |

## Fixed parameters of method v2

* `WEEKDAY_WEIGHT = 1` (plain sum; no longer tuned).
* `MIN_Z = 3`, `N_SURROGATES = 39`, `SURROGATE_MAX_ROWS = 2000`. These are fixed a priori at conventional values, not tuned.
* `DEFAULT_THRESHOLD_BITS = 2`, chosen on DEV by the v2 selection rule in `bench/tune_dev.py`: maximise correct − 5 × silent-wrong, subject to silent-wrong ≤ 2%. DEV at τ = 2 gave 72.2% auto-correct, 0% silent-wrong and 27.8% abstain on 360 ambiguous DEV cases; τ = 4…20 gave 71.1% / 0% / 28.9%. The chosen τ also passed the synthetic-null check (≤ 2% wrong decisions per trial at every size).

## Rule-change disclosure

The DEV selection rule itself changed once, before this spec. The v1 rule ("maximise auto-correct subject to ≤ 2% silent-wrong") picked a setting that traded 4 correct answers for 4 silent errors. It was replaced by the utility rule above. Both are recorded in `docs/ACTIVITY_LOG.md`.
