# Exposure log: who saw the fresh evaluation set before the systems were frozen

Rule: nobody who changes either system (the accrete engine, accrete's GUIDE, or the baseline_v2
code, tooling and READMEs) may see the fresh challenges (challenges/fresh: briefs, hidden tests,
reference) or any hidden-test feedback on them before both systems are frozen. This file records
every exposure.

## Exposure 1: the experimenter (the session that built accrete v2 and runs the experiment)

- **When:** 2026-10-01 ~08:05 UTC. The independent challenger agent finished and its hand-back
  message reached the experimenter.
- **What was seen:**
  - the challenger's summary table of F01-F14: one-line description, app, categories,
    dependencies, superseded test counts;
  - the full brief of F01 (printed while checking the meta.json format);
  - the pass counts of the hidden tests on the unchanged starting applications. These are
    before-change counts only, with no feedback from any implementation.
- **What had NOT been seen:** the hidden-test source code (except file names), the other 13 full
  briefs, and the reference implementation code.
- **Last change to either system before the exposure:** commit d1c07ab (07:38 UTC). Nothing in
  `accrete/accrete/`, `docs/GUIDE.md` or `baseline_v2/` changed between d1c07ab and the exposure
  (`git log -- accrete/accrete docs/GUIDE.md baseline_v2`).
- **Consequence:** from this point on, the experimenter does not change either system. Every later
  improvement is made by isolated improver agents (see below). The experimenter only:
  - writes the improvement briefs;
  - runs the mechanical checks (regression tests, planted-bug rounds, coverage guard);
  - merges the improvers' output unchanged.
- **Residual risk:** the improvement briefs are written by the exposed experimenter. To limit it:
  - each brief lists only weaknesses that were measured and committed before the exposure (commit
    references are given in the brief);
  - each brief asks for general solutions;
  - the briefs are committed verbatim in `results/v2/improvers/`, so anyone can check that they
    contain nothing derived from the fresh set.

## Isolation of the improver agents

- Each improver works in a fresh copy of the repository made by `harness/isolated_copy.py`. The
  copy has no `.git` directory, no `challenges/fresh`, no `challenges/heldout`, no `results/`, and
  no run workspaces.
- Each improver is told not to read anything outside its copy.
- After it finishes, the experimenter checks the improver's file accesses that are recorded in its
  transcript. Any read outside the copy is recorded here.
- The improver's copy is then diffed against the source and the diff is applied.

## Implementer agents (the experiment's subjects)

Implementers of fresh challenges see only their own workspace: the brief, CONTRACT, REQUIREMENTS,
the application and the public test client. Hidden-test results are never shown to them except
through the repair loop (`experiment2.py repair`), which reports failing behaviours of their own
attempt after the freeze. That is part of the measured procedure and is identical for both systems.

## Recorded exposures of improvers

(filled in after each improver run)
