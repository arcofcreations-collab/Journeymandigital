# Revision log

Every design revision, why it was made and what evidence triggered it. Revisions after the
development challenges started cite the challenge that exposed the problem. Evaluation
challenges that inform a redesign are reclassified as development evidence.

## Before any challenge (foundation phase)

| # | Problem found | Evidence | Revision |
|---|---|---|---|
| F1 | Computed fields returned `None` (library base suite 42/59) | base acceptance suite | comprehensions could not see locals passed to `eval`; the whole scope now goes into globals → 59/59 |
| F2 | Replay gate auto-accepted every difference in anything that *depended* on the change, so an unintended side-effect through a dependency passed silently | design review of smoke test (guard reading `status`) | footprint split into **direct** (accepted) vs **consequences** (must be acknowledged under `consequences:`); read-rule changes no longer propagate through collection reads |
| F3 | Generated probes sampled 3 records per entity and missed the records a data change touched | smoke test: a data change on book 2 was not exercised | focus probes for every record touched by a data change |
| F4 | Spurious "consequences" on create probes | smoke test | probe rollback did not restore `next_id` / outbox counter, so ids drifted between old and new runs; rollback now restores them |
| F5 | `revert` used the pre-F2 footprint format | revert smoke test | revert acknowledges the original change's direct + consequence + declared labels |
| F6 | Reverting a change to a *computed* field left `null` values stored under that field id, so the reverted app was behaviourally identical but its storage was not byte-identical to the original | the live demo's exact-equality check after reverting all changes | inverses now record which records had *no* stored value (vs. a stored `null`); restoring a computed definition removes stored values. The demo now verifies model and every record identical after revert |
| P1 | Runtime overhead: list requests 10–20x slower than the Flask baseline; profiling showed ~30% of time re-parsing and re-validating the same expression strings | `harness/bench_latency.py` + cProfile | compiled-expression cache keyed by source string (sources are immutable). Medians for list requests fell 30–55%. Still several times slower than hand-written SQL; see RESULTS |

## After the first development round (D01–D11 on accrete version `6c62594`)

