# v2 freeze (accrete v2.1 and baseline v2.1), before the fresh evaluation

Frozen in the commit that adds this file. `docs/FREEZE_V2.sha256` holds SHA-256 checksums of:
- the accrete engine (`accrete/*.py`) and `docs/GUIDE.md`;
- the whole `baseline_v2/` tree, including dev.py, READMEs, tests and pins;
- the base accrete apps;
- the experiment harness and test client;
- the fresh challenge set's SHA256SUMS.

Verify with `sha256sum -c docs/FREEZE_V2.sha256` from this directory.

What changed since v2.0, each from one isolated improver round with no access to the fresh set
(docs/EXPOSURE.md):

- **accrete v2.1:** extra probes, comparison of failed-request side effects, multi-time replay,
  plain-text guard_message, per-element scope warnings (docs/REVISIONS.md, "v2.1").
  Archived v2.0: archive/v2_0.
- **baseline v2.1:**
  - `dev.py pin`, a recorded behaviour snapshot that `check` compares against, with a grouped diff
    for review;
  - fixed stale notes snapshots;
  - `seed.py` keeps migration apply times;
  - new data.db integrity rules.

  See baseline_v2/IMPROVEMENTS_V2_1.md. Archived v2.0: archive/baseline_v2_0.

**Integration validation:**
- the accrete regression tests pass (37);
- `dev.py check` passes in all three baseline apps;
- the accrete planted-bug round 4 (engine study, oracle and change-level study) runs on the frozen
  engine. Its results are measurements and change nothing.

No further changes are made to either system before the fresh evaluation is complete.
