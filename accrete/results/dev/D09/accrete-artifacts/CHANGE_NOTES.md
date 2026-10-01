# D09: Withdraw the second-approval rule

Interpretation: D08's two-step approval is reverted to the original single approval by the
employee's manager, for any amount. The first approval of claims that were waiting for a second
approval stands, so they become `approved`. Claims that were already decided keep their values.

Changed with `accrete apply` (changes/0003-withdraw-second-approval.yaml, ledger #3):
- Migrated the 3 `awaiting_second_approval` claims (21, 22, 44) to `approved`, setting
  `decided_by`/`decided_at` from `first_approved_by`/`first_approved_at`.
- Restored the original read rule (employee, employee's manager, finance).
- Restored approve/reject: allow = employee's manager, guard = `submitted`; approve sets
  approved/decided_at/decided_by.
- Removed the fields `first_approved_by`/`first_approved_at` and the enum value
  `awaiting_second_approval`.

Verification: the pipeline passed (1375 replayed requests, 102 changed as intended,
0 unexplained), plus 18 expectations: the migrated values, read access, 403/409/400 on
approve/reject, single approval of a large claim, and paying a migrated claim. I also loaded
a copy of the app through app_entry.py (WSGI) and checked the API and UI: the removed
fields/status do not appear anywhere and `pay` is offered on the migrated claims.
