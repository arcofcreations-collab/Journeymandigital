# dmguard: is `03/04/2021` the 3rd of April or March 4th? Ask the calendar, not the locale.

[![tests](https://github.com/arcofcreations-collab/Journeymandigital/actions/workflows/tests.yml/badge.svg)](https://github.com/arcofcreations-collab/Journeymandigital/actions/workflows/tests.yml) ![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue) ![no dependencies](https://img.shields.io/badge/dependencies-none-brightgreen) ![license MIT](https://img.shields.io/badge/license-MIT-lightgrey)

`dmguard` is a small command-line tool and Python library. It decides whether a column of numeric dates is **day-first or month-first** when the values alone cannot tell, and it **refuses to guess** when the data doesn't support a decision.

It was built during an AI capability test ("invent something new and useful, then build it"). The research, frozen specification, evaluation and an honest log are in [`docs/`](docs).

**Shareable overview page with a live in-browser checker:** https://claude.ai/artifact/JU1tQWUaknZ16xJiUpwBq1. It is private until the owner shares it. The page source is `web/page_template.html` (build it with `python3 web/build_page.py`). It runs `web/dmguard.js`, a JavaScript port whose verdicts match the Python tool on all 5,946 benchmark, demo and stress-test columns (`python3 web/parity_check.py`).

## The problem

When every date in a column has a day of 12 or less (`01/02/2020, 01/03/2020, …`), each value reads validly both ways. Common tools then **silently** pick one order:

* pandas `to_datetime` (month-first by default)
* DuckDB's CSV sniffer (fixed preference)
* spreadsheets (machine locale)

For a file from the "other" side of the Atlantic, every date is transposed, and nothing warns. Many 2025–26 bug reports describe this in real importers (see [`docs/RESEARCH.md`](docs/RESEARCH.md)). The careful workaround, "resolve only if some value is > 12, else ask the user", pushes the decision onto a person who often doesn't know the sender's convention either.

**Who it's for:** analysts, researchers, data journalists, NGO and public-sector data staff, and developers of CSV importers, anyone loading tables from sources whose date convention they don't control.

## The mechanism (what is new)

The two readings of an ambiguous column are value-for-value mirror images, so no property of the individual strings can separate them. What differs is the **calendar structure** the column has under each reading. dmguard measures that structure as a **code length in bits** (minimum description length):

1. **Row-order steps.** The file order is coded as calendar-aware steps: "+1 month" when the day of month is kept, otherwise "+n days". Direction is coded separately. A file in date order is cheap under the right reading; under the wrong one it jumps backwards at regular intervals.
2. **Sampling grid.** The sorted distinct dates are coded the same way. This is used instead of step 1 when the rows aren't in date order, via a two-part code with the arrangement cost, which is the same for both readings. Monthly data on the 1st is one repeated step under the right reading and "1–12 January, then a jump" under the wrong one.
3. **Weekdays** of the distinct dates. Business-day or weekly data concentrates on a few weekdays only under the right reading.
4. **Significance.** The lean towards one reading counts only if it is self-evidently significant (paired z ≥ 3), or if the column is more regular than **every one of 39 scrambled copies of itself**, where a random half of the values have day and month swapped (a randomisation test, p < 1/40).
5. **Mirror-pattern check** (added in 1.1). "The 1st of every month" read the other way is "1–12 January every year", which is also a regular calendar. When the losing reading is itself a regular pattern, simplicity is only a *preference*. Then only weekday evidence, which is not mirrored, can decide. Otherwise the answer is **`AMBIGUOUS (likely X)`**, with both patterns explained.

When none of these settle it, the answer is **`AMBIGUOUS`** and the exit code is 2.

Before any of this, value ranges settle a column outright (one reading has impossible dates). Another date column in the same file is only used if you declare that the file uses one convention (`--assume-same-convention`). There is no locale prior: the model is exactly symmetric between DMY and MDY.

Date-format detection already exists, including compression and entropy-based methods (e.g. Liang 2025). The novelty search found no tool, paper, patent or repository that uses the column's *calendar structure* to choose the day/month order, with a mirror-pattern check and abstention. See [`docs/RESEARCH.md`](docs/RESEARCH.md) for the dated search, the comparison table and the stated gaps.

## Install and run

Requires Python ≥ 3.9. **No third-party dependencies.**

```bash
pip install "git+https://github.com/arcofcreations-collab/Journeymandigital@main"
dmguard check your_file.csv        # report each date column's order and why
dmguard fix your_file.csv -o clean.csv   # also write resolved columns as ISO 8601
dmguard fix your_file.csv -o clean.csv --assume DMY   # your decision for columns the data can't settle
dmguard fix your_file.csv -o clean.csv --accept-likely   # apply "likely" orders (a preference, not proof)
dmguard check your_file.csv --assume-same-convention     # let proven columns settle ambiguous ones
dmguard check your_file.csv --json # machine-readable
```

`fix` is lossless: each value keeps exactly its time precision (`13/04/2021 12:30:00.123456` → `2021-04-13 12:30:00.123456`). Cells that are not valid dates are left unchanged and listed with their line numbers.

Or work from a clone (no install needed): `git clone https://github.com/arcofcreations-collab/Journeymandigital.git && cd Journeymandigital && python3 -m dmguard check your_file.csv`.

Exit codes:
* `0`: every date column is resolved and every date cell is valid.
* `2`: needs attention. A date column is ambiguous or inconsistent, or some cells are not valid dates, so pipelines stop.
* `1`: the input could not be read.

Python API:

```python
from dmguard import resolve_column
r = resolve_column(["01/02/2019", "01/03/2019", "01/04/2019", ...])
r.verdict, r.likely, r.method, r.reasons   # e.g. 'AMBIGUOUS', 'DMY', 'competing', [...]
```

## Live demo (≈3 minutes, suitable for recording)

```bash
pip install -r requirements-bench.txt   # pandas + duckdb, only for the side-by-side comparison
python3 bench/fetch_data.py             # downloads the pinned public datasets (~16 MB)
python3 demo/make_demo_data.py          # builds demo CSVs from real data
bash demo/run_demo.sh                   # every command is printed before it runs
```

A recorded run of that script is in [`demo/DEMO_OUTPUT.txt`](demo/DEMO_OUTPUT.txt). What to point at:

1. **UK-style monthly CPI export.** pandas silently reads 60 monthly values as 1–12 January of each year. dmguard says **AMBIGUOUS (likely DMY)** and explains the two patterns. The user, who knows the data is monthly, applies it with `--accept-likely`.
2. **Proof on real data.** S&P 500 closes on the first *trading* day of each month (2000–2004, UK style). pandas misreads it; dmguard proves **DMY** from the weekdays, which the mirror reading can't reproduce.
3. **US-style panel, rows shuffled.** This time **DuckDB** silently transposes it; dmguard says AMBIGUOUS (likely MDY).
4. **Two date columns.** A hint by default; the neighbour's order is adopted only with `--assume-same-convention`.
5. **Genuinely ambiguous** (12 monthly values of one year): `AMBIGUOUS`, exit 2. `--assume` records a human decision.
6. **A miss, shown on purpose.** Eight consecutive days early in a month: `AMBIGUOUS`.
7. **Lossless timestamps and an invalid cell.** Fractional seconds are kept exactly; `n/k` is flagged by line and left unchanged, with exit 2.
8. **Bad input:** mixed formats, non-dates, an empty file, a missing file.

## Evidence

Full details are in [`docs/RESULTS.md`](docs/RESULTS.md). The real-data TEST split has 3,468 cases from 22 public date columns: the dates are real, and the DMY/MDY renderings and row windows are generated. The misleading-pattern set is synthetic (840 ambiguous columns, fresh seed, run once).

| Ambiguous cases: correct / **silently wrong** | Real data (n = 1,246) | Misleading patterns (n = 840) |
|---|---|---|
| pandas default / `dayfirst=True` | 50.0% / **50.0%** | 50.0% / **50.0%** |
| DuckDB CSV auto-detect | 50.0% / **50.0%** | 50.0% / **50.0%** |
| "Range rule + ask the user" | 0% / 0% | 0% / 0% |
| dmguard 1.0.0 | 72.4% / 0% | 54.5% / **11.4%** |
| **dmguard 1.1.0 (default)** | **0.3% / 0%** | **28.3% / 0%** |
| dmguard 1.1.0 `--accept-likely` | 72.4% / 0% | 54.5% / **11.4%** |

Everything dmguard does not answer is flagged, never loaded wrong. On unambiguous cases all versions score 100% (1,962/1,962). A 100k-row column takes ≤ 1.3 s.

**Limitations, stated plainly:**

* **1.1.0's default rarely answers real monthly data on its own.** Those series have a mirror twin ("1–12 January every year"), so it reports *likely* instead. The suggestion was right in all 902 real cases where one was made, but only 70% of the time on the deliberately misleading set. The original goal of answering ≥ 50% of ambiguous real cases automatically **is not met** by the default; safety was chosen over coverage.
* 1.0.0 was confidently wrong on 11.4% of the misleading set, almost all "1–12 January every year" columns. An external review found this, and 1.1.0 fixes it.
* The real-data TEST split was no longer unseen when 1.1.0 was re-tested. The misleading-pattern set is synthetic. There was no human study, and real-world prevalence is unknown.
* Scope: numeric dates only (4-digit years, or 2-digit years in last position; optional time).

## Reproduce everything

```bash
pip install -r requirements-bench.txt
python3 -m pytest -q                    # 39 tests, incl. misleading-pattern and review regressions
python3 bench/fetch_data.py             # pinned sources, sha256 in bench/data/MANIFEST.json
python3 bench/tune_dev.py               # DEV-only threshold choice  -> bench/results/dev_tuning.json
python3 bench/run_eval.py DEV
python3 bench/run_eval.py TEST          # -> bench/results/summary_TEST.json, raw_TEST.jsonl (~1 min)
python3 bench/adversarial_eval.py       # fresh misleading-pattern set (seed 777)
python3 bench/perf_t4.py                # runtime criterion
python3 bench/posthoc_value_prior.py    # exploratory, not pre-registered
```

## Repository map

| Path | What |
|---|---|
| `dmguard/core.py` | The resolver (validity → calendar-structure MDL → significance test → verdict) |
| `dmguard/table.py`, `dmguard/cli.py` | CSV reading, file-level consistency, ISO rewrite, CLI |
| `tests/` | Unit and CLI tests, including symmetry and invalid-input cases |
| `bench/` | Pinned sources, case generator, baselines, evaluation, tuning, performance |
| `demo/` | Demo data builder, walkthrough script, recorded output |
| `web/` | JavaScript port, parity check against Python, source of the shareable page |
| `docs/RESEARCH.md` | Need evidence, 3 candidates, rejection log, dated novelty searches, comparison table |
| `docs/SPEC_v1_FROZEN.md`, `docs/SPEC_v2_METHOD_UPDATE.md`, `docs/SPEC_v3_REVIEW_FIXES.md` | Pre-registered hypothesis and criteria; method changes with reasons; fixes after the external review |
| `docs/RESULTS.md` | Results, breakdowns, post-hoc comparison, limitations |
| `docs/ACTIVITY_LOG.md` | Chronological log, human interventions, costs, mistakes and corrections |

## Run report (time, cost, assistance)

* **Elapsed:** started 08:37 UTC and finished about 09:40 UTC on 2026-09-29, roughly 1 h wall-clock. Active versus waiting time could not be measured separately.
* **Cost:** no paid APIs or services. The agent's own model-inference cost is not visible from the environment.
* **Human assistance:** the user supplied the task, asked one question mid-run, and later relayed an external review that found four defects, fixed in 1.1.0. There was no manual labelling or manual step in the product or evaluation.
* **Mistakes made and corrected** are listed in `docs/ACTIVITY_LOG.md`.

License: MIT.
