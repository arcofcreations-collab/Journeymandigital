# Improvement brief for accrete v2 (isolated improver)

You are improving accrete, an experimental programming system: an application is a model changed
only through typed, checked, invertible change files. Your copy of the repository is at the path
given in your task. It contains the engine (`accrete/`), the guide implementers read
(`docs/GUIDE.md`), apps, the harness, regression tests (`tests/`), and dev evidence in `EVIDENCE/`.

**Rules:**
- Work only inside your copy. Do not read, list or search anything outside it.
- There is no git history in your copy, by design.
- Make **general** fixes for the weakness classes below. Do not special-case the examples. A fix is
  general when it would apply to applications and changes nobody has seen yet.
- Keep every existing test passing (`python -m pytest tests -q`) and add regression tests for what
  you change.
- Never lose existing detections. Probes may be added but not removed or altered
  (`_probes_v1`/`_probes_extra` keep their output; add new generators alongside).
- Do not make `apply` slower than about 2x on the apps in `apps/`. Report the timings before and
  after with `accrete apply --dry-run` of a small change.
- Record what you changed and why in `docs/REVISIONS.md` (a new section "v2.1"). Update
  `docs/GUIDE.md` only where behaviour visible to implementers changed. Keep the guide short.
- Finish with a short report:
  - the files changed;
  - for each weakness, what you did, or why you left it;
  - the test results;
  - the timings.

## Weaknesses measured on development material (evidence in EVIDENCE/)

1. **Engine-upgrade check (`accrete upgrade-check`; golden probes recorded at each commit) misses
   some harmful engine regressions.** An independent random differential oracle confirmed
   these bugs as harmful in the following number of apps (EVIDENCE/engine_oracle_round3.json).
   Each was planted in a temporary copy of the engine; the patches are in
   `harness/planted_engine.py` MUTANTS.

   | Planted engine bug | Harmful in | Missed by the check |
   |---|---|---|
   | numbers stored with 1 decimal instead of 6 | 4 apps | 3 |
   | defaults overwrite values the client explicitly provided | 18 apps | 7 |
   | `count()` off by one | 21 apps | 2 |
   | `days(n)` off by one | 21 apps | 1 |

   The common cause is the probe inputs: values with full numeric precision, explicitly provided
   values for defaulted fields, and data near the boundaries of computed expressions are not
   systematically exercised.
2. **Side effects of failed requests are not compared.** With the bug "failed requests keep the
   messages they emitted", a request that emits a message and then fails (status 409) left a
   message in the stored outbox. `upgrade-check` reported no difference
   (EVIDENCE/rollback_outbox_triggers.json, "minimal"). No app in the corpus currently has such an
   action, but changes can create one at any time. Probes need to compare the full side effects
   (stored records and outbox) of failing requests too, and the probe set needs to include
   requests that reach late failures.
3. **Replay happens at a single point in time.** Consequences that depend on time are invisible
   when they do not show at that moment. Example (EVIDENCE/raw_round3.jsonl, E04, stray-computed
   `work_orders.due_date`): a stray change to `due_date` alters `overdue`, but only for orders
   whose due date falls between the two versions. At the change's real time no request showed it,
   so the change committed with no consequence and no scope warning. A run at a later time did
   catch it. Time-dependent behaviour (`now`, `today`, `days()`) should be replayed at more than
   one time.
4. **Implementers waste a full apply cycle on `guard_message`.** In 9 of 28 dev runs the first
   `accrete apply` was rejected because `guard_message` was written as plain text instead of a
   quoted expression (EVIDENCE/accrete2_dev_rejected_attempts.json). Make the common case work, or
   fail with an exact one-line fix, without changing the meaning of any existing valid model.
5. **Scope warnings.** These are advisory warnings for elements a change touched that the request
   does not mention. They raise false alarms on valid changes: 3 of 24 originals and 8 of 24
   originals with a harmless extra field (EVIDENCE/summary_round3.json, `valid:*`). They also miss
   most stray data edits (stray-data: 4 of 24 warned). Improve their precision and recall where a
   general rule exists. If none exists, say so.

The planted-bug harnesses (`harness/planted.py`, `harness/planted_engine.py`) and the coverage
guard (`harness/coverage_guard.py`) are in your copy. You may run `python harness/planted_engine.py`
for engine-level feedback. Its output goes to `results/v2/planted/`, which you can create in your
copy.

Note: in your copy the planted harnesses only see the three base apps in `apps/`. Run them with
`ACCRETE_RUNS=/nonexistent`, because the larger corpus of implementer apps is not in your copy.

Important: an `accrete` command is installed system-wide from ANOTHER checkout. Never use it, and
never pip-install anything. Always run from your copy's root with `PYTHONPATH=/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/improver_accrete`, for example
`PYTHONPATH=/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/improver_accrete python -m accrete.cli ...` and `PYTHONPATH=/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/improver_accrete python -m pytest tests -q`. To confirm
you are on your copy:
`PYTHONPATH=/tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/improver_accrete python -c "import accrete; print(accrete.__file__)"` must print a path inside /tmp/claude-0/-home-user-Journeymandigital/d6243dbf-52d7-59df-a403-d35a058b8748/scratchpad/improver_accrete.
