# Accrete: archived candidate (missed the 5x target)

Status: **completed candidate, target MISSED** in the current evaluation (results/v2/fresh/PRELIMINARY_VERDICT.md).
Kept as the comparison point and benchmark harness; no further development.

Explicit limitations of the evaluation that produced this verdict:
- 1 trial per (challenge, system) instead of the declared 3: repeatability is not established.
- Chained challenges F02-F06 and F14 not run; F11 (accrete) failed at attempt 1 and its repair was not run.
  Correctness is therefore reported only for 8 of 14 challenges at attempt 1 (accrete 7/8, baseline 8/8).
- The speed verdict does not depend on these: 8 of 14 challenges have baseline/accrete < 5 (max 2.45), so the
  declared median statistic cannot reach 5.
- Development comparison (28 challenges, both systems 100% correct at attempt 1): median ratio 1.8-1.9.

What it taught: docs/LESSONS (summary in candidates/CANDIDATES.md and candidates/experiments/*/RESULT.md).
Main measured finding: implementer wall time = ~11.8 s per tool call (r=0.94 over 71 runs); accrete cut steps
from ~22 to ~16 per change, i.e. ~1.4-1.9x, because verification and confidence-building steps remained.
