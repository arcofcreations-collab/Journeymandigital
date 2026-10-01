# Improvement brief for the conventional baseline v2 (isolated improver)

This is the baseline's counterpart of the accrete v2.1 improvement round: one isolated round,
with the same rules. Your copy of the repository is at the path given in your task. The baseline
is in `baseline_v2/` (`library`, `expenses`, `maintenance`): three conventional Flask + SQLite
applications. Each has a README and a `dev.py` tool (overview, check, call, migrations, notes),
plus tests. AI implementers use them to apply change requests. Evidence from the development
comparison is in `EVIDENCE/`.

**Rules:**
- Work only inside your copy. Do not read, list or search anything outside it. There is no git
  history.
- Make **general** improvements: tooling, documentation and workflow that would help on change
  requests nobody has seen yet. Do not special-case the examples.
- Keep every app's test suite passing (`python dev.py check` in each app directory) and do not
  change the apps' externally observable behaviour.
- Do not weaken any check. `dev.py check` must stay at least as strict as it is.
- Record what you changed and why in `baseline_v2/IMPROVEMENTS_V2_1.md`. Update the READMEs only
  where the workflow changed. Keep them short; implementers read them first.
- Finish with a short report:
  - the files changed;
  - for each finding, what you did, or why you left it;
  - check results;
  - how `dev.py check` run time changed.

## Findings measured on development material (EVIDENCE/)

1. **Generated change notes go stale.** In 6 of the 28 dev runs, the implementer wrote
   CHANGE_NOTES.md by hand: `dev.py notes` compared against a snapshot taken before earlier
   changes in a sequence, so the draft also listed older work (EVIDENCE/baseline2_dev_friction.json).
   In another run, rebuilding data.db with `python seed.py` reset the recorded apply times of
   earlier migrations, and the implementer restored them by hand.
2. **Where the time goes** (EVIDENCE/time_breakdown.json, aggregate `baseline2`; an estimate from
   transcripts):
   - writing tests: about 40% of attributed time, about 21k characters per change;
   - orientation: about 20%;
   - running checks: about 15%;
   - writing the implementation: about 14%;
   - bookkeeping (notes, README): about 10%.

   Anything that lets an implementer establish correctness or orient themselves with less work,
   without lowering the bar, is in scope.
3. **Reliability of `dev.py check` against planted bugs** (EVIDENCE/baseline_summary.json and
   baseline_raw.jsonl): 176 of 181 behaviour-changing mutants were rejected, and 0 of 19 valid
   final apps were rejected. The 5 misses were:
   - three edits in migration SQL: a partial-index predicate, and sqlite_sequence adjustments;
   - two swapped error classes in a permission branch that the tests do not exercise.

   Improve this where a general rule exists.
