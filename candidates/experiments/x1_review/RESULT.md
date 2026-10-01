# X1 result: verification by reading a behavioural delta

**Question:** can an implementer establish whether a change is correct by READING a system-computed
behavioural delta, more dependably and more cheaply than by WRITING expectations?

## Design

- **Cases:** 40, regenerated with accrete's planted-bug generator (seed 7) from real v1 change files.
  - 10 valid originals.
  - 30 mutants, 3 for each of 10 fault categories. Each was **independently confirmed harmful**:
    the exhaustive API/data oracle shows a difference from the original change, or the challenge's
    hidden tests fail. The checker's own expectation failures were *not* used as evidence.
- **Reviewer input:** the change request (challenge brief) and the delta rendered by
  `candidates/dr/delta.py` (about 1.6k-16.6k characters, median about 8k). They did not see the
  change file or the expectations.
- **Arms:**
  - (A) the delta including a "MODEL CHANGES" section;
  - (B) a behaviour-only delta (stored-data changes and request differences only), with different
    reviewer agents and different packet composition.
- **Procedure:** 8 reviewer agents per arm, 5 cases each. Each reviewer wrote a timestamped verdict
  after every case.
- **Comparisons:** on the same faults, as recorded by accrete's planted-bug study (round 3):
  - the v1 implementers' own authored expectations;
  - accrete's automatic checks alone;
  - the hidden tests.

## Results (raw: raw/, result_with-model.json, result_behaviour-only.json)

| | Arm A (with model changes) | Arm B (behaviour only) | Authored expectations | Automatic checks only | Hidden tests |
|---|---|---|---|---|---|
| Harmful faults rejected (of 30) | **28** | **27** | 21 | 2 | 23 |
| Valid changes wrongly rejected (of 10) | 0 | 0 | (0 of 24 in the study) | | |
| Seconds per case, median (mean) | 5.3 (8.3) | 5.4 (7.9) | | | |

**Misses in arm B:**
- **C05:** a slip in an effect that writes an event record. The delta summary did not include
  records written by successful requests: `delta.py` dropped the "writes" component. This is a
  general gap in the summariser, not in the idea.
- **C15:** a permission slip for a role that no stored user has. No generated request exercised it.
  This is the bounded-space limitation.
- **C38:** a constraint slip on a numeric range whose boundary was never exercised. This is also
  the bounded-space limitation.

Arm A also missed C05 and C38.

## What this establishes, and what it does not

**Established:**
- On these 30 confirmed-harmful faults in real changes, reviewers reading deltas rejected more of
  them (27-28) than the implementers' own expectations did (21), at about 5-8 seconds per case. A
  typical accrete change spent about 28 s writing expectations plus about 35 s on extra manual
  checks (transcript estimate).
- Removing the model-change section barely changed detection, so detection rests on behaviour.
- No valid change was rejected.

**Not established:**
- **Total completion time.** X1 measures the verification step in isolation. An end-to-end pilot
  (X2) is required.
- **Self-review.** Here, reviewers judged other people's changes, and were told that some were
  faulty. In the intended workflow, the implementer reviews its own change. Misreadings of the
  request would then be shared by the change and the review.
- **Faults that look intentional and realistic.** The mutation operators produce some salient
  artifacts, for example a `_x` suffix on a string constant. Stray changes are easy to spot as
  "unrequested". Slips such as inverted conditions, which carry no artifact, were caught 11 of 12
  times in arm B.
- **Faults outside the generated space.** These are invisible to review by construction (C15, C38).
  Reach of the generator is the limit, and it needs its own measurement.

**Decision:** X1 supports K1/K4's central assumption, which is that verification can be done by
reading a delta, more dependably than by the expectations agents actually write, at lower cost.
Two follow-ups:
- (1) fix the summariser gap (show records written by successful requests);
- (2) run X2 end-to-end before choosing.
