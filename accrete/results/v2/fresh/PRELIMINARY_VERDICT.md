# Accrete v2.1 vs baseline v2.1, fresh set: PRELIMINARY verdict (1 trial; 8 of 14 challenges)

Rule (decidable before the results, a mathematical consequence of the declared primary statistic): the target needs
median over 14 challenges of r_i = baseline cost / accrete cost >= 5. If 8 challenges have r_i < 5, the median is < 5
whatever the other 6 show. The 8 independent challenges (F01, F07-F13) were run first for that reason, not selected by result.

| challenge | accrete s (correct?) | baseline s (correct?) | r |
|---|---|---|---|
| F01 | 154.0 (yes) | 116.0 (yes) | 0.75 |
| F07 | 123.9 (yes) | 218.9 (yes) | 1.77 |
| F08 | 77.0 (yes) | 114.2 (yes) | 1.48 |
| F09 (must reject) | 24.3 (yes, clarification) | 34.4 (yes, clarification) | 1.42 |
| F10 | 72.2 (yes) | 154.0 (yes) | 2.13 |
| F11 | 84.2 (NO at attempt 1: 9/10 hidden; repair pending) | 205.9 (yes) | <= 2.45 (repair can only lower it) |
| F12 | 132.3 (yes) | 202.2 (yes) | 1.53 |
| F13 | 58.7 (yes) | 85.5 (yes) | 1.46 |

**Verdict: target MISSED** (all 8 r_i < 5; median of these 8 ~1.5). Not a full benchmark: 1 trial instead of the
declared 3; chained challenges F02-F06 and F14 not run (needed only for complete correctness/regression reporting);
F11 repair not yet run. Correctness at attempt 1: accrete 7/8, baseline 8/8. No regressions observed in these runs.
Infrastructure: two discarded launches (usage limit, user interrupt) - INFRA_LOG.md.
