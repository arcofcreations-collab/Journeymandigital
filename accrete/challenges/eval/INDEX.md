# Evaluation challenge set (E01-E14)

| ID | App | Categories | depends_on | Superseded base tests | Summary |
|---|---|---|---|---|---|
| E01 | maintenance | new_concept, new_relationship, failure_atomicity, cross_cutting | - | 2 | Spare parts: `parts` (8 seeded), read-only `part_usages`, atomic multi-line `use_parts` with stock 409 beating invalid-item 400, `low_stock` channel, frozen derived `parts_cost` added to `work_completed`. |
| E02 | maintenance | new_concept, permissions, rule_change, data_migration, conflict_or_ambiguity, sequence | E01 | 3 | Technician self-dispatch (`claim`) and a 3-order workload cap also for `assign`; read-only `dispatch` back-filled (self = requester is assignee); existing overload kept by policy. |
| E03 | maintenance | rule_change, data_migration, cross_cutting, interaction, sequence | E02 | 17 | Priorities become p1-p4 (offsets 1/3/7/30); migration uses asset criticality; p4 refused on high-criticality assets (existing ones kept); claim limited to p3/p4 (403). |
| E04 | maintenance | new_concept, data_migration, rule_change, interaction, sequence | E03 | 19 | `time_entries` + `log_time`; `labor_minutes` becomes derived; `complete` takes only a resolution and needs an entry (409); 39 entries back-filled with exact ids. |
| E05 | maintenance | reversal, data_migration, sequence, interaction, conflict_or_ambiguity | E04 | 19 | Partial reversal of E02: `claim` (404) and `dispatch` removed, cap kept; self-claimed orders still `assigned` (72, 75) return to the open pool. |
| E06 | maintenance | permissions, rule_change, data_migration, cross_cutting, sequence | E05 | 27 | New `manager` role (sofia migrated); supervisors scoped to their site for orders, creation, assets and parts; staff writes manager-only. |
| E07 | maintenance | new_concept, new_relationship, interaction, cross_cutting, sequence | E06 | 27 | Preventive `schedules` (5 seeded) with `generate` (7-day window, once-only advance, unfinished-order block, site-scoped rights), `preventive_generated` channel, retirement deactivates schedules. |
| E08 | library | new_concept, new_relationship, data_migration, cross_cutting | - | 8 | Physical `copies` (40 migrated + 2 extra), loans gain `copy`, book status/`available_copies` from copies, borrow takes lowest-id available copy, payload gains `copy`. |
| E09 | library | permissions, new_relationship, data_migration, conflict_or_ambiguity | - | 0 | Household `guardian` links (4 migrated): guardians read dependants' records/loans, borrow and return for them, cannot edit them; no chains. |
| E10 | library | should_reject, conflict_or_ambiguity | - | 0 | "Right to be forgotten" that must delete a member's loans yet keep returning them with the member id: must be refused with CLARIFICATION.md. **(expect_rejection)** |
| E11 | expenses | new_relationship, data_migration, rule_change, cross_cutting | - | 2 | `cost_centres` with budgets and derived committed/remaining; claims migrated by department; approval beyond budget 409; payment payload gains `cost_centre`. |
| E12 | expenses | failure_atomicity, new_concept, permissions, cross_cutting | - | 0 | Atomic `offboard` (deactivate, re-manage reports, delete drafts, one message) with 404/403/409/400 ordering; inactive users read but never write. |
| E13 | expenses | rule_change, new_concept, conflict_or_ambiguity | - | 0 | `withdraw` within 168 h of submission and `revise` of rejected claims (max 2) with `revision` / `previous_rejection_reason`. |
| E14 | library | sequence, interaction, rule_change, data_migration, failure_atomicity | E08 | 12 | Lost copies on top of E08: `declare_lost` closes the loan and removes the copy from circulation, `found` restores it; loans 46/50 migrated as lost. |

## Notes

- **New application.** E01-E07 run on `maintenance` (spec/apps/maintenance.md, 129 seed records,
  base suite tests/base/test_maintenance_base.py with 50 tests). The sequence is cumulative: the app
  under test for E0k has E01..E0k applied in order, including every data migration.
- **Sequence interactions.** E02's cap interacts with E01-era orders and is kept by E05 while the rest
  of E02 is withdrawn; E03 restricts E02's claim by priority (and that rule vanishes with E05); E04
  changes the completion rule and therefore E01's `work_completed` payload values; E06 re-scopes the
  rights used by E01 (parts) and E07 (schedules); E07's generated orders go through E03 due dates,
  E04 time logging, E01 parts and the E05 cap. Each later test file re-checks earlier behaviour.
- **Superseded lists are cumulative** (as in the development set): each lists every base test of the
  app that is false after that step. E03 supersedes 17 tests because every base test that sends or
  compares `urgent/normal/low` becomes false; E05 does not restore any base test because the cap and
  the E03/E04 changes stay. The other library/expenses challenges are independent of each other,
  except E14, which lists E08's eight plus four of its own.
- **Data migrations transforming seed records:** E02 (dispatch back-fill), E03 (priority mapping with
  criticality), E04 (39 time entries, labor becomes derived), E05 (two orders back to the pool), E06
  (sofia -> manager), E08 (copies; loans gain `copy`), E09 (guardians), E11 (claims gain cost centres),
  E14 (two loans/copies lost).
- **Failure atomicity:** E01 (`use_parts`), E12 (`offboard`) and E14 (`declare_lost`) compare full
  snapshots (records, related collections, outbox) before/after refused operations; E07 also checks
  that refused `generate` calls leave no trace.
- **Permissions:** E02 (claim eligibility), E06 (site scoping and manager role), E09 (guardian rights),
  E12 (inactive users, finance-only offboarding).
- **Ambiguity with stated policy:** E02 (existing overload), E03 (existing p4 on high assets), E05
  (which claimed orders revert), E09 (active flags, immediate effect), E13 (window boundary, field
  clearing). **Should reject:** E10 (contradictory delete-yet-keep requirements); tests check
  CLARIFICATION.md and unchanged behaviour (forget is a 404).
- **Validation of the tests.** A private reference implementation of the contract
  (`_ref/`, author tooling only, not given to implementers) was built for all three base apps and for
  every challenge state. All base suites pass on it; for every challenge the hidden tests pass on the
  reference with the change applied, mostly fail on the state before the change, and the
  `superseded_base_tests` lists equal exactly the base tests that fail on the changed reference.
  Expected values in the tests were computed with scripts from the seed JSON files.
- Outbox assertions only inspect messages added after a recorded point (the initial outbox is not
  assumed empty) and only on channels defined by the spec or the brief.