| # | Problem found | Evidence | Revision |
|---|---|---|---|
| R1 | References always render as ids in the generated UI; a text field promoted to a reference changed what the UI showed, a regression the API-only replay cannot see | D01 accrete failed 1 hidden test and regressed 1 base UI test | entity `display` field + `set_display` operator; the UI shows referenced records by it (when the caller may read them). `promote_field` now sets it, so promoting a field preserves the UI. `promote_field` numbers new records in order of first appearance instead of alphabetically (the agent had to work around this) |
| R2 | No way to hold a list of references; collection-wide operations impossible | D11 accrete: agent correctly wrote CLARIFICATION (0/11); D06 accrete passed only by unrolling list positions 1..3 by hand | `list` field/param type (`of`, `distinct`); `{for: v, in: expr, do: [...]}` effect; typed `it` / loop variables so static checks and renames reach inside effects |
| R3 | "409 wins over 400" was impossible on create: input errors were raised before any guard | D11 brief + contract precedence | `create_guard` rule (409) evaluated after `create` (403) and before input errors (400); list inputs keep their valid items so the guard can still run |
| R4 | A default that cannot be computed from incomplete input crashed (500) | found while exercising R2 | defaults failing on incomplete input are reported as 400 field errors, after 403/409 |
| R5 | YAML reads the key `on:` as boolean `true`, so `add_trigger` with `on: create` failed with a misleading error | found while exercising R2 | change files normalise boolean keys to `on`/`off` |
| R6 | `/api/_outbox?channel=` did not filter (agents' outbox checks were weaker than they believed) | D04 accrete agent report | outbox supports the same exact-match filtering as collections |
| G1 | Guide: documents R1–R6, and states that expectations + replay are the verification | — | documentation only |

## After the second development round (D01/D11 rerun, D12–D14; accrete version `9aa7905`)

| # | Problem found | Evidence | Revision |
|---|---|---|---|
| R7 | `promote_field` dropped the field's `required` flag | D01 attempt-2 agent had to restore it by hand | macros expand when applied (they see the model at that point); `promote_field` keeps `required` |
| R8 | R6's outbox filter was never wired to the dispatcher | D11 attempt-2 agent report | fixed; covered by a regression test |
| R9 | No referential policy other than "409 while referenced"; deleting a parent with its children was impossible | D12 agent stored `claim_lines.claim` as a plain integer to make "deleting a draft claim deletes its lines" possible, losing reference semantics | `on_delete: restrict (default) / cascade / nullify` on references and lists of references; `delete` effects use the same policies; a change to a reference field puts its target's `delete` in the direct footprint |
| R10 | Whether a field was *sent* (vs. unchanged) was not knowable in triggers; `input` existed in rules but was undocumented | D12 agent reported a 409 rule it could not express | `input` documented; also available in create/update triggers |
| R11 | Rename rewrote expressions with `ast.unparse`, so a rename followed by its revert left equivalent but textually different expressions | new accrete regression test (exact revert) | renames splice only the renamed identifiers into the original text |
| R12 | Changing a trigger did not count the actions that fire it as consequences: replay rejected the (real) difference as "unexplained" | new regression test (trigger on loans.create changes books.borrow) | trigger changes add every action/trigger whose effects can cause that event as consequences |
| C1 | **Engine upgrades are outside the change pipeline.** Introducing the typed `list` broke the D06 app, whose author had declared an untyped `list` param that the old engine passed through; nothing in accrete detected it | re-running every dev app's hidden tests on the new engine (D06: 5/11) | untyped lists keep the old meaning. The general gap remains: accrete gates *application* changes, not changes to accrete itself. Re-running applications' acceptance checks after engine upgrades (done here with `harness/compat_check.sh`) is the stop-gap; storing responses in the request corpus would let replay check engine upgrades too (not built) |

## Harness revisions

| # | Problem | Revision |
|---|---|---|
| H1 | In the development runs the public test client (`harness/accept_client.py`) was outside the workspaces. The baseline apps' own pytest suites import it from `../../harness`, so baseline agents spent time writing stand-ins. That is a disadvantage for the baseline (accrete agents do not need it). | From the evaluation set on, `prepare` places the public client at `<run>/harness/accept_client.py`, where the apps' tests find it, and the prompt (identical for both systems) allows reading it. Dev-set baseline times are therefore somewhat pessimistic for the baseline; the evaluation set is the fair comparison. |

## After the evaluation (post-freeze; evaluation results are NOT re-scored)

The evaluation used the frozen engine (`FREEZE.md`). Both accrete evaluation failures, and the
two base-suite failures of the accrete maintenance build, came from two engine gaps. They were
fixed only after every accrete evaluation run had finished. They are reported here so the
first-attempt results stand as the measured result.

| # | Problem found | Evidence | Revision |
|---|---|---|---|
| PE1 | A filter on a field the collection does not have returned `200 {"items": []}`; there was no way for an application to ask for 400 | maintenance base suite (2 tests, transfer build) and E05 (1 hidden test); both agents identified the cause themselves | unknown filter fields are a 400 (`id` and every field of the collection are known) |
| PE2 | `required` text accepted `""` and whitespace-only strings | E11 (1 hidden test) | client input for a required text field must contain a non-whitespace character (stored data is not re-validated, so existing records are unaffected) |

After PE1 and PE2 the outputs the agents already produced, re-run unchanged against the
patched engine, pass:
- every development and evaluation run (`harness/compat_check.sh dev|eval`), including E05 (7/7) and E11 (9/9);
- the maintenance base suite (50/50).

This shows the engine-level nature of these failures. It also shows a property of the design:
a fix in the engine reaches every application built on it, with no change to the applications.
The flip side is C1: the change pipeline does not check engine upgrades.

# v2 (second phase; v1 preserved in archive/v1/)

Evidence used for v2 design:
- the v1 agents' tool-call traces (`results/v1_step_analysis.txt`);
- the planted-bug study rounds 1–3 (`results/v2/planted/`; development evidence);
- the 28 original challenges, rerun as development comparisons.

| # | Change | Evidence | Notes |
|---|---|---|---|
| V1 | `accrete context`: one-screen overview (model, users by role, two sample API records per collection, ledger, exact request semantics) | v1 agents spent about 4 calls per change reading files and probing data with `accrete call` | |
| V2 | `expect` supports UI pages (`ui:` fields, actions, inputs, rows) | v1 agents spent about 2.7 calls per change writing ad-hoc UI check scripts | |
| V3 | `apply --notes` writes CHANGE_NOTES.md from the change and its report; `NEXT:` hints on every rejection | notes and post-rejection diagnosis took about 2 calls per change | |
| V4 | Engine-upgrade gate: every commit stores probes, responses and data; `accrete upgrade-check` replays them on the installed engine | v1 finding C1 (an engine change broke an app silently) | |
| V5 | Escape hatch: `add_function` / `change_function` / `remove_function` (sandboxed pure Python). Static name/attribute checks; calls treated as reading everything (conservative); renames a body still uses are rejected | gaps that change files cannot express | guarantees and limits in GUIDE.md; 8 interaction tests |
| V6 | PE1/PE2 (unknown filters 400, required text non-empty) carried into v2 | v1 evaluation failures | |
| P1 | Probes also compare the records a request **writes** (not only its response) | planted engine bugs `days+1`/`count+1` changed stored loans that no response showed | write differences are explained by field labels, or by the operation's effects label |
| P2 | Footprint labels split: action `allow` (403) / `guard` (409) / `params` (400) / `effects`; rule vs `*_guard` | planted round 1: a change that legitimately edited an action's `allow` made every behaviour of that action "intended", hiding planted guard bugs | old labels (e.g. `books.action:borrow`) still cover their parts |
| P3 | Probe additions (filters incl. unknown field, empty create, fractional numbers, duplicate unique values, PATCH of each writable field, users editing their own record); engine-upgrade snapshots use every user and up to 40 records | planted engine round 1 misses | see below |
| P4 | Scope warnings: edits to elements the request/interpretation never mention are flagged (not rejected) | planted rounds: "stray" edits declared by operators are invisible to replay by design | measured hit rate and false-alarm rate |

**Coverage regression in P3, and the fix.** Round 2 of the engine study lost detections that
round 1 had: `unique-skipped` 31/31 → 0/31 and `write-if-ignored`. The cause: P3 had *replaced*
the v1 PATCH probe instead of adding to it. The v1 probe wrote the *last* record's value into the
*first* record, which by accident violated uniqueness and exercised field permissions. Fix:
- `generate_probes` now returns every v1 probe verbatim (the v1 function is kept as `_probes_v1`)
  followed by the additions, so the requests compared can only grow;
- `harness/coverage_guard.py` checks after each round that nothing an earlier round detected is
  now missed.

**Round 2 vs round 1 for change mutants:** 14 gained, 9 lost. All 9 losses were explained:
- 8 E03 mutants had been "detected" in round 1 only because the **unmutated** E03 change was also
  rejected. Round 1 replayed at a fixed date (2026-03-01), where E03 really does alter `overdue`.
  From round 2 on, each change is replayed at its original run time.
- 1 E04 mutant was detected in round 1 only through the same time-dependent `overdue`
  difference.

Neither was a loss of real coverage. Both show a real limitation: **replay observes behaviour at
one point in time**, so time-dependent consequences can be missed.

**No tuning on reported numbers.** The dev rounds above are development evidence. The reported
reliability (`docs/RELIABILITY.md`) is measured once, after the v2 freeze, on held-out bugs:
- engine regressions written by an independent agent who never saw the development mutants;
- change mutants generated from the fresh evaluation set's changes with a new seed.
