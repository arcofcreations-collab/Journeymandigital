# X3 result: are acceptance examples alone cheap? (decisive test for K2, Example-Synthesised changes)

**Design.**
- Six spent challenges (D01, D05, D08, D10, E09, E12), run concurrently in two arms.
- **Examples only:** the agent writes only the `expect:` list that would establish that an
  implementation is correct, with no operators and no `accrete apply`.
- **Full change (control):** the normal accrete v2.1 workflow.
- Both arms use the same model, the same workspace content and the same guide.
- Times are the agents' wall-clock durations (times.tsv).

| Challenge | Examples only (s) | Full change (s) | Ratio |
|---|---|---|---|
| D01 | 201 | 77 | 2.61 |
| D05 | 205 | 83 | 2.46 |
| D08 | 193 | 116 | 1.67 |
| D10 | 287 | 152 | 1.89 |
| E09 | 275 | 98 | 2.81 |
| E12 | 220 | 97 | 2.26 |
| **Median** | **212** | **97** | **2.36** |

**Finding.** Writing the verification alone took about 2.4x longer than making and checking the
whole change.

Without a running implementation to query, the agents derived every expected value by hand from
the data: counts, ids, payloads. In the full workflow the system computes those, and the agent
only confirms them. A synthesiser that removed implementation would therefore leave the expensive
part in place.

**Decision.** K2 (example-synthesised changes) is rejected for the efficiency goal. The measurement
also supports the K1/K4 premise from the other side: the system should *produce* the observable
behaviour and the human or agent should *judge* it. Specifying it in advance is the costly part.

**Limits.**
- n = 6, a single trial.
- The examples-only arm had no feedback loop. A feedback loop would be part of any real K2 system,
  but it would need an implementation to run against.
- This does not show that K2 is useless for correctness; only that it does not remove the dominant
  cost.
