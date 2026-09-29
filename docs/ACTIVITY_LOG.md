# Activity log (chronological, UTC, 2026-09-29)

**Timestamp sources.** Times marked **[git]** or **[file]** come from commit and file-modification times in the container. Times marked **≈** are interpolated between those anchors (±3 min). An earlier draft of this log used my own estimates for several entries ("~10:00", "~10:18"), which ran ahead of the real clock. It was rewritten against the anchors at 09:33. Active execution time versus waiting time **could not be measured separately** in this environment and is reported as unavailable.

| Time (UTC) | Event |
|---|---|
| 08:37 | Run started (`date -u`). Capability inspection: empty git repo on branch `claude/ai-capability-test-invention-a53mgb`, Linux x86_64, 4 vCPU, 15 GB RAM, Python 3.11.15, Node 22, Chromium/Playwright preinstalled. Outbound HTTPS goes through a proxy that allows a web-search API, GitHub and PyPI only. No authorised paid API key; no spending limit supplied, so no paid services used. No explicit time or token limit (context budget ~15M tokens). |
| 08:38–08:46 | Web research on three candidates: date-order ambiguity, WCAG 1.4.12 clipping detection, name-validator auditing. arXiv, patent, ResearchGate and most documentation sites are blocked (`EGRESS_BLOCKED`). |
| 08:39 | Rejected B (TestParty and TestMu AI already automate 1.4.12 clipping detection) and C (FormFair already audits name-validation constraints). |
| 08:40–08:46 | Novelty search on A: read source of DashAI `date_utils.py`, prism `hellmode.py`, freshdata `config.py`, dateinfer 0.2.0; search snippets for DuckDB sniffer, Google US8239350, Liang 2025, lubridate/datefixR, Power Query, Sumo Logic. No temporal-structure disambiguation found. A selected. **[file 08:46 RESEARCH.md]** |
| 08:47–08:48 | Cloned public dataset repos. Froze `SPEC_v1_FROZEN.md` (hypothesis, baselines, DEV/TEST split, thresholds T1–T4). **[git 08:48 d7ce870]** |
| 08:50–08:56 | Implemented `dmguard` 1.0 (standard library only): core resolver, CSV layer with file-level consistency and ISO rewrite, CLI. **[file]** |
| ≈08:56–09:00 | Benchmark harness: pinned sources and fetcher (37 files), seeded case generator, 5 methods, runner with Wilson and cluster-bootstrap CIs, DEV tuner. Installed pandas 3.0.6, duckdb 1.5.6, numpy 2.4.6, pytest 8.4.2. |
| ≈09:00 | DEV tuning v1 rule. Inspecting DEV errors showed the weekday code counted repeated rows (event data), so it was changed to distinct dates. |
| ≈09:01 | DEV **selection-rule change v1 → v2**: v1 picked weekday weight 2 at 6 bits, trading 4 correct DEV answers for 4 silent errors. Replaced by utility = correct − 5 × silent-wrong, ties to weight 1 and the geometric-midpoint threshold. |
| ≈09:02 | First DEV run: 77.8% correct / 0% silent-wrong on 360 ambiguous DEV cases (baselines 50% silent-wrong). |
| ≈09:03 | 23 unit tests written. They exposed the file-order noise flaw on shuffled rows. Fix: two-part MDL code. |
| ≈09:04–09:10 | **Synthetic null stress test** (labelled synthetic) exposed coin-flip decisions on unsorted, structureless columns. Tried: (A) paired z-gate (DEV 19%), (B) gate only order-free coding (DEV 48%, null unsafe), (C) surrogate test on the evidence difference (DEV 47%). |
| ≈09:10 | User interrupted to ask about the invention's value; answered with DEV-only evidence. The interrupted command had already applied (D), the structure-existence randomisation test; I wrongly told the user the code was still at (C). |
| 09:12 | WIP committed. **[git 2cb9097]** The commit note "2 unit tests fail" is also wrong: with (D) all 23 passed. Both mistakes were corrected here. |
| ≈09:13–09:16 | (D) measured: DEV 256/360 correct, 0 wrong. Null: unsorted safe; dense sorted columns 5/150 wrong. Coded step direction separately: dense-sorted null 0/150 wrong. |
| ≈09:17–09:20 | T4 check on the forced surrogate path: 2.15 s at 100k rows, so the subsample cap was lowered from 5,000 to 2,000. |
| 09:23 | DEV re-tuning with the full procedure: rule v2 selects τ = 2 bits (72.2% / 0% / 27.8%). Synthetic null at τ = 2: ≤ 2% wrong decisions per trial at every size. **[file dev_tuning.json]** |
| 09:25 | Wrote `SPEC_v2_METHOD_UPDATE.md`; **method v2 frozen and pushed before any TEST run**. **[git 26bfe0e]** |
| 09:26 | Official DEV run. **[file raw_DEV.jsonl]** |
| ≈09:27 | **Held-out TEST run (first and only evaluation of the frozen method):** dmguard 902/1246 correct (72.4%), **0 silent-wrong**, 344 abstain; pandas/DuckDB 50% silent-wrong; range rule 100% abstain; unambiguous 1962/1962. T1, T2, T3 pass. |
| 09:28 | T4 formal measurement: worst case 1.26 s for 100k rows. Pass. **[file perf_t4.json]** |
| ≈09:28–09:29 | Built demo files from real data and ran the demo. Display-only fixes (date formatting in examples, a clearer step-size explanation). |
| 09:30 | TEST re-run after the display-only change; outcomes verified **identical** case by case (3468/3468). **[file raw_TEST.jsonl]** |
| 09:31 | Final targeted novelty search (MDL/compression, infer_freq + dayfirst, first-of-month swap detection, Trifacta/Alteryx/Tableau/Sheets). New detail: Liang 2025 runs a CKY/PCFG parser on 32 randomly sampled values. Post-hoc exploratory comparison with a value-prior heuristic ("constant field = day"): 91.0% correct but **8.7% silent-wrong** on TEST, versus dmguard 72.4% / 0%. **[file posthoc_value_prior_TEST.json]** |
| 09:33–09:40 | Wrote README, RESULTS, final novelty section, LICENSE, pinned `requirements-bench.txt`; corrected this log. The demo script had suppressed pandas warnings while printing "no warning"; it now records warnings (none are emitted, verified separately). |
| ≈09:40 | Reproducibility check in a clean venv (`pip install .`, `dmguard --version`, API example) found a real bug: piping output into `head` crashed with BrokenPipeError. Fixed in the CLI; added a regression test (24 tests), confirmed to fail on the old code and pass on the new. Resolver logic untouched, so TEST outcomes are unaffected. |

| after 09:45 | The user asked for a shareable page covering why the problem matters, who benefits, how it helps people, and where to test it. Removed duplicate and dead code from `core.py` (TEST outcomes re-verified identical). Ported the resolver to JavaScript (`web/dmguard.js`), including CPython's tuple hash and Mersenne Twister for the surrogate test. Parity check: 5,946 columns, 0 verdict mismatches, 0 evidence-bit mismatches. Verified `pip install git+…@branch` from GitHub works. Built and published the page with a live checker and real samples. |

## Human interventions

* The user set the goal (master prompt) and interrupted once, at ≈09:10, to ask "what's the value on the invention". After the build, the user asked for a shareable explanatory page. There was no other human input, manual data labelling, or manual step inside the product or the evaluation.
* All data labels come from the source datasets' own unambiguous date encodings.

## Costs

* No paid API or service calls were made by the product or the benchmark. Model inference cost for this agent session is **not visible** from inside the environment (unavailable).
* Compute: one 4-vCPU VM. Full TEST evaluation of all 5 methods takes about 60 s; dmguard's share is about 13 s for 3,468 cases.
