# Pre-declared target (written and committed before any challenge was run)

The target is fixed here, before any development or evaluation challenge has been run on either
system. It will not be changed after results are seen. If it is missed, the report says so.

## Primary target (evaluation set)

accrete passes only if **all** of the following hold on the fresh evaluation set:

1. **Speed.** Median end-to-end change time is at least **5x lower** for accrete than for the
   conventional baseline, comparing the median accrete time with the median baseline time over
   the same challenges.
   - End-to-end time = the implementing agent's wall-clock duration from receiving the request
     to its final reply. This is the agent's `duration_ms` as reported by the harness, which
     covers reading, implementing, migrating data and self-verification.
   - Independent acceptance checks run afterwards by the harness are excluded for both systems,
     because they are identical.
2. **Correctness.** Every mandatory challenge is correct for accrete: all of its hidden
   acceptance tests pass, and no base-suite test regresses (except tests the challenge
   explicitly supersedes).
   - For challenges that should be refused, "correct" means the application is unchanged and a
     clarification is written.
3. **Data integrity.** No existing record is lost or corrupted in any accrete run, as checked by
   the challenges' existing-data assertions and the unchanged base-suite data checks.
4. **No hidden human repairs.** No human or orchestrator edits to an accrete workspace between
   the agent's reply and verification. Any re-run is reported as a separate attempt, and the
   first attempt is the one that counts.

## Secondary measurements (reported, not part of pass/fail)

- Success rate and regressions for both systems.
- Tool calls and tokens per change.
- Runtime overhead: request latency of the accrete interpreter vs the Flask baseline.
- Time spent inside the change pipeline (from accrete's own reports).
- Foundation investment (building accrete and the initial apps), reported separately and
  never amortised into the per-change numbers.

## Fairness conditions

- Both systems receive the same request text.
- Both use the same assistant (the same agent type and model in this session).
- Both are given the same contract and requirements documents and the same isolated workspace
  layout.
- Each system gets one paragraph pointing at its own documentation (accrete: `GUIDE.md`;
  baseline: the app's `README.md`).
- Hidden tests are never visible to either implementer.
- The baseline is a clean Flask + SQLite codebase with numbered migrations and a pytest suite
  that passes the same independent base acceptance suite as the accrete apps.
