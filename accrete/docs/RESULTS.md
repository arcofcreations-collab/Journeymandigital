# Results

**Short version.** accrete made AI-implemented changes about **2.4x faster** end to end (median 2.02 vs 4.91 minutes per change; faster in every one of the 14 evaluation challenges, by 1.2x to 4.0x)
than a clean conventional Flask codebase changed by the same AI assistant. It also produced
changes about 5x smaller (median 120 vs 640 changed lines) and used about 1.6x fewer tokens. It **did not meet the pre-declared
target**, on two counts:

- the 5x speed reduction was not reached;
- not every mandatory evaluation task was correct: accrete got 12/14 on first attempt, against
  the baseline's 14/14 (see the evaluation table).

Both accrete evaluation failures came from gaps in the frozen engine. E05 could not be expressed
at all. E11 could have been avoided by the agent with an explicit constraint.
Data integrity was preserved in every run of both systems. No hidden human repairs were made.

All numbers below are generated from `results/` by `harness/report.py` and `harness/analyze.py`.
The full per-run tables are in [`results/tables.md`](../results/tables.md).

## 1. Against the pre-declared target (`docs/TARGET.md`, committed before any challenge ran)

| Criterion | Required | Measured (evaluation set, first attempts) | Met? |
|---|---|---|---|
| Median end-to-end change time | ≥ 5x lower than baseline | **2.43x** lower (accrete 2.02 min vs baseline 4.91 min) | **No** |
| All mandatory tasks correct | 14/14 | accrete **12/14** (E05, E11 failed); baseline 14/14 | **No** |
| Data integrity preserved | no loss or corruption | no data-integrity failure in any run (all existing-data assertions passed; 0 regressions) | Yes |
| No hidden human repairs | none | none: no workspace was touched between an agent's reply and verification; failed runs are kept | Yes |

**Verdict: the target was not met.** The target was not moved after seeing results.

The frozen engine was checked against every evaluation result file, using the `accrete_version`
it records:
- the engine source at every recorded commit is identical to the freeze commit `cefce2f`;
- the last accrete evaluation run ended (`t_end`) before the post-evaluation fixes were
  committed.

## 2. Evaluation set (fresh challenges, frozen engine)

| | accrete | baseline | baseline ÷ accrete |
|---|---|---|---|
| correct (all hidden tests pass, no regressions) | 12/14 | 14/14 | |
| regressions | 0 | 0 | |
| median change time (min) | 2.02 | 4.91 | **2.43x** |
| mean change time (min) | 2.04 | 4.88 | 2.39x |
| total agent time (min) | 28.6 | 68.3 | 2.39x |
| median tool calls | 17.0 | 31.0 | 1.82x |
| median tokens (k) | 79.3 | 133.3 | 1.68x |
| total tokens (k) | 1127.4 | 1818.4 | 1.61x |
| median changed lines (non-zero) | 120 | 640 | 5.33x |
| paired time ratio: median / min / max | | | 2.46x / 1.22x / 4.00x |
| challenges where accrete was ≥5x faster | | | 0/14 |

Per challenge (first attempts):

