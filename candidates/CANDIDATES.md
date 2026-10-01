# Next invention: candidate mechanisms (after accrete)

Status: **design + decisive experiments**. No large framework is built until an experiment
supports a candidate's central assumption.

## What accrete taught (inputs to this document; details in accrete/docs/LESSONS.md)

These come from 56 dev-comparison runs: 28 challenges x 2 systems, all correct at the first
attempt.

- **Cost.** The median time to a correct result was about 91-153 s for accrete v2 and 168-272 s
  for the conventional baseline v2. The median ratio was 1.8x; the target was 5x.
- **Where the time goes** (estimated from transcripts; model time is attributed to the tool call
  that follows it). Accrete, about 127 s attributed per change:

  | Activity | Time | Share |
  |---|---|---|
  | Running checks | 47 s | 37% |
  | Writing verification | 28 s | 22% |
  | Writing the change | 20 s | 16% |
  | Orientation | 15 s | 11% |
  | Bookkeeping | 12 s | 10% |

  - Checks: 2.0 `apply` runs, plus 3.7 hand-written smoke tests through the test client, plus
    2.6 `call` probes per change.
  - Verification: about 10.8k characters of `expect:` per change, about 5x the size of the
    operators (about 2.2k characters).

  Baseline, about 224 s: writing tests 90 s (40%, about 21k characters), orientation 46 s,
  running checks 34 s, writing the implementation 30 s, bookkeeping 22 s.
- **Amdahl.** Making implementation free would remove only about 16% of accrete's time. The
  remaining cost is establishing correctness (verification and checks, about 60%) and
  understanding.
- **Authored expectations mostly cost cycles.** Of the 9 distinct rejections caused by failing
  expectations in the dev runs, 7 were followed by an attempt with the operators unchanged: the
  expectation was wrong, not the change. Only 2 led to changes in the operators.
- **Agents re-verify after the pipeline has passed.** They write test-client scripts and
  `call` probes. The guide told them that the pipeline's checks had measured but incomplete
  reliability. Some re-verification is justified; for example, slips are caught automatically at
  only 6-40% depending on category. The rest duplicates what expectations already checked.
- **Orientation is about 3x cheaper on a compact model** than on conventional code: 15 s vs
  46 s.

## Candidates

### K1. Delta Review (DR): verify by reading a system-computed behavioural delta

- **Work removed:** writing expectations and tests for the change; manual smoke checks; rechecking
  unchanged behaviour. The implementer writes the change, the system executes old and new over a
  bounded request (and time) space, and prints a grouped summary of every observable difference:
  status, fields, records shown, messages, stored data. The implementer's verification act is to
  compare that summary with the request: reading, not writing.
- **Enabler:**
  - deterministic execution with snapshot/restore of state;
  - a generator of a bounded request space (users x records x operations x parameter values x
    clock offsets);
  - a summariser that groups differences by request shape and kind of difference.
- **Unanticipated capabilities:** the summary is black-box. It needs determinism and request
  introspection, not a catalogue of operators, so new concepts appear in the delta automatically
  once the generator reaches them.
- **Preservation:** within the bounded space, "not listed = unchanged". Approved deltas become the
  new baseline, so later changes show only new differences.
- **Cost relocated to:**
  - generator design, especially for reaching deep states such as temporal sequences;
  - CPU time;
  - reading large deltas for broad changes;
  - reviewer judgement errors: a slip that looks intentional can be approved.
- **Falsified if:**
  - (X1) reviewers detect clearly fewer confirmed-harmful planted faults than the agents' own
    authored expectations or tests do on the same faults; or they reject valid changes;
  - (X2) end-to-end time on spent dev challenges is not cut sharply versus accrete v2 measured in
    parallel; or correctness drops.

### K2. Example-Synthesised changes (ES): write only examples; the system writes the change

- **Work removed:** writing the implementation. The implementer writes acceptance examples; a
  synthesiser searches edits to the model that satisfy all the examples with the smallest
  behavioural delta elsewhere.
