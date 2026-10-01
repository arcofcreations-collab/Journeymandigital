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
