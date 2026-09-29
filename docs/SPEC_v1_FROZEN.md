# Frozen specification v1: `dmguard`

Frozen **2026-09-29 ~08:55 UTC**, before any implementation or evaluation. If later evidence forces a change, it goes in a new file (`SPEC_v2_…`) with the reason, and the evaluation is re-run. This file is not edited after the first test-set run, except to fix typos.

## Product

* **Intended user.** A person who receives a table (CSV) with numeric dates such as `03/04/2021` and must load it correctly without knowing the sender's convention: analysts, researchers, journalists, NGO and public-sector data staff, and developers building importers.
* **Concrete input.** A CSV file (UTF-8; delimiter sniffed by the stdlib) or, via the Python API, a list of strings for one column.
* **Output.** For each column: a verdict (`DMY`, `MDY`, `YMD`, `YDM`, `AMBIGUOUS`, or not a date column), how it was decided (value ranges and validity / calendar-structure evidence / file-level consistency), an evidence margin in bits, and example readings. Optionally a rewritten CSV with resolved columns converted to ISO 8601, and a non-zero exit code if any date column is still ambiguous.
* **New mechanism.**
  1. **Hard constraints.** A reading is eliminated if any value is invalid under it: month > 12, or a day beyond the month's length (31/04, 29/02 in a non-leap year).
  2. **Calendar-structure evidence** when both readings survive. For each reading, compute the adaptive code length in bits of:
     * (a) the date sequence in *file order*, coded as calendar-aware deltas (whole-month steps when the day-of-month is kept, day steps otherwise);
     * (b) the *sorted distinct* dates, coded the same way (the sampling grid);
     * (c) the weekday of every value.

     The reading whose calendar structure is more compressible wins. Evidence = difference of total code lengths in bits.
  3. **Abstention.** If |evidence| < τ bits, the verdict is `AMBIGUOUS` and the tool says so explicitly instead of guessing.
  4. **File-level consistency.** If another date column in the same file with the same layout (same separator and year position) was settled by hard constraints, an ambiguous column adopts that order, labelled as such.
* **No locale prior.** The tool never prefers DMY or MDY a priori. The model is symmetric.
* **Out of scope.** Two-digit years in the first position; dates without a year (`03/04`); month names (those are already unambiguous); mixed-format columns (reported as not a single format); timezones. Trailing times (`03/04/2021 13:45`) are accepted, and the time is used for ordering.

## Representative user journey

`dmguard check export.csv` prints that column `Date` was read as **DMY** by calendar structure (+37 bits), and why: "rows are in date order under DMY, not under MDY; the sorted dates form a regular weekly grid on Mondays under DMY". Then `dmguard fix export.csv -o clean.csv` writes ISO dates. If the evidence were weak, the tool would print `AMBIGUOUS`, show both readings of sample values, and exit with code 2 so a pipeline stops rather than silently loading transposed dates.

## Hypothesis

> For people importing tabular data whose numeric dates have an unknown day/month order, **calendar-structure compression with abstention** should **reduce silently wrong date columns** compared with **pandas `to_datetime` default inference and DuckDB's CSV auto-detection**, and should **automatically and correctly resolve a large share of the fully ambiguous columns** that the conservative "range rule + ask the user" workaround leaves to a human. It should do this on held-out real public time series, **without worsening** accuracy on columns that are already unambiguous.

## Baselines (all run on identical inputs)

1. **pandas default**: `pandas.to_datetime(values)` (pandas 3.0.6, pinned). A raised exception counts as "error" (not silent).
2. **pandas dayfirst**: `pandas.to_datetime(values, dayfirst=True)`.
3. **DuckDB sniffer**: `duckdb.read_csv(path)` with default auto-detection (duckdb 1.5.6, pinned). A column left as VARCHAR counts as "not parsed" (not silent).
4. **Range rule + ask** (the workaround recommended in the GitHub issues): decide only when hard constraints eliminate one reading, otherwise abstain.
5. **dmguard** (this invention).

