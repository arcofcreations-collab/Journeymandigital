# Need discovery and novelty search

Searches ran on **2026-09-29, 08:38–08:46 UTC**. All access dates below are that day.

**Coverage limits (read first).** The container's egress proxy lets through only a web-search API, GitHub (code search, raw files, API) and package registries (PyPI, npm). arXiv, Google Patents, USPTO, ResearchGate, Semantic Scholar, OpenAlex, Crossref and most vendor documentation sites are **blocked** (`EGRESS_BLOCKED`). So:

* For papers and patents I could read only search-engine abstracts and snippets, not full text. This is a real gap. Two sources are affected: Liang 2025 (arXiv 2501.05640) and patent US8239350.
* I could read primary **source code** for GitHub and PyPI projects, and did so for the closest matches (DashAI, prism, freshdata, dateinfer).
* Commercial closed-source tools (Excel, Power Query, Tableau, Alteryx, Trifacta) could not be inspected. Their behaviour is taken from public documentation snippets.

---

## 1. Three candidate problems

### Candidate A: Ambiguous numeric dates silently transposed on import (SELECTED)

* **Who and what task.** Analysts, researchers, data journalists, public-sector and NGO data staff, and app developers. They import CSV or spreadsheet exports whose dates look like `03/04/2021`, with a day/month order they don't know. Typical case: a UK/EU/AU export read by US-default software, or the reverse.
* **Evidence the problem occurs and matters.** This is anecdotal but plentiful and recent. There are many independent bug reports of silent day/month swaps in import code:
  * submersion-app/submersion#1828: "CSV import … swaps day and month when the day is 12 or less".
  * felixtosh/FiBuKI#303 and PR #353, which say: "A file that happens to contain only early-month dates parses at 100% month-first, and every date is silently transposed … Nothing warns, and the trend is wrong rather than absent."
  * NonoHM/budgetpilot#433: "A non-European date format imports on the wrong date rather than being refused".
  * TriasDev/tabular#58: "reading 11.01.2018 as 1 November".
  * MGrin/scani-oss PR #646, saineshnakra/automated-data-analyst#23, and Omarbayom/wp_chat_report PR #5.
  * pandas-dev/pandas#12585, "Inconsistent date parsing of to_datetime". The pandas docs state that `dayfirst` "is not strict".

  I found **no measured prevalence study**, so I make no prevalence claim.
* **Current tools and workarounds.**
  * pandas and dateutil infer the order from the first element, defaulting to month-first; `dayfirst=True` flips that.
  * DuckDB's CSV sniffer eliminates formats that fail on some value, then falls back to a fixed preference order.
  * lubridate and datefixR need the user to give an order (datefixR defaults to day-first).
  * Power Query and Excel use the machine locale or "Change type with locale".
  * Hand-written importers use a whole-column ">12" rule, then **ask the user** or refuse.
* **Gap.** Every approach resolves the order only when some value has a component above 12, or the format is otherwise invalid for one order. For a **fully ambiguous column** (every day ≤ 12) they either guess a fixed order, which silently corrupts the data when wrong, or push the decision back to a human who often doesn't know the source convention either.
* **Mechanism we can build and test now.** Use the *calendar structure* of the whole column, which only one of the two readings usually shows:
  * sorted or monotone row order;
  * a regular sampling grid (daily, business-daily, weekly, monthly, quarterly);
  * weekday concentration (business days or a fixed weekday).

  Score the two readings with a compression (minimum description length) comparison, and **abstain** when the evidence margin is small. Evaluation can be automatic against real public time series whose true dates are known.

### Candidate B: Automated detection of WCAG 1.4.12 text-spacing failures (REJECTED)

* **Users.** People with dyslexia or low vision who override text spacing, and the accessibility testers who serve them. The WCAG Understanding document for 1.4.12 and failure F104 (clipped or overlapped content) establish the need.
* **Why rejected.** Commercial prior art already claims this capability. TestParty says it "simulates the WCAG 1.4.12 spacing requirements in its rendering engine and flags components where content clips, overlaps" (testparty.ai blog, 2025). TestMu AI (formerly LambdaTest) documents a rule for 1.4.12 that "tests whether content is clipped, truncated, or overlapping". A new tool here would be a re-implementation, not an invention.

