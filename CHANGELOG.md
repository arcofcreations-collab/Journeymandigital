# Changelog

## 1.1.0 (2026-09-29)

Fixes the four defects found in an external review of 1.0.0.

* **No silent cross-column transfer.** A column's proven order is applied to another column only with `--assume-same-convention`; otherwise it is shown as a hint.
* **Lossless conversion.** `fix` keeps each value's exact time precision, including every fractional-second digit.
* **Mirror-pattern check.** When the losing order is itself a regular calendar pattern (e.g. "1st of every month" vs "1-12 January every year"), the column is `AMBIGUOUS` with a `likely` order, applied only with `--accept-likely`. Weekday evidence can still prove the order.
* **Invalid cells need attention.** Values that are not valid dates are listed by line number and left unchanged, and the exit code becomes 2. Columns that are mostly dates are no longer skipped.
* `fix` keeps the input file's line endings.
* New adversarial tests (misleading calendar patterns) and review regression tests; 39 tests.
* Re-evaluation: 0 silent errors on real TEST data and on a fresh adversarial set. Automatic answers on the real monthly data now require `--accept-likely` (see `docs/RESULTS.md`).

## 1.0.0 (2026-09-29)

First release.

* `dmguard check` / `dmguard fix` command-line tool and `dmguard.resolve_column` Python API (standard library only, Python 3.9+).
* Resolves day-first vs month-first numeric dates by value validity, then by the calendar structure of the column (row-order steps, sorted sampling grid, weekdays) with a significance test; abstains with `AMBIGUOUS` (exit code 2) when the data cannot settle it.
* File-level consistency: an ambiguous column adopts the order proven by another date column in the same file.
* Benchmark on 22 held-out public date columns: 72.4% of fully ambiguous cases resolved correctly, 0 silent errors (see `docs/RESULTS.md`).
* `web/dmguard.js`: in-browser port with verdict parity to the Python tool (`web/parity_check.py`).
