# Results

## dmguard 1.1.0: re-evaluation after the external review (current)

An external reviewer ran 1.0.0 and found four defects: cross-column convention transfer, lossy timestamps, a confident error on a mirror calendar pattern, and success reported despite invalid cells. All four were reproduced and fixed. See [`SPEC_v3_REVIEW_FIXES.md`](SPEC_v3_REVIEW_FIXES.md), which was committed before these numbers were produced. Raw outputs are in `bench/results/`: `raw_TEST.jsonl`, `summary_TEST.json`, `adversarial_777.json` and `perf_t4.json`.

**Read first:**
* The TEST split is **no longer unseen**: 1.0.0's results on it were known before 1.1.0 was designed. Its 1.1.0 numbers are a re-run.
* The fresh adversarial set (seed 777, 840 ambiguous synthetic columns) was generated and run **once**, after the spec was committed.

### Ambiguous cases: correct / silently wrong / flagged for a person

| Method | Real data, TEST (n = 1,246) | Fresh misleading patterns (n = 840, synthetic) |
|---|---|---|
| pandas default / `dayfirst=True` | 50.0% / **50.0%** / 0% | 50.0% / **50.0%** / 0% |
| DuckDB auto-detect | 50.0% / **50.0%** / 0% | 50.0% / **50.0%** / 0% |
| Range rule + ask | 0% / 0% / 100% | 0% / 0% / 100% |
| dmguard 1.0.0 (frozen) | 72.4% / 0% / 27.6% | 54.5% / **11.4%** / 34.0% |
| **dmguard 1.1.0 default** | **0.3% / 0% / 99.7%** | **28.3% / 0% / 71.7%** |
| dmguard 1.1.0 `--accept-likely` | 72.4% / 0% / 27.6% | 54.5% / **11.4%** / 34.0% |

Additional detail:
* **Silent-wrong for 1.1.0 default:** 0/1246 on TEST (Wilson 95% 0.0–0.3%; cluster bootstrap 0.0–0.0%) and 0/840 on the adversarial set.
* **Where 1.0.0 goes wrong on the adversarial set:** 94 of its 96 errors are in the "daily run each year" family (e.g. 1–12 January every year), which is the reviewer's case. The other 2 are short daily runs.
* **"Likely" suggestions** (applied only with `--accept-likely`) were right in 902/902 real TEST cases where one was made. On the adversarial set they were right in 220 of 316 (70%), because it contains mirror twins of both kinds by construction.
* **DEV:** 1.1.0 default 0/360 correct and 0 wrong; with `--accept-likely` 260 correct and 0 wrong (same as 1.0.0).
* **Unambiguous TEST cases:** 1,962/1,962 correct for 1.0.0 and for 1.1.0 (both modes).

### Criteria

| ID | Criterion | Result | Verdict |
|---|---|---|---|
| R1 | 1.1.0 default silent-wrong on ambiguous TEST ≤ 5% | 0.0% | PASS |
| R2 | 1.1.0 default silent-wrong on fresh adversarial set ≤ 1% | 0.0% | PASS |
| R3 | Unambiguous TEST accuracy ≥ 99.9% | 100% | PASS |
| R4 | Lossless conversion and invalid-cell regression tests | 5/5 pass (`tests/test_review_regressions.py`) | PASS |
| R5 | 100,000-row column < 2 s | 1.30 s worst case | PASS |
| T2 (original, not lowered) | Auto-correct ≥ 50% of ambiguous TEST cases | 0.3% (default); 72.4% only with `--accept-likely` | **FAIL** for the default |

### What changed in the claim

Every automatic answer 1.0.0 gave on real data came from monthly series dated on the 1st. Those have a mirror twin ("1–12 January every year"), so calendar regularity only *prefers* them; it does not prove them. The review showed the twin really does occur in data (US-format January runs), and 1.0.0 misread it.

1.1.0 therefore no longer resolves such columns by itself. It reports `AMBIGUOUS (likely X)` with both patterns explained, and the user or pipeline decides (`--accept-likely` or `--assume`). It still proves the order when the losing reading is not a regular pattern (weekly data, irregular events with enough rows), or when weekdays break the mirror. An example of the latter, on real data: 60 monthly S&P 500 closes dated on the first *trading* day, proven by weekdays alone (`demo/sp500_first_trading_day_uk.csv`).

The measured benefit of the default is now: **no silent errors** (versus 50% for pandas and DuckDB), plus an explained suggestion where the data leans one way. The measured benefit is **not** high automatic coverage.

---

