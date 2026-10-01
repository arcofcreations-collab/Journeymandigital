# Results

**Short version.** accrete made AI-implemented changes about **2.4x faster** end to end (median)
than a clean conventional Flask codebase changed by the same AI assistant. It also produced
changes about 4–5x smaller and used about 1.5x fewer tokens. It **did not meet the pre-declared
target**, on two counts:

- the 5x speed reduction was not reached;
- not every mandatory evaluation task was correct: accrete got 12/14 on first attempt, against
  the baseline's 14/14 (see the evaluation table).

Both accrete evaluation failures were gaps in the frozen engine, not mistakes by the agents.
Data integrity was preserved in every run of both systems. No hidden human repairs were made.

All numbers below are generated from `results/` by `harness/report.py` and `harness/analyze.py`.
The full per-run tables are in [`results/tables.md`](../results/tables.md).

## 1. Against the pre-declared target (`docs/TARGET.md`, committed before any challenge ran)

| Criterion | Required | Measured (evaluation set, first attempts) | Met? |
|---|---|---|---|
| Median end-to-end change time | ≥ 5x lower than baseline | **EVAL_RATIO** lower (accrete EVAL_A_MED min vs baseline EVAL_B_MED min) | **No** |
| All mandatory tasks correct | 14/14 | accrete **12/14** (E05, E11 failed); baseline EVAL_B_OK | **No** |
| Data integrity preserved | no loss or corruption | no data-integrity failure in any run (all existing-data assertions passed; 0 regressions) | Yes |
| No hidden human repairs | none | none: no workspace was touched between an agent's reply and verification; failed runs are kept | Yes |

**Verdict: the target was not met.** The target was not moved after seeing results.

## 2. Evaluation set (fresh challenges, frozen engine)

EVAL_SUMMARY

Per challenge (first attempts):

EVAL_TABLE

### The two accrete failures

Both were **engine gaps**. The implementing agents diagnosed both correctly and disclosed them in
their notes.

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

DEV_SUMMARY

The development set was used to find and fix weaknesses, so it is not the headline result:

- **D01** failed: the UI showed references as ids.
- **D11** failed: there was no list type; the agent correctly refused with a clarification.
- **D06** passed only through a hand-unrolled workaround.

Each failure led to a general engine revision (R1–R12 in `REVISIONS.md`). After it, D01 and D11
passed on a second attempt (not counted above). The development baseline had a small
disadvantage: the public test client was outside its workspace (`REVISIONS.md` H1). This was
fixed before the evaluation.

DEV_TABLE

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
- baseline: EVAL_SEQ_B correct.

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

- touches about 13 files: schema migration, repository, services, permissions, API routes, UI
  routes, templates, seed script, README and tests;
- needs about 1.7x more tool calls and about 1.5x more tokens.

accrete removes most of the *artifact* work: changes are 4–5x smaller, in 1 file instead of
about 13. But a large fixed cost per change remains, which accrete does not touch: understanding
the request, reading the current system, and the assistant's own verification habits. With an
AI implementer, the end-to-end time is dominated by the number of assistant turns, not by the
amount of code. A 4–5x smaller change became about 2.4x less time.

For a 5x end-to-end reduction, the number of assistant turns per change would have to fall from
about 17 to about 6. Turns that could plausibly go:

- reading a compact model view instead of the full guide;
- trusting the pipeline instead of re-checking by hand.

This is a hypothesis, not tested here.

## 6. Correctness, regressions, data integrity

| | Development (first attempts) | Evaluation (first attempts) |
|---|---|---|
| accrete correct | 12/14 | 12/14 |
| baseline correct | 14/14 | EVAL_B_OK |
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

- **Tokens per change:** accrete median EVAL_A_TOK k vs baseline EVAL_B_TOK k (evaluation).
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

- **Speed.** End-to-end change time was about 2.4x lower (median, evaluation), with a paired
  ratio above 1 in nearly every challenge.
- **Smaller changes.** About 4–5x fewer changed lines; 1 artifact instead of about 13 files.
- **Fewer tokens** per change, about 1.5x.
- **Transfer.** A new domain was built 2.2x faster, in about 220 lines.
- **Revert** is exact: model and every stored record are byte-identical (checked by `accrete demo`
  and the regression tests).
- **Unintended side-effects** surface automatically with concrete examples. In the demo, a status
  change silently blocking borrowing was caught before commit.
- **Engine fixes reach every app at once.** The two post-evaluation engine fixes repaired the
  failing applications without touching them.

**Did not improve, or got worse:**

- **The 5x target was missed.** The assistant's fixed per-change cost dominates.
- **Correctness was not better than the baseline** (12/14 vs 13/13 or better). Engine
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
