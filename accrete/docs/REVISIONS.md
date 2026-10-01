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
| R5 | YAML reads the key `on:` as boolean `true`, so `add_trigger` with `on: create` failed with a misleading error | found while exercising R2 (agents had been writing `"on": create` or failing silently) | change files normalise boolean keys to `on`/`off` |
| R6 | `/api/_outbox?channel=` did not filter (agents' outbox checks were weaker than they believed) | D04 accrete agent report | outbox supports the same exact-match filtering as collections |
| G1 | Guide: documents R1–R6, and states that expectations + replay are the verification | — | documentation only |