## dmguard 1.0.0: original pre-registered evaluation (historical, superseded)

The numbers below are for the frozen 1.0.0 method (called `dmguard_v1_0_0` in the current raw files). They remain accurate for 1.0.0. The review showed that its automatic answers on monthly data were preferences rather than proof; see above.

All numbers are produced by `bench/run_eval.py` (raw per-case outcomes in `bench/results/raw_{DEV,TEST}.jsonl`, summaries in `bench/results/summary_{DEV,TEST}.json`). Method: dmguard 1.0.0 as frozen in commit `26bfe0e` (spec v2). Environment: Python 3.11.15, pandas 3.0.6, duckdb 1.5.6, 4-vCPU Intel Xeon VM.

**Benchmark nature: semi-synthetic.** The dates, their order, duplicates and gaps are real, taken from 37 public files pinned to commits. The DD/MM/YYYY and MM/DD/YYYY renderings and the row windows are generated, and every case is rendered both ways. This measures a *technical* property: how often each method loads the right dates. It does **not** measure user preference, adoption, or real-world prevalence.

## Pass / fail against the frozen criteria (held-out TEST split)

| ID | Criterion | dmguard | Best baseline | Verdict |
|---|---|---|---|---|
| T1 | Silent-wrong rate on ambiguous cases ≤ 5%, and ≤ 1/5 of pandas & DuckDB | **0 / 1246 = 0.0%** (Wilson 95%: 0.0–0.3%; cluster bootstrap over 18 source columns: 0.0–0.0%) | pandas 50.0%, DuckDB 50.0% | **PASS** |
| T2 | Auto-correct rate on ambiguous cases ≥ 50% | **902 / 1246 = 72.4%** (Wilson 69.8–74.8%; cluster bootstrap 61.2–77.2%) | range rule + ask: 0% | **PASS** |
| T3 | Accuracy on unambiguous cases ≥ 99.9% | **1962 / 1962 = 100%** (Wilson 99.8–100%) | DuckDB 96.6%, pandas 82.0% (rest raised errors) | **PASS** |
| T4 | One 100,000-row column < 2 s | **1.26 s** worst case (forced randomisation test); 0.49 s sorted panel; 0.21 s unambiguous | – | **PASS** |

## TEST split, full table (3,468 cases from 22 held-out source columns)

Ambiguous: both readings valid and different (1,246 cases from 18 source columns).

| Method | Correct | Silently wrong | Abstained / asked user | Error (visible) |
|---|---|---|---|---|
| pandas `to_datetime` default | 50.0% | 50.0% | 0% | 0% |
| pandas `dayfirst=True` | 50.0% | 50.0% | 0% | 0% |
| DuckDB `read_csv` auto-detect | 50.0% | 50.0% | 0% | 0% |
| Range rule + ask user | 0% | 0% | 100% | 0% |
| **dmguard** | **72.4%** | **0%** | 27.6% | 0% |

Unambiguous: 1,962 cases. dmguard, the range rule and DuckDB's sniffer never returned wrong dates. pandas raised an exception on 18.0% of cases, when the first value was ambiguous but a later value ruled its guess out. DuckDB left 3.4% of cases as text. Degenerate cases (day equals month in every value, 260): all methods 100%.

DEV split, for reference (tuning data, not independent evidence): dmguard 72.2% correct / 0% wrong / 27.8% abstain on 360 ambiguous cases; baselines as above.

## Where the benefit comes from (TEST, ambiguous cases)

| Group | n | dmguard correct | wrong | abstained |
|---|---|---|---|---|
| Monthly series dated on the 1st (7 source columns) | 1134 | 902 (79.5%) | 0 | 232 |
| Daily, business-daily or hourly windows (11 source columns) | 112 | **0** | 0 | 112 |
| Window of 6 rows | 304 | 4 | 0 | 300 |
| Window of 12 rows | 252 | 212 | 0 | 40 |
| Window of 24 rows | 228 | 224 | 0 | 4 |
| Window of 60 / 250 rows, and full columns | 462 | 462 | 0 | 0 |
| Original row order | 630 | 458 | 0 | 172 |
| Shuffled rows | 616 | 444 | 0 | 172 |

**Read this honestly.** On TEST, *all* of dmguard's gains came from monthly (first-of-month) series. Fully ambiguous windows of daily or hourly data are short runs inside days 1–12 of one month. dmguard abstained on every one of them: it never mislabelled them, and it never helped with them. The unit tests show weekly, business-day and shuffled business-day series being resolved, but the held-out benchmark contained no fully ambiguous examples of those kinds. So that capability is **not** demonstrated on held-out real data. Resolution needs about 12+ rows. Row order doesn't matter (shuffled ≈ original), because the method falls back to the order-free grid and weekday evidence.