| ID | app | categories | accrete | min | tools | ktok | Δlines | baseline | min | tools | ktok | Δlines | time ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E01 | maintenance | new_concept, new_relationship, failure_atomicity, cross_cutting | ✔ 15/15 | 4.25 | 26 | 97 | 228 | ✔ 15/15 | 6.28 | 36 | 142 | 984 | 1.5x |
| E02 | maintenance | new_concept, permissions, rule_change, data_migration, conflict_or_ambiguity, sequence | ✔ 11/11 | 2.16 | 21 | 80 | 120 | ✔ 11/11 | 4.96 | 33 | 137 | 412 | 2.3x |
| E03 | maintenance | rule_change, data_migration, cross_cutting, interaction, sequence | ✔ 8/8 | 1.63 | 17 | 78 | 110 | ✔ 8/8 | 6.52 | 38 | 154 | 521 | 4.0x |
| E04 | maintenance | new_concept, data_migration, rule_change, interaction, sequence | ✔ 10/10 | 2.42 | 20 | 95 | 188 | ✔ 10/10 | 4.86 | 27 | 160 | 654 | 2.0x |
| E05 | maintenance | reversal, data_migration, sequence, interaction, conflict_or_ambiguity | ✘ 6/7 | 1.93 | 19 | 88 | 83 | ✔ 7/7 | 4.86 | 29 | 144 | 743 | 2.5x |
| E06 | maintenance | permissions, rule_change, data_migration, cross_cutting, sequence | ✔ 10/10 | 2.32 | 15 | 90 | 135 | ✔ 10/10 | 6.61 | 35 | 171 | 660 | 2.8x |
| E07 | maintenance | new_concept, new_relationship, interaction, cross_cutting, sequence | ✔ 12/12 | 2.58 | 18 | 97 | 180 | ✔ 12/12 | 6.88 | 43 | 172 | 879 | 2.7x |
| E08 | library | new_concept, new_relationship, data_migration, cross_cutting | ✔ 10/10 | 2.03 | 16 | 74 | 154 | ✔ 10/10 | 5.89 | 36 | 125 | 640 | 2.9x |
| E09 | library | permissions, new_relationship, data_migration, conflict_or_ambiguity | ✔ 9/9 | 1.75 | 12 | 70 | 76 | ✔ 9/9 | 4.20 | 26 | 105 | 383 | 2.4x |
| E10 | library | should_reject, conflict_or_ambiguity | ✔ 4/4 | 0.49 | 6 | 54 | 0 | ✔ 4/4 | 0.59 | 8 | 51 | 0 | 1.2x |
| E11 | expenses | new_relationship, data_migration, rule_change, cross_cutting | ✘ 8/9 | 2.06 | 16 | 82 | 144 | ✔ 9/9 | 6.09 | 33 | 130 | 718 | 3.0x |
| E12 | expenses | failure_atomicity, new_concept, permissions, cross_cutting | ✔ 9/9 | 2.01 | 17 | 73 | 70 | ✔ 9/9 | 3.66 | 22 | 118 | 406 | 1.8x |
| E13 | expenses | rule_change, new_concept, conflict_or_ambiguity | ✔ 8/8 | 1.39 | 17 | 74 | 61 | ✔ 8/8 | 2.65 | 20 | 95 | 344 | 1.9x |
| E14 | library | sequence, interaction, rule_change, data_migration, failure_atomicity | ✔ 7/7 | 1.58 | 15 | 75 | 108 | ✔ 7/7 | 4.21 | 24 | 115 | 450 | 2.7x |

### The two accrete failures

Both trace back to **engine gaps**:
- the E05 agent diagnosed its gap itself and disclosed it in its notes;
- the E11 agent did not notice its gap.

- **E05** (maintenance sequence step 5, reversal): 6/7. The brief requires
  `GET /api/work_orders?dispatch=…` to be a 400 once the field is removed. The frozen engine
  answered every filter on an unknown field with `200 []`, and no operator could change that.
  The same gap cost the accrete *transfer build* 2 of the 50 maintenance base tests (see §4).
  The baseline apps reject unknown filters in hand-written code.
- **E11** (expenses cost centres): 8/9. The test expects an empty `code` (a required text field)
  to be a 400. In the frozen engine `required` only rejected missing values. The agent did not
  add an explicit constraint for it; a constraint was possible, so this is partly an implementer
  miss.

After the evaluation, the engine was patched for both gaps (`REVISIONS.md` PE1, PE2). The
outputs the agents had already produced then passed unchanged, E05 7/7 and E11 9/9, without
re-implementing anything. **These are not counted.** The scored result is the first attempt.

## 3. Development set (D01–D14, used to improve accrete)

| | accrete | baseline | baseline ÷ accrete |
|---|---|---|---|
| correct (all hidden tests pass, no regressions) | 12/14 | 14/14 | |
| regressions | 1 | 0 | |
| median change time (min) | 1.56 | 3.87 | **2.48x** |
| mean change time (min) | 1.83 | 3.65 | 1.99x |
| total agent time (min) | 25.7 | 51.1 | 1.99x |
| median tool calls | 15.0 | 23.0 | 1.53x |
| median tokens (k) | 70.8 | 109.0 | 1.54x |
| total tokens (k) | 1009.6 | 1441.4 | 1.43x |
| median changed lines (non-zero) | 93 | 407 | 4.38x |
| paired time ratio: median / min / max | | | 2.34x / 0.73x / 3.65x |
| challenges where accrete was ≥5x faster | | | 0/14 |