### Candidate C: Auditing form validators that reject real people's names (REJECTED)

* **Users.** People whose names contain apostrophes, diacritics, non-Latin scripts, mononyms and so on, and the developers who write form validation. The need is shown by "Falsehoods programmers believe about names", the Unicode L2/09-232 "Personal Name Validation Characters" document, and Irish fada campaigns.
* **Why rejected.** github.com/rukshanm123-art/formfair already does "static analysis of declared personal-name validation constraints in web-form markup", with fixtures of real names that expose exclusion. My remaining ideas (corpus-driven fuzzing) looked like incremental test-data curation rather than a material new mechanism.

---

## 2. Novelty search for Candidate A (attempt to disprove)

### Queries run (web-search API, 2026-09-29)

1. `infer day-first or month-first date format ambiguous column all days less than 12`
2. `pandas to_datetime dayfirst silently wrong ambiguous dates issue`
3. `disambiguate day month order dates using time series regularity spacing`
4. `date format inference weekday weekend distribution resolve DD/MM MM/DD ambiguity algorithm`
5. `DuckDB CSV sniffer ambiguous date format dayfirst detection`
6. `paper automatic date format detection ambiguous day month tabular data type inference`
7. `"Automating Date Format Detection for Data Visualization" Liang ambiguity M/d/yyyy d/M/yyyy method`
8. `Zixuan Liang date format detection "minimum entropy" algorithm …`
9. `patent determine date format column "day-month" order based on intervals between consecutive dates sequence`
10. `R package guess date order dmy mdy automatically ambiguous lubridate guess_formats datefixR anytime`
11. `"sorted" dates infer whether day or month first "monotonic" ambiguous CSV import heuristic`
12. `business days weekends detect wrong date format swapped day month stock prices csv weekend dates`
13. `US8239350 "date ambiguity resolution" patent abstract`
14. `US9747280 "date and time processing" patent abstract ambiguous dates`
15. `Power Query OpenRefine Excel "detect data type" date locale ambiguous day month automatic inference column`
16. `date format detection "periodicity" OR "regular interval" resolve ambiguous day month order log timestamps column heuristic`
17. `Sumo Logic ambiguous timestamp day month … auto-correct … current time`

GitHub searches: repository search for `infer date format day month ambiguity` and `dayfirst detection csv dates` (0 results). Code search for `dayfirst weekend ambiguous language:python` (8,592 hits, first 30 inspected), `"dayfirst" "diff" "mode" infer ambiguous dates language:python` (first 15 inspected), and `"day_first" "regular" "interval" guess date order` (first 15 inspected; unrelated).

PyPI checks: `dateinfer` 0.2.0, `pydateinfer` 0.3.0, `date-guesser` 2.1.4, `dateparser` 1.4.3, `datefinder` 1.0.0.

### Primary material inspected

* **DashAI `DashAI/back/types/date_utils.py`** (commit e4f0d7b). It tries `guess_datetime_format` under both readings on 5 sample values, then accepts the first candidate that parses the *whole column*. Its docstring says the ptype hint `"date-eu"` "is the only thing that can disambiguate a value like `01/02/2020`". It does compute `diff().mode()` of gaps, but only in `infer_frequency` **after** parsing, never to choose the order.
* **prism `modules/hellmode.py`** (commit 02264f0). `find_ambiguous_dates` lists values whose two readings differ and shows both to the user. `resolve_dates(series, day_first=True)` needs the caller to choose.
* **freshdata `config.py`** (commit 4eb6b0d). `dayfirst="auto"` sends ambiguous values ("01/02/2023") to `report.coerced_cells` for human review.
* **dateinfer 0.2.0 `infer.py`.** A rule-rewrite system over tokens of single examples (e.g. `If(Duplicate(MonthNum), Swap(MonthNum, DayOfMonth))`). It has no temporal reasoning.
* **DuckDB CSV sniffer** (duckdb.org blog 2023-10-27 and the auto-detection docs, via search snippet). It resolves the order when some value (e.g. 21-02-2000) rules one format out; "if ambiguities cannot be resolved from the data, the system uses a list of format preferences".
* **FiBuKI #303 / PR #353, submersion #1828 / PR #1846, scani-oss PR #646** (search snippets of GitHub pages). They use a whole-column >12 rule; a fully ambiguous column is "a tie, so detection returns null … the preview asks the user".
* **Google patent US8239350 "Date ambiguity resolution"** (abstract via search). It assigns per-string confidence "based on the amount of specificity with which the first text string conforms to each date format" and merges formats across strings. That is per-value specificity, not calendar or sequence structure.
* **Liang 2025, arXiv 2501.05640 "Automating Date Format Detection for Data Visualization"** (abstract and snippets only; full text blocked). It gives two algorithms, "minimum entropy" and a PCFG / natural-language model, to derive format strings from string data, with >90% accuracy on a column corpus. From the abstract, the entropy concerns format derivation. **I could not confirm whether it uses calendar or temporal structure. This is the largest remaining uncertainty.**
* **Sumo Logic timestamp docs** (snippet). Timestamps more than a day away from recent messages are *auto-corrected to the current time*. That is outlier correction, not choosing between day-first and month-first.