## Benchmark (semi-synthetic, clearly labelled)

* **Ground truth.** Real public CSV/JSON datasets with dates stored unambiguously (ISO 8601, `YYYY/MM/DD`, month names, or epoch ms). The true dates, their row order, duplicates and gaps are all real. **Synthetic part:** we re-render the true dates in `DD/MM/YYYY` and in `MM/DD/YYYY` (times kept as `HH:MM:SS` when present), and we cut contiguous row windows to mimic smaller extracts. Every case is rendered both ways, so the two orders are exactly balanced (50/50).
* **Case generation** (seeded, `random.Random(20260929)`). For each source date column: the full column (capped at the first 20,000 rows), plus 8 random contiguous windows for each size n ∈ {6, 12, 24, 60, 250} that the column can hold. Each window also gets a *shuffled-row* variant (seeded), to test data that is not in date order. Every case is rendered DMY and MDY.
* **Case classes.**
  * *Unambiguous*: exactly one reading is valid.
  * *Ambiguous*: both readings valid and they give different dates.
  * *Degenerate*: both readings give identical dates (every value has day == month). Degenerate cases are reported separately.
* **Split by source dataset** (no source appears in both).
  * **DEV** (for designing and tuning τ and weights only): `datasets/oil-prices` (all files), `datasets/natural-gas` (daily, monthly-processed), `datasets/gold-prices` (monthly-processed), `datasets/finance-vix` (daily, monthly), `jbrownlee/daily-min-temperatures`, `vega/birdstrikes`.
  * **TEST** (held out; run once the method is frozen): `datasets/exchange-rates` (daily, monthly, annual), `datasets/covid-19` (countries-aggregated-sample, key-countries-pivoted, worldwide-aggregate), `datasets/cpi-us` (cpiai), `datasets/house-prices-us` (national-month), `datasets/bond-yields-us-10y` (monthly), `datasets/s-and-p-500` (archive/fred_sp500), `vega/seattle-weather`, `vega/weather`, `vega/sp500-2000`, `vega/movies` (Release Date), `vega/la-riots` (death_date), `vega/stocks`, `vega/unemployment-across-industries`, `vega/co2-concentration`, `vega/iowa-electricity`, `vega/github` (hourly timestamps), `jbrownlee/daily-max-temperatures`, `jbrownlee/daily-total-female-births`.
* **Required minimum cases** (in addition to the benchmark): one ordinary end-to-end case (CLI on a real-derived CSV), one challenging case (panel data with repeated dates, or shuffled rows), and invalid-input cases (non-date column, mixed formats, empty file, impossible dates, binary/undecodable file).

## Metrics and pass thresholds (primary analysis = TEST split)

| ID | Metric | Threshold to pass |
|---|---|---|
| T1 | **Silent-wrong rate** on *ambiguous* TEST cases (wrong dates returned with no abstention/error) | dmguard ≤ **5%**, and ≤ **1/5** of both the pandas-default and DuckDB rates |
| T2 | **Auto-correct rate** on *ambiguous* TEST cases | dmguard ≥ **50%** (range-rule baseline = 0% by construction) |
| T3 | Accuracy on *unambiguous* TEST cases | dmguard ≥ **99.9%** |
| T4 | Runtime for one 100,000-row column (this VM, 1 core) | < **2 s** |

Uncertainty: Wilson 95% intervals on rates, plus a cluster bootstrap over source columns (2,000 resamples) for T1 and T2, because windows from the same column are correlated. Tables are also broken down by window size, row order (original vs shuffled), and sampling frequency.

## Failure conditions

The claim fails if any of T1–T3 fails on TEST. It also fails if the mechanism is found to be hard-coded or tuned on TEST, or if closer prior art turns up in the final search. A T4 failure is reported as a performance limitation. It does not invalidate the benefit claim, but it does count as a failed criterion.
