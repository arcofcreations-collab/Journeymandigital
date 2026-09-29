# dmguard: is `03/04/2021` the 3rd of April or March 4th? Ask the calendar, not the locale.

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
4. **Significance.** The lean towards one reading counts only if it is self-evidently significant (paired z ≥ 3), or if the column is more regular than **every one of 39 scrambled copies of itself**, where a random half of the values have day and month swapped (a randomisation test, p < 1/40). Otherwise the answer is **`AMBIGUOUS`**, with exit code 2.

Before any of this, value ranges settle a column outright (one reading has impossible dates), and an ambiguous column can adopt the order of another date column in the same file that was settled that way. There is no locale prior: the model is exactly symmetric between DMY and MDY.

The novelty search found no tool, paper, patent or repository that uses temporal or calendar structure to choose the order. See [`docs/RESEARCH.md`](docs/RESEARCH.md) for the dated search, the comparison table and the stated gaps.

## Install and run

Requires Python ≥ 3.9. **No third-party dependencies.**

```bash
git clone <this repo> && cd Journeymandigital
pip install .                      # or skip installing and use: python3 -m dmguard ...
dmguard check your_file.csv        # report each date column's order and why
dmguard fix your_file.csv -o clean.csv   # also write resolved columns as ISO 8601
dmguard fix your_file.csv -o clean.csv --assume DMY   # your decision for columns the data can't settle
dmguard check your_file.csv --json # machine-readable
```

Exit codes: `0` all date columns resolved · `2` at least one date column ambiguous or inconsistent (so pipelines stop) · `1` input error.

Python API:

```python
from dmguard import resolve_column
r = resolve_column(["01/02/2019", "01/03/2019", "01/04/2019", ...])
r.verdict, r.method, r.evidence_bits, r.reasons   # e.g. 'DMY', 'structure', 62.8, [...]
```

## Live demo (≈3 minutes, suitable for recording)

```bash
pip install -r requirements-bench.txt   # pandas + duckdb, only for the side-by-side comparison
python3 bench/fetch_data.py             # downloads the pinned public datasets (~16 MB)
python3 demo/make_demo_data.py          # builds demo CSVs from real data
bash demo/run_demo.sh                   # every command is printed before it runs
```

A recorded run of that script is in [`demo/DEMO_OUTPUT.txt`](demo/DEMO_OUTPUT.txt). What to point at:

1. **UK-style monthly CPI export.** pandas silently reads 60 monthly values as 1–12 January of each year. dmguard says **DMY** ("sorted dates step by '1 month' 100% of the time under DMY vs '1 day' 93% under MDY") and `fix` writes ISO dates.
2. **US-style panel, rows shuffled.** This time **DuckDB** is the one that silently transposes it. dmguard says **MDY**, even though the rows are out of order.
3. **File consistency.** An ambiguous "Order start" column takes the order proven by the neighbouring "Invoice date" column.
4. **Genuinely ambiguous** (12 monthly values of one year): `AMBIGUOUS`, exit 2. `--assume` records a human decision.
5. **A miss, shown on purpose.** Eight consecutive days early in a month: `AMBIGUOUS`. dmguard doesn't help here, but doesn't harm either.
6. **Bad input:** mixed formats, non-dates, an empty file, a missing file.

## Evidence

Held-out TEST split: 3,468 cases from 22 real public date columns. The dates are real; the DMY/MDY renderings and row windows are generated (semi-synthetic). The frozen method ran once. Full details are in [`docs/RESULTS.md`](docs/RESULTS.md).

| Fully ambiguous cases (n = 1,246) | Correct | **Silently wrong** | Abstained |
|---|---|---|---|
| pandas default / `dayfirst=True` | 50.0% | **50.0%** | 0% |
| DuckDB CSV auto-detect | 50.0% | **50.0%** | 0% |
| "Range rule + ask the user" | 0% | 0% | 100% |
| **dmguard** | **72.4%** | **0.0%** (95% CI 0–0.3%) | 27.6% |

Unambiguous cases: dmguard 100% (1,962/1,962). A 100k-row column takes ≤ 1.26 s. All four pre-registered criteria (T1–T4) pass.

**Limitations, stated plainly:**

* On held-out data, **all gains came from monthly (first-of-month) series**. Short daily and hourly windows were always abstained. Weekly and business-day resolution is shown only by unit tests.
* A simple value-prior shortcut ("the constant field is the day"), tested post hoc, resolves *more* monthly columns (91%) but silently transposes 8.7% of cases. dmguard's edge is **safety**, not coverage.
* The benchmark is semi-synthetic. There was no human study, and real-world prevalence is unknown.
* Scope: numeric dates only (4-digit years, or 2-digit years in last position; optional time).

## Reproduce everything

```bash
pip install -r requirements-bench.txt
python3 -m pytest -q                    # 24 unit/CLI tests
python3 bench/fetch_data.py             # pinned sources, sha256 in bench/data/MANIFEST.json
python3 bench/tune_dev.py               # DEV-only threshold choice  -> bench/results/dev_tuning.json
python3 bench/run_eval.py DEV
python3 bench/run_eval.py TEST          # -> bench/results/summary_TEST.json, raw_TEST.jsonl (~1 min)
python3 bench/perf_t4.py                # runtime criterion T4
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
| `docs/SPEC_v1_FROZEN.md`, `docs/SPEC_v2_METHOD_UPDATE.md` | Pre-registered hypothesis and criteria; method changes before TEST, with reasons |
| `docs/RESULTS.md` | Results, breakdowns, post-hoc comparison, limitations |
| `docs/ACTIVITY_LOG.md` | Chronological log, human interventions, costs, mistakes and corrections |

## Run report (time, cost, assistance)

* **Elapsed:** started 08:37 UTC and finished about 09:40 UTC on 2026-09-29, roughly 1 h wall-clock. Active versus waiting time could not be measured separately.
* **Cost:** no paid APIs or services. The agent's own model-inference cost is not visible from the environment.
* **Human assistance:** the user supplied the task and asked one question mid-run. There was no manual labelling or manual step in the product or evaluation.
* **Mistakes made and corrected** are listed in `docs/ACTIVITY_LOG.md`.

License: MIT.