The development set was used to find and fix weaknesses, so it is not the headline result:

- **D01** failed: the UI showed references as ids.
- **D11** failed: there was no list type; the agent correctly refused with a clarification.
- **D06** passed only through a hand-unrolled workaround.

Each failure led to a general engine revision (R1–R12 in `REVISIONS.md`). After it, D01 and D11
passed on a second attempt (not counted above). The development baseline had a small
disadvantage: the public test client was outside its workspace (`REVISIONS.md` H1). This was
fixed before the evaluation.

| ID | app | categories | accrete | min | tools | ktok | Δlines | baseline | min | tools | ktok | Δlines | time ratio |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| D01 | library | data_migration, new_relationship, new_concept, cross_cutting | ✘ 11/12 r1 | 3.11 | 31 | 86 | – | ✔ 12/12 | 5.35 | 32 | 114 | 560 | 1.7x |
| D02 | library | new_concept, cross_cutting, rule_change | ✔ 13/13 | 2.34 | 16 | 75 | 143 | ✔ 13/13 | 4.21 | 22 | 105 | 658 | 1.8x |
| D03 | library | rule_change, sequence, interaction | ✔ 11/11 | 1.08 | 14 | 66 | 55 | ✔ 11/11 | 2.88 | 18 | 106 | 229 | 2.7x |
| D04 | library | rule_change, sequence, interaction, data_migration, cross_cutting | ✔ 11/11 | 2.45 | 16 | 87 | 131 | ✔ 11/11 | 5.56 | 31 | 129 | 397 | 2.3x |
| D05 | library | permissions, rule_change | ✔ 11/11 | 1.25 | 12 | 63 | 79 | ✔ 11/11 | 3.19 | 21 | 97 | 321 | 2.6x |
| D06 | library | failure_atomicity, new_concept, cross_cutting | ✔ 11/11 | 2.85 | 17 | 77 | 86 | ✔ 11/11 | 2.80 | 19 | 91 | 241 | 1.0x |
| D07 | library | rule_change, conflict_or_ambiguity | ✔ 11/11 | 0.96 | 11 | 62 | 53 | ✔ 11/11 | 2.27 | 19 | 79 | 130 | 2.4x |
| D08 | expenses | rule_change, permissions, data_migration, conflict_or_ambiguity | ✔ 12/12 | 1.56 | 14 | 72 | 93 | ✔ 12/12 | 4.10 | 28 | 112 | 404 | 2.6x |
| D09 | expenses | reversal, data_migration, sequence, permissions | ✔ 8/8 | 0.80 | 10 | 63 | 55 | ✔ 8/8 | 2.93 | 21 | 112 | 537 | 3.6x |
| D10 | expenses | cross_cutting, new_concept, data_migration | ✔ 11/11 | 1.57 | 16 | 70 | 218 | ✔ 11/11 | 3.63 | 27 | 104 | 407 | 2.3x |
| D11 | expenses | failure_atomicity, new_concept, new_relationship, interaction, sequence | ✘ 0/11 | 1.56 | 14 | 76 | – | ✔ 11/11 | 4.25 | 24 | 112 | 573 | 2.7x |
| D12 | expenses | new_relationship, data_migration, cross_cutting, conflict_or_ambiguity | ✔ 13/13 | 4.11 | 23 | 96 | 207 | ✔ 13/13 | 5.14 | 32 | 121 | 505 | 1.3x |
| D13 | expenses | new_concept, permissions, conflict_or_ambiguity | ✔ 11/11 | 1.65 | 17 | 66 | 105 | ✔ 11/11 | 4.52 | 29 | 112 | 607 | 2.7x |
| D14 | expenses | should_reject, conflict_or_ambiguity | ✔ 7/7 | 0.39 | 6 | 52 | 0 | ✔ 7/7 | 0.29 | 5 | 49 | 0 | 0.7x |

