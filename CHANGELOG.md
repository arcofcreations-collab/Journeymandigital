# Changelog

## 1.0.0 (2026-09-29)

First release.

* `dmguard check` / `dmguard fix` command-line tool and `dmguard.resolve_column` Python API (standard library only, Python 3.9+).
* Resolves day-first vs month-first numeric dates by value validity, then by the calendar structure of the column (row-order steps, sorted sampling grid, weekdays) with a significance test; abstains with `AMBIGUOUS` (exit code 2) when the data cannot settle it.
* File-level consistency: an ambiguous column adopts the order proven by another date column in the same file.
* Benchmark on 22 held-out public date columns: 72.4% of fully ambiguous cases resolved correctly, 0 silent errors (see `docs/RESULTS.md`).
* `web/dmguard.js`: in-browser port with verdict parity to the Python tool (`web/parity_check.py`).
