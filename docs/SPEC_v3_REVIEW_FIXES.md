# Specification v3 (dmguard 1.1.0): fixes after external review

Written 2026-09-29, **before** re-running any evaluation of 1.1.0.

## What the review found in 1.0.0 (all four reproduced)

1. **Cross-column transfer.** A proven UK-format column decided a separate US-format column, turning 5 April into 4 May, and reported it as resolved.
2. **Lossy conversion.** `13/04/2021 12:30:00.123456` became `2021-04-13 12:30:00`, and the tool reported success.
3. **Confidently wrong on a mirror pattern.** US-format 1–12 January over several years was read as "the 1st of every month". Both are regular calendars; regularity gave a *preference*, not proof. This is the same class that produced every automatic answer in the 1.0.0 benchmark.
4. **Invalid cells and success.** 19 valid dates plus `BAD` gave exit code 0 and "all date columns resolved". Columns with 5–50% non-date values were silently skipped.

## Changes in 1.1.0

| # | Change |
|---|---|
| 1 | Adopting another column's proven order is **opt-in** (`--assume-same-convention`, method `file-consistency`). By default it is only a hint and the column stays AMBIGUOUS. |
| 2 | Conversion is **lossless**: each value keeps exactly its time precision (minutes, seconds, every fractional digit as written; `,` decimal becomes `.`; AM/PM becomes 24-hour). Two-digit-year expansion is reported as a note. |
| 3 | **Competing-pattern check.** A structural verdict is issued only if the losing order is *not* itself a regular calendar pattern. It counts as one when it keeps ≥ 30% of the winner's structure (relative to 39 scrambled copies), or when its sorted step sizes have entropy ≤ 2 bits. In that case only weekday evidence can still decide, because weekday patterns are not mirrored: it must reach the threshold and beat every scrambled copy. Otherwise the column is `AMBIGUOUS` with `likely = X` (method `competing`), and `--accept-likely` applies X (method `likely-accepted`). |
| 4 | A column is a date column when ≥ 50% of its non-blank values are numeric dates (was 95%). Any value that is not a valid date is listed with its line number, left unchanged by `fix`, and makes the exit code **2 (needs attention)**. |

**Where the new parameters came from.**
* 0.30 and 2.0 bits were fixed on synthetic design cases (weekly, monthly, quarterly, business days, 1–12 January, random) *and* after an adversarial unit test (`tests/test_misleading_patterns.py`, seed 424242) exposed a failure: shuffled 2–5 March over 5 years. That test set is therefore **not independent** evidence.
* Independent evidence comes only from a **fresh adversarial set** generated with a new seed (777, 60 columns per family, both renderings). It is run once, after this file is committed.

## Re-evaluation protocol

* **TEST split is no longer held out.** Its 1.0.0 results were seen, and the review's finding 3 concerns the class that dominated them. 1.1.0 numbers on TEST are a *re-run*, not fresh held-out evidence.
* **Methods:** pandas default, pandas dayfirst, DuckDB, range rule + ask, **dmguard 1.0.0** (frozen code, vendored), **dmguard 1.1.0 default**, **dmguard 1.1.0 `--accept-likely`**.
* **Fresh adversarial set** (`bench/adversarial_eval.py`, seed 777): families are monthly-on-day-k, a daily run each year, quarterly, weekly, business days, short daily run, and irregular. 40% of columns are shuffled. Truth is known by construction (synthetic, labelled as such).

## Criteria for 1.1.0 (set now)

| ID | Criterion | Threshold |
|---|---|---|
| R1 | Silent-wrong rate, dmguard 1.1.0 default, TEST ambiguous | ≤ 5% |
| R2 | Silent-wrong rate, dmguard 1.1.0 default, fresh adversarial set | ≤ 1% |
| R3 | Accuracy on unambiguous TEST cases | ≥ 99.9% |
| R4 | Lossless conversion and invalid-cell regression tests | all pass |
| R5 | One 100,000-row column | < 2 s |

The original **T2** (≥ 50% automatic correct answers on ambiguous TEST cases) is kept and reported for 1.1.0 default without lowering it. **It is expected to fail**, because the monthly class that supplied 1.0.0's answers is now reported as "likely" instead of resolved. The accuracy of the "likely" suggestions is reported separately.