D01 accrete second attempt (after engine revision, not counted above): ✔ 12/12, 1.02 min, 11 tools, 64 ktok

D11 accrete second attempt (after engine revision, not counted above): ✔ 11/11, 2.19 min, 22 tools, 88 ktok

## 4. Transfer test: a third, previously unused domain

The evaluation challenger invented a new **maintenance work-order** domain:

- 3 collections, 3 roles and 4 actions;
- 129 seed records;
- a 50-test base suite.

Each system built the domain from the same spec:

| | accrete | baseline |
|---|---|---|
| Agent time to build the whole app | **3.7 min** (221 s, 23 tool calls, 99k tokens) | 8.2 min (489 s, 34 tool calls, 154k tokens) |
| Artifact | one change file, 222 lines (`apps/maintenance/changes/0001-initial.yaml`) | about 2,650 lines of Python, SQL and templates, plus about 690 lines of tests |
| Independent base suite | 48/50 (both failures: the unknown-filter engine gap) | 50/50 |

Then came the 7-step sequence E01–E07 on this new app:

- accrete: 6/7 correct, all failures caused by the same gap;
- baseline: 7/7 correct.

Application-specific work:

- In accrete, nothing outside change files: no engine code was written for the domain.
- The one requirement accrete could not express (400 on unknown filters) needed an engine change.
  That change was made after the evaluation.

## 5. Where the time goes, and why the speed-up stops at about 2.4x

The accrete pipeline checks every change in **under one second**:

- static check;
- re-validation of every record;
- replay of 250–3,500 recorded and generated requests on both versions;
- expectations.

The largest change took 0.84 s. So almost all of accrete's roughly 2 minutes per change is the AI
assistant itself:

- reading the guide and the model;
- writing the change file;
- one or two dry runs;
- often extra checks of its own through `accrete call` or the test client;
- writing notes.

The baseline's roughly 4–5 minutes goes on the same loop over more files. A typical baseline
change:

- touches about 18 files (evaluation median): schema migration, repository, services, permissions, API routes, UI
  routes, templates, seed script, README and tests;
- needs about 1.8x more tool calls and about 1.7x more tokens (medians).

accrete removes most of the *artifact* work: changes are about 5x smaller, in 1 file instead of
about 18. But a large fixed cost per change remains, which accrete does not touch: understanding
the request, reading the current system, and the assistant's own verification habits. With an
AI implementer, the end-to-end time is dominated by the number of assistant turns, not by the
amount of code. A 5x smaller change became about 2.4x less time.

For a 5x end-to-end reduction, the number of assistant turns per change would have to fall from
about 17 to about 6 (the baseline needs about 31). Turns that could plausibly go:

- reading a compact model view instead of the full guide;
- trusting the pipeline instead of re-checking by hand.

This is a hypothesis, not tested here.

## 6. Correctness, regressions, data integrity

| | Development (first attempts) | Evaluation (first attempts) |
|---|---|---|
| accrete correct | 12/14 | 12/14 |
| baseline correct | 14/14 | 14/14 |
| regressions (base tests that passed before, fail after, not superseded): accrete / baseline | 1 / 0 | 0 / 0 |
| should-reject handled (clarification, app unchanged) | D14: both | E10: both |

- **No data-integrity failure** in any run: every migrated-data assertion passed for both systems
  in every successful run, and the failed runs failed on validation behaviour, not data.
- **The replay gate never let an unexplained difference through.** In the evaluation:
  - every committed accrete change had 0 unexplained differences;
  - agents used `consequences:` to acknowledge real side-effects;
  - several agents reported that the pipeline rejected a first attempt (dry run) and pointed them
    to the fix.

  This is reported by the agents, not independently counted. Dry runs are not stored in the
  ledger.