- **Enabler:** a small, typed edit space (rules, guards, computed fields, new fields and entities)
  plus differential execution.
- **Unanticipated capabilities:** poor. The synthesiser can only find edits in its search space.
- **Preservation:** minimal-delta objective plus replay.
- **Cost relocated to:** the examples, which become both specification and verification, and to
  synthesis time and failures.
- **Falsified if:** (X3) writing the examples alone takes at least half the time of a full
  accrete change. Then even perfect synthesis gives under 2x. The time breakdown already points
  that way (verification 22% vs implementation 16%), so X3 measures it directly.

### K3. Generic contract invariants (GI): check the generic automatically, author only the specific

- **Work removed:** the generic part of verification. Generic properties are derived once from
  the external contract: UI forms match API permissions, lists match read rules, the 403 > 409 >
  400 order, failed requests leave no effect, filters are exact. They are checked on every change
  without anyone writing them.
- **Enabler:** a property library over the contract.
- **Unanticipated capabilities:** good for properties stated in the contract; none for domain
  semantics.
- **Preservation:** universally quantified properties, checked over the generated space.
- **Cost relocated to:** writing the property library (once); false alarms where a request
  legitimately deviates.
- **Falsified if:** (X4) generic properties account for only a small share of what implementers
  verify, or catch few confirmed-harmful planted faults beyond what accrete already guarantees by
  construction.

### K4. Delta Review on conventional code (DR-code): the representation question

- Same as K1, but the application is ordinary Python (Flask + SQLite). The delta is computed
  black-box by running two versions of the app over generated requests and clock offsets.
- **Work removed:** writing tests. Orientation stays as costly as for any code.
- **Unanticipated capabilities:** best of all candidates. Any code is allowed, so there is no
  abstraction to extend.
- **Cost relocated to:** orientation (about 46 s measured for the baseline), multi-file edits,
  generator reach.
- **Falsified if:** (X5) time with DR-code is not well below the baseline's with the same model.
  Comparing K1 with K4 also shows how much of the advantage comes from the representation.

### K5. Temporal and interactive domains (requirement, tested with K1/K4)

A domain whose essential behaviour is temporal (scheduling with recurrence, retries, windows;
or a simulation stepping over time). It tests whether differential review can reach
time-dependent behaviour: generated clock offsets and multi-step sequences. It also tests whether
an "unexpected capability" can be added without engine work:
- in K1, by an extension of the abstraction, counted as engine work;
- in K4, as plain code.

## Decisive experiments (small, measuring real behaviour)

| id | Tests | Candidate | Measures | Features exercised |
|---|---|---|---|---|
| X1 | Do reviewers catch faults by reading deltas? | K1 | detection among confirmed-harmful planted faults; false rejections of valid originals; minutes per review | unintended faults, legitimate changes, cross-feature changes, data migration |
| X2 | Does DR cut end-to-end time without losing correctness? | K1 | paired time vs accrete v2 control run in parallel; hidden-test correctness | real change requests incl. migrations, cross-feature changes |
| X3 | Are examples alone cheap? | K2 | examples-only authoring time / full-change time (paired) | real change requests |
| X4 | How much verification is generic? | K3 | share of authored checks that are generic; planted-fault detection by generic properties alone | unintended faults |
| X5 | Does DR work on plain code? | K4 | paired time vs baseline v2 control; correctness | real change requests |
| X6 | Temporal domain + unexpected capability | K1/K4 | whether the delta exposes a planted temporal fault; engine work needed in K1 vs K4 | time-dependent behaviour, an unanticipated capability |

**Decision rule.** Continue with the candidate whose X-results support its central assumption and
whose measured time reduction is large enough that 5x is plausible after it is built properly. If
none qualifies, return to mechanism design with the new evidence. Experiments are run on spent
development material only (dev and v1-eval challenges). The fresh v2 set is used only for
evaluating accrete v2.1 and is then spent too. Any new candidate is evaluated on a new set
generated independently after the candidate's freeze.