### Comparison with the nearest alternatives

| EXISTING SOLUTION | WHAT IT ALREADY DOES | GAP IT LEAVES | OUR SPECIFIC ADVANCE | SUPPORTING SOURCE |
|---|---|---|---|---|
| pandas `to_datetime` / dateutil | Infers format from first element; `dayfirst` hint | Fully ambiguous columns are read month-first (or day-first) regardless of truth; silent | Chooses order from calendar structure of the whole column, abstains if unsupported | pandas docs ("dayfirst … not strict"); pandas#12585 |
| DuckDB CSV sniffer | Eliminates formats contradicted by some value; else fixed preference list | Fixed preference in fully ambiguous case → silent error for half of such files | Same as above | duckdb.org/2023/10/27/csv-sniffer |
| Whole-column ">12" rule + ask user (FiBuKI, submersion, scani-oss, freshdata, prism) | Correct when any value is disambiguating; asks human otherwise | Every fully ambiguous column needs a human who may not know the convention | Resolves a large share of those columns automatically with evidence, still asks only when evidence is weak | GitHub PRs/issues listed above; freshdata `config.py` |
| DashAI date_utils | Candidate formats checked on whole column; frequency inference after parsing | Order still set by ptype hint; frequency never used for disambiguation | Uses grid regularity *as evidence for the order itself* | DashAI `date_utils.py` (read in full) |
| dateinfer / pydateinfer | Token rewrite rules on examples | No sequence/calendar reasoning | Sequence/calendar reasoning | dateinfer 0.2.0 source |
| lubridate `guess_formats`, datefixR, anytime | User-specified orders; datefixR defaults to DMY | Requires user choice; default silently wrong for MDY data | Data-driven choice with abstention | datefixR README (search snippet) |
| Google US8239350 | Per-string specificity confidence, merge across strings | Specificity is identical for both readings of `03/04/2021` | Calendar-structure evidence breaks that symmetry | Patent abstract (search snippet) |
| Liang 2025 (minimum-entropy & PCFG) | Derives format strings for columns, >90% accuracy | Unknown (full text not accessible) whether fully ambiguous columns are resolved by temporal structure | Explicit calendar-aware sequence compression + weekday evidence + abstention | arXiv abstract (search snippet) |
| Excel / Power Query | Machine locale or "Change type with locale" | User must know the source locale | Infers it from the data | Microsoft Learn Power Query docs (snippet) |

### Novelty statement (written before implementation)

