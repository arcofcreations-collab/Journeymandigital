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