## Post-hoc exploratory comparison (not pre-registered)

Added after the final novelty search. That search found that Liang 2025 resolves formats with a parser whose probabilities are learned from a corpus. Priors of that kind, such as "a field that is always 01 is the day", could handle first-of-month series without any calendar reasoning. As a stand-in I tested the simplest such rule, `bench/posthoc_value_prior.py`: *if exactly one field is constant, it is the day*.

| TEST ambiguous (n = 1246) | Correct | Silently wrong | Abstained |
|---|---|---|---|
| "Constant field = day" heuristic | 1134 (91.0%) | **108 (8.7%)** | 4 |
| dmguard | 902 (72.4%) | **0 (0%)** | 344 |

The heuristic resolves more monthly columns, including very short ones, but silently transposes the daily and hourly windows (DEV: 36/360 wrong). dmguard's demonstrated advantage over value priors is therefore **safety** (no silent errors, explicit abstention), not coverage. The heuristic would fail T1 (> 5%). This comparison was designed after TEST results were known, so it is exploratory.

## Synthetic stress test (design data, not benefit evidence)

Uniformly random dates with days ≤ 12 over 3 years: no calendar structure, 150 columns per cell, method v2 at τ = 2. **Wrong** decisions per 150 columns:

| n rows | 6 | 12 | 24 | 60 | 250 | 1000 |
|---|---|---|---|---|---|---|
| unsorted | 0 | 1 | 2 | 2 | 1 | 3 |
| sorted (true order) | 0 | 1 | 0 | 0 | 0 | 0 |

When the rows are sorted, date order is itself real structure, so decisions on those columns are legitimate; the sorted row counts only the wrong ones. Worst cell: 3/150 = 2% wrong.

## Required minimum cases (end-to-end, `demo/run_demo.sh`, output in `demo/DEMO_OUTPUT.txt`)

* **Ordinary:** a UK-style export of monthly US CPI (2015–2019). pandas silently reads 60 monthly values as 1–12 January of each year (span 2015-01-01 .. 2019-01-12); DuckDB happens to be right. dmguard: DMY by calendar structure (62.8 bits), and `fix` writes ISO dates.
* **Challenging:** a US-style panel of 14 industries × 24 months with shuffled rows. DuckDB silently reads it day-first (span 2005-01-01 .. 2006-01-12); pandas happens to be right. dmguard: MDY (24.5 bits; one step size, "1 month", versus two).
* **File-level consistency:** an ambiguous column adopts the order settled by its neighbour.
* **Genuine ambiguity:** one year of monthly data. `AMBIGUOUS`, exit code 2, and `--assume` records the user's decision.
* **Representative miss:** 8 consecutive days early in a month. `AMBIGUOUS` (0.0 bits): no help.
* **Invalid input:** mixed formats → `INCONSISTENT`; version strings → not a date; empty file / missing file → error exit 1. Undecodable and binary files are covered by `tests/test_cli.py`.

## Limitations

1. **Held-out gains are concentrated in first-of-month series.** Short daily and hourly windows are always abstained. Weekly and business-day resolution is shown only in unit tests (synthetic).
2. **Semi-synthetic benchmark.** Renderings and windows are generated. Real-world prevalence of fully ambiguous columns, and the mix of data types in them, are unknown. No study was found and none was run.
3. **No human evaluation.** Nobody used the tool; time saved, trust and adoption are untested.
4. **Coverage ceiling.** Genuinely symmetric data (e.g. 12 monthly values of one year, which reads equally well as 1–12 January) is always abstained by design. A value-prior heuristic resolves more of these, at the price of silent errors elsewhere.
5. **Tuning history.** The threshold and design were revised several times on DEV and on the synthetic null before the TEST run (see ACTIVITY_LOG and SPEC_v2). TEST was run once on the frozen method. A display-only change was re-verified to give identical outcomes.
6. **Scope.** Numeric day/month/year with `/ . -` separators, 4-digit years or 2-digit years in last position (pivot 69), optional times. Not supported: dates without years, `YY/MM/DD` versus `DD/MM/YY` year ambiguity, time zones, non-Gregorian calendars, Excel serial numbers.
7. **Randomisation test.** p < 1/40 per column. Across many columns, occasional chance decisions are expected (≤ 2% of structureless columns in the stress test).
