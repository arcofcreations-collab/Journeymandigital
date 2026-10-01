# v2 fresh evaluation: scoring rules (declared before any fresh run)

The target is unchanged from docs/TARGET.md: **at least 5x median improvement in time to a correct
result, with every mandatory evaluation task correctly completed**, with no regressions and no
data-integrity violations found by the independent evaluation.

## Material

- 14 fresh challenges F01-F14 (challenges/fresh), written by an independent challenger and frozen
  (SHA256SUMS) before any run.
- F01-F06 are a sequential chain on expenses. Each step starts from the same system's and trial's
  result of the previous step.
- F09 must be rejected: the expected outcome is a clarification with the app unchanged.
- Systems: accrete v2.1 (frozen) and baseline v2.1 (frozen), the same model and settings, the same
  prompt template (harness/experiment2.py).
- 3 independent trials per system and challenge. Every trial starts clean, and no workspace
  contains another trial's or system's work.

## Correctness of one run (challenge x system x trial)

An attempt is correct when all of these hold:
- every hidden test passes;
- no previously passing base acceptance test fails, except the challenge's declared superseded
  tests;
- for F09, a clarification is written and the app is unchanged.

The hidden and base tests are the independent evaluation, and they include data-migration checks.

**Repair rule:** if attempt 1 is not correct, the implementer gets a repair prompt listing the
failing behaviours (`experiment2.py repair`), up to 2 repairs (3 attempts). The prompt is the same
for both systems. A run still incorrect after the last repair is a **failure**.

Reported separately:
- correct at attempt 1;
- correct after repairs;
- failures.

## Cost of one run

`cost_s` = the sum over attempts of:
- the implementing agent's wall-clock duration;
- the harness verification time;
- recorded extra work, i.e. any engine or tooling change needed for the task (none are allowed
  after the freeze, so any such need is a failure).

Tokens and tool calls are summed over attempts and reported separately. The agent's duration is
wall-clock time, including model latency. Runs execute concurrently, and both systems are
interleaved in time.

## Primary statistic (declared)

For each challenge i:

    r_i = median over trials of baseline cost_i,t / median over trials of accrete cost_i,t

using all trials, including failed ones at their full cost. **Primary = median of r_i over the 14
challenges.**

## Alternatives that will also be reported (ambiguities disclosed)

- **A2:** median of the 42 paired per-trial ratios, baseline cost_i,t / accrete cost_i,t.
- **A3:** ratio of overall medians: median of all baseline costs / median of all accrete costs.
- **A4:** per-trial medians of r_i (variation across trials).
- **Failure handling in ratios.** A run that fails is shown at its full cost (primary). As a
  sensitivity check, ratios are also shown with a failed accrete run as ratio 0 and a failed
  baseline run as ratio +inf.

## Target verdict

- **Achieved:** the primary statistic is ≥ 5, and every run of every challenge is correct (after
  the repair rule), with no regressions.
- **Missed:** either condition fails.
- **Lenient reading of "every mandatory task" (also disclosed):** every challenge correct in at
  least 2 of 3 trials.
- **Evidence insufficient:** runs are incomplete because of infrastructure problems that cannot be
  attributed to either system.