- Both systems' **failures were silent to their own checks**:
  - the accrete pipeline cannot know a requirement it was not told about (replay checks "nothing
    else changed", not "the right thing changed");
  - the baseline agents' own tests passed in every run, and the baseline happened to have no
    failures to hide.

## 7. Compute and runtime overhead

- **Tokens per change:** accrete median 79 k vs baseline 133 k (evaluation).
- **Engine time per change:** at most 0.84 s; no separate migration step is needed.
- **Request latency** (`results/latency.json`, same request mix, in-process WSGI, 200 rounds):

  | request | accrete median | Flask baseline median |
  |---|---|---|
  | list books (librarian) | 5.4 ms | 0.33 ms |
  | get book | 0.95 ms | 0.20 ms |
  | UI list books | 3.6 ms | 0.88 ms |
  | borrow (write, includes request recording) | 2.5 ms | 1.6 ms |
  | list claims (finance) | 3.7 ms | 0.69 ms |
  | create claim | 2.0 ms | 1.5 ms |

  accrete interprets expressions per record and records every API request for replay. It is
  3–16x slower on reads and 1.3–1.6x on writes, but still a few milliseconds per request on these
  data sizes (hundreds of records). Computed fields that scan collections are O(records ×
  collection). **Scalability to large data was not tested** and is a real risk.

## 8. Foundation investment (reported separately, not amortised)

| Item | Cost |
|---|---|
| accrete engine (expressions, model, runtime, UI, store, operators, pipeline, CLI, demo) | about 3,900 lines of Python, written by the orchestrating assistant in this session. Roughly 20 minutes of session wall-clock to the first version passing both base suites, then about 50 minutes of development-set revisions to the freeze. Agent-assisted wall-clock is not comparable to human effort |
| library + expenses models | 71 + 70 lines of change files (written with the engine) |
| baseline library + expenses | built by one agent in 14.9 min (about 3,840 lines of code plus about 840 lines of tests) |
| maintenance (transfer) | accrete 3.7 min / baseline 8.2 min (§4) |
| harness, challengers, analysis | shared by both systems |

## 9. What improved, what did not, what remains unproven

**Improved (measured):**

- **Speed.** End-to-end change time was about 2.4x lower (median, evaluation), faster in all 14
  evaluation challenges (paired ratio 1.2x–4.0x).
- **Smaller changes.** About 5x fewer changed lines; 1 artifact instead of about 18 files.
- **Fewer tokens** per change, about 1.6x; fewer tool calls, about 1.8x.
- **Transfer.** A new domain was built 2.2x faster, in about 220 lines.
- **Revert** is exact: model and every stored record are byte-identical (checked by `accrete demo`
  and the regression tests).
- **Unintended side-effects** surface automatically with concrete examples. In the demo, a status
  change silently blocking borrowing was caught before commit.
- **Engine fixes reach every app at once.** The two post-evaluation engine fixes repaired the
  failing applications without touching them.

**Did not improve, or got worse:**

- **The 5x target was missed.** The assistant's fixed per-change cost dominates.
- **Correctness was worse than the baseline** (12/14 vs 14/14 on the evaluation set; 12/14 vs 14/14 on development first attempts). Engine
  expressiveness gaps make some requirements impossible to meet from a change file. A
  conventional codebase can always express anything. That is the price of a closed operator
  vocabulary.
- **Runtime is several times slower per request.**
- **Engine upgrades are outside the safety net.** A runtime change silently broke an existing app
  during development (`REVISIONS.md` C1). Only re-running acceptance checks caught it.

**Unproven:**

- **Variance and scale of the sample.** One run per cell, one AI model, 14 + 14 challenges. The
  variance is unknown; the medians could move.
- **Human developers.** Whether humans would see a different ratio is untested. Humans might
  benefit more from fewer files, or less from an unfamiliar DSL.
- **Larger systems** with many more entities, years of history, large data, performance-sensitive
  paths, or external integrations beyond an outbox.
- **Long-term maintainability** of a model built from many operator changes, versus code.
- **Whether the replay gate catches more real regressions than a good test suite.** Its value was
  shown in constructed cases (demo, regression tests) and reported by agents. It was not measured
  against seeded bugs.
- **Isolation of implementers was instruction-based.** Several agents reported minor slips, such
  as temporary files just outside their workspace. None reported reading hidden tests.
