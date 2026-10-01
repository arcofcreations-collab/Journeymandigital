# Experiment design: baseline, challenges, comparison procedure

## Question

Does accrete make changes made after the initial build cheaper end to end, from a change request to
a verified result, than a credible conventional codebase changed with the same AI assistance?
It must do so without losing correctness or data integrity.

## Systems under comparison

| | accrete | baseline |
|---|---|---|
| Stack | the accrete engine; each app is `app_entry.py` + `app.db` + `changes/*.yaml` | Python 3.11, Flask 3.1, sqlite3, Jinja2, numbered SQL migrations with a runner, pytest |
| How a change is made | write a change file of operators, `accrete apply` (pipeline checks it) | edit code, add a migration, migrate `data.db`, update and run the app's own tests |
| Documentation given | `GUIDE.md` (the complete accrete guide) | the app's `README.md` (structure, tests, migrations) |
| Initial apps | library and expenses: written by me with operators; maintenance: built by an agent (transfer build) | all three built by an independent agent instructed to write clean, idiomatic, conventional code (no generic engine) |

Both systems implement the same external contract (`spec/CONTRACT.md`) and the same requirement
documents and seed data (`spec/apps/`). Before any challenge ran, both passed the same
independent base acceptance suites:

| Base suite | accrete | baseline |
|---|---|---|
| library | 59/59 | 59/59 |
| expenses | 47/47 | 47/47 |
| maintenance | 48/50 (see below) | 50/50 |

On every development hidden test, run against the *unchanged* apps, the two systems gave
identical results. That is evidence that the starting points are behaviourally equivalent.

## Challenges

Challenges were written by **separate challenger agents**. These agents saw only the contract,
the requirements, the seed data and the base suites, never the implementations. Each challenge
has:

- `meta.json`, whose `brief` is the exact text implementers receive;
- `challenge.md`, with the six frozen criteria:
  1. requested outcome;
  2. observable acceptance criteria;
  3. behaviour that must remain intact;
  4. existing-data requirements;
  5. failure and recovery conditions;
  6. measurements;
- `test_<ID>.py`, the hidden acceptance tests.

Each challenge was committed (frozen) before any implementation was attempted:

| Set | Commit | Content |
|---|---|---|
| Development D01–D14 | `7ba1989` | 7 library + 7 expenses; chains D02→D03→D04, D08→D09 (reversal), D10→D11; one should-reject (D14) |
| Evaluation E01–E14 | `db1c0f1` | written by a new challenger *after* the engine freeze (`cefce2f`, see `FREEZE.md`). E01–E07: a 7-step sequence on the new **maintenance** domain (transfer test) with a reversal at E05; E08–E14 fresh library/expenses changes (chain E08→E14); one should-reject (E10) |

All 12 categories (cross_cutting, new_concept, rule_change, data_migration, new_relationship,
permissions, failure_atomicity, conflict_or_ambiguity, reversal, sequence, interaction,
should_reject) are covered in each set (`challenges/*/INDEX.md`). The evaluation challenger also
checked its tests against a private reference implementation of its own.

## Procedure per challenge and system (`harness/experiment.py`)

1. **prepare**: copy the starting app into an isolated workspace. The starting app is the base
   app, or, for chained challenges, the same system's result of the previous step. Then:
   - write the identical prompt for both systems, which differ only in the one paragraph pointing
     at their own documentation;
   - run the base suite on the starting state, so regressions are counted relative to it;
   - stamp the engine version.
2. **implement**: a fresh general-purpose agent (same model and tools for both systems) reads the
   prompt and works only in the workspace. It writes `t_start` first and `t_end` last. It must
   implement, migrate data, verify, and write `CHANGE_NOTES.md`, or else refuse with
   `CLARIFICATION.md`.
3. **record**: the agent's wall-clock `duration_ms`, tool calls and tokens, as reported by the
   agent runtime.
4. **verify**: run the hidden tests and the base suite on the result:
   - **Success** means every hidden test passes and there are no regressions.
   - A **regression** is a base test that passed before the change, fails after it, and is not
     superseded by the challenge.
   - For should-reject challenges, the hidden tests check that behaviour is unchanged and that a
     clarification was written.

There are no hidden human repairs: nobody touches a workspace between the agent's reply and
verification. Failed runs are kept. When the engine changed after a failure (development set
only), the first attempt was archived as `*.attempt1.json` and is what counts in first-attempt
statistics.

## Measured

| Measure | Source |
|---|---|
| End-to-end change time | the implementing agent's `duration_ms`: request to final reply, covering reading, implementing, migrating, self-verification and notes. The self-timed `t_start`/`t_end` are kept as a cross-check |
| Correctness | hidden tests, regressions, should-reject handling |
| Data integrity | the hidden tests' existing-data assertions, plus base-suite data checks |
| Compute | tool calls and tokens per change |
| Runtime overhead | request latency of the same request mix on both implementations (`harness/bench_latency.py`) |
| Foundation investment | reported separately (engine, initial apps, transfer builds); never amortised into per-change numbers |

## Threats to validity (known before results)

- **Isolation is instruction-based.** Agents are told not to read outside their workspace, and
  several reported small slips, all of which they disclosed. The hidden tests are in the
  repository, but no agent reported reading them, and their changes do not look as if they did.
- **One model, one run per cell.** The variance of agent behaviour is not measured. Medians
  over 14 challenges hide that.
- **Concurrency.** Many agents ran at the same time, so wall-clock times include contention.
  Both systems ran under the same conditions, interleaved.
- **The author of accrete ran the experiment.** The challengers and implementers were
  independent agents and the tests were frozen first, but the harness and the analysis are mine.
- **Development-set fairness gap (fixed for evaluation):** see `REVISIONS.md` H1.

## Reproducing

```bash
pip install -e accrete flask==3.1.2 pyyaml pytest
cd accrete
python harness/run_acceptance.py apps/library challenges/base/test_library_base.py     # base suites
python harness/run_acceptance.py baseline/library challenges/base/test_library_base.py
python harness/experiment.py prepare eval E08 accrete     # writes the workspace and prints the prompt
#   ... give PROMPT.txt to an agent ...
python harness/experiment.py record eval E08 accrete <duration_ms> <tool_uses> <tokens>
python harness/experiment.py verify eval E08 accrete
python harness/analyze.py eval
python harness/bench_latency.py apps/library baseline/library apps/expenses baseline/expenses
```

Workspaces from this run (the final applications produced by every agent) are not in the
repository. They lived in the session's scratch space. The result files, the change files the
accrete agents wrote, and the frozen tests are enough to re-verify or re-run any cell.
