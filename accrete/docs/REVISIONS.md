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
