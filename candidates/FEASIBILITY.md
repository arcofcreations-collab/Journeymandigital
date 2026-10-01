# Feasibility plan after Accrete (bounded budget)

## The constraint the evidence imposes

Over 71 implementer runs, wall time = -56 s + 11.8 s x tool calls (r = 0.94).

| | Median tool calls | Median time |
|---|---|---|
| Baseline | 22.5 | 216 s |
| Accrete | 16 | 110 s |

A 5x advantage therefore needs about 4-5 calls per change, and two of those are the mandated timestamp calls. So a
mechanism must collapse **the number of decide-act-observe cycles** across understanding, implementing and verifying.
Shrinking any one phase is not enough. Accrete's calls broke down as follows (transcript estimate):
- 3.2 orientation;
- 1.5 authoring;
- 7.1 checks (2 apply runs, 3.7 hand-written smoke scripts, 2.6 manual calls);
- 2.6 bookkeeping;
- 2 timestamps.

## Candidate mechanisms, judged on total work

| | Mechanism | Understanding | Implementing | Verifying | Status |
|---|---|---|---|---|---|
| K1 | **Delta Review**: accept a change by reviewing the system-computed behaviour difference over a declared input space | no change | no change | replaces test writing and smoke checks with one review | **supporting component** (it only addresses verification) |
| K2 | Example-synthesised changes | no change | removed | becomes the whole cost | **rejected** (X3: examples alone took 2.4x a full change) |
| K3 | Generic contract invariants | no change | no change | small share | **weak**: accrete's automatic checks caught 2/30 confirmed-harmful faults in X1 |
| K5 | **Push-context, one-shot change**: a compact executable representation small enough that the *whole relevant application* is in the request, plus a single command returning checks and delta | ~0 calls (pushed, not explored) | 1 artifact | 1 command plus 1 review | **to test (X4)** |
| K6 | Same protocol on conventional code (baseline arm of X4) | pushed source (large) | multi-file edits | tests or pin | **control** |

**K5 is the only candidate that targets all three phases.** Its claim is representational. A compact model can be pushed
into the request whole; conventional code generally cannot be pushed in at useful size. One small artifact expresses a
cross-cutting change. The system computes evidence the agent would otherwise write. **What falsifies it:** the same
minimal-call protocol, given to the baseline, reaches a similar number of calls. That would mean the protocol, not the
representation, is doing the work.

## Experiments (spent development material only; no fresh or held-out material)

### X4: call floor, K5 vs K6

- **Design:** 2 spent challenges x 2 systems, one trial, the same "fewest steps while correct" protocol for both.
  - Accrete gets its whole model pushed into the prompt, plus `apply` whose output includes the behaviour delta.
  - The baseline gets its relevant source files pushed into the prompt, plus `dev.py check` with the pin diff.
- **Measures:** calls, time, tokens, hidden-test correctness.
- **Plausibility bar for a further build:**
  - K5 at or below 6 calls and correct;
  - K6 at or above 2.5x K5's calls under the same protocol.

### X5: Delta Review feasibility on the organiser (conventional Python)

1. A legitimate change with many intended output differences: does the reviewer accept it, and in how many seconds?
2. The same change plus one subtle harmful edit among mostly valid differences: does the reviewer reject it?
3. A fault in behaviour that the generated behaviour space does not contain: Delta Review is blind by construction. Do
   the independent checks (the existing pytest suite plus a scenario test written before results) catch it?
4. **Effort:** one implementer run per arm (Delta Review vs write-tests) of the same legitimate change. Measured as
   calls, time, tokens and hidden-check correctness. "Approved" is never counted as "correct"; correctness comes only
   from the independent checks.

## Budget (subagent tokens, estimated from run medians)

| Item | Estimate |
|---|---|
| X4: 4 runs | about 0.30-0.40M |
| X5: 2 implementer runs | about 0.15-0.20M |
| X5: 1 reviewer run (4 cases) | about 0.07M |
| **Cap** | **0.65M** |

Main-session work (harness construction, analysis) is additional, roughly 0.2-0.3M tokens of context processed.
The 1.5-2.5M organiser benchmark is **not** run unless X4 and X5 meet their bars.

## Results (one trial each; spent development material; subagent tokens used: about 0.52M of the 0.65M cap)

### X5: Delta Review on the organiser
- The independent check was corrected once, before any agent ran (NOTES.md).

| Case | Delta Review (reviewer, blind) | Existing tests | Independent check |
|---|---|---|---|
| V1 legitimate change (14 intended differences) | accepted (correct) | pass | pass |
| V2 legitimate change + subtle bug ("today" moved to the next day in the evening; 2 of 16 differences) | **rejected, both cases named** | **missed** | caught |
| V3 legitimate change + fault outside the generated space (RCS coverage warning dropped) | accepted, **missed by construction** | **missed** | **missed** (the check did not test it) |

Review effort: 27 s and about 48k tokens for 3 cases.

Implementation of the legitimate change, one implementer per arm:

| Arm | Time | Calls | Tokens | Independent check |
|---|---|---|---|---|
| Delta Review | 50 s | 10 | about 60k | 7/7 |
| Writing tests | 64 s | 11 | about 63k | 7/7 |

That is only **1.27x**. The tests arm wrote 17 tests with boundary cases; the Delta Review arm also probed boundaries by
hand, outside the space. Both arms independently flagged the same real side effect: saved corrections keyed on the old
work date detach.

**Conclusion:** Delta Review is a sound *supporting* verification component. It caught the subtle bug that the existing
tests missed, and it is blind outside its space. On its own it gives no large speed-up.

### X4: step floor, same "fewest steps" protocol and whole application pushed into the prompt, for both systems

| | Accrete calls / time | Baseline calls / time | Ratio | Earlier, normal protocol |
|---|---|---|---|---|
| E09 | 7 / 69.5 s, correct 9/9 | 11 / 218.4 s, correct 9/9 | **3.14x** | 2.13x |
| E13 | 6 / 63.6 s, correct 8/8 | 12 / 141.7 s, correct 8/8 | **2.23x** | 1.39x |

- The baseline **also** cut its calls about in half, so the step protocol is not unique to the compact representation.
  The call ratio was 1.6-2.0x, **below the 2.5x bar**.
- Time ratios rose to 2.2-3.1x, because time now tracks **characters written**. Accrete wrote about 12.5k characters per
  change, of which most were `expect:` blocks. The baseline wrote about 27-45k characters of code plus tests. Roughly
  4-5 ms per character, plus per-call overhead.

**Plausibility verdict:** the step protocol plus push context gives about 2-3x, which is **short of 5x**. The remaining
lever the data points to is *output volume*: Accrete's expectations are about 70-80% of what it writes, and X1 showed
that reviewing a delta catches more confirmed-harmful faults than those expectations do. Untested hypothesis K5b:
compact representation + push + Delta Review in place of expectations could reach about 4-6x. That requires the
baseline also being allowed to review its pin diff in place of writing tests (fairness), and it may still fall short.