> Our proposed new contribution is **a day/month-order resolver that decides fully ambiguous numeric date columns by comparing how compressible the column's calendar structure is under each reading**. The structure is: row-order deltas, the sorted sampling grid measured in calendar units (days vs. whole months), and weekday concentration. It **abstains** with an explicit "ambiguous" verdict when the evidence margin (in bits) is below a threshold. The closest known alternatives are pandas/dateutil, the DuckDB CSV sniffer, whole-column ">12" importers (FiBuKI, submersion, scani-oss, freshdata, prism), DashAI's date utilities, dateinfer, Google patent US8239350, and Liang 2025. According to their source code or documentation, **they do not use temporal or calendar structure to choose between day-first and month-first**: they rely on per-value validity or specificity, a fixed preference, a user or locale setting, or a human prompt. Remaining search uncertainty: the full texts of Liang 2025 and of patents could not be read (egress blocked); closed commercial tools (Excel, Tableau, Alteryx, Trifacta/Dataprep) could not be inspected; and the search was in English only.

### Rejection log

| Candidate | Decision | Reason |
|---|---|---|
| B. WCAG 1.4.12 clipping detector | Rejected 08:39 | TestParty and TestMu AI already market automated clipping/overlap detection under spacing overrides |
| C. Name-validator auditor | Rejected 08:39 | FormFair (GitHub) already audits name-validation constraints with real-name fixtures |
| A. Temporal-structure date-order resolver | Selected 08:46 | No equivalent found in documented search; buildable and testable offline with real public time series |

---

## 3. Final targeted novelty search (after the build, 2026-09-29 ≈09:31 UTC)

Terminology from the build: minimum description length / compression, frequency inference, first-of-month swap detection, commercial data-prep tools.

Queries (web-search API):

1. `minimum description length compression infer date format day month order column`
2. `"infer_freq" dayfirst ambiguous dates choose interpretation regular frequency pandas`
3. `detect swapped day and month dates using regular monthly interval "first of the month" data cleaning tool automatic`
4. `Trifacta OR Alteryx OR Tableau OR "Google Sheets" automatic date format detection ambiguous dd/mm mm/dd how decided`
5. `"Automating Date Format Detection" Liang entropy "day" "month" field distribution ambiguous resolved accuracy corpus columns Tableau Prep`
6. `arxiv 2501.05640 minimum entropy date format "tokens" algorithm description`

Findings:

* **Liang 2025 (arXiv 2501.05640).** Snippets give more detail. A CKY parser runs over a *random sample of 32 non-null values* per column, producing a probability distribution over parse trees, with rule probabilities learned from a training set. The most likely tree is then applied to the whole column. The corpus is about 62,000 columns from Tableau Public, and the two algorithms agree ~98% of the time, with differences "mostly for ambiguous data". Random sampling discards row order, and nothing indicates use of intervals, sorted grids or weekdays, so the *mechanism* differs. However, learned priors over field values (e.g. that a constant "01" field is usually the day) could resolve first-of-month series, the class where dmguard's held-out gains are concentrated. I could not run or read the full paper. A post-hoc stand-in heuristic ("constant field = day") was therefore tested; see RESULTS.md. It resolves more monthly columns than dmguard but silently transposes 8.7% of ambiguous TEST cases, where dmguard transposes 0%.
* **pandas `infer_freq`** infers a frequency only after parsing; `dayfirst` is a non-strict hint. They are not combined anywhere found.
* **Alteryx, Trifacta, Google Sheets, Tableau** (help pages and forum snippets) rely on explicit formats or locale settings. An Alteryx community answer says there is "no real way of distinguishing" dd/mm from mm/dd.
* **MDL / compression.** The MDL principle is general. No source found applies it to calendar structure to choose the component order of dates.

### Novelty conclusion

> **No close equivalent was found in the documented search as of 2026-09-29.** dmguard chooses between day-first and month-first for fully ambiguous columns by comparing the compressibility of the column's *calendar structure*: row-order steps with separately coded direction, the sorted grid in calendar units, and weekdays of distinct dates. It uses a paired z-test / randomisation test against day-month-scrambled copies of the column, and abstains explicitly otherwise.
>
> **Limitations of this conclusion:**
> * the full texts of Liang 2025 and of patents could not be read (egress blocked);
> * closed commercial tools could not be inspected;
> * the search was English-only and used one web-search API plus GitHub and PyPI;
> * a learned value-prior approach such as Liang's may achieve **overlapping practical results on first-of-month series** without the mechanism. dmguard's measured distinction there is zero silent errors plus abstention, not higher coverage.
>
> This is not a patentability opinion.
